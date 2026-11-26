"""Pure diff of an import document against the current entries of one scope (settings §A.4, §A.7.6).

The document is the parsed ``ConfigDocument`` of ``platform.config.sources.document``; domain code may not
import ``platform``, so it is read structurally (``ImportDocument``). The document decides the lock flag of
each of its keys: a key is locked exactly when it is listed in ``lock``. A lock listed for a key without an
entry in the document is a parse problem (``lock_without_entry``) and is not planned here. The plan does not
validate values: an ``after`` state is the document's request for the write rules (R1-R13, R16), which
collect every problem of the import.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from skm.kernel.json_types import JsonValue

from .entry import ConfigEntry, EntryOp, check_op_value, copy_value, same_value

__all__ = ["ChangeType", "DocumentEntry", "EntryChange", "ImportDocument", "ImportPlan", "plan_import"]

type EntryState = tuple[EntryOp, JsonValue | None, bool]  # (op, value, locked)


class ChangeType(StrEnum):
    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"
    UNCHANGED = "unchanged"
    LOCK_CHANGED = "lock_changed"


class DocumentEntry(Protocol):
    """``DocEntry`` of a parsed document."""

    @property
    def op(self) -> str: ...
    @property
    def value(self) -> JsonValue: ...


class ImportDocument(Protocol):
    """``ConfigDocument`` of a parsed document: entries by key and the keys listed in ``lock``."""

    @property
    def entries(self) -> Mapping[str, DocumentEntry]: ...
    @property
    def locks(self) -> frozenset[str]: ...


def _state(state: EntryState | None, *, stored: bool) -> EntryState | None:
    """``before`` is a stored entry and keeps its invariants (``check_op_value``, ``value_issue`` included).
    ``after`` is what the document asks for, not yet checked: an ``append`` of a non-array, a ``set`` of
    ``null``, a lone surrogate or a value over 64 KiB stays as written, so ``collect_write_problems`` reports
    it (R5) instead of the planner failing; only ``unset`` must be bare. Integers of any width are kept."""
    if state is None:
        return None
    op, value, locked = state
    op = EntryOp(op)
    value = copy_value(value)
    if stored:
        check_op_value(op, value)
    elif op is EntryOp.UNSET and value is not None:
        raise ValueError("op=unset carries no value")
    if not isinstance(locked, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("locked must be a bool")
    return op, value, locked


@dataclass(frozen=True, slots=True)
class EntryChange:
    key: str
    change: ChangeType
    before: EntryState | None
    after: EntryState | None

    def __post_init__(self) -> None:
        change = ChangeType(self.change)
        if (change is ChangeType.ADDED) != (self.before is None) or (change is ChangeType.REMOVED) != (
            self.after is None
        ):
            raise ValueError(f"before/after do not fit change {change.value!r}")
        object.__setattr__(self, "change", change)
        object.__setattr__(self, "before", _state(self.before, stored=True))
        object.__setattr__(self, "after", _state(self.after, stored=False))

    @property
    def lock_change(self) -> bool:
        """Whether the change sets or clears a lock (R13 needs ``config.lock``)."""
        was = self.before is not None and self.before[2]
        becomes = self.after is not None and self.after[2]
        return was != becomes


@dataclass(frozen=True, slots=True)
class ImportPlan:
    changes: tuple[EntryChange, ...]  # sorted by key

    def __post_init__(self) -> None:
        changes = tuple(self.changes)
        keys = [change.key for change in changes]
        if keys != sorted(set(keys)):
            raise ValueError("plan changes are unique and sorted by key")
        object.__setattr__(self, "changes", changes)

    @property
    def effective(self) -> tuple[EntryChange, ...]:
        """Changes that write something (everything except ``unchanged``)."""
        return tuple(change for change in self.changes if change.change is not ChangeType.UNCHANGED)


def _diff(key: str, current: ConfigEntry | None, wanted: EntryState) -> EntryChange:
    if current is None:
        return EntryChange(key, ChangeType.ADDED, None, wanted)
    before: EntryState = (current.op, current.value, current.locked)
    op, value, locked = wanted
    if current.op != op or not same_value(current.value, value):
        return EntryChange(key, ChangeType.UPDATED, before, wanted)
    if current.locked != locked:
        return EntryChange(key, ChangeType.LOCK_CHANGED, before, wanted)
    return EntryChange(key, ChangeType.UNCHANGED, before, wanted)


def plan_import(
    current: Mapping[str, ConfigEntry], document: ImportDocument, *, mode: Literal["merge", "replace"]
) -> ImportPlan:
    """merge: document keys become added/updated/unchanged/lock_changed, other entries stay untouched;
    replace: additionally every current key missing from the document is removed."""
    if mode not in ("merge", "replace"):
        raise ValueError(f"import mode must be merge or replace, not {mode!r}")
    for key, entry in current.items():
        if entry.key != key:
            raise ValueError(f"current entry {entry.key!r} is listed under {key!r}")
    changes: dict[str, EntryChange] = {}
    for key, item in document.entries.items():
        op = EntryOp(item.op)
        value = None if op is EntryOp.UNSET else item.value
        changes[key] = _diff(key, current.get(key), (op, value, key in document.locks))
    if mode == "replace":
        for key, entry in current.items():
            if key not in changes:
                changes[key] = EntryChange(
                    key, ChangeType.REMOVED, (entry.op, entry.value, entry.locked), None
                )
    return ImportPlan(tuple(changes[key] for key in sorted(changes)))
