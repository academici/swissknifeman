"""The only channel from host code to the control plane (kernel-platform §4.6, ADR 0023).

``EmbeddedClient`` (bus in process) is here; the HTTP client is declared in ``adapters.http_client``.
Bytes never travel through bus DTOs: ``upload_blob`` stages them and returns a ``StagedBlobRef`` that a
command then references.
"""

import base64
import time
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from copy import copy
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, BinaryIO, Final, Protocol
from uuid import UUID

from skm.application_bus.context import AuthBasis
from skm.application_bus.ports import EventReader
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.events import EventEnvelope
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWorkFactory

if TYPE_CHECKING:
    from skm.application_bus.bus import Bus

__all__ = [
    "BlobUploader",
    "ContentOpener",
    "EmbeddedClient",
    "EventReaderSession",
    "QueryMeta",
    "SkmClient",
    "StagedBlobRef",
    "UploadedBlob",
    "embedded_client_factory",
    "new_request_id",
]

_EVENTS_BATCH: Final = 200
_POLL_SECONDS: Final = 0.5

# A short-lived read session: entering yields an ``EventReader`` bound to one readonly unit of work.
type EventReaderSession = AbstractContextManager[EventReader]


def new_request_id(ids: IdGenerator) -> str:
    """``"req_"`` + 26 base32 characters of a uuid7 (``RequestMeta.request_id``)."""
    return "req_" + base64.b32encode(ids.new_id().bytes).decode("ascii").rstrip("=")


@dataclass(frozen=True, slots=True)
class QueryMeta:
    """Response metadata of a query, not part of its result schema (kernel-platform §4.4)."""

    events_cursor: int | None  # max(workspace_seq) of the target workspace in the query snapshot


@dataclass(frozen=True, slots=True)
class StagedBlobRef:
    """Staged upload; same fields as ``urn:skm:artifacts:defs:v1#/$defs/staged_blob_ref``."""

    staged_blob_id: UUID
    workspace_id: WorkspaceId
    digest: str  # "sha256:<hex>"
    size: int
    media_type: str

    def to_json(self) -> JsonObject:
        return {
            "staged_blob_id": str(self.staged_blob_id),
            "workspace_id": str(self.workspace_id),
            "digest": self.digest,
            "size": self.size,
            "media_type": self.media_type,
        }


class UploadedBlob(Protocol):
    @property
    def staged_blob_id(self) -> UUID: ...
    @property
    def workspace_id(self) -> UUID: ...
    @property
    def digest(self) -> str: ...
    @property
    def size(self) -> int: ...
    @property
    def media_type(self) -> str: ...


class BlobUploader(Protocol):
    def __call__(
        self,
        *,
        actor: Actor,
        meta: RequestMeta,
        workspace_id: WorkspaceId,
        stream: Iterable[bytes],
        size: int,
        expected_digest: str | None,
        media_type: str | None,
        auth_basis: AuthBasis | None = None,
    ) -> StagedBlobRef | UploadedBlob: ...


class ContentOpener(Protocol):
    def __call__(
        self,
        *,
        actor: Actor,
        meta: RequestMeta,
        file_version_id: FileVersionId,
        auth_basis: AuthBasis | None = None,
    ) -> BinaryIO: ...


class SkmClient(Protocol):
    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object: ...

    def ask(self, query: object) -> object: ...

    def ask_with_meta(self, query: object) -> tuple[object, QueryMeta]:
        """HTTP reads ``QueryMeta`` from the ``SKM-Events-Cursor`` header."""
        ...

    def events(
        self,
        *,
        workspace_id: WorkspaceId,
        after: int,
        types: frozenset[str] | None = None,
        wait_seconds: float = 0.0,
    ) -> Iterator[EventEnvelope]: ...

    def upload_blob(
        self,
        workspace_id: WorkspaceId,
        stream: Iterable[bytes],
        *,
        size: int,
        expected_digest: str | None = None,
        media_type: str | None = None,
    ) -> StagedBlobRef:
        """Exact ``size``; a size or digest mismatch is ``BLOB_DIGEST_MISMATCH``. Requires ``file.write``."""
        ...

    def open_file_version_content(self, file_version_id: FileVersionId) -> BinaryIO:
        """Requires ``file.read`` on the file scope; the caller reads and closes the stream."""
        ...

    def new_idempotency_key(self) -> str:
        """``"idem_"`` + uuid7 hex."""
        ...


