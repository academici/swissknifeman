"""``settings.get_generation`` (settings §A.8): the instance-wide generation counter, without resolving keys.

A cheap freshness check for host caches; ``scope`` (default instance) only selects where ``config.read`` is
checked.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.generated.queries import GetGeneration
from skm.modules.settings.generated.results import GetGenerationResult
from skm.modules.settings.ports import ConfigGenerationCounter

__all__ = ["SPEC", "handle"]


def handle(query: GetGeneration, ctx: QueryContext, uow: UnitOfWork) -> GetGenerationResult:  # noqa: ARG001
    return GetGenerationResult(generation=uow.repo(ConfigGenerationCounter).current())


SPEC = QuerySpec(
    name="settings.get_generation",
    dto=GetGeneration,
    result=GetGenerationResult,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
