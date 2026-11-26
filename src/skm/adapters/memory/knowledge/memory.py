"""In-memory ephemeral memory repository."""

import re
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.pagination import Cursor, Page, validate_page_limit
from skm.modules.knowledge.domain.memory_entry import MemoryEntry, MemoryEntryId, MemoryState, expire
from skm.modules.knowledge.domain.memory_kind import MemoryKind
from skm.modules.knowledge.domain.memory_scope import MemoryScope, scope_lock_key
from skm.modules.knowledge.ports import SortKey, page_of, start_after

from .mapping import knowledge_state

__all__ = ["MemoryMemoryRepository"]

_WORD = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
_FUTURE_SKEW = timedelta(seconds=60)


def _lexemes(text: str) -> set[str]:
    # The simple dictionary lowercases whole words, retaining hyphenated words and their parts.
    return {piece for word in _WORD.findall(text.lower()) for piece in (word, *word.split("-"))}


def _key(entry: MemoryEntry) -> SortKey:
    return entry.created_at.astimezone(UTC), entry.id


def _live(entry: MemoryEntry, now: datetime, created_after: datetime | None) -> bool:
    return (
        entry.state is MemoryState.LIVE
        and entry.expires_at > now
        and entry.created_at <= now + _FUTURE_SKEW
        and (created_after is None or entry.created_at > created_after)
    )


class MemoryMemoryRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._rows = knowledge_state(state).entries

    def lock_scope(self, scope: MemoryScope) -> None:  # noqa: ARG002 -- backend-wide UoW lock
        # The backend holds its write lock for the entire UoW, including count and insert.
        self._state.core.require_writable()

    def get(self, entry_id: MemoryEntryId) -> MemoryEntry:
        row = self._rows.get(entry_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Memory entry not found")
        return row

    def _check_handoff(self, entry: MemoryEntry) -> None:
        if (
            entry.state is MemoryState.LIVE
            and entry.kind is MemoryKind.ACTIVE_HANDOFF
            and any(
                row.id != entry.id
                and row.scope == entry.scope
                and row.state is MemoryState.LIVE
                and row.kind is MemoryKind.ACTIVE_HANDOFF
                for row in self._rows.values()
            )
        ):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "An active handoff already exists",
                details={"constraint": "uq_memory_entries__live_handoff"},
            )

    def add(self, entry: MemoryEntry) -> None:
        self._state.core.require_writable()
        if entry.id in self._rows:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Memory entry already exists")
        self._check_handoff(entry)
        self._rows[entry.id] = entry

    def save(self, entry: MemoryEntry, *, expected_version: int) -> None:
        self._state.core.require_writable()
        current = self.get(entry.id)
        if current.row_version != expected_version:
            raise Conflict(ErrorCode.VERSION_CONFLICT, "Memory entry version changed")
        updated = replace(
            current,
            state=entry.state,
            state_changed_at=entry.state_changed_at,
            row_version=expected_version + 1,
        )
        self._check_handoff(updated)
        self._rows[entry.id] = updated

    def count_live(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        exclude_kinds: frozenset[MemoryKind],
        created_after: datetime | None = None,
    ) -> int:
        return sum(
            row.scope == scope and row.kind not in exclude_kinds and _live(row, now, created_after)
            for row in self._rows.values()
        )

    def live_handoff(self, scope: MemoryScope, *, now: datetime) -> MemoryEntry | None:  # noqa: ARG002 -- CAS uses stored state
        return next(
            (
                row
                for row in self._rows.values()
                if row.scope == scope
                and row.state is MemoryState.LIVE
                and row.kind is MemoryKind.ACTIVE_HANDOFF
            ),
            None,
        )

    def search_candidates(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        query: str | None,
        created_after: datetime | None = None,
    ) -> Iterator[MemoryEntry]:
        terms = None if query is None else _lexemes(query)
        rows = (
            row
            for row in self._rows.values()
            if row.scope == scope
            and _live(row, now, created_after)
            and (terms is None or (terms and terms <= _lexemes(row.body)))
        )
        return iter(sorted(rows, key=lambda row: row.id, reverse=True))

    def list(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        include_expired: bool,
        after: Cursor | None,
        limit: int,
        created_after: datetime | None = None,
    ) -> Page[MemoryEntry]:
        limit = validate_page_limit(limit)
        filters = f"memory:{scope_lock_key(scope)}:{include_expired}"
        when, row_id = start_after(after, filters)
        rows = [
            row
            for row in self._rows.values()
            if row.scope == scope
            and (include_expired or _live(row, now, created_after))
            and (when is None or row_id is None or _key(row) < (when, row_id))
        ]
        return page_of(sorted(rows, key=_key, reverse=True), limit, filters, _key)

    def expire_due(self, *, now: datetime, batch: int) -> int:
        self._state.core.require_writable()
        due = sorted(
            (row for row in self._rows.values() if row.state is MemoryState.LIVE and row.expires_at <= now),
            key=lambda row: (row.expires_at, row.id),
        )[:batch]
        for row in due:
            self.lock_scope(row.scope)
            self._rows[row.id] = expire(row, now)
        return len(due)

    def purge_older_than(self, *, before: datetime, batch: int) -> int:
        self._state.core.require_writable()
        candidates = sorted(
            (row.state_changed_at, row.id)
            for row in self._rows.values()
            if row.state_changed_at is not None and row.state_changed_at < before
        )[:batch]
        deleted = {row_id for _, row_id in candidates}
        for row_id in deleted:
            del self._rows[row_id]
        if deleted:
            for row in tuple(self._rows.values()):
                if row.supersedes_id in deleted:
                    self._rows[row.id] = replace(row, supersedes_id=None)
        return len(deleted)
