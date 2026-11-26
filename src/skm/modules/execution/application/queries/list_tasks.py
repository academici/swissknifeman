"""``execution.list_tasks`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.domain.task import TaskKind, TaskStatus
from skm.modules.execution.generated.queries import ListTasks
from skm.modules.execution.generated.views import TasksView
from skm.modules.execution.ports import ExecutionQueries, RunRepository, TaskRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: ListTasks, _ctx: QueryContext, uow: UnitOfWork) -> TasksView:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    try:
        st_filter = {TaskStatus(s).value for s in query.statuses} if query.statuses else None
        kd_filter = {TaskKind(k).value for k in query.kinds} if query.kinds else None
    except ValueError:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid task filter") from None
    raw_tasks = uow.repo(ExecutionQueries).task_views(run_id)
    filtered = [
        t
        for t in raw_tasks
        if (st_filter is None or t.get("status") in st_filter)
        and (kd_filter is None or t.get("kind") in kd_filter)
    ]
    kept_ids = {str(t["task_id"]) for t in filtered}
    edges = [
        {
            "prerequisite_task_id": str(e.prerequisite_task_id),
            "dependent_task_id": str(e.dependent_task_id),
            "kind": e.kind.value,
        }
        for e in uow.repo(TaskRepository).edges_for_run(run_id)
        if (st_filter is None and kd_filter is None)
        or (str(e.prerequisite_task_id) in kept_ids and str(e.dependent_task_id) in kept_ids)
    ]
    return TasksView.from_json({"tasks": filtered, "edges": edges})


SPEC = QuerySpec(
    name="execution.list_tasks",
    dto=ListTasks,
    result=TasksView,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
