"""Owner pause preserves selected stages and releases only available assignments."""

from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import (
    assignments_for_run,
    lock_run,
    revoke_assignment,
    run_scope,
)
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.run import pause
from skm.modules.execution.domain.task import TaskStatus, transition
from skm.modules.execution.generated.commands import PauseRun
from skm.modules.execution.generated.results import PauseRunResult
from skm.modules.execution.ports import AttemptRepository, RunRepository, StageRepository, TaskRepository


def handle(cmd: PauseRun, ctx: Any, uow: UnitOfWork) -> PauseRunResult:
    run = lock_run(uow, cmd.run_id, cmd.expected_row_version)
    system = ctx.actor.principal_id == SYSTEM_PRINCIPAL_ID
    stop_code = (
        ErrorCode.PLAN_ARCHIVED.value
        if system and cmd.reason == "plan archived"
        else "ITEM_BLOCKED"
        if system
        else None
    )
    coordinator = run.autopilot and ctx.actor.kind is not PrincipalKind.HUMAN
    if coordinator and not system:
        stop_code = "COORDINATOR_PAUSED"
    updated = pause(
        run,
        reason=cmd.reason,
        source="system" if system or coordinator else "owner",
        stop_code=stop_code,
    )
    if updated == run:
        return PauseRunResult(run.id, run.status.value, run.row_version)
    uow.repo(RunRepository).save(updated, expected_version=run.row_version)
    why = cause("subscription" if system else "wait_changed", codes=[stop_code or "RUN_PAUSED"])
    for assignment in assignments_for_run(uow, run.id):
        if assignment.state is not AssignmentState.AVAILABLE or assignment.reconcile_effect_id is not None:
            continue
        revoke_assignment(uow, ctx, assignment)
        task = uow.repo(TaskRepository).get(assignment.task_id, for_update=True)
        attempt = uow.repo(AttemptRepository).get(assignment.attempt_id, for_update=True)
        if (
            task.status is TaskStatus.ASSIGNED
            and attempt.state is AttemptState.PREPARING
            and not uow.repo(StageRepository).history(attempt.id).entries
        ):
            ready = transition(task, TaskStatus.READY, rule="T4")
            save_task(uow, run, task, ready, why, ctx.clock.now())
            emit(uow, run, "task-ready", {"task_id": str(task.id), "reason": "pause"}, why)
    emit(
        uow,
        run,
        "run-paused",
        {
            "reason": stop_code or "RUN_PAUSED",
            "by": str(ctx.actor.principal_id),
            "pause_source": updated.pause_source,
            "stop_code": updated.stop_code,
        },
        why,
    )
    return PauseRunResult(run.id, updated.status.value, updated.row_version)


SPEC = CommandSpec(
    name="execution.pause_run",
    dto=PauseRun,
    result=PauseRunResult,
    permission="run.control",
    scope_of=run_scope,
    handler=handle,
)
