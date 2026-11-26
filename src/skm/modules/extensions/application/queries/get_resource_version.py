"""``extensions.get_resource_version`` (extensions §8): an immutable version, its bodies only on request."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ResourceVersionId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.extensions.application.resolving import resource_version_view
from skm.modules.extensions.generated.queries import GetResourceVersion
from skm.modules.extensions.generated.views import ResourceVersionView

__all__ = ["SPEC", "handle"]


def handle(query: GetResourceVersion, ctx: QueryContext, uow: UnitOfWork) -> ResourceVersionView:
    del ctx
    return resource_version_view(
        uow, ResourceVersionId(query.resource_version_id), include_bodies=query.include_bodies
    )


SPEC = QuerySpec(
    name="extensions.get_resource_version",
    dto=GetResourceVersion,
    result=ResourceVersionView,
    permission="ext.read",
    scope_of=None,
    handler=handle,
)
