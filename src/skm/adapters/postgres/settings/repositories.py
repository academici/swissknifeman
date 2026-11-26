"""PostgreSQL implementations of the settings repository ports (settings §A.6, §A.11).

Constructed per unit of work over its connection; they never commit or close it. Every writer marks the
transaction (``mark_pending``) so ``ConfigStore.pending_writes`` keeps the loader cache free of uncommitted
configuration. Values use the JSON form of ``adapters/postgres/config_store.py`` (``jsonb_value`` in,
``value::text`` and ``loads_value`` out); a row that does not fit the domain types is storage damage
(``INTERNAL_ERROR``).

Locking. The singleton ``skm_config.generation`` row serializes config writers. ``counter.increment`` updates
it, and a read ``for_update`` (``find``, ``entries_of_scope``: the first read of every settings command)
locks it **before** reading the entries, then locks the entry rows it returns. A second writer therefore
waits before its own reads, and under READ COMMITTED its next statements see what the first one committed:
the candidate checks of R14 (validators across keys) never run on a snapshot that a concurrent commit has
already made stale, and two writers of a new ``(scope, key)`` cannot both see it missing. Lock order is
generation, then entry rows, in every command.

CAS. ``save`` and ``remove`` are conditional on the version the command read (``WHERE id = … AND
row_version = …``); zero rows is ``Conflict(VERSION_CONFLICT, {expected, actual})`` with ``actual = 0`` when
the entry is gone. ``add`` and ``history.append`` insert with ``ON CONFLICT DO NOTHING``, so a duplicate is
``Conflict(ALREADY_EXISTS)`` without aborting the transaction, as in the memory adapter. History rows are
append-only (trigger ``tg_entry_history__append_only``).

Paging. Entries page by ``(key, scope_id)`` ascending with keys in byte order (``COLLATE "C"``, as Python
orders them); history by ``changed_at DESC, id DESC``. Cursors are bound to the filter that produced them
(``adapters/postgres/pagination.py``); a foreign or damaged cursor is ``SCHEMA_INVALID`` (``field=after``).
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.config_store import (
    damaged_row,
    generation_row_missing,
    jsonb_value,
    loads_value,
    mark_pending,
)
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.pagination import decode_cursor, page_of, query_digest
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.pagination import Page, validate_page_limit
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.settings.domain.entry import ConfigEntry, ConfigEntryId, EntryOp, version_conflict
from skm.modules.settings.domain.history import ChangeKind, HistoryRecord

__all__ = [
    "PostgresConfigEntryRepository",
    "PostgresConfigGenerationCounter",
    "PostgresConfigHistoryRepository",
]

type _Row = tuple[object, ...]

# ``e`` is skm_config.entries, ``s`` the joined skm_core.scopes row: its kind is the level of the entry.
_ENTRY: Final = (
    "SELECT e.id, e.scope_id, s.kind, e.key, e.op, e.value::text, e.locked, e.row_version, e.reason, "
    "e.created_by, e.created_at, e.updated_by, e.updated_at "
    "FROM skm_config.entries e JOIN skm_core.scopes s ON s.id = e.scope_id "
)
_HISTORY_COLUMNS: Final = (
    "SELECT id, entry_id, scope_id, key, change_kind, old_op, old_value::text, old_locked, new_op, "
    "new_value::text, new_locked, actor_id, request_id, reason, generation, changed_at "
    "FROM skm_config.entry_history "
)
_LOCK_WRITERS: Final = "SELECT value FROM skm_config.generation WHERE id = 1 FOR UPDATE"
_GET: Final = _ENTRY + "WHERE e.id = %s"
_FIND: Final = _ENTRY + "WHERE e.scope_id = %s AND e.key = %s"
_FIND_LOCKED: Final = _FIND + " FOR UPDATE OF e"
_OF_SCOPE: Final = _ENTRY + 'WHERE e.scope_id = %s ORDER BY e.key COLLATE "C"'
_OF_SCOPE_LOCKED: Final = _OF_SCOPE + " FOR UPDATE OF e"
_FOR_SCOPES: Final = _ENTRY + 'WHERE e.scope_id = ANY(%s) ORDER BY e.scope_id, e.key COLLATE "C"'
_INSERT: Final = """
INSERT INTO skm_config.entries
    (id, scope_id, key, op, value, locked, row_version, reason,
     created_by, created_at, updated_by, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_KEY_TAKEN: Final = "SELECT 1 FROM skm_config.entries WHERE scope_id = %s AND key = %s"
_UPDATE: Final = """
UPDATE skm_config.entries
   SET op = %s, value = %s, locked = %s, row_version = %s, reason = %s, updated_by = %s, updated_at = %s
 WHERE id = %s AND scope_id = %s AND key = %s AND row_version = %s
RETURNING id
"""
_VERSION_AT: Final = "SELECT row_version FROM skm_config.entries WHERE id = %s AND scope_id = %s AND key = %s"
_DELETE: Final = "DELETE FROM skm_config.entries WHERE id = %s AND row_version = %s RETURNING id"
_VERSION_OF: Final = "SELECT row_version FROM skm_config.entries WHERE id = %s"
_LIST: Final = (
    _ENTRY
    + """
 WHERE (%(scope)s::uuid IS NULL OR e.scope_id = %(scope)s::uuid)
   AND (%(level)s::text IS NULL OR s.kind = %(level)s::text)
   AND (%(prefix)s::text IS NULL OR starts_with(e.key, %(prefix)s::text))
   AND e.key <> ALL(%(exclude_keys)s::text[])
   AND (%(key)s::text IS NULL
        OR (e.key COLLATE "C", e.scope_id) > (%(key)s::text COLLATE "C", %(scope_after)s::uuid))
 ORDER BY e.key COLLATE "C", e.scope_id
 LIMIT %(limit)s
"""
)
# Descendants of a scope; the tree is five levels deep at most, the bound only stops a damaged cycle.
_SHADOWED: Final = """
WITH RECURSIVE below AS (
    SELECT id, 1 AS depth FROM skm_core.scopes WHERE parent_id = %s
    UNION ALL
    SELECT s.id, b.depth + 1 FROM skm_core.scopes s JOIN below b ON s.parent_id = b.id WHERE b.depth < 16
)
SELECT count(*) FROM skm_config.entries e JOIN below b ON e.scope_id = b.id WHERE e.key = %s
"""
_APPEND: Final = """
INSERT INTO skm_config.entry_history
    (id, entry_id, scope_id, key, change_kind, old_op, old_value, old_locked, new_op, new_value, new_locked,
     actor_id, request_id, reason, generation, changed_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING RETURNING id
"""
_HISTORY: Final = (
    _HISTORY_COLUMNS
    + """
 WHERE (%(scope)s::uuid IS NULL OR scope_id = %(scope)s::uuid)
   AND (%(key)s::text IS NULL OR key = %(key)s::text)
   AND key <> ALL(%(exclude_keys)s::text[])
   AND (%(at)s::timestamptz IS NULL OR (changed_at, id) < (%(at)s::timestamptz, %(id)s::uuid))
 ORDER BY changed_at DESC, id DESC
 LIMIT %(limit)s
"""
)
_CURRENT: Final = "SELECT value FROM skm_config.generation WHERE id = 1"
_INCREMENT: Final = "UPDATE skm_config.generation SET value = value + 1 WHERE id = 1 RETURNING value"


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})


