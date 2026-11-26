"""``workspace.list_repositories`` (workspace §8): the repositories of a workspace; no checkout locators."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.views import repository_view
from skm.modules.workspace.generated.queries import ListRepositories
from skm.modules.workspace.generated.views import ListRepositoriesView
from skm.modules.workspace.ports import RepositoryRepository, WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListRepositories, ctx: QueryContext, uow: UnitOfWork) -> ListRepositoriesView:
    del ctx
    workspace = uow.repo(WorkspaceRepository).get(WorkspaceId(query.workspace_id))
    page = uow.repo(RepositoryRepository).list(
        workspace.id, id_prefix=query.id_prefix, after=query.after, limit=query.limit
    )
    return ListRepositoriesView(items=tuple(repository_view(item) for item in page.items), next=page.next)


SPEC = QuerySpec(
    name="workspace.list_repositories",
    dto=ListRepositories,
    result=ListRepositoriesView,
    permission="workspace.read",
    scope_of=lambda query: ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id)),
    handler=handle,
)
