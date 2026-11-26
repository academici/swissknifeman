"""PostgreSQL queue and immutable per-vault receipts."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import EventId, HostId, ProjectId, WorkspaceId
from skm.modules.exports.domain.note import (
    NoteKind,
    VaultNote,
    VaultNoteId,
    VaultNoteWrite,
    check_existing_write,
    check_generation,
    check_write,
    validate_relative_path,
)
from skm.modules.exports.ports import PENDING_SCAN_LIMIT, CandidatePage, NoteKey, candidate_page

from .mapping import note_from_row, write_from_row

__all__ = ["PostgresVaultNoteRepository"]

_ADD = """
INSERT INTO skm_exports.vault_notes (
    id, workspace_id, project_id, kind, event_id, source_id, name, subfolder, body,
    body_digest, generation, state, created_at, requeued_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (event_id, kind) DO NOTHING RETURNING id
"""
_GET = "SELECT * FROM skm_exports.vault_notes WHERE id = %s"
_LOCK = "SELECT * FROM skm_exports.vault_notes WHERE id = %s FOR UPDATE"
_BY_EVENT = "SELECT * FROM skm_exports.vault_notes WHERE event_id = %s AND kind = %s"
_CHECKOUT = """
SELECT p.id FROM skm_workspace.checkout_bindings AS b
JOIN skm_workspace.hosts AS h ON h.id = b.host_id AND h.state = 'active'
JOIN skm_workspace.workspaces AS w ON w.id = b.workspace_id AND w.state = 'active'
JOIN skm_workspace.project_repositories AS m
    ON m.workspace_id = b.workspace_id AND m.repository_id = b.repository_id
JOIN skm_workspace.projects AS p
    ON p.workspace_id = m.workspace_id AND p.id = m.project_id AND p.state = 'active'
WHERE b.workspace_id = %(workspace)s AND b.host_id = %(host)s AND b.state = 'active'
"""
_ACTIVE_CHECKOUT = _CHECKOUT + " AND (%(project)s::uuid IS NULL OR p.id = %(project)s) LIMIT 1"
_PENDING = """
WITH eligible_projects AS (
    SELECT p.id FROM skm_workspace.checkout_bindings AS b
    JOIN skm_workspace.hosts AS h ON h.id = b.host_id AND h.state = 'active'
    JOIN skm_workspace.workspaces AS w ON w.id = b.workspace_id AND w.state = 'active'
    JOIN skm_workspace.project_repositories AS m
        ON m.workspace_id = b.workspace_id AND m.repository_id = b.repository_id
    JOIN skm_workspace.projects AS p
        ON p.workspace_id = m.workspace_id AND p.id = m.project_id AND p.state = 'active'
    WHERE b.workspace_id = %(workspace)s AND b.host_id = %(host)s AND b.state = 'active'
), candidate_keys AS MATERIALIZED (
    SELECT n.created_at, n.id FROM skm_exports.vault_notes AS n
    WHERE n.workspace_id = %(workspace)s AND n.state = 'pending'
        AND COALESCE(n.requeued_at, n.created_at) > %(cutoff)s
        AND (%(at)s::timestamptz IS NULL OR (n.created_at, n.id) > (%(at)s, %(id)s))
        AND n.project_id IN (SELECT id FROM eligible_projects)
        AND NOT EXISTS (
            SELECT 1 FROM skm_exports.vault_note_writes AS r
            WHERE r.note_id = n.id AND r.vault_id = %(vault)s AND r.generation = n.generation
        )
    ORDER BY n.created_at, n.id LIMIT (%(limit)s + 1)
), page_keys AS (
    SELECT created_at, id FROM candidate_keys ORDER BY created_at, id LIMIT %(limit)s
)
SELECT n.*, EXISTS (SELECT 1 FROM candidate_keys OFFSET %(limit)s) AS has_more
FROM page_keys AS page JOIN skm_exports.vault_notes AS n ON n.id = page.id
ORDER BY page.created_at, page.id
"""
_LIST = """
SELECT * FROM skm_exports.vault_notes
WHERE project_id = %(project)s
    AND (%(at)s::timestamptz IS NULL OR (created_at, id) > (%(at)s, %(id)s))
ORDER BY created_at, id LIMIT %(limit)s
"""
_WRITE = """
INSERT INTO skm_exports.vault_note_writes (
    note_id, vault_id, generation, host_id, relative_path, outcome,
    expected_digest, observed_digest, written_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""
_GET_WRITE = (
    "SELECT * FROM skm_exports.vault_note_writes WHERE note_id = %s AND vault_id = %s AND generation = %s"
)
_WRITES = "SELECT * FROM skm_exports.vault_note_writes WHERE note_id = %s ORDER BY generation, vault_id"
_REQUEUE = """
UPDATE skm_exports.vault_notes SET state = 'pending', generation = generation + 1, requeued_at = %s
WHERE id = %s AND generation = %s RETURNING generation
"""
_EXPIRE = """
WITH due AS (
    SELECT id FROM skm_exports.vault_notes
    WHERE state = 'pending' AND COALESCE(requeued_at, created_at) <= %(cutoff)s
    ORDER BY COALESCE(requeued_at, created_at), id LIMIT %(limit)s FOR UPDATE SKIP LOCKED
)
UPDATE skm_exports.vault_notes AS n SET state = 'expired'
FROM due WHERE n.id = due.id AND n.state = 'pending' AND COALESCE(n.requeued_at, n.created_at) <= %(cutoff)s
RETURNING n.id
"""
_PURGE = """
WITH due AS (
    SELECT id FROM skm_exports.vault_notes
    WHERE COALESCE(requeued_at, created_at) <= %(cutoff)s
    ORDER BY COALESCE(requeued_at, created_at), id LIMIT %(limit)s FOR UPDATE SKIP LOCKED
)
DELETE FROM skm_exports.vault_notes AS n USING due
WHERE n.id = due.id AND COALESCE(n.requeued_at, n.created_at) <= %(cutoff)s
RETURNING n.id
"""


class PostgresVaultNoteRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def _run(
        self,
        operation: Callable[[psycopg.Cursor[dict[str, Any]]], psycopg.Cursor[dict[str, Any]]],
        *,
        fetch: bool = True,
    ) -> list[dict[str, Any]]:
        try:
            with self._conn.cursor(row_factory=dict_row) as cursor:
                operation(cursor)
                return cursor.fetchall() if fetch else []
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    def by_event(self, event_id: EventId, kind: NoteKind) -> VaultNote | None:
        rows = self._run(lambda c: c.execute(_BY_EVENT, (event_id, kind.value)))
        return note_from_row(rows[0]) if rows else None

    def add(self, note: VaultNote) -> bool:
        return bool(
            self._run(
                lambda c: c.execute(
                    _ADD,
                    (
                        note.id,
                        note.workspace_id,
                        note.project_id,
                        note.kind.value,
                        note.event_id,
                        note.source_id,
                        note.name,
                        note.subfolder,
                        note.body,
                        note.body_digest,
                        note.generation,
                        note.state.value,
                        note.created_at,
                        note.requeued_at,
                    ),
                )
            )
        )

    def get(self, note_id: VaultNoteId, *, for_update: bool = False) -> VaultNote:
        if for_update:
            rows = self._run(lambda c: c.execute(_LOCK, (note_id,)))
        else:
            rows = self._run(lambda c: c.execute(_GET, (note_id,)))
        if not rows:
            raise NotFound(ErrorCode.NOT_FOUND, "Vault note not found")
        return note_from_row(rows[0])

    def active_checkout(
        self, workspace_id: WorkspaceId, host_id: HostId, project_id: ProjectId | None = None
    ) -> bool:
        return bool(
            self._run(
                lambda c: c.execute(
                    _ACTIVE_CHECKOUT,
                    {"workspace": workspace_id, "host": host_id, "project": project_id},
                )
            )
        )

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
    ) -> CandidatePage:
        at, identifier = after or (None, None)
        rows = self._run(
            lambda c: c.execute(
                _PENDING,
                {
                    "workspace": workspace_id,
                    "host": host_id,
                    "vault": vault_id,
                    "cutoff": now - timedelta(days=ttl_days),
                    "at": at,
                    "id": identifier,
                    "limit": min(scan_limit, PENDING_SCAN_LIMIT),
                },
            )
        )
        return CandidatePage(tuple(map(note_from_row, rows)), bool(rows and rows[0]["has_more"]))

    def list(self, project_id: ProjectId, *, after: NoteKey | None, limit: int) -> CandidatePage:
        at, identifier = after or (None, None)
        rows = self._run(
            lambda c: c.execute(
                _LIST,
                {"project": project_id, "at": at, "id": identifier, "limit": limit + 1},
            )
        )
        return candidate_page([note_from_row(row) for row in rows], limit)

    def add_write(self, w: VaultNoteWrite, *, now: datetime, ttl_days: int) -> bool:
        note = self.get(w.note_id, for_update=True)
        validate_relative_path(w.relative_path)
        check_write(note, w, now=now, ttl_days=ttl_days)
        rows = self._run(lambda c: c.execute(_GET_WRITE, (w.note_id, w.vault_id, w.generation)))
        if rows:
            check_existing_write(write_from_row(rows[0]), w)
            return False
        self._run(
            lambda c: c.execute(
                _WRITE,
                (
                    w.note_id,
                    w.vault_id,
                    w.generation,
                    w.host_id,
                    w.relative_path,
                    w.outcome,
                    w.expected_digest,
                    w.observed_digest,
                    w.written_at,
                ),
            ),
            fetch=False,
        )
        return True

    def writes(self, note_id: VaultNoteId) -> tuple[VaultNoteWrite, ...]:
        return tuple(map(write_from_row, self._run(lambda c: c.execute(_WRITES, (note_id,)))))

    def requeue(self, note_id: VaultNoteId, expected_generation: int, at: datetime) -> int:
        note = self.get(note_id, for_update=True)
        check_generation(note, expected_generation)
        self._run(lambda c: c.execute(_REQUEUE, (at, note_id, expected_generation)))
        return note.generation + 1

    def expire_due(self, now: datetime, ttl_days: int, *, limit: int) -> int:
        cutoff = now - timedelta(days=ttl_days)
        return len(self._run(lambda c: c.execute(_EXPIRE, {"cutoff": cutoff, "limit": limit})))

    def delete_older_than(self, cutoff: datetime, *, limit: int) -> int:
        return len(self._run(lambda c: c.execute(_PURGE, {"cutoff": cutoff, "limit": limit})))
