"""Hourly worker token rotation with atomic client handover and uninterrupted in-flight calls."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from typing import TYPE_CHECKING, BinaryIO, cast
from uuid import UUID

from skm.kernel.gateways import host_gateway
from skm.modules.access.public import RotateToken, RotateTokenResult
from skm.modules.runtimes.public import SecretStr

__all__ = ["RotatingClient", "TokenRotation", "WorkerCredential", "rotation_due"]


if TYPE_CHECKING:
    from skm.application_bus.client import QueryMeta, SkmClient, StagedBlobRef
    from skm.kernel.clock import Clock, Monotonic
    from skm.kernel.events import EventEnvelope
    from skm.kernel.ids import FileVersionId, WorkspaceId


@dataclass(frozen=True, slots=True)
class WorkerCredential:
    token_id: UUID
    expires_at: datetime
    secret: SecretStr = field(repr=False)
    kind: str = "worker"


def rotation_due(
    credential: WorkerCredential, now: datetime, *, rotate_before_hours: int, ttl_hours: int
) -> bool:
    if now.utcoffset() is None or credential.expires_at.utcoffset() is None:
        raise ValueError("token rotation requires timezone-aware timestamps")
    window = timedelta(hours=min(rotate_before_hours, ttl_hours / 2))
    return credential.kind == "worker" and credential.expires_at - now <= window


class RotatingClient:
    """Each call snapshots one complete client; exchanging it never closes an in-flight client."""

    def __init__(self, client: SkmClient) -> None:
        self.__current = client
        self.__lock = RLock()

    def replace(self, client: SkmClient) -> None:
        with self.__lock:
            self.__current = client

    def _snapshot(self) -> SkmClient:
        with self.__lock:
            return self.__current

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        return self._snapshot().dispatch(command, idempotency_key=idempotency_key)

    def ask(self, query: object) -> object:
        return self._snapshot().ask(query)

    def ask_with_meta(self, query: object) -> tuple[object, QueryMeta]:
        return self._snapshot().ask_with_meta(query)

    def events(
        self,
        *,
        workspace_id: WorkspaceId,
        after: int,
        types: frozenset[str] | None = None,
        wait_seconds: float = 0.0,
    ) -> Iterator[EventEnvelope]:
        return self._snapshot().events(
            workspace_id=workspace_id, after=after, types=types, wait_seconds=wait_seconds
        )

    def upload_blob(
        self,
        workspace_id: WorkspaceId,
        stream: Iterable[bytes],
        *,
        size: int,
        expected_digest: str | None = None,
        media_type: str | None = None,
    ) -> StagedBlobRef:
        return self._snapshot().upload_blob(
            workspace_id, stream, size=size, expected_digest=expected_digest, media_type=media_type
        )

    def open_file_version_content(self, file_version_id: FileVersionId) -> BinaryIO:
        return self._snapshot().open_file_version_content(file_version_id)

    def new_idempotency_key(self) -> str:
        return self._snapshot().new_idempotency_key()


@host_gateway
class TokenRotation:
    def __init__(
        self,
        credential: WorkerCredential,
        client: RotatingClient,
        *,
        clock: Clock,
        monotonic: Monotonic,
        config: Callable[[str], object],
        save: Callable[[WorkerCredential], None],
        make_client: Callable[[SecretStr], SkmClient],
    ) -> None:
        self._credential, self.client = credential, client
        self._clock, self._monotonic, self._config = clock, monotonic, config
        self._save, self._make_client = save, make_client
        self._next_check: float | None = None
        self._lock = RLock()
        self._uncertain = False
        self._pending: WorkerCredential | None = None

    def token_id(self) -> UUID:
        with self._lock:
            return self._credential.token_id

    def live_token(self) -> str:
        with self._lock:
            return self._credential.secret.reveal()

    def tick(self) -> None:
        with self._lock:
            moment = self._monotonic.monotonic()
            if self._next_check is not None and moment < self._next_check and self._pending is None:
                return
            due = rotation_due(
                self._credential,
                self._clock.now(),
                rotate_before_hours=int(
                    cast("int", self._config("access.tokens.worker_rotate_before_hours"))
                ),
                ttl_hours=int(cast("int", self._config("access.tokens.worker_ttl_hours"))),
            )
            if due and self._pending is None:
                if self._uncertain:
                    raise RuntimeError("worker token rotation has an unknown outcome; recovery is required")
                self._uncertain = True
                result = cast(
                    "RotateTokenResult",
                    self.client.dispatch(RotateToken(self._credential.token_id)),
                )
                if result.previous_token_id != self._credential.token_id or result.expires_at is None:
                    raise ValueError("rotated worker credential has an invalid binding or expiry")
                self._pending = WorkerCredential(result.token_id, result.expires_at, SecretStr(result.secret))
                self._uncertain = False
            if self._pending is not None:
                # Retain the same receipt in memory if persistence/client construction fails.
                replacement = self._make_client(self._pending.secret)
                self._save(self._pending)
                self.client.replace(replacement)
                self._credential, self._pending = self._pending, None
            self._next_check = moment + 3600
