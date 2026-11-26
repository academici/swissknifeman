"""Schedule one vault drain at a time on the registered worker host."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, Any, cast, override
from uuid import UUID

from skm.kernel.cancel import Cancelled, CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, ValidationFailed
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.exports.public import ListPendingNotes, RecordNoteWritten
from skm.modules.settings.public import ExplainConfig, ExplainConfigResult

from .service_runner import BackgroundService, TickResult

if TYPE_CHECKING:
    from skm.kernel.cancel import CancelToken
    from skm.kernel.json_types import JsonObject

__all__ = ["VaultPush"]


class VaultPush(BackgroundService):
    name = "vault_push"

    def __init__(
        self,
        ask: Callable[[object], object],
        push: Callable[[UUID, CancelToken], JsonObject],
        *,
        interval: int,
        log: Callable[..., None],
    ) -> None:
        self._ask, self._push, self._interval, self._log = ask, push, interval, log
        self._cancel = CancelSource()
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.name)
        self._future: Future[TickResult] | None = None
        self._next = 0.0

    @override
    def tick(self) -> TickResult:
        try:
            identity = self._ask(WhoAmI())
            if not isinstance(identity, WhoAmIView) or not identity.modules.get("exports"):
                return TickResult(0)
            workspace = next((m.scope_id for m in identity.memberships if m.scope_kind == "workspace"), None)
            if workspace is None:
                return TickResult(0)
            report = self._push(workspace, self._cancel.token)
            if report.get("partial"):
                self._log("vault.push.partial", reason=report.get("reason"))
            completed = sum(
                len(rows)
                for key in ("created", "verified_existing", "modified_existing")
                if isinstance(rows := report.get(key), list)
            )
            return TickResult(completed, 0 if report.get("has_more") else None)
        except Cancelled:
            return TickResult(0)
        except SkmError as exc:
            if exc.code not in (ErrorCode.EXPORT_VAULT_MISSING, ErrorCode.EXPORT_VAULT_NOT_FOUND) and (
                exc.details.get("reason") != "vault_writer_unbound"
            ):
                self._log("vault.push.failed", code=exc.code.value)
            return TickResult(0)

    def poll(self) -> None:
        with self._lock:
            if self._cancel.token.cancelled or not self._interval:
                return
            now = monotonic()
            if self._future is not None:
                if not self._future.done():
                    return
                try:
                    delay = self._future.result().next_delay_seconds
                except Exception as exc:  # noqa: BLE001 - a background failure cannot stop lease handling
                    self._log("vault.push.failed", error_type=type(exc).__name__)
                    delay = None
                self._future = None
                self._next = now + (self._interval if delay is None else delay)
            if now >= self._next:
                self._future = self._executor.submit(self.tick)

    def close(self) -> None:
        with self._lock:
            self._cancel.cancel("shutdown")
        self._executor.shutdown(wait=True, cancel_futures=True)


class VaultHostClient:
    """Supply trusted embedded host metadata only for the two delivery operations."""

    def __init__(
        self,
        client: Any,
        ask: Callable[[object], object],
        dispatch: Callable[[object, str | None], object],
    ) -> None:
        self._client, self._ask, self._dispatch = client, ask, dispatch

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def ask(self, query: object) -> object:
        return self._ask(query) if isinstance(query, ListPendingNotes) else self._client.ask(query)

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        if isinstance(command, RecordNoteWritten):
            return self._dispatch(command, idempotency_key)
        return self._client.dispatch(command, idempotency_key=idempotency_key)


class VaultConfig:
    """Read each host or work settings chain at its owning scope."""

    def __init__(self, host: Any, ask: Callable[[object], object]) -> None:
        self._host, self._ask = host, ask

    def get(self, key: str) -> object:
        return self._host.get(key)

    def for_scope(self, level: str, scope_id: UUID) -> JsonObject:
        return export_settings(self._ask, level, scope_id)


def export_settings(ask: Callable[[object], object], level: str, scope_id: UUID) -> JsonObject:
    query = ExplainConfig.from_json(
        {
            "scope": {"level": level, "scope_id": str(scope_id)},
            "section": "exports",
            "detail": "full",
        }
    )
    result = cast("ExplainConfigResult", ask(query))
    settings: JsonObject = {}
    for row in cast("list[JsonObject]", result.to_json()["keys"]):
        key = str(row["key"])
        if row.get("valid") is False:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid exports setting", details={"key": key})
        settings[key] = row.get("value")
    return settings
