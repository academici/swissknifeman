"""``workspace.list_workers`` (workspace §8)."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.views import worker_view
from skm.modules.workspace.domain.worker import WorkerState
from skm.modules.workspace.generated.queries import ListWorkers
from skm.modules.workspace.generated.views import ListWorkersView
from skm.modules.workspace.ports import WorkerRepository, WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListWorkers, ctx: QueryContext, uow: UnitOfWork) -> ListWorkersView:
    del ctx
    workspace = uow.repo(WorkspaceRepository).get(WorkspaceId(query.workspace_id))
    state = None if query.state is None else WorkerState(query.state)
    page = uow.repo(WorkerRepository).list(workspace.id, state=state, after=query.after, limit=query.limit)
    return ListWorkersView(items=tuple(worker_view(item) for item in page.items), next=page.next)


SPEC = QuerySpec(
    name="workspace.list_workers",
    dto=ListWorkers,
    result=ListWorkersView,
    permission="workspace.read",
    scope_of=lambda query: ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id)),
    handler=handle,
)
