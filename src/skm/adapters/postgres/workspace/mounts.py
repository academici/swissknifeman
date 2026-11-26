"""PostgreSQL ``MountRepository`` (workspace §6, §11; DDL ``0007``): repositories mounted in projects.

``project_repositories`` carries the composite FKs ``(workspace_id, project_id)`` and ``(workspace_id,
repository_id)``: a repository of another workspace is never mounted (``INVALID_REFERENCE``). ``add`` first
locks the mounts of the project (``SELECT … FOR UPDATE``, workspace §11), then inserts ``ON CONFLICT DO
NOTHING``: a taken mount name (the primary key), a second primary mount
(``uq_project_repositories__one_primary``) or the repository mounted twice in the project is
``ALREADY_EXISTS`` and the transaction goes on. A concurrent attach of the same key waits for the other
transaction and then gets the same conflict.
"""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.workspace.mapping import Row, damaged, run
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount

__all__ = ["PostgresMountRepository"]

_COLUMNS: Final = (
    "SELECT workspace_id, project_id, repository_id, mount_name, role, attached_at "
    "FROM skm_workspace.project_repositories "
)
_OF_PROJECT: Final = _COLUMNS + 'WHERE project_id = %s ORDER BY attached_at, mount_name COLLATE "C"'
# Locked in mount order whatever the plan, so two writers of one project cannot deadlock each other.
_LOCK_PROJECT: Final = (
    "SELECT mount_name FROM skm_workspace.project_repositories WHERE project_id = %s "
    "ORDER BY mount_name FOR UPDATE"
)
_PROJECTS_OF: Final = (
    "SELECT DISTINCT project_id FROM skm_workspace.project_repositories "
    "WHERE repository_id = %s ORDER BY project_id"
)
_INSERT: Final = """
INSERT INTO skm_workspace.project_repositories
    (workspace_id, project_id, repository_id, mount_name, role, attached_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING mount_name
"""
_DELETE: Final = """
DELETE FROM skm_workspace.project_repositories WHERE project_id = %s AND mount_name = %s
RETURNING workspace_id, project_id, repository_id, mount_name, role, attached_at
"""


def _mount(row: Row) -> ProjectMount:
    try:
        return ProjectMount(
            workspace_id=WorkspaceId(cast("UUID", row[0])),
            project_id=ProjectId(cast("UUID", row[1])),
            repository_id=RepositoryId(cast("UUID", row[2])),
            mount_name=MountName(cast("str", row[3])),
            role=MountRole(cast("str", row[4])),
            attached_at=cast("datetime", row[5]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("project_repositories", f"{row[1]}/{row[3]}", exc) from exc


class PostgresMountRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        del (
            clock
        )  # the uniform factory signature of the workspace adapters; attached_at comes from the domain
        self._conn = conn

    def for_project(self, project_id: ProjectId) -> tuple[ProjectMount, ...]:
        rows = run(lambda: self._conn.execute(_OF_PROJECT, (project_id,)).fetchall())
        return tuple(_mount(row) for row in rows)

    def projects_of(self, repository_id: RepositoryId) -> tuple[ProjectId, ...]:
        rows = run(lambda: self._conn.execute(_PROJECTS_OF, (repository_id,)).fetchall())
        return tuple(ProjectId(cast("UUID", row[0])) for row in rows)

    def add(self, mount: ProjectMount) -> None:
        run(lambda: self._conn.execute(_LOCK_PROJECT, (mount.project_id,)))
        params = (
            mount.workspace_id,
            mount.project_id,
            mount.repository_id,
            mount.mount_name.value,
            MountRole(mount.role).value,
            mount.attached_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "the mount name or the primary mount is already used in the project",
                details={"kind": "mount", "mount_name": mount.mount_name.value},
            )

    def remove(self, project_id: ProjectId, mount_name: MountName) -> ProjectMount | None:
        row = run(lambda: self._conn.execute(_DELETE, (project_id, mount_name.value)).fetchone())
        return None if row is None else _mount(row)
