"""``workspace.get_project`` (workspace §8): by id or by ``workspace_slug`` and ``project_slug``.

A slug names no scope the bus could check, so the handler decides ``project.read`` on the loaded project. A
caller without the right gets ``NOT_FOUND`` for slugs and ``FORBIDDEN`` for an id.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.guards import holds, require
from skm.modules.workspace.application.views import project_view
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.generated.queries import GetProject
from skm.modules.workspace.generated.views import ProjectView
from skm.modules.workspace.ports import (
    MountRepository,
    ProjectRepository,
    RepositoryRepository,
    WorkspaceRepository,
)

__all__ = ["SPEC", "handle"]

PERMISSION = "project.read"


def _not_found(ref: str) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, "project not found", details={"kind": "project", "ref": ref})


def handle(query: GetProject, ctx: QueryContext, uow: UnitOfWork) -> ProjectView:
    projects = uow.repo(ProjectRepository)
    if query.project_id is not None and query.workspace_slug is None and query.project_slug is None:
        project = projects.get(ProjectId(query.project_id))
        require(uow, ctx.clock, ctx.actor, PERMISSION, project.id)
    elif query.project_id is None and query.workspace_slug is not None and query.project_slug is not None:
        workspace = uow.repo(WorkspaceRepository).find_by_slug(Slug(query.workspace_slug))
        found = None if workspace is None else projects.find_by_slug(workspace.id, Slug(query.project_slug))
        if found is None or not holds(uow, ctx.clock, ctx.actor, PERMISSION, found.id):
            raise _not_found(f"{query.workspace_slug}/{query.project_slug}")
        project = found
    else:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "name either project_id or both workspace_slug and project_slug",
            details={"field": "project_id", "reason": "one_of"},
        )
    repositories = uow.repo(RepositoryRepository)
    mounts = tuple(
        (mount, repositories.get(mount.repository_id))
        for mount in uow.repo(MountRepository).for_project(project.id)
    )
    return project_view(project, mounts)


SPEC = QuerySpec(
    name="workspace.get_project",
    dto=GetProject,
    result=ProjectView,
    permission=None,  # the handler checks project.read on the resolved project
    scope_of=None,
    handler=handle,
)
