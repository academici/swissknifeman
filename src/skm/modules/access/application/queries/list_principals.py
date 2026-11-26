"""``access.list_principals`` (access §8): keyset ``(created_at, id)``."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application.views import principal_summary
from skm.modules.access.generated.queries import ListPrincipals
from skm.modules.access.generated.views import ListPrincipalsView
from skm.modules.access.ports import PrincipalRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListPrincipals, _ctx: QueryContext, uow: UnitOfWork) -> ListPrincipalsView:
    page = uow.repo(PrincipalRepository).list(
        kind=None if query.kind is None else PrincipalKind(query.kind.value),
        after=query.after,
        limit=query.limit,
    )
    return ListPrincipalsView(items=tuple(principal_summary(p) for p in page.items), next=page.next)


SPEC = QuerySpec(
    name="access.list_principals",
    dto=ListPrincipals,
    result=ListPrincipalsView,
    permission="principal.manage",
    scope_of=None,
    handler=handle,
)
