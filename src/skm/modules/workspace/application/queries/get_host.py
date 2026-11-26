"""``workspace.get_host`` (workspace §8, §18 K17): by id or by name.

With ``host_id`` the scope is the host (a worker reads the host it runs on, a person with any workspace
membership reads any host: ``access`` §4.4 rows 6a/6b); otherwise the workspace the caller names, otherwise
the instance.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import HostId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.guards import scope_ref
from skm.modules.workspace.application.views import host_view
from skm.modules.workspace.generated.queries import GetHost
from skm.modules.workspace.generated.views import HostView
from skm.modules.workspace.ports import HostRepository

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: GetHost) -> ScopeRef | None:
    if query.host_id is not None:
        return scope_ref(ScopeKind.HOST, query.host_id)
    return scope_ref(ScopeKind.WORKSPACE, query.workspace_id)


def handle(query: GetHost, ctx: QueryContext, uow: UnitOfWork) -> HostView:
    del ctx
    hosts = uow.repo(HostRepository)
    if query.host_id is not None and query.name is None:
        return host_view(hosts.get(HostId(query.host_id)))
    if query.name is not None and query.host_id is None:
        found = hosts.find_by_name(query.name)
        if found is None:
            raise NotFound(ErrorCode.NOT_FOUND, "host not found", details={"kind": "host", "ref": query.name})
        return host_view(found)
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "name exactly one of host_id and name",
        details={"field": "host_id", "reason": "one_of"},
    )


SPEC = QuerySpec(
    name="workspace.get_host",
    dto=GetHost,
    result=HostView,
    permission="workspace.read",
    scope_of=scope_of,
    handler=handle,
)
