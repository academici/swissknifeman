"""PostgreSQL ``WorkspaceRepository`` (workspace §6, §11): explicit SQL, mapping next to the queries.

``add`` runs ``ON CONFLICT DO NOTHING``: a taken id or slug is ``ALREADY_EXISTS`` and the transaction goes on.
``save`` locks the row, compares ``row_version`` and writes title and state only; the slug and the creation
time are kept (``ValueError``). Pages ascend by ``(slug, id)``, filtered by state.
"""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.pagination import page_of, query_digest
from skm.adapters.postgres.workspace.mapping import (
    Row,
    damaged,
    ensure_kept,
    keyset,
    not_found,
    run,
    text_key,
    version_conflict,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.domain.workspace import Workspace, WorkspaceState
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresWorkspaceRepository"]

_COLUMNS: Final = "SELECT id, slug, title, state, row_version, created_at FROM skm_workspace.workspaces "
_GET: Final = _COLUMNS + "WHERE id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_BY_SLUG: Final = _COLUMNS + "WHERE slug = %s"
_INSERT: Final = """
INSERT INTO skm_workspace.workspaces (id, slug, title, state, row_version, created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_workspace.workspaces
   SET title = %s, state = %s, row_version = %s, updated_at = greatest(updated_at, %s)
 WHERE id = %s AND row_version = %s
"""
_LIST: Final = (
    _COLUMNS
    + """
 WHERE (%(state)s::text IS NULL OR state = %(state)s::text)
   AND (%(at)s::text IS NULL OR (slug COLLATE "C", id) > (%(at)s::text COLLATE "C", %(id)s::uuid))
 ORDER BY slug COLLATE "C", id
 LIMIT %(limit)s
"""
)


def _workspace(row: Row) -> Workspace:
    try:
        return Workspace(
            id=WorkspaceId(cast("UUID", row[0])),
            slug=Slug(cast("str", row[1])),
            title=cast("str", row[2]),
            state=WorkspaceState(cast("str", row[3])),
            row_version=cast("int", row[4]),
            created_at=cast("datetime", row[5]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("workspaces", row[0], exc) from exc


class PostgresWorkspaceRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, workspace_id: WorkspaceId) -> Workspace:
        row = run(lambda: self._conn.execute(_GET, (workspace_id,)).fetchone())
        if row is None:
            raise not_found("workspace", workspace_id)
        return _workspace(row)

    def find_by_slug(self, slug: Slug) -> Workspace | None:
        row = run(lambda: self._conn.execute(_BY_SLUG, (slug.value,)).fetchone())
        return None if row is None else _workspace(row)

    def add(self, workspace: Workspace) -> None:
        params = (
            workspace.id,
            workspace.slug.value,
            workspace.title,
            WorkspaceState(workspace.state).value,
            workspace.row_version,
            workspace.created_at,
            workspace.created_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "workspace already exists",
                details={"kind": "workspace", "slug": workspace.slug.value},
            )

    def save(self, workspace: Workspace, *, expected_version: int) -> None:
        row = run(lambda: self._conn.execute(_LOCKED, (workspace.id,)).fetchone())
        if row is None:
            raise not_found("workspace", workspace.id)
        current = _workspace(row)
        if current.row_version != expected_version:
            raise version_conflict("workspace", expected_version, current.row_version)
        ensure_kept("workspace", current, workspace, ("slug", "created_at"))
        params = (
            workspace.title,
            WorkspaceState(workspace.state).value,
            workspace.row_version,
            self._clock.now(),
            workspace.id,
            expected_version,
        )
        run(lambda: self._conn.execute(_UPDATE, params))

    def list(self, *, state: WorkspaceState | None, after: str | None, limit: int) -> Page[Workspace]:
        limit = validate_page_limit(limit)
        state_value = None if state is None else WorkspaceState(state).value
        digest = query_digest({"kind": "workspace_workspaces", "state": state_value})
        at, start = keyset(after, digest, text_key)
        params = {"state": state_value, "at": at, "id": start, "limit": limit + 1}
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_workspace(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.slug.value, str(item.id)),
        )
