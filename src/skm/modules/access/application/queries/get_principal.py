"""``access.get_principal`` (access §8): the actor itself, or any principal with ``principal.manage``."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application import authz
from skm.modules.access.generated.queries import GetPrincipal
from skm.modules.access.generated.views import GetPrincipalView, GetPrincipalViewIdentitiesItem
from skm.modules.access.generated.views import PrincipalKind as ViewKind
from skm.modules.access.ports import IdentityRepository, PrincipalRepository

__all__ = ["SPEC", "handle"]


def handle(query: GetPrincipal, ctx: QueryContext, uow: UnitOfWork) -> GetPrincipalView:
    actor = ctx.actor
    target = PrincipalId(query.principal_id)
    if target != actor.principal_id:
        authz.require(uow, actor, "principal.manage", authz.chain_of(uow, None))
    principal = uow.repo(PrincipalRepository).get(target)
    identities = uow.repo(IdentityRepository).for_principal(principal.id)
    return GetPrincipalView(
        principal_id=principal.id,
        kind=ViewKind(principal.kind.value),
        display_name=principal.display_name,
        state=principal.state.value,
        created_at=principal.created_at,
        row_version=principal.row_version,
        identities=tuple(
            GetPrincipalViewIdentitiesItem(issuer=i.issuer, subject=i.subject) for i in identities
        ),
    )


SPEC = QuerySpec(
    name="access.get_principal",
    dto=GetPrincipal,
    result=GetPrincipalView,
    permission="token.own",  # self right at the bus; another principal needs principal.manage here
    scope_of=None,
    handler=handle,
)
