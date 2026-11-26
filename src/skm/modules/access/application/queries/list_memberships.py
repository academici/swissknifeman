"""``access.list_memberships`` (access §8): a scope's members, or the memberships of one principal.

Own memberships are always readable. Others need the read right of the scope they ask about:
``workspace.read`` on a workspace, ``project.read`` below it, ``principal.manage`` on the instance and
for a bare principal.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.application import authz
from skm.modules.access.application.scopes import scope_by_id
from skm.modules.access.application.views import membership_view
from skm.modules.access.generated.queries import ListMemberships
from skm.modules.access.generated.views import ListMembershipsView
from skm.modules.access.ports import MembershipRepository, PrincipalRepository

__all__ = ["SPEC", "handle", "scope_of"]

_READ = {
    ScopeKind.WORKSPACE: "workspace.read",
    ScopeKind.PROJECT: "project.read",
    ScopeKind.PLAN: "project.read",
    ScopeKind.RUN: "project.read",
}


def scope_of(query: ListMemberships) -> ScopeRef | None:
    return scope_by_id(query.scope_id)


def handle(query: ListMemberships, ctx: QueryContext, uow: UnitOfWork) -> ListMembershipsView:
    actor = ctx.actor
    if query.scope_id is None and query.principal_id is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "scope_id or principal_id is required",
            details={"field": "scope_id", "reason": "scope_or_principal_required"},
        )
    own = query.principal_id is not None and PrincipalId(query.principal_id) == actor.principal_id
    if not own:
        if query.scope_id is not None:
            chain = authz.chain_of(uow, ScopeId(query.scope_id))
            authz.require(uow, actor, _READ.get(chain[-1].kind, "principal.manage"), chain)
        else:
            authz.require(uow, actor, "principal.manage", authz.chain_of(uow, None))
    page = uow.repo(MembershipRepository).list(
        scope_id=None if query.scope_id is None else ScopeId(query.scope_id),
        principal_id=None if query.principal_id is None else PrincipalId(query.principal_id),
        after=query.after,
        limit=query.limit,
    )
    scopes, principals = uow.repo(ScopeRegistry), uow.repo(PrincipalRepository)
    items = tuple(
        membership_view(m, scopes.get(m.scope_id).kind, principals.get(m.principal_id).display_name)
        for m in page.items
    )
    return ListMembershipsView(items=items, next=page.next)


SPEC = QuerySpec(
    name="access.list_memberships",
    dto=ListMemberships,
    result=ListMembershipsView,
    permission="token.own",  # self right at the bus; the read right of the scope is checked here
    scope_of=scope_of,
    handler=handle,
)
