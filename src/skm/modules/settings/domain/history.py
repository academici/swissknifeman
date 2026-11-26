"""Append-only history of config entries (settings §A.4, DDL ``ck_entry_history__shape``)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

from skm.kernel.ids import PrincipalId
from skm.kernel.json_types import JsonValue

from .entry import REASON_MAX_LENGTH, ConfigEntry, ConfigEntryId, EntryOp, copy_value

__all__ = ["ChangeKind", "HistoryRecord", "history_record"]


class ChangeKind(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    id: UUID
    entry_id: ConfigEntryId
    scope_id: UUID
    key: str
    change_kind: ChangeKind
    old_op: EntryOp | None
    old_value: JsonValue | None
    old_locked: bool | None
    new_op: EntryOp | None
    new_value: JsonValue | None
    new_locked: bool | None
    actor_id: PrincipalId
    request_id: str | None
    reason: str
    generation: int
    changed_at: datetime

    def __post_init__(self) -> None:
        kind = ChangeKind(self.change_kind)
        old = self.old_op is not None
        new = self.new_op is not None
        # CREATED ⇒ no old state; REMOVED ⇒ no new state; UPDATED/LOCKED/UNLOCKED ⇒ both
        if (kind is ChangeKind.CREATED) == old or (kind is ChangeKind.REMOVED) == new:
            raise ValueError(f"history shape does not fit change kind {kind.value!r}")
        for present, locked, value in (
            (old, self.old_locked, self.old_value),
            (new, self.new_locked, self.new_value),
        ):
            if not present and (locked is not None or value is not None):
                raise ValueError("an absent side of a history record carries no value or lock flag")
            if present and not isinstance(cast("object", locked), bool):
                raise ValueError("a present side of a history record has a lock flag")
        if kind is ChangeKind.LOCKED and not (self.old_locked is False and self.new_locked is True):
            raise ValueError("a locked record goes from unlocked to locked")
        if kind is ChangeKind.UNLOCKED and not (self.old_locked is True and self.new_locked is False):
            raise ValueError("an unlocked record goes from locked to unlocked")
        if isinstance(self.generation, bool) or not isinstance(cast("object", self.generation), int):
            raise ValueError("generation must be an integer")
        if self.generation < 1:
            raise ValueError("generation must be >= 1: history follows counter.increment()")
        if not isinstance(cast("object", self.reason), str) or len(self.reason) > REASON_MAX_LENGTH:
            raise ValueError(f"reason must be a string of at most {REASON_MAX_LENGTH} characters")
        if self.changed_at.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")
        object.__setattr__(self, "change_kind", kind)
        object.__setattr__(self, "old_op", None if self.old_op is None else EntryOp(self.old_op))
        object.__setattr__(self, "new_op", None if self.new_op is None else EntryOp(self.new_op))
        object.__setattr__(self, "old_value", copy_value(self.old_value))
        object.__setattr__(self, "new_value", copy_value(self.new_value))


def history_record(  # noqa: PLR0913 -- signature fixed by settings §A.4
    *,
    record_id: UUID,
    before: ConfigEntry | None,
    after: ConfigEntry | None,
    kind: ChangeKind,
    actor: PrincipalId,
    request_id: str | None,
    reason: str,
    generation: int,
    now: datetime,
) -> HistoryRecord:
    """History of one change; ``before``/``after`` must describe the same entry (id, scope and key)."""
    subject = after if after is not None else before
    if subject is None:
        raise ValueError("a history record needs the entry before or after the change")
    if (
        before is not None
        and after is not None
        and (before.id != after.id or before.scope != after.scope or before.key != after.key)
    ):
        raise ValueError("before and after are different entries")
    return HistoryRecord(
        id=record_id,
        entry_id=subject.id,
        scope_id=subject.scope.id,
        key=subject.key,
        change_kind=kind,
        old_op=None if before is None else before.op,
        old_value=None if before is None else before.value,
        old_locked=None if before is None else before.locked,
        new_op=None if after is None else after.op,
        new_value=None if after is None else after.value,
        new_locked=None if after is None else after.locked,
        actor_id=actor,
        request_id=request_id,
        reason=reason,
        generation=generation,
        changed_at=now,
    )
