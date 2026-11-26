"""``workspace.resolve_checkout`` (workspace §8): where a mount of a project lies on a host."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import HostId, ProjectId, ScopeId
from skm.kernel.ports_uow import Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.guards import stale_after_days
from skm.modules.workspace.application.locations import resolve_location
from skm.modules.workspace.domain.checkout_binding import checkout_id_from_locator
from skm.modules.workspace.generated.queries import ResolveCheckout
from skm.modules.workspace.generated.views import CheckoutLocationView

__all__ = ["SPEC", "handle"]


def handle(query: ResolveCheckout, ctx: QueryContext, uow: UnitOfWork) -> CheckoutLocationView:
    result = resolve_location(
        uow,
        ProjectId(query.project_id),
        query.mount_name,
        HostId(query.host_id),
        now=ctx.clock.now(),
        stale_days=stale_after_days(ctx),
    )
    if ctx.meta.surface is Surface.API and checkout_id_from_locator(result.local_locator) is None:
        raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "Checkout requires a machine binding")
    return result


SPEC = QuerySpec(
    name="workspace.resolve_checkout",
    dto=ResolveCheckout,
    result=CheckoutLocationView,
    permission="checkout.read_locator",
    scope_of=lambda query: ScopeRef(ScopeKind.PROJECT, ScopeId(query.project_id)),
    handler=handle,
)
