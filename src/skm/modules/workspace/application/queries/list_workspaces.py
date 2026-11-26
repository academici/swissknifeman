"""``workspace.list_workspaces`` (workspace §8): only the workspaces where the actor holds ``workspace.read``.

The bus checks the self right at the instance; each workspace is then decided on its own scope. A page may
hold fewer than ``limit`` items (the invisible ones are skipped) and still carry ``next``: follow ``next``
until it is ``None``.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.guards import SELF_PERMISSION, holds
from skm.modules.workspace.application.views import workspace_summary
from skm.modules.workspace.domain.workspace import WorkspaceState
from skm.modules.workspace.generated.queries import ListWorkspaces
from skm.modules.workspace.generated.views import ListWorkspacesView
from skm.modules.workspace.ports import WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListWorkspaces, ctx: QueryContext, uow: UnitOfWork) -> ListWorkspacesView:
    state = None if query.state is None else WorkspaceState(query.state)
    page = uow.repo(WorkspaceRepository).list(state=state, after=query.after, limit=query.limit)
    visible = (
        workspace
        for workspace in page.items
        if holds(uow, ctx.clock, ctx.actor, "workspace.read", workspace.id)
    )
    return ListWorkspacesView(items=tuple(workspace_summary(item) for item in visible), next=page.next)


SPEC = QuerySpec(
    name="workspace.list_workspaces",
    dto=ListWorkspaces,
    result=ListWorkspacesView,
    permission=SELF_PERMISSION,
    scope_of=None,
    handler=handle,
)
