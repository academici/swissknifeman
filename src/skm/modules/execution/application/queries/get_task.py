"""``execution.get_task`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import ScopeId, TaskId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.generated.queries import GetTask
from skm.modules.execution.generated.views import TaskView
from skm.modules.execution.ports import ExecutionQueries, TaskRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_scope(query: GetTask, uow: UnitOfWork) -> ScopeRef | None:
    try:
        task = uow.repo(TaskRepository).get(TaskId(query.task_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(task.run_id))


def handle(query: GetTask, _ctx: QueryContext, uow: UnitOfWork) -> TaskView:
    tid = TaskId(query.task_id)
    uow.repo(TaskRepository).get(tid)
    return TaskView.from_json(uow.repo(ExecutionQueries).task_view(tid))


SPEC = QuerySpec(
    name="execution.get_task",
    dto=GetTask,
    result=TaskView,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
