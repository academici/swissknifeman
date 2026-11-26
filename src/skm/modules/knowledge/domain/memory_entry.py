"""Ephemeral memory entries and their immutable state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, NewType
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PrincipalId

from .memory_kind import MemoryKind
from .memory_scope import MemoryScope

MemoryEntryId = NewType("MemoryEntryId", UUID)
type MemorySource = Literal["cli", "mcp", "hook", "api", "internal"]


class MemoryState(StrEnum):
    LIVE = "live"
    FORGOTTEN = "forgotten"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    id: MemoryEntryId
    scope: MemoryScope
    kind: MemoryKind
    body: str
    created_at: datetime
    expires_at: datetime
    created_by: PrincipalId
    writer: str
    source: MemorySource
    state: MemoryState
    state_changed_at: datetime | None
    supersedes_id: MemoryEntryId | None
    row_version: int

    def __post_init__(self) -> None:
        if self.created_at.utcoffset() is None or self.expires_at.utcoffset() is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory timestamps must be timezone-aware")
        if self.expires_at.astimezone(UTC) <= self.created_at.astimezone(UTC):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory expiry must follow creation")
        # The storage ceiling applies to existing entries even after the configured write limit is narrowed.
        if not 1 <= len(self.body) <= 2000 or self.body != self.body.strip():
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid stored memory body")
        if (self.state is MemoryState.LIVE) != (self.state_changed_at is None):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid memory state timestamp")
        if self.state_changed_at is not None and self.state_changed_at.utcoffset() is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory state timestamp must be timezone-aware")
        if self.row_version < 1:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory row version must be at least one")


def new_entry(  # noqa: PLR0913
    *,
    entry_id: MemoryEntryId,
    scope: MemoryScope,
    kind: MemoryKind,
    body: str,
    created_at: datetime,
    expires_at: datetime,
    created_by: PrincipalId,
    writer: str,
    source: MemorySource,
    max_chars: int = 800,
    supersedes_id: MemoryEntryId | None = None,
) -> MemoryEntry:
    if len(body) > max_chars:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory body exceeds the configured length limit")
    return MemoryEntry(
        id=entry_id,
        scope=scope,
        kind=kind,
        body=body.strip(),
        created_at=created_at,
        expires_at=expires_at,
        created_by=created_by,
        writer=writer,
        source=source,
        state=MemoryState.LIVE,
        state_changed_at=None,
        supersedes_id=supersedes_id,
        row_version=1,
    )


def _transition(entry: MemoryEntry, state: MemoryState, now: datetime) -> MemoryEntry:
    if entry.state is not MemoryState.LIVE:
        return entry
    return replace(entry, state=state, state_changed_at=now, row_version=entry.row_version + 1)


def expire(entry: MemoryEntry, now: datetime) -> MemoryEntry:
    """Mark an entry selected as due by the caller's expiry policy."""
    return _transition(entry, MemoryState.EXPIRED, now)


def forget(entry: MemoryEntry, now: datetime) -> MemoryEntry:
    return _transition(entry, MemoryState.FORGOTTEN, now)


def supersede(entry: MemoryEntry, now: datetime) -> MemoryEntry:
    return _transition(entry, MemoryState.SUPERSEDED, now)
