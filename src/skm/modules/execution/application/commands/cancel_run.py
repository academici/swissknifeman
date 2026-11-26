"""Cancel execution authority and retain uncertain external outcomes for reconciliation."""

from dataclasses import replace
from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.ids import RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import close_attempt, lock_run, run_scope
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.application._primitives import attempts_for_run, server_context
from skm.modules.execution.application.commands.report_attempt_failure import close_before_cancel
from skm.modules.execution.domain.attempt import AttemptEndReason
from skm.modules.execution.domain.decision_request import DecisionState
from skm.modules.execution.domain.run import RunStatus, cancel
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, TaskStatus, transition
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.generated.results import CancelRunResult
from skm.modules.execution.ports import (
    AssignmentRepository,
    DecisionRepository,
    RunRepository,
    TaskRepository,
)


def handle(cmd: CancelRun, ctx: Any, uow: UnitOfWork) -> CancelRunResult:
    ctx = server_context(ctx, uow)
    run = uow.repo(RunRepository).get(RunId(cmd.run_id), for_update=True)
    if run.status is RunStatus.CANCELLED:
        return CancelRunResult(run.id, run.status.value, run.row_version)
    run = lock_run(uow, cmd.run_id)
    why = cause("cancel", codes=["RUN_CANCELLED"])
    for task in sorted(uow.repo(TaskRepository).list_for_run(run.id), key=lambda t: str(t.id)):
        uow.repo(TaskRepository).get(task.id, for_update=True)
    for attempt in attempts_for_run(uow, run.id):
        if any(
            a.reconcile_effect_id is not None and a.state.value in {"available", "leased"}
            for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
        ):
            continue

        close_before_cancel(uow, ctx, run, attempt)
        close_attempt(uow, ctx, run, attempt, code="RUN_CANCELLED", reason=AttemptEndReason.CANCELLED)
    for task in uow.repo(TaskRepository).list_for_run(run.id):
        if task.status not in TERMINAL_TASK_STATUSES:
            locked = uow.repo(TaskRepository).get(task.id, for_update=True)
            save_task(
                uow, run, locked, transition(locked, TaskStatus.CANCELLED, rule="T24"), why, ctx.clock.now()
            )
        for request in uow.repo(DecisionRepository).open_for_task(task.id):
            uow.repo(DecisionRepository).save(replace(request, state=DecisionState.CANCELLED))
    latest = uow.repo(RunRepository).get(run.id, for_update=True)
    updated = cancel(latest, now=ctx.clock.now())
    uow.repo(RunRepository).save(updated, expected_version=latest.row_version)
    emit(
        uow,
        run,
        "run-cancelled",
        {"reason": "RUN_CANCELLED", "by": str(ctx.actor.principal_id), "previous_stop_code": run.stop_code},
        why,
    )
    return CancelRunResult(run.id, updated.status.value, updated.row_version)


SPEC = CommandSpec(
    name="execution.cancel_run",
    dto=CancelRun,
    result=CancelRunResult,
    permission="run.control",
    scope_of=run_scope,
    handler=handle,
)
