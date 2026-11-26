"""Locked control operations; no host IO and no inferred process-death proof."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import AttemptId, RunId, ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._primitives import attempt_effect_ids, attempts_for_run
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.domain.assignment import AssignmentState, transition_assignment
from skm.modules.execution.domain.attempt import (
    TERMINAL_ATTEMPT_STATES,
    AttemptEndReason,
    AttemptState,
    transition_attempt,
)
from skm.modules.execution.domain.budget import close_reservation, usage_charge
from skm.modules.execution.domain.decision_request import DecisionState
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.domain.readiness import canonical_digest
from skm.modules.execution.domain.run import TERMINAL_RUN_STATUSES
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES, StageOutcomeKind, interrupt_stage
from skm.modules.execution.domain.step import StepState, finish_step
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    AutopilotRepository,
    BudgetRepository,
    DecisionRepository,
    EffectRepository,
    IntegrationSlotRepository,
    RecoveryRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning
from skm.modules.policy.public import record_outcome
from skm.modules.workspace import public as workspace

from ._events import cause, emit
from ._worker_dtos import document


def require_permission(uow: UnitOfWork, ctx: Any, run: Any, permission: str, *, human: bool = False) -> None:
    if human and ctx.actor.kind is not PrincipalKind.HUMAN:
        raise error_for(ErrorCode.FORBIDDEN, "trusted human authority is required")
    if permission not in access.effective_permissions(uow, ctx.actor, ScopeId(run.id)):
        raise error_for(
            ErrorCode.FORBIDDEN, "required permission is missing", details={"permission": permission}
        )


def lock_run(uow: UnitOfWork, run_id: Any, expected: int | None = None) -> Any:
    run = uow.repo(RunRepository).get(run_id, for_update=True)
    if run.status in TERMINAL_RUN_STATUSES:
        raise error_for(ErrorCode.RUN_NOT_ACTIVE, "run is terminal")
    if expected is not None and expected != run.row_version:
        raise error_for(ErrorCode.VERSION_CONFLICT, "run version changed")
    return run


def lock_task(uow: UnitOfWork, task_id: Any) -> tuple[Any, Any, Any]:
    observed = uow.repo(TaskRepository).get(task_id)
    run = lock_run(uow, observed.run_id)
    task = uow.repo(TaskRepository).get(task_id, for_update=True)
    attempt = (
        None
        if task.current_attempt_id is None
        else uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
    )
    return run, task, attempt


def live_guard(uow: UnitOfWork, ctx: Any, run: Any) -> None:
    if run.plan_id is not None:
        planning.require_active_plan(uow, run.plan_id)
    workspace.require_active_project(uow, run.project_id)
    if run.project_id in uow.repo(AutopilotRepository).emergency_project_ids():
        raise error_for(ErrorCode.EMERGENCY_STOPPED, "project emergency stop is active")
    if ctx.config.get("execution.kill_switch") is True:
        raise error_for(ErrorCode.FORBIDDEN, "live policy kill switch")


def assignments_for_run(uow: UnitOfWork, run_id: Any) -> list[Any]:
    return [
        a
        for attempt in attempts_for_run(uow, run_id)
        for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
    ]


def revoke_assignment(uow: UnitOfWork, ctx: Any, assignment: Any) -> None:
    repo = uow.repo(AssignmentRepository)
    locked = repo.get(assignment.id, for_update=True)
    if locked.reconcile_effect_id is not None or locked.state not in {
        AssignmentState.AVAILABLE,
        AssignmentState.LEASED,
    }:
        return
    repo.lease(locked.id, for_update=True)
    repo.save(transition_assignment(locked, AssignmentState.CANCELLED), expected_version=locked.row_version)
    repo.drop_lease(locked.id)
    access.revoke_assignment_tokens(
        uow, assignment_id=locked.id, by=ctx.actor.principal_id, now=ctx.clock.now()
    )
    artifacts.revoke_grants(
        uow, reason=artifacts.GrantReason.ASSIGNMENT, ref=str(locked.id), now=ctx.clock.now()
    )


def stage_completed(uow: UnitOfWork, run: Any, stage: Any, steps: list[Any], why: Any) -> None:
    emit(
        uow,
        run,
        "stage-completed",
        {
            "task_id": str(stage.task_id),
            "attempt_id": str(stage.attempt_id),
            "stage_record_id": str(stage.id),
            "stage_id": stage.stage_id,
            "stage_type": stage.stage_type,
            "state": stage.state.value,
            "outcome_kind": None if stage.outcome_kind is None else stage.outcome_kind.value,
            "error_code": stage.error_code,
            "diagnostics": [],
            "step_ids": [str(s.id) for s in steps],
            "step_states": [{"step_id": str(s.id), "state": s.state.value} for s in steps],
            "output_ids": [],
            "check_execution_ids": [],
            "review_ids": [],
            "decision_ids": [],
            "effect_ids": [],
            "observation_refs": [],
            "timing": {
                "started_at": stage.started_at.isoformat(),
                "finished_at": stage.finished_at.isoformat(),
                "basis": "db_transition",
            },
            "coverage": "unavailable",
        },
        why,
    )


def close_attempt(  # noqa: PLR0912 -- per-stage cancellation and settlement
    uow: UnitOfWork, ctx: Any, run: Any, attempt: Any, *, code: str, reason: AttemptEndReason
) -> None:
    now = uow.repo(RunRepository).now()
    why = cause("cancel" if code == "RUN_CANCELLED" else "restart", codes=[code])
    att_repo = uow.repo(AttemptRepository)
    attempt = att_repo.get(attempt.id, for_update=True)
    for assignment in uow.repo(AssignmentRepository).for_attempt(attempt.id):
        revoke_assignment(uow, ctx, assignment)
    history = uow.repo(StageRepository).history(attempt.id)
    budget = uow.repo(BudgetRepository)

    _bundle, values = effective_values(uow, run.id)
    for entry in history.entries:
        stage = uow.repo(StageRepository).get(entry.record.id, for_update=True)
        closed_steps: list[Any] = []
        for old_step in uow.repo(StepRepository).for_stage(stage.id):
            step = uow.repo(StepRepository).get(old_step.id)
            for reservation in budget.open_for_steps((step.id,)):
                accounts = budget.accounts_for(run.id, attempt.task_id, reservation.dimension)
                selected = [a for a in accounts if a.id in reservation.account_ids]
                outcome = close_reservation(
                    selected,
                    reservation,
                    runtime_started=stage.runtime_started_at is not None,
                    usage=usage_charge(step.usage, reservation.dimension) if step.usage else None,
                    usage_so_far=usage_charge(step.usage_so_far, reservation.dimension)
                    if step.usage_so_far
                    else None,
                    policy=values.get("budgets.unknown_usage_policy", "block"),
                    unknown_charge=reservation.amount,
                    now=now,
                )
                if outcome.reservation.state == "released":
                    budget.release(reservation)
                else:
                    budget.settle(reservation, outcome.charged)
                if outcome.unmetered and run.unmetered_at is None:
                    latest = uow.repo(RunRepository).get(run.id, for_update=True)
                    uow.repo(RunRepository).save(
                        replace(latest, unmetered_at=now, row_version=latest.row_version + 1),
                        expected_version=latest.row_version,
                    )
            if step.state is not StepState.STARTED:
                closed_steps.append(step)
                continue
            closed = finish_step(step, state=StepState.CANCELLED, now=now, error_code=code)
            uow.repo(StepRepository).save(closed)
            emit(
                uow,
                run,
                "step-observation-recorded",
                {
                    "task_id": str(stage.task_id),
                    "attempt_id": str(stage.attempt_id),
                    "stage_record_id": str(stage.id),
                    "step_id": str(step.id),
                    "observation": None,
                    "observation_digest": None,
                    "route_snapshot": document(step.route_snapshot),
                    "role": step.role.value,
                    "purpose": step.purpose.value,
                    "seq": step.seq,
                    "parent_step_id": None if step.parent_step_id is None else str(step.parent_step_id),
                    "context_manifest_id": str(step.context_manifest_id),
                    "binding_consistency": "unavailable",
                },
                why,
            )
            closed_steps.append(closed)
        if stage.state not in ACTIVE_STAGE_STATES:
            continue
        closed_stage = replace(
            interrupt_stage(stage, now=now), outcome_kind=StageOutcomeKind.CANCELLED, error_code=code
        )
        uow.repo(StageRepository).save(closed_stage)
        stage_completed(uow, run, closed_stage, closed_steps, why)
    for effect_id in attempt_effect_ids(uow, attempt.id):
        effect = uow.repo(EffectRepository).get(effect_id, for_update=True)
        if effect.state not in {EffectState.INTENDED, EffectState.EXECUTING}:
            continue
        unknown = effect.state is EffectState.EXECUTING
        diagnostics = effect.receipt or {
            "reason_code": code,
            "recovery_required": unknown,
            "attempt_id": str(attempt.id),
            "stage_record_ids": [str(e.record.id) for e in history.entries],
        }
        closed = replace(
            effect,
            state=EffectState.OUTCOME_UNKNOWN if unknown else EffectState.FAILED,
            updated_at=now,
            receipt=effect.receipt if unknown else diagnostics,
        )
        uow.repo(EffectRepository).save(closed)
        if unknown:
            if effect.intent_id is not None:
                record_outcome(
                    uow,
                    ctx,
                    intent_id=ToolIntentId(effect.intent_id),
                    outcome="outcome_unknown",
                    receipt=diagnostics,
                )
            emit(
                uow,
                run,
                "external-effect-outcome-unknown",
                {
                    "effect_id": str(effect.id),
                    "attempt_id": str(effect.attempt_id),
                    "kind": effect.kind.value,
                },
                {
                    **why,
                    "refs": [
                        {"kind": "effect", "id": str(effect.id)},
                        *[{"kind": "stage", "id": str(e.record.id)} for e in history.entries],
                    ],
                },
            )
    uow.repo(IntegrationSlotRepository).release_for_attempt(attempt.id)
    for request in uow.repo(DecisionRepository).open_for_task(attempt.task_id):
        uow.repo(DecisionRepository).save(replace(request, state=DecisionState.CANCELLED))
    if attempt.state not in TERMINAL_ATTEMPT_STATES:
        terminal = (
            AttemptState.OWNERSHIP_LOST if attempt.state is AttemptState.SUBMITTED else AttemptState.ABANDONED
        )
        closed = transition_attempt(attempt, terminal, now=now, end_reason=reason)
        att_repo.save(closed, expected_version=att_repo.version(attempt.id))


def checkpoint_state(
    uow: UnitOfWork, run_id: RunId, *, closing_attempt_id: AttemptId | None = None
) -> dict[str, bool]:
    state = {"leased_claim": False, "unfinished_stage": False, "open_recovery": False}
    for attempt in attempts_for_run(uow, run_id):
        # Restart closes stages and revokes ordinary assignments on its own attempt.
        for assignment in uow.repo(AssignmentRepository).for_attempt(attempt.id):
            if assignment.state is AssignmentState.LEASED and (
                attempt.id != closing_attempt_id or assignment.reconcile_effect_id is not None
            ):
                state["leased_claim"] = True
        for entry in uow.repo(StageRepository).history(attempt.id).entries:
            if entry.record.state in ACTIVE_STAGE_STATES and attempt.id != closing_attempt_id:
                state["unfinished_stage"] = True
            if uow.repo(RecoveryRepository).open_for_stage(entry.record.id) is not None:
                state["open_recovery"] = True
    return state


def checkpoint(uow: UnitOfWork, run_id: RunId) -> None:
    state = checkpoint_state(uow, run_id)
    if any(state.values()):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "release every claim before reconfiguration"
            if state["leased_claim"]
            else "finish stages and recovery before reconfiguration",
            details={"reason": "reconfiguration_checkpoint_required"},
        )


def run_scope(cmd: Any) -> ScopeRef:
    return ScopeRef(ScopeKind.RUN, ScopeId(cmd.run_id))


def task_scope(cmd: Any, uow: UnitOfWork) -> ScopeRef | None:
    try:
        task = uow.repo(TaskRepository).get(cmd.task_id)
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(task.run_id))


def current_binding_digest(uow: UnitOfWork, attempt: Any) -> str:
    """Saved stage input, or the server's immutable pre-stage binding."""
    last = uow.repo(StageRepository).history(attempt.id).last()
    return (
        last.record.input_digest
        if last
        else canonical_digest(
            {
                "attempt_id": str(attempt.id),
                "output_id": None if attempt.current_output_id is None else str(attempt.current_output_id),
            }
        )
    )
