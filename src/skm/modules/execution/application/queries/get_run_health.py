"""``execution.get_run_health`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.generated.queries import GetRunHealth
from skm.modules.execution.generated.views import RunHealth
from skm.modules.execution.ports import ExecutionQueries, RunRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: GetRunHealth, ctx: QueryContext, uow: UnitOfWork) -> RunHealth:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    return RunHealth.from_json(uow.repo(ExecutionQueries).run_health_view(run_id, now=ctx.clock.now()))


SPEC = QuerySpec(
    name="execution.get_run_health",
    dto=GetRunHealth,
    result=RunHealth,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
