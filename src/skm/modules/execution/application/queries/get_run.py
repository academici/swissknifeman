"""``execution.get_run`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.generated.queries import GetRun
from skm.modules.execution.generated.views import RunView
from skm.modules.execution.ports import ExecutionQueries, RunRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_scope(query: GetRun, uow: UnitOfWork) -> ScopeRef | None:
    try:
        run = uow.repo(RunRepository).get(RunId(query.run_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(run.id))


def handle(query: GetRun, ctx: QueryContext, uow: UnitOfWork) -> RunView:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    queries = uow.repo(ExecutionQueries)
    view = dict(queries.run_view(run_id))
    view["health"] = queries.run_health_view(run_id, now=ctx.clock.now())
    return RunView.from_json(view)


SPEC = QuerySpec(
    name="execution.get_run",
    dto=GetRun,
    result=RunView,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
