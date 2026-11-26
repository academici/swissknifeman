"""PostgreSQL ``ProjectRepository`` (workspace §6, §11; golden slice): SQL with its mapping next to it.

``(workspace_id, slug)`` is unique and ``(workspace_id, id)`` is the target of the composite FKs of mounts.
``add`` runs ``ON CONFLICT DO NOTHING``; ``save`` locks the row, compares ``row_version`` and writes title,
description and state only: a project never moves to another workspace and keeps its slug (``ValueError``).
Pages ascend by ``(slug, id)`` and are filtered in SQL by workspace and state.
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
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.workspace.domain.project import Project, ProjectState
from skm.modules.workspace.domain.slug import Slug
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresProjectRepository"]

_COLUMNS: Final = (
    "SELECT id, workspace_id, slug, title, description, state, row_version, created_at "
    "FROM skm_workspace.projects "
)
_GET: Final = _COLUMNS + "WHERE id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_BY_SLUG: Final = _COLUMNS + "WHERE workspace_id = %s AND slug = %s"
_INSERT: Final = """
INSERT INTO skm_workspace.projects
    (id, workspace_id, slug, title, description, state, row_version, created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_workspace.projects
   SET title = %s, description = %s, state = %s, row_version = %s, updated_at = greatest(updated_at, %s)
 WHERE id = %s AND row_version = %s
"""
_LIST: Final = (
    _COLUMNS
    + """
 WHERE workspace_id = %(workspace)s
   AND (%(state)s::text IS NULL OR state = %(state)s::text)
   AND (%(at)s::text IS NULL OR (slug COLLATE "C", id) > (%(at)s::text COLLATE "C", %(id)s::uuid))
 ORDER BY slug COLLATE "C", id
 LIMIT %(limit)s
"""
)
_COUNT: Final = "SELECT count(*) FROM skm_workspace.projects WHERE workspace_id = %s"


def _project(row: Row) -> Project:
    try:
        return Project(
            id=ProjectId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            slug=Slug(cast("str", row[2])),
            title=cast("str", row[3]),
            description=cast("str", row[4]),
            state=ProjectState(cast("str", row[5])),
            row_version=cast("int", row[6]),
            created_at=cast("datetime", row[7]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("projects", row[0], exc) from exc


class PostgresProjectRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, project_id: ProjectId) -> Project:
        row = run(lambda: self._conn.execute(_GET, (project_id,)).fetchone())
        if row is None:
            raise not_found("project", project_id)
        return _project(row)

    def find_by_slug(self, workspace_id: WorkspaceId, slug: Slug) -> Project | None:
        row = run(lambda: self._conn.execute(_BY_SLUG, (workspace_id, slug.value)).fetchone())
        return None if row is None else _project(row)

    def add(self, project: Project) -> None:
        params = (
            project.id,
            project.workspace_id,
            project.slug.value,
            project.title,
            project.description,
            ProjectState(project.state).value,
            project.row_version,
            project.created_at,
            project.created_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "project already exists",
                details={"kind": "project", "slug": project.slug.value},
            )

    def save(self, project: Project, *, expected_version: int) -> None:
        row = run(lambda: self._conn.execute(_LOCKED, (project.id,)).fetchone())
        if row is None:
            raise not_found("project", project.id)
        current = _project(row)
        if current.row_version != expected_version:
            raise version_conflict("project", expected_version, current.row_version)
        ensure_kept("project", current, project, ("workspace_id", "slug", "created_at"))
        params = (
            project.title,
            project.description,
            ProjectState(project.state).value,
            project.row_version,
            self._clock.now(),
            project.id,
            expected_version,
        )
        run(lambda: self._conn.execute(_UPDATE, params))

    def list(
        self, workspace_id: WorkspaceId, *, state: ProjectState | None, after: str | None, limit: int
    ) -> Page[Project]:
        limit = validate_page_limit(limit)
        state_value = None if state is None else ProjectState(state).value
        digest = query_digest(
            {"kind": "workspace_projects", "workspace_id": str(workspace_id), "state": state_value}
        )
        at, start = keyset(after, digest, text_key)
        params = {"workspace": workspace_id, "state": state_value, "at": at, "id": start, "limit": limit + 1}
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_project(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.slug.value, str(item.id)),
        )

    def count(self, workspace_id: WorkspaceId) -> int:
        row = run(lambda: self._conn.execute(_COUNT, (workspace_id,)).fetchone())
        return 0 if row is None else cast("int", row[0])
