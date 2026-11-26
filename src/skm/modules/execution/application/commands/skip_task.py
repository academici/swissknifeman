"""Explicitly skip a pending task and open only its now-satisfied dependents."""

from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._action_effects import finish_run
from skm.modules.execution.application._control import close_attempt, lock_task, task_scope
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.application.apply_action import release_dependents
from skm.modules.execution.domain.attempt import AttemptEndReason
from skm.modules.execution.domain.task import TaskStatus, transition
from skm.modules.execution.generated.commands import SkipTask
from skm.modules.execution.generated.results import SkipTaskResult
from skm.modules.execution.ports import RunRepository


def handle(cmd: SkipTask, ctx: Any, uow: UnitOfWork) -> SkipTaskResult:
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import error_for

    run, task, attempt = lock_task(uow, cmd.task_id)
    if not cmd.reason.strip():
        raise error_for(ErrorCode.SCHEMA_INVALID, "skip requires a reason")
    updated = transition(task, TaskStatus.SKIPPED, rule="T25")
    if attempt is not None:
        close_attempt(uow, ctx, run, attempt, code="TASK_SKIPPED", reason=AttemptEndReason.SKIPPED)
    why = cause("skip")
    save_task(uow, run, task, updated, why, ctx.clock.now())
    emit(
        uow,
        run,
        "task-skipped",
        {"task_id": str(task.id), "reason": cmd.reason, "by": str(ctx.actor.principal_id)},
        why,
    )
    release_dependents(uow, ctx, run, why)

    finish_run(uow, ctx, uow.repo(RunRepository).get(run.id), why)
    return SkipTaskResult(task.id, updated.status.value)


SPEC = CommandSpec(
    name="execution.skip_task",
    dto=SkipTask,
    result=SkipTaskResult,
    permission="run.control",
    scope_of=None,
    scope_resolver=task_scope,
    handler=handle,
)
