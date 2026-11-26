"""``execution.get_run_timeline`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application.queries import MAX_TIMELINE_LIMIT, check_limit
from skm.modules.execution.generated.queries import GetRunTimeline
from skm.modules.execution.generated.views import RunTimelineView
from skm.modules.execution.ports import ExecutionQueries, RunRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: GetRunTimeline, _ctx: QueryContext, uow: UnitOfWork) -> RunTimelineView:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    limit = check_limit(query.limit, default=100, maximum=MAX_TIMELINE_LIMIT)
    if query.after_seq is not None and (isinstance(query.after_seq, bool) or query.after_seq < 0):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "after_seq must be >= 0", details={"field": "after_seq"}
        )
    return RunTimelineView.from_json(uow.repo(ExecutionQueries).timeline(run_id, query.after_seq, limit))


SPEC = QuerySpec(
    name="execution.get_run_timeline",
    dto=GetRunTimeline,
    result=RunTimelineView,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
