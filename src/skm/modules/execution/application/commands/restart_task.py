"""Abandon the current attempt without erasing spend, history, or integration host pins."""

from dataclasses import replace
from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import (
    close_attempt,
    lock_task,
    require_permission,
    task_scope,
)
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application.commands.reconfigure_run import handle as reconfigure
from skm.modules.execution.domain.attempt import AttemptEndReason
from skm.modules.execution.domain.run import TERMINAL_RUN_STATUSES, RunStatus
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, TaskStatus
from skm.modules.execution.generated.commands import ReconfigureRun, RestartTask
from skm.modules.execution.generated.results import RestartTaskResult
from skm.modules.execution.ports import IntegrationSlotRepository, RunRepository


def restart_allowed(run_status: RunStatus, task_status: TaskStatus) -> bool:
    return run_status not in TERMINAL_RUN_STATUSES and (
        task_status is TaskStatus.FAILED or task_status not in TERMINAL_TASK_STATUSES
    )


def handle(cmd: RestartTask, ctx: Any, uow: UnitOfWork) -> RestartTaskResult:
    run, task, attempt = lock_task(uow, cmd.task_id)
    if not restart_allowed(run.status, task.status):
        raise error_for(ErrorCode.INVALID_TRANSITION, "this terminal task cannot restart")
    _, values = effective_values(uow, run.id)
    limit = values.get("budgets.task.max_attempts", 3)
    if cmd.raise_attempts_limit:
        require_permission(uow, ctx, run, "deviation.accept", human=True)
    if limit and task.attempt_count >= limit and not cmd.raise_attempts_limit:
        raise error_for(ErrorCode.BUDGET_EXHAUSTED, "attempt limit reached")
    if attempt is not None:
        close_attempt(uow, ctx, run, attempt, code="TASK_RESTARTED", reason=AttemptEndReason.RESTARTED)
    if limit and task.attempt_count >= limit:
        latest = uow.repo(RunRepository).get(run.id)
        reconfigure(
            ReconfigureRun(
                run.id, latest.row_version, {"budgets.task.max_attempts": task.attempt_count + 1}, cmd.reason
            ),
            ctx,
            uow,
        )
    hosts = uow.repo(IntegrationSlotRepository).hosts_for_run(run.id)
    ready = replace(
        task,
        status=TaskStatus.READY,
        current_attempt_id=None,
        blocking_reason=None,
        required_host_id=next(iter(hosts.values()), None),
        row_version=task.row_version + 1,
    )
    why = cause("restart")
    save_task(uow, run, task, ready, why, ctx.clock.now())
    emit(uow, run, "task-ready", {"task_id": str(task.id), "reason": cmd.reason}, why)
    return RestartTaskResult(task.id, ready.status.value)


SPEC = CommandSpec(
    name="execution.restart_task",
    dto=RestartTask,
    result=RestartTaskResult,
    permission="run.control",
    scope_of=None,
    scope_resolver=task_scope,
    handler=handle,
)
