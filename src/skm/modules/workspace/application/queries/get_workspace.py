"""``workspace.get_workspace`` (workspace §8): by id or by slug.

A slug names no scope the bus could check, so the handler decides ``workspace.read`` on the loaded workspace.
A caller without the right gets ``NOT_FOUND`` for a slug (it must not learn which slugs exist) and
``FORBIDDEN`` for an id.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.guards import holds, require
from skm.modules.workspace.application.views import workspace_view
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.generated.queries import GetWorkspace
from skm.modules.workspace.generated.views import WorkspaceView
from skm.modules.workspace.ports import ProjectRepository, WorkspaceRepository

__all__ = ["SPEC", "handle"]

PERMISSION = "workspace.read"


def handle(query: GetWorkspace, ctx: QueryContext, uow: UnitOfWork) -> WorkspaceView:
    workspaces = uow.repo(WorkspaceRepository)
    if query.workspace_id is not None and query.slug is None:
        workspace = workspaces.get(WorkspaceId(query.workspace_id))
        require(uow, ctx.clock, ctx.actor, PERMISSION, workspace.id)
    elif query.slug is not None and query.workspace_id is None:
        found = workspaces.find_by_slug(Slug(query.slug))
        if found is None or not holds(uow, ctx.clock, ctx.actor, PERMISSION, found.id):
            raise NotFound(
                ErrorCode.NOT_FOUND, "workspace not found", details={"kind": "workspace", "ref": query.slug}
            )
        workspace = found
    else:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "name exactly one of workspace_id and slug",
            details={"field": "workspace_id", "reason": "one_of"},
        )
    return workspace_view(workspace, uow.repo(ProjectRepository).count(workspace.id))


SPEC = QuerySpec(
    name="workspace.get_workspace",
    dto=GetWorkspace,
    result=WorkspaceView,
    permission=None,  # The handler requires workspace.read on the resolved workspace.
    scope_of=None,
    handler=handle,
)