class EmbeddedClient:
    """``SkmClient`` over a bus in the same process (CLI embedded mode, tests).

    By default each call gets a fresh request ID and the client's surface and label. An HTTP request can
    supply its transport metadata using ``for_request``.
    """

    def __init__(  # noqa: PLR0913 - explicit composition injection without ambient locators
        self,
        bus: "Bus",
        *,
        actor: Actor,
        surface: Surface,
        events: Callable[[], EventReaderSession],
        clock: Clock,
        ids: IdGenerator,
        client_label: str,
        blob_uploader: BlobUploader | None = None,
        content_opener: ContentOpener | None = None,
        auth_basis: AuthBasis | None = None,
    ) -> None:
        if auth_basis is not None and auth_basis.actor != actor:
            raise ValueError("EmbeddedClient auth_basis.actor must match actor")
        self._bus = bus
        self._actor = actor
        self._auth_basis = auth_basis if auth_basis is not None else AuthBasis.from_actor(actor)
        self._surface = surface
        self._events = events
        self._clock = clock
        self._ids = ids
        self._client_label = client_label
        self._blob_uploader = blob_uploader
        self._content_opener = content_opener
        self._request_meta: RequestMeta | None = None

    @property
    def auth_basis(self) -> AuthBasis:
        return self._auth_basis

    def for_request(self, meta: RequestMeta, *, auth_basis: AuthBasis | None = None) -> "EmbeddedClient":
        """Bind transport metadata and optional AuthBasis to a per-request client."""
        if auth_basis is not None and auth_basis.actor != self._actor:
            raise ValueError("EmbeddedClient.for_request auth_basis.actor must match actor")
        client = copy(self)
        client._request_meta = meta
        if auth_basis is not None:
            client._auth_basis = auth_basis
        return client

    def _meta(self, idempotency_key: str | None) -> RequestMeta:
        if self._request_meta is not None:
            return self._request_meta
        return RequestMeta(
            request_id=new_request_id(self._ids),
            surface=self._surface,
            idempotency_key=idempotency_key,
            received_at=self._clock.now(),
            client=self._client_label,
        )

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        return self._bus.dispatch(
            command, actor=self._actor, meta=self._meta(idempotency_key), auth_basis=self._auth_basis
        )

    def safe_retry_deadline(self) -> datetime:
        return self._bus.safe_retry_deadline()

    def dispatch_before(self, command: object, *, idempotency_key: str, safe_until: datetime) -> object:
        meta = replace(
            self._meta(idempotency_key), idempotency_key=idempotency_key, idempotency_deadline=safe_until
        )
        return self._bus.dispatch(command, actor=self._actor, meta=meta, auth_basis=self._auth_basis)

    def ask(self, query: object) -> object:
        return self._bus.ask(query, actor=self._actor, meta=self._meta(None), auth_basis=self._auth_basis)

    def ask_with_meta(self, query: object) -> tuple[object, QueryMeta]:
        return self._bus.ask_with_meta(
            query, actor=self._actor, meta=self._meta(None), auth_basis=self._auth_basis
        )

    def events(
        self,
        *,
        workspace_id: WorkspaceId,
        after: int,
        types: frozenset[str] | None = None,
        wait_seconds: float = 0.0,
    ) -> Iterator[EventEnvelope]:
        """Batches of 200; with ``wait_seconds > 0`` the poll repeats every 0.5 s until events or the end."""
        deadline = time.monotonic() + wait_seconds
        cursor = after
        while True:
            with self._events() as reader:
                batch = reader.after_workspace_seq(workspace_id, cursor, types=types, limit=_EVENTS_BATCH)
            if batch:
                yield from batch
                cursor = batch[-1].workspace_seq or cursor
                if len(batch) == _EVENTS_BATCH:
                    continue
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(_POLL_SECONDS, remaining))

    def project_events(
        self,
        *,
        project_id: ProjectId,
        workspace_id: WorkspaceId,
        after: int,
        types: frozenset[str] | None = None,
        wait_seconds: float = 0.0,
    ) -> Iterator[EventEnvelope]:
        """Project-scoped event stream in embedded mode."""
        target = str(project_id)
        for event in self.events(
            workspace_id=workspace_id, after=after, types=types, wait_seconds=wait_seconds
        ):
            if event.stream_id == project_id or event.payload.get("project_id") == target:
                yield event

    def upload_blob(
        self,
        workspace_id: WorkspaceId,
        stream: Iterable[bytes],
        *,
        size: int,
        expected_digest: str | None = None,
        media_type: str | None = None,
    ) -> StagedBlobRef:
        if self._blob_uploader is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "blob upload is not configured on this client",
                details={"operation": "upload_blob"},
            )
        res = self._blob_uploader(
            actor=self._actor,
            meta=self._meta(None),
            workspace_id=workspace_id,
            stream=stream,
            size=size,
            expected_digest=expected_digest,
            media_type=media_type,
            auth_basis=self._auth_basis,
        )
        if isinstance(res, StagedBlobRef):
            return res
        return StagedBlobRef(
            res.staged_blob_id, WorkspaceId(res.workspace_id), res.digest, res.size, res.media_type
        )

    def open_file_version_content(self, file_version_id: FileVersionId) -> BinaryIO:
        if self._content_opener is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "blob content streaming is not configured on this client",
                details={"operation": "open_file_version_content"},
            )
        return self._content_opener(
            actor=self._actor,
            meta=self._meta(None),
            file_version_id=file_version_id,
            auth_basis=self._auth_basis,
        )

    def new_idempotency_key(self) -> str:
        return "idem_" + self._ids.new_id().hex


def embedded_client_factory(
    bus: "Bus",
    uow_factory: UnitOfWorkFactory,
    *,
    surface: Surface,
    ids: IdGenerator,
    clock: Clock,
    backend: str,
    callbacks: tuple[BlobUploader | None, ContentOpener | None] = (None, None),
) -> Callable[[Actor, Surface], SkmClient]:
    """Build ``App.client`` factory over an embedded bus and read-only event sessions."""
    uploader, opener = callbacks

    @contextmanager
    def _reader() -> Generator[EventReader]:
        meta = RequestMeta(new_request_id(ids), surface, None, clock.now())
        with uow_factory(meta, readonly=True) as uow:
            yield uow.repo(EventReader)

    def make_client(actor: Actor, client_surface: Surface) -> SkmClient:
        return EmbeddedClient(
            bus,
            actor=actor,
            surface=client_surface,
            events=_reader,
            clock=clock,
            ids=ids,
            client_label=f"{client_surface.value}/{backend}",
            blob_uploader=uploader,
            content_opener=opener,
        )

    return make_client
