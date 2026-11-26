"""``workspace.list_hosts`` (workspace §8, §18 K17): the hosts of the instance, no locators.

The scope is the workspace the caller names (``workspace_id``) or the instance: a member of only that
workspace lists the hosts through it; without ``workspace_id`` the caller needs a membership of the instance.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.pagination import Page
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind
from skm.modules.workspace.application.guards import scope_ref
from skm.modules.workspace.application.views import host_view
from skm.modules.workspace.domain.host import Host, HostState
from skm.modules.workspace.generated.queries import ListHosts
from skm.modules.workspace.generated.views import ListHostsView
from skm.modules.workspace.ports import HostRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListHosts, ctx: QueryContext, uow: UnitOfWork) -> ListHostsView:
    del ctx
    hosts = uow.repo(HostRepository)
    if query.name is not None:  # a name is unique: at most one host, and no page after it
        found = hosts.find_by_name(query.name)
        wanted = None if query.state is None else HostState(query.state)
        listed: tuple[Host, ...] = () if found is None or (wanted and found.state is not wanted) else (found,)
        return ListHostsView(items=tuple(host_view(item) for item in listed), next=None)
    state = None if query.state is None else HostState(query.state)
    page: Page[Host] = hosts.list(state=state, after=query.after, limit=query.limit)
    return ListHostsView(items=tuple(host_view(item) for item in page.items), next=page.next)


SPEC = QuerySpec(
    name="workspace.list_hosts",
    dto=ListHosts,
    result=ListHostsView,
    permission="workspace.read",
    scope_of=lambda query: scope_ref(ScopeKind.WORKSPACE, query.workspace_id),
    handler=handle,
)
