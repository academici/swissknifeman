"""PostgreSQL memory storage with transaction-scoped locks on complete scope identities."""

from collections.abc import Iterator
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.pagination import Cursor, Page, validate_page_limit
from skm.modules.knowledge.domain.memory_entry import MemoryEntry, MemoryEntryId
from skm.modules.knowledge.domain.memory_kind import MemoryKind
from skm.modules.knowledge.domain.memory_scope import MemoryScope, scope_lock_key
from skm.modules.knowledge.ports import page_of, start_after

from .mapping import memory_from_row, run, scope_from_row

__all__ = ["PostgresMemoryRepository"]

_LOCK_SCOPE: Final = "SELECT pg_advisory_xact_lock(%s)"
# The two-int advisory keyspace is disjoint from the single bigint scope keys.
_LOCK_SWEEPER: Final = "SELECT pg_advisory_xact_lock(21, 1)"
_TABLE: Final = "skm_knowledge.memory_entries"
_COLUMNS: Final = """
id, scope_kind, scope_id, namespace, workspace_id, kind, body, state, writer, source, created_by,
supersedes_id, created_at, expires_at, state_changed_at, row_version
"""
_SELECT: Final = "SELECT " + _COLUMNS + " FROM " + _TABLE  # noqa: S608 -- SQL fragments are module constants
_GET: Final = _SELECT + " WHERE id = %s"
_INSERT: Final = (
    "INSERT INTO " + _TABLE + "(" + _COLUMNS + ")"  # noqa: S608 -- SQL fragments are module constants
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_UPDATE: Final = """
UPDATE skm_knowledge.memory_entries
SET state = %s, state_changed_at = %s, row_version = row_version + 1
WHERE id = %s AND row_version = %s
"""
_SCOPE: Final = """
scope_kind = %(scope_kind)s
AND scope_id IS NOT DISTINCT FROM %(scope_id)s::uuid
AND namespace IS NOT DISTINCT FROM %(namespace)s::text
AND workspace_id IS NOT DISTINCT FROM %(workspace)s::uuid
"""
_LIVE: Final = """
state = 'live' AND expires_at > %(now)s::timestamptz
AND created_at <= %(now)s::timestamptz + interval '60 seconds'
AND (%(created_after)s::timestamptz IS NULL OR created_at > %(created_after)s::timestamptz)
"""
_COUNT: Final = (
    "SELECT count(*) FROM "  # noqa: S608 -- SQL fragments are module constants
    + _TABLE
    + " WHERE "
    + _SCOPE
    + " AND "
    + _LIVE
    + " AND kind <> ALL(%(excluded)s::text[])"
)
_HANDOFF: Final = _SELECT + " WHERE " + _SCOPE + " AND kind = 'active_handoff' AND state = 'live'"
_SEARCH: Final = (
    _SELECT
    + " WHERE "
    + _SCOPE
    + " AND "
    + _LIVE
    + """
    AND (%(query)s::text IS NULL OR to_tsvector('simple', body) @@ plainto_tsquery('simple', %(query)s))
    ORDER BY id DESC
    """
)
_LIST: Final = (
    _SELECT
    + " WHERE "
    + _SCOPE
    + " AND (%(history)s OR ("
    + _LIVE
    + """))
    AND (%(after)s::timestamptz IS NULL OR (created_at, id) < (%(after)s::timestamptz, %(id)s::uuid))
    ORDER BY created_at DESC, id DESC
    LIMIT %(limit)s
    """
)
_DUE: Final = """
SELECT id, scope_kind, scope_id, namespace, workspace_id
FROM skm_knowledge.memory_entries
WHERE state = 'live' AND expires_at <= %s
ORDER BY expires_at, id LIMIT %s
"""
_EXPIRE: Final = """
UPDATE skm_knowledge.memory_entries
SET state = 'expired', state_changed_at = %s, row_version = row_version + 1
WHERE id = ANY(%s::uuid[]) AND state = 'live' AND expires_at <= %s
"""
_PURGE: Final = """
DELETE FROM skm_knowledge.memory_entries WHERE id IN (
    SELECT id FROM skm_knowledge.memory_entries WHERE state <> 'live' AND state_changed_at < %s
    ORDER BY state_changed_at, id LIMIT %s FOR UPDATE SKIP LOCKED
)
"""


def _scope_params(scope: MemoryScope) -> dict[str, object]:
    return {
        "scope_kind": scope.kind.value,
        "scope_id": scope.scope_id,
        "namespace": scope.namespace,
        "workspace": scope.workspace_id,
    }


class PostgresMemoryRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def lock_scope(self, scope: MemoryScope) -> None:
        run(lambda: self._conn.execute(_LOCK_SCOPE, (scope_lock_key(scope),)))

    def add(self, entry: MemoryEntry) -> None:
        scope = entry.scope
        params = (
            entry.id,
            scope.kind.value,
            scope.scope_id,
            scope.namespace,
            scope.workspace_id,
            entry.kind.value,
            entry.body,
            entry.state.value,
            entry.writer,
            entry.source,
            entry.created_by,
            entry.supersedes_id,
            entry.created_at,
            entry.expires_at,
            entry.state_changed_at,
            entry.row_version,
        )
        run(lambda: self._conn.execute(_INSERT, params))

    def get(self, entry_id: MemoryEntryId) -> MemoryEntry:
        row = run(lambda: self._conn.execute(_GET, (entry_id,)).fetchone())
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Memory entry not found")
        return memory_from_row(row)

    def save(self, entry: MemoryEntry, *, expected_version: int) -> None:
        params = (entry.state.value, entry.state_changed_at, entry.id, expected_version)
        if not run(lambda: self._conn.execute(_UPDATE, params).rowcount):
            self.get(entry.id)
            raise Conflict(ErrorCode.VERSION_CONFLICT, "Memory entry version changed")

    def count_live(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        exclude_kinds: frozenset[MemoryKind],
        created_after: datetime | None = None,
    ) -> int:
        params = dict(
            _scope_params(scope),
            now=now,
            created_after=created_after,
            excluded=[kind.value for kind in exclude_kinds],
        )
        row = run(lambda: self._conn.execute(_COUNT, params).fetchone())
        assert row is not None  # noqa: S101 -- count(*) always returns one row
        return cast("int", row[0])

    def live_handoff(self, scope: MemoryScope, *, now: datetime) -> MemoryEntry | None:  # noqa: ARG002 -- CAS uses stored state
        row = run(lambda: self._conn.execute(_HANDOFF, _scope_params(scope)).fetchone())
        return None if row is None else memory_from_row(row)

    def search_candidates(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        query: str | None,
        created_after: datetime | None = None,
    ) -> Iterator[MemoryEntry]:
        params = dict(_scope_params(scope), now=now, query=query, created_after=created_after)
        with self._conn.cursor(name="knowledge_memory_search") as cursor:
            run(lambda: cursor.execute(_SEARCH, params))
            while rows := run(lambda: cursor.fetchmany(100)):
                yield from map(memory_from_row, rows)

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
        params = dict(
            _scope_params(scope),
            now=now,
            history=include_expired,
            after=when,
            id=row_id,
            limit=limit + 1,
            created_after=created_after,
        )
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            tuple(map(memory_from_row, rows)), limit, filters, lambda row: (row.created_at, row.id)
        )

    def expire_due(self, *, now: datetime, batch: int) -> int:
        run(lambda: self._conn.execute(_LOCK_SWEEPER))
        due = run(lambda: self._conn.execute(_DUE, (now, batch)).fetchall())
        if not due:
            return 0
        # No row lock precedes the scope lock. Recheck state after waiting for a writer.
        for scope in sorted({scope_from_row(row[1:]) for row in due}, key=scope_lock_key):
            self.lock_scope(scope)
        ids = [cast("UUID", row[0]) for row in due]
        return run(lambda: self._conn.execute(_EXPIRE, (now, ids, now)).rowcount)

    def purge_older_than(self, *, before: datetime, batch: int) -> int:
        run(lambda: self._conn.execute(_LOCK_SWEEPER))
        return run(lambda: self._conn.execute(_PURGE, (before, batch)).rowcount)
