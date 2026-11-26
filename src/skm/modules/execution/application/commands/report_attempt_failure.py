"""Close failed work and unresolved effects under the current fence."""

from dataclasses import replace
from typing import Any

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._primitives import attempt_effect_ids, save_attempt
from skm.modules.execution.application._worker_budget import close_budgets, pause_budget, priced_usage
from skm.modules.execution.application._worker_dtos import ReportAttemptFailure, ReportAttemptFailureResult
from skm.modules.execution.application._worker_events import close_steps, stage_completed
from skm.modules.execution.application._worker_protocol import (
    fenced_scope,
    lock_fenced_context,
    locked_stage,
    next_instruction,
    revoke_authority,
)
from skm.modules.execution.application._worker_result import advance_terminal
from skm.modules.execution.application.apply_action import apply_action, process_pending
from skm.modules.execution.application.commands.reconcile_external_effect import (
    RELEASE,
    admin_context,
    close_admin,
)
from skm.modules.execution.domain.assignment import AssignmentState, transition_assignment
from skm.modules.execution.domain.attempt import (
    AttemptState,
    ContinuationCause,
    SelectedStage,
    select_stage,
    transition_attempt,
)
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.domain.retry import STOP_CODES
from skm.modules.execution.domain.stage_record import (
    ACTIVE_STAGE_STATES,
    StageOutcomeKind,
    fail_stage,
    interrupt_stage,
)
from skm.modules.execution.domain.workflow.actions import ActionDecision, NewAttempt
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    EffectRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.policy.public import (
    record_outcome,
)


def close_effects(uow: UnitOfWork, ctx: Any, fenced: Any, *, code: str = "WORKER_FAILURE") -> None:

    repo = uow.repo(EffectRepository)
    for identity in sorted(attempt_effect_ids(uow, fenced.attempt.id)):
        effect = repo.get(identity, for_update=True)
        if effect.state not in {EffectState.INTENDED, EffectState.EXECUTING}:
            continue
        state = EffectState.OUTCOME_UNKNOWN if effect.state is EffectState.EXECUTING else EffectState.FAILED
        updated = replace(
            effect,
            state=state,
            updated_at=fenced.now,
            receipt=effect.receipt
            if state is EffectState.OUTCOME_UNKNOWN
            else effect.receipt or {"error_code": code},
        )
        repo.save(updated)
        if effect.intent_id is not None and state is EffectState.OUTCOME_UNKNOWN:
            record_outcome(
                uow,
                ctx,
                intent_id=ToolIntentId(effect.intent_id),
                outcome=state.value,
                receipt=updated.receipt or {"error_code": code},
            )
        if state is EffectState.OUTCOME_UNKNOWN:
            emit(
                uow,
                fenced.run,
                "external-effect-outcome-unknown",
                {
                    "effect_id": str(effect.id),
                    "attempt_id": str(effect.attempt_id),
                    "kind": effect.kind.value,
                },
                cause("cancel" if code == "RUN_CANCELLED" else "lease_recovery"),
            )


def close_before_cancel(uow: UnitOfWork, ctx: Any, run: Any, attempt: Any) -> None:
    """Diagnostics are not immutable receipts; close IO before cancel revokes the lease."""
    from types import SimpleNamespace

    attempt = uow.repo(AttemptRepository).get(attempt.id, for_update=True)
    assignments = uow.repo(AssignmentRepository)
    for row in assignments.for_attempt(attempt.id):
        assignments.get(row.id, for_update=True)
        assignments.lease(row.id, for_update=True)
    stages = uow.repo(StageRepository)
    for entry in stages.history(attempt.id).entries:
        stages.get(entry.record.id, for_update=True)
    close_effects(
        uow,
        ctx,
        SimpleNamespace(run=run, attempt=attempt, now=uow.repo(RunRepository).now()),
        code="RUN_CANCELLED",
    )