def _cursor_values(after: str, digest: str) -> tuple[str, str]:
    values = decode_cursor(after, expected_query_digest=digest).sort_values
    if len(values) != 2 or not isinstance(values[0], str) or not isinstance(values[1], str):
        raise _bad_cursor()
    return values[0], values[1]


# ---------------------------------------------------------------------------------------------- rows
def _entry(row: _Row) -> ConfigEntry:
    try:
        return ConfigEntry(
            id=ConfigEntryId(cast("UUID", row[0])),
            scope=ScopeRef(ScopeKind(cast("str", row[2])), ScopeId(cast("UUID", row[1]))),
            key=cast("str", row[3]),
            op=EntryOp(cast("str", row[4])),
            value=loads_value(cast("str | None", row[5])),
            locked=cast("bool", row[6]),
            row_version=cast("int", row[7]),
            reason=cast("str", row[8]),
            created_by=PrincipalId(cast("UUID", row[9])),
            created_at=cast("datetime", row[10]),
            updated_by=PrincipalId(cast("UUID", row[11])),
            updated_at=cast("datetime", row[12]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged_row("entries", row[0], exc) from exc


def _op(value: object) -> EntryOp | None:
    return None if value is None else EntryOp(cast("str", value))


def _record(row: _Row) -> HistoryRecord:
    try:
        return HistoryRecord(
            id=cast("UUID", row[0]),
            entry_id=ConfigEntryId(cast("UUID", row[1])),
            scope_id=cast("UUID", row[2]),
            key=cast("str", row[3]),
            change_kind=ChangeKind(cast("str", row[4])),
            old_op=_op(row[5]),
            old_value=loads_value(cast("str | None", row[6])),
            old_locked=cast("bool | None", row[7]),
            new_op=_op(row[8]),
            new_value=loads_value(cast("str | None", row[9])),
            new_locked=cast("bool | None", row[10]),
            actor_id=PrincipalId(cast("UUID", row[11])),
            request_id=cast("str | None", row[12]),
            reason=cast("str", row[13]),
            generation=cast("int", row[14]),
            changed_at=cast("datetime", row[15]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged_row("entry_history", row[0], exc) from exc


def _lock_writers(conn: psycopg.Connection) -> None:
    """Take the writer lock of ``skm_config`` (the generation row) for the rest of the transaction."""
    if _run(lambda: conn.execute(_LOCK_WRITERS).fetchone()) is None:
        raise generation_row_missing()


# ---------------------------------------------------------------------------------------------- repositories
class PostgresConfigEntryRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------ reads
    def get(self, entry_id: ConfigEntryId) -> ConfigEntry:
        row = _run(lambda: self._conn.execute(_GET, (entry_id,)).fetchone())
        if row is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "config entry not found",
                details={"kind": "config_entry", "ref": str(entry_id)},
            )
        return _entry(row)

    def find(self, scope_id: UUID, key: str, *, for_update: bool = False) -> ConfigEntry | None:
        if for_update:
            _lock_writers(self._conn)
            statement = _FIND_LOCKED
        else:
            statement = _FIND
        row = _run(lambda: self._conn.execute(statement, (scope_id, key)).fetchone())
        return None if row is None else _entry(row)

    def entries_of_scope(self, scope_id: UUID, *, for_update: bool = False) -> Mapping[str, ConfigEntry]:
        if for_update:
            _lock_writers(self._conn)
            statement = _OF_SCOPE_LOCKED
        else:
            statement = _OF_SCOPE
        rows = _run(lambda: self._conn.execute(statement, (scope_id,)).fetchall())
        entries = (_entry(row) for row in rows)
        return {entry.key: entry for entry in entries}

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, ConfigEntry]]:
        wanted = list(dict.fromkeys(scope_ids))
        if not wanted:
            return {}
        found: dict[UUID, dict[str, ConfigEntry]] = {}
        for row in _run(lambda: self._conn.execute(_FOR_SCOPES, (wanted,)).fetchall()):
            entry = _entry(row)
            found.setdefault(entry.scope.id, {})[entry.key] = entry
        return found

    def _key_taken(self, entry: ConfigEntry) -> bool:
        params = (entry.scope.id, entry.key)
        return _run(lambda: self._conn.execute(_KEY_TAKEN, params).fetchone()) is not None

    def _version_at(self, entry: ConfigEntry) -> int:
        params = (entry.id, entry.scope.id, entry.key)
        row = _run(lambda: self._conn.execute(_VERSION_AT, params).fetchone())
        return 0 if row is None else cast("int", row[0])

    # ------------------------------------------------------------------ writes
    def add(self, entry: ConfigEntry) -> None:
        if self._key_taken(entry):
            raise _key_conflict(entry)
        if entry.row_version != 1:
            raise ValueError("a new entry starts at row_version 1")
        mark_pending(self._conn)
        params = (
            entry.id,
            entry.scope.id,
            entry.key,
            entry.op.value,
            jsonb_value(entry.value),
            entry.locked,
            entry.row_version,
            entry.reason,
            entry.created_by,
            entry.created_at,
            entry.updated_by,
            entry.updated_at,
        )
        if _run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            if self._key_taken(entry):  # a concurrent writer took the key
                raise _key_conflict(entry)
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a config entry with this id exists",
                details={"kind": "config_entry", "ref": str(entry.id)},
            )

    def save(self, entry: ConfigEntry, *, expected_version: int) -> None:
        if entry.row_version <= expected_version:  # a caller error, reported after a stale version (memory)
            actual = self._version_at(entry)
            if actual != expected_version:
                raise version_conflict(expected_version, actual)
            raise ValueError("a saved entry carries a row_version above the expected one")
        mark_pending(self._conn)
        params = (
            entry.op.value,
            jsonb_value(entry.value),
            entry.locked,
            entry.row_version,
            entry.reason,
            entry.updated_by,
            entry.updated_at,
            entry.id,
            entry.scope.id,
            entry.key,
            expected_version,
        )
        if _run(lambda: self._conn.execute(_UPDATE, params).fetchone()) is None:
            raise version_conflict(expected_version, self._version_at(entry))

    def remove(self, entry_id: ConfigEntryId, *, expected_version: int) -> None:
        mark_pending(self._conn)
        if _run(lambda: self._conn.execute(_DELETE, (entry_id, expected_version)).fetchone()) is None:
            row = _run(lambda: self._conn.execute(_VERSION_OF, (entry_id,)).fetchone())
            raise version_conflict(expected_version, 0 if row is None else cast("int", row[0]))

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
        limit = validate_page_limit(limit)
        kind = None if level is None else ScopeKind(level).value
        digest = query_digest(
            {
                "kind": "config_entries",
                "scope_id": None if scope_id is None else str(scope_id),
                "level": kind,
                "key_prefix": key_prefix,
            }
        )
        start_key: str | None = None
        start_scope: UUID | None = None
        if after is not None:
            start_key, scope_text = _cursor_values(after, digest)
            try:
                start_scope = UUID(scope_text)
            except ValueError as exc:
                raise _bad_cursor() from exc
        params = {
            "scope": scope_id,
            "level": kind,
            "prefix": key_prefix,
            "exclude_keys": sorted(exclude_keys),
            "key": start_key,
            "scope_after": start_scope,
            "limit": limit + 1,
        }
        rows = _run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_entry(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda entry: (entry.key, str(entry.scope.id)),
        )

    def count_shadowed_below(self, scope_id: UUID, key: str) -> int:
        row = _run(lambda: self._conn.execute(_SHADOWED, (scope_id, key)).fetchone())
        return 0 if row is None else cast("int", row[0])


