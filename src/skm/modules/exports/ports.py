"""Repository and host gateway contracts for exports."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from skm.kernel.gateways import host_gateway
from skm.kernel.ids import EventId, HostId, ProjectId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, repository_port

from .domain.contracts import ScanBudget
from .domain.note import NoteKind, VaultNote, VaultNoteId, VaultNoteWrite
from .domain.vault import VaultIdentity

if TYPE_CHECKING:
    from pathlib import Path

type Cursor = str
type NoteKey = tuple[datetime, UUID]

PENDING_SCAN_LIMIT = 500


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultRequestMeta(RequestMeta):
    """Caller host selection, checked against the live actor and checkout during delivery."""

    host_id: HostId


@dataclass(frozen=True, slots=True)
class CandidatePage:
    items: tuple[VaultNote, ...]
    has_more: bool


def note_key(note: VaultNote) -> NoteKey:
    return note.created_at, note.id


def candidate_page(rows: Sequence[VaultNote], limit: int) -> CandidatePage:
    return CandidatePage(tuple(rows[:limit]), len(rows) > limit)


@repository_port
class VaultNoteRepository(Protocol):
    def add(self, note: VaultNote) -> bool: ...

    def by_event(self, event_id: EventId, kind: NoteKind) -> VaultNote | None: ...

    def get(self, note_id: VaultNoteId, *, for_update: bool = False) -> VaultNote: ...

    def active_checkout(
        self, workspace_id: WorkspaceId, host_id: HostId, project_id: ProjectId | None = None
    ) -> bool: ...

    def pending_for_host(
        self,
        workspace_id: WorkspaceId,
        host_id: HostId,
        vault_id: UUID,
        *,
        now: datetime,
        ttl_days: int,
        after: NoteKey | None,
        scan_limit: int,
    ) -> CandidatePage: ...

    def add_write(self, w: VaultNoteWrite, *, now: datetime, ttl_days: int) -> bool: ...

    def writes(self, note_id: VaultNoteId) -> tuple[VaultNoteWrite, ...]: ...

    def requeue(self, note_id: VaultNoteId, expected_generation: int, at: datetime) -> int: ...

    def list(self, project_id: ProjectId, *, after: NoteKey | None, limit: int) -> CandidatePage: ...

    def expire_due(self, now: datetime, ttl_days: int, *, limit: int) -> int: ...

    def delete_older_than(self, cutoff: datetime, *, limit: int) -> int: ...


@host_gateway
class VaultFs(Protocol):
    root: Path

    def ensure_identity(self) -> VaultIdentity: ...

    def is_dir(self, rel: str) -> bool: ...

    def read_head(self, rel: str, *, limit: int = 8192) -> bytes | None: ...

    def glob(self, rel_dir: str, pattern: str, *, budget: ScanBudget) -> Iterator[str]: ...

    def read_bounded(self, rel: str, *, max_bytes: int, durable: bool = False) -> bytes | None: ...

    def create_new(self, rel: str, data: bytes) -> bool: ...

    def write_atomic(self, rel: str, data: bytes, *, replace: Literal[True]) -> None: ...

    def lock(self, vault_id: UUID, *, deadline_seconds: float) -> AbstractContextManager[None]: ...