def handle(cmd: ReportAttemptFailure, ctx: Any, uow: UnitOfWork) -> ReportAttemptFailureResult:
    admin = admin_context(uow, ctx, cmd["claim"])
    if admin is not None:
        if cmd.get("stage_record_id"):
            stage = locked_stage(uow, admin, cmd["stage_record_id"])
            if stage.stage_id != "reconcile_" + admin.assignment.id.hex[-22:]:
                raise error_for(ErrorCode.LEASE_LOST, "failure is not bound to the administrative read")
        close_admin(uow, ctx, admin, code="WORKER_FAILURE")
        return ReportAttemptFailureResult(task_status=admin.task.status.value, next=RELEASE)
    fenced = lock_fenced_context(uow, ctx, cmd["claim"])
    repo = uow.repo(StageRepository)
    stage = (
        locked_stage(uow, fenced, cmd["stage_record_id"])
        if cmd.get("stage_record_id")
        else repo.started_without_result(fenced.attempt.id)
    )
    if stage is None or stage.state not in ACTIVE_STAGE_STATES:
        raise error_for(ErrorCode.INVALID_TRANSITION, "failure requires an unfinished owned stage")
    steps = uow.repo(StepRepository).for_stage(stage.id)
    shutdown = cmd["error_class"] == "worker_shutdown"
    environment_lost = cmd["error_class"] == "environment_lost"
    code = (
        "WORKER_SHUTDOWN"
        if shutdown
        else "ENVIRONMENT_LOST"
        if environment_lost
        else STOP_CODES.get(str(cmd["error_class"]), STOP_CODES["unknown"])
    )
    closed = close_steps(
        uow,
        fenced,
        stage,
        steps,
        successful=False,
        code=code,
        usage=priced_usage(uow, ctx, fenced, steps[0] if steps else None, cmd.get("usage")),
    )
    budget_refusal = close_budgets(uow, fenced, stage, closed)
    close_effects(uow, ctx, fenced)
    stage = (
        replace(interrupt_stage(stage, now=fenced.now), error_code=code)
        if shutdown
        else replace(
            fail_stage(stage, error_code=code, now=fenced.now, outcome_kind=StageOutcomeKind.RUNTIME_ERROR),
            outcome={
                "error_class": cmd["error_class"],
                "error_code": code,
                "detail": cmd["detail"],
                "worktree_dirty": cmd["worktree_dirty"],
                "retry_after_seconds": cmd.get("retry_after_seconds"),
            },
        )
    )
    repo.save(stage)
    revoke_authority(uow, ctx, fenced)
    stage_completed(uow, fenced, stage, closed)
    if budget_refusal is not None:
        pause_budget(uow, ctx, fenced, budget_refusal)
    if environment_lost:
        why = cause("stage_outcome", codes=[code])
        apply_action(ActionDecision(NewAttempt(code), why), ctx, uow, task_id=fenced.task.id, why=why)
    elif shutdown:
        selected = SelectedStage(
            stage.stage_id,
            stage.stage_type,
            StageMode.RESUME_INTERRUPTED if stage.runtime_started_at is not None else stage.mode,
            stage.round_no,
            {"role": steps[0].role.value} if steps else {},
            None,
            None,
            FeedbackRefs(interrupted_stage_record_id=stage.id),
            fenced.attempt.current_output_id,
            None,
        )
        attempt = select_stage(
            fenced.attempt,
            cause=ContinuationCause("lease_recovery", "L2"),
            stage=selected,
            continuation_id=ctx.ids.new_id(),
        )
        if attempt.state is AttemptState.RUNNING:
            attempt = transition_attempt(attempt, AttemptState.WAITING)
        save_attempt(uow, attempt)
        assignments = uow.repo(AssignmentRepository)
        assignments.save(
            transition_assignment(fenced.assignment, AssignmentState.COMPLETED),
            expected_version=fenced.assignment.row_version,
        )
        assignments.drop_lease(fenced.assignment.id)
        process_pending(uow, ctx, attempt.id)
    else:
        advance_terminal(uow, ctx, fenced, stage)
    return ReportAttemptFailureResult(
        task_status=uow.repo(TaskRepository).get(fenced.task.id).status.value,
        next={"kind": "release", "release_reason": "waiting"}
        if shutdown or environment_lost
        else next_instruction(uow, fenced),
    )


SPEC = CommandSpec(
    name="execution.report_attempt_failure",
    dto=ReportAttemptFailure,
    result=ReportAttemptFailureResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