def _key_conflict(entry: ConfigEntry) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS,
        "a config entry for this scope and key exists",
        details={"kind": "config_entry", "scope_id": str(entry.scope.id), "key": entry.key},
    )


class PostgresConfigHistoryRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def append(self, record: HistoryRecord) -> None:
        mark_pending(self._conn)
        params = (
            record.id,
            record.entry_id,
            record.scope_id,
            record.key,
            record.change_kind.value,
            None if record.old_op is None else record.old_op.value,
            jsonb_value(record.old_value),
            record.old_locked,
            None if record.new_op is None else record.new_op.value,
            jsonb_value(record.new_value),
            record.new_locked,
            record.actor_id,
            record.request_id,
            record.reason,
            record.generation,
            record.changed_at,
        )
        if _run(lambda: self._conn.execute(_APPEND, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a history record with this id exists",
                details={"kind": "config_history", "ref": str(record.id)},
            )

    def list(
        self,
        *,
        scope_id: UUID | None,
        key: str | None,
        after: str | None,
        limit: int,
        exclude_keys: frozenset[str] = frozenset(),
    ) -> Page[HistoryRecord]:
        limit = validate_page_limit(limit)
        digest = query_digest(
            {"kind": "config_history", "scope_id": None if scope_id is None else str(scope_id), "key": key}
        )
        start_at: datetime | None = None
        start_id: UUID | None = None
        if after is not None:
            at_text, id_text = _cursor_values(after, digest)
            try:
                start_at, start_id = datetime.fromisoformat(at_text), UUID(id_text)
            except ValueError as exc:
                raise _bad_cursor() from exc
            if start_at.utcoffset() is None:  # a naive time cannot be ordered against changed_at
                raise _bad_cursor()
        params = {
            "scope": scope_id,
            "key": key,
            "at": start_at,
            "id": start_id,
            "exclude_keys": sorted(exclude_keys),
            "limit": limit + 1,
        }
        rows = _run(lambda: self._conn.execute(_HISTORY, params).fetchall())
        return page_of(
            [_record(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda record: (record.changed_at.isoformat(), str(record.id)),
        )


class PostgresConfigGenerationCounter:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def current(self) -> int:
        row = _run(lambda: self._conn.execute(_CURRENT).fetchone())
        if row is None:
            raise generation_row_missing()
        return cast("int", row[0])

    def increment(self) -> int:
        """The new generation; the row stays locked until the transaction ends (serializes writers)."""
        mark_pending(self._conn)
        row = _run(lambda: self._conn.execute(_INCREMENT).fetchone())
        if row is None:
            raise generation_row_missing()
        return cast("int", row[0])
