"""Memory implementations of the settings repository ports (settings §A.6, §A.11).

The full entries (with reason and audit stamps) and the history live in the module state
``MemoryBackendState.modules["settings"]``; every entry write also goes through the writers of
``adapters/memory/config_store.py`` into ``MemoryCoreState.config_entries``, the rows ``ConfigStore`` reads.
Both copies change together in the working copy of one unit of work, so the resolver of the same
transaction sees uncommitted writes and a rollback drops both. A row of one copy without the other, or with
different content, is storage damage: reads fail closed with ``INTERNAL_ERROR``.

``save`` and ``remove`` are conditional on the version the command read (``VERSION_CONFLICT`` otherwise),
like the ``WHERE id = … AND row_version = …`` updates of PostgreSQL. Cursors are opaque base64 JSON:
``[key, scope_id]`` for entries (keyset by key, scope id) and ``[changed_at, id]`` for history
(``changed_at DESC, id DESC``).
"""

import base64
import binascii
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, cast
from uuid import UUID

from skm.adapters.memory.config_store import (
    delete_config_entry,
    entry_row,
    increment_config_generation,
    write_config_entry,
)
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.pagination import Cursor, Page, validate_cursor, validate_page_limit
from skm.kernel.scopes import ScopeKind
from skm.modules.settings.domain.entry import ConfigEntry, ConfigEntryId, version_conflict
from skm.modules.settings.domain.history import HistoryRecord
from skm.platform.config.store import StoredContribution

__all__ = [
    "STATE_KEY",
    "MemoryConfigEntryRepository",
    "MemoryConfigGenerationCounter",
    "MemoryConfigHistoryRepository",
    "MemorySettingsState",
    "settings_state",
]

STATE_KEY: Final = "settings"


@dataclass
class MemorySettingsState:
    """Tables of ``skm_config`` that the core state does not hold: full entries and their history."""

    entries: dict[UUID, dict[str, ConfigEntry]] = field(default_factory=dict[UUID, dict[str, ConfigEntry]])
    history: list[HistoryRecord] = field(default_factory=list[HistoryRecord])


def settings_state(state: MemoryBackendState) -> MemorySettingsState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemorySettingsState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemorySettingsState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "settings memory state is malformed", details={"module": STATE_KEY}
        )
    return found


def _stored(entry: ConfigEntry) -> StoredContribution:
    return StoredContribution(
        entry_id=entry.id,
        key=entry.key,
        op=entry.op.value,
        value=entry.value,
        locked=entry.locked,
        row_version=entry.row_version,
    )


def _damaged(scope_id: UUID, key: str) -> InternalError:
    return InternalError(
        ErrorCode.INTERNAL_ERROR,
        "config entry tables are out of sync",
        details={"scope_id": str(scope_id), "key": key},
    )


def _encode_cursor(parts: Sequence[str]) -> Cursor:
    raw = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return validate_cursor(base64.urlsafe_b64encode(raw).decode("ascii"))


def _decode_cursor(cursor: str | None, size: int) -> tuple[str, ...] | None:
    if cursor is None:
        return None
    try:
        parts = json.loads(base64.urlsafe_b64decode(validate_cursor(cursor).encode("ascii")))
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        parts = None
    if not isinstance(parts, list) or len(cast("list[object]", parts)) != size:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})
    items = cast("list[object]", parts)
    if not all(isinstance(item, str) for item in items):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})
    return tuple(cast("list[str]", items))


def _page[T](rows: list[T], limit: int, cursor_of: Callable[[T], Sequence[str]]) -> Page[T]:
    limit = validate_page_limit(limit)
    items = rows[:limit]
    following = _encode_cursor(cursor_of(items[-1])) if len(rows) > limit else None
    return Page(items=tuple(items), next=following)


class MemoryConfigEntryRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables = settings_state(state)

    # ------------------------------------------------------------------ reads
    def _scope(self, scope_id: UUID) -> dict[str, ConfigEntry]:
        """Entries of one scope, checked against the rows the resolver reads."""
        entries = self._tables.entries.get(scope_id, {})
        rows = self._state.core.config_entries.get(scope_id, {})
        if set(rows) != set(entries):
            key = sorted(set(rows) ^ set(entries))[0]
            raise _damaged(scope_id, key)
        for key, entry in entries.items():
            if entry.key != key or entry.scope.id != scope_id or rows[key] != entry_row(_stored(entry)):
                raise _damaged(scope_id, key)
        return entries

    def _all(self) -> Iterable[ConfigEntry]:
        scope_ids = set(self._tables.entries) | set(self._state.core.config_entries)
        for scope_id in scope_ids:
            yield from self._scope(scope_id).values()

    def get(self, entry_id: ConfigEntryId) -> ConfigEntry:
        for entry in self._all():
            if entry.id == entry_id:
                return entry
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "config entry not found",
            details={"kind": "config_entry", "ref": str(entry_id)},
        )

    # ``for_update`` needs no lock here: one unit of work at a time makes every read exclusive.
    def find(self, scope_id: UUID, key: str, *, for_update: bool = False) -> ConfigEntry | None:  # noqa: ARG002
        return self._scope(scope_id).get(key)

    def entries_of_scope(self, scope_id: UUID, *, for_update: bool = False) -> Mapping[str, ConfigEntry]:  # noqa: ARG002
        entries = self._scope(scope_id)
        return {key: entries[key] for key in sorted(entries)}

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, ConfigEntry]]:
        found: dict[UUID, Mapping[str, ConfigEntry]] = {}
        for scope_id in dict.fromkeys(scope_ids):
            entries = self.entries_of_scope(scope_id)
            if entries:
                found[scope_id] = entries
        return found

    # ------------------------------------------------------------------ writes
    def _write(self, entry: ConfigEntry) -> None:
        write_config_entry(self._state, entry.scope.id, _stored(entry))
        self._tables.entries.setdefault(entry.scope.id, {})[entry.key] = entry

    def add(self, entry: ConfigEntry) -> None:
        if self.find(entry.scope.id, entry.key) is not None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a config entry for this scope and key exists",
                details={"kind": "config_entry", "scope_id": str(entry.scope.id), "key": entry.key},
            )
        if any(other.id == entry.id for other in self._all()):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a config entry with this id exists",
                details={"kind": "config_entry", "ref": str(entry.id)},
            )
        if entry.row_version != 1:
            raise ValueError("a new entry starts at row_version 1")
        self._write(entry)

    def save(self, entry: ConfigEntry, *, expected_version: int) -> None:
        current = self.find(entry.scope.id, entry.key)
        if current is None or current.id != entry.id:
            raise version_conflict(expected_version, 0)
        if current.row_version != expected_version:
            raise version_conflict(expected_version, current.row_version)
        if entry.row_version <= expected_version:
            raise ValueError("a saved entry carries a row_version above the expected one")
        self._write(entry)

    def remove(self, entry_id: ConfigEntryId, *, expected_version: int) -> None:
        current = next((entry for entry in self._all() if entry.id == entry_id), None)
        if current is None:
            raise version_conflict(expected_version, 0)
        if current.row_version != expected_version:
            raise version_conflict(expected_version, current.row_version)
        delete_config_entry(self._state, current.scope.id, current.key)
        rows = self._tables.entries[current.scope.id]
        del rows[current.key]
        if not rows:
            del self._tables.entries[current.scope.id]

    # ------------------------------------------------------------------ listings
    def list(
        self,
        *,
        scope_id: UUID | None,
        level: ScopeKind | None,
        key_prefix: str | None,
        after: str | None,
        limit: int,
        exclude_keys: frozenset[str] = frozenset(),
    ) -> Page[ConfigEntry]:
        start = _decode_cursor(after, 2)
        rows = sorted(
            (
                entry
                for entry in self._all()
                if entry.key not in exclude_keys
                and (scope_id is None or entry.scope.id == scope_id)
                and (level is None or entry.scope.kind is ScopeKind(level))
                and (key_prefix is None or entry.key.startswith(key_prefix))
            ),
            key=lambda entry: (entry.key, str(entry.scope.id)),
        )
        if start is not None:
            rows = [entry for entry in rows if (entry.key, str(entry.scope.id)) > start]
        return _page(rows, limit, lambda entry: (entry.key, str(entry.scope.id)))

    def count_shadowed_below(self, scope_id: UUID, key: str) -> int:
        children: dict[UUID, list[UUID]] = {}
        for record in self._state.core.scopes.values():
            if record.parent_id is not None:
                children.setdefault(record.parent_id, []).append(record.id)
        below: list[UUID] = []
        pending = list(children.get(ScopeId(scope_id), ()))
        while pending:
            current = pending.pop()
            below.append(current)
            pending.extend(children.get(ScopeId(current), ()))
        return sum(1 for descendant in below if self.find(descendant, key) is not None)


class MemoryConfigHistoryRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables = settings_state(state)

    def append(self, record: HistoryRecord) -> None:
        self._state.core.require_writable()
        if any(other.id == record.id for other in self._tables.history):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a history record with this id exists",
                details={"kind": "config_history", "ref": str(record.id)},
            )
        self._tables.history.append(record)

    def list(
        self,
        *,
        scope_id: UUID | None,
        key: str | None,
        after: str | None,
        limit: int,
        exclude_keys: frozenset[str] = frozenset(),
    ) -> Page[HistoryRecord]:
        start = _decode_cursor(after, 2)

        def order(record: HistoryRecord) -> tuple[str, str]:
            return (record.changed_at.isoformat(), str(record.id))

        rows = sorted(
            (
                record
                for record in self._tables.history
                if record.key not in exclude_keys
                and (scope_id is None or record.scope_id == scope_id)
                and (key is None or record.key == key)
            ),
            key=lambda record: (record.changed_at, str(record.id)),
            reverse=True,
        )
        if start is not None:
            try:
                changed_at = datetime.fromisoformat(start[0])
            except ValueError as exc:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"}
                ) from exc
            if changed_at.utcoffset() is None:  # a date or a naive time cannot be ordered against changed_at
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"}
                )
            bound = (changed_at, start[1])
            rows = [record for record in rows if (record.changed_at, str(record.id)) < bound]
        return _page(rows, limit, order)


class MemoryConfigGenerationCounter:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state

    def current(self) -> int:
        return self._state.core.config_generation

    def increment(self) -> int:
        return increment_config_generation(self._state)
