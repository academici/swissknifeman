"""``workspace.list_projects`` (workspace §8)."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.views import project_summary
from skm.modules.workspace.domain.project import ProjectState
from skm.modules.workspace.generated.queries import ListProjects
from skm.modules.workspace.generated.views import ListProjectsView
from skm.modules.workspace.ports import ProjectRepository, WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListProjects, ctx: QueryContext, uow: UnitOfWork) -> ListProjectsView:
    del ctx
    workspace = uow.repo(WorkspaceRepository).get(WorkspaceId(query.workspace_id))
    state = None if query.state is None else ProjectState(query.state)
    page = uow.repo(ProjectRepository).list(workspace.id, state=state, after=query.after, limit=query.limit)
    return ListProjectsView(items=tuple(project_summary(item) for item in page.items), next=page.next)


SPEC = QuerySpec(
    name="workspace.list_projects",
    dto=ListProjects,
    result=ListProjectsView,
    permission="workspace.read",
    scope_of=lambda query: ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id)),
    handler=handle,
)
