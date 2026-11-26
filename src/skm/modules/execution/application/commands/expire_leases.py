"""Lease loss closes DB authority and budgets; OS containment remains a separate fact."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, error_for
from skm.kernel.ids import HostId, WorkerId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import assignments_for_run, revoke_assignment
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._json_reads import objects
from skm.modules.execution.application._live_control import cancellation_code
from skm.modules.execution.application._primitives import move, save_attempt, server_context
from skm.modules.execution.application._stage_agent_helpers import stage_route_available
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_budget import close_budgets
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application._worker_events import close_steps, stage_completed
from skm.modules.execution.application._worker_protocol import revoke_authority
from skm.modules.execution.application.apply_action import process_pending
from skm.modules.execution.application.commands.reconcile_external_effect import close_admin, schedule_unknown
from skm.modules.execution.application.commands.report_attempt_failure import close_effects
from skm.modules.execution.domain.assignment import (
    AssignmentState,
    WorkerOffer,
    reissue,
    transition_assignment,
    worker_matches,
)
from skm.modules.execution.domain.attempt import (
    TERMINAL_ATTEMPT_STATES,
    AttemptEndReason,
    AttemptState,
    ContinuationCause,
    DeferredTrigger,
    EntityRef,
    defer_trigger,
    transition_attempt,
)
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.ids import StageRecordId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.domain.run import pause
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState, interrupt_stage
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.commands import expire_leases_from_json
from skm.modules.execution.generated.results import expire_leases_result_from_json
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    EnvironmentRepository,
    ExecutionQueries,
    IntegrationSlotRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.workspace import public as workspace


class ExpireLeases(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:expire-leases:v1"


class ExpireLeasesResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:expire-leases:v1"


def system_guard(ctx: Any) -> None:
    if ctx.actor.principal_id != SYSTEM_PRINCIPAL_ID or ctx.actor.kind is not PrincipalKind.SERVICE:
        raise error_for(ErrorCode.FORBIDDEN, "background execution requires the system service")


def control_now(uow: UnitOfWork) -> Any:
    """Sample server time after the caller has acquired ownership locks."""
    return uow.repo(RunRepository).now()


def monitor(  # noqa: PLR0913 -- one bounded evaluation envelope
    uow: UnitOfWork,
    ctx: Any,
    run: Any,
    *,
    name: str,
    rule: str,
    thresholds: Any,
    verdict: str = "healthy",
    action: str = "none",
    stage: Any = None,
    reason: str = "ADMISSION_CHECKED",
) -> None:
    now = control_now(uow).isoformat()
    emit(
        uow,
        run,
        "monitor-evaluated",
        {
            "evaluation_id": str(ctx.ids.new_id()),
            "monitor_id": name,
            "rule_id": rule,
            "rule_version": "1",
            "target_stage_record_id": None if stage is None else str(stage.id),
            "fencing_token": None if stage is None else stage.fencing_token,
            "thresholds": [
                {"key": f"execution.{name}.{k}", "value": v}
                for k, v in sorted(thresholds.items())
                if type(v) in {int, float, bool}
            ],
            "config_digest": ctx.config.digest,
            "config_generation": ctx.config.generation,
            "input_watermark": uow.repo(ExecutionQueries).head_run_seq(run.id),
            "input_coverage": "partial",
            "last_signal_at": None,
            "scheduled_at": now,
            "started_at": now,
            "finished_at": now,
            "verdict": verdict,
            "action": action,
            "action_request_id": None,
            "recovery_record_id": None,
            "recovery_mode": None,
            "reason_code": reason,
        },
        cause("lease_recovery" if name == "lease_sweeper" else "wait_changed"),
    )


def handoff_lost(uow: UnitOfWork, ctx: Any, run: Any, task: Any, attempt: Any) -> None:
    """T22a is legal during pause; terminal ownership and null cursor share one save."""
    why = cause(
        "lease_recovery", rule="L3", codes=["LEASE_LOST"], refs=[{"kind": "attempt", "id": str(attempt.id)}]
    )
    for assignment in sorted(uow.repo(AssignmentRepository).for_attempt(attempt.id), key=lambda a: str(a.id)):
        revoke_assignment(uow, ctx, assignment)
    if attempt.state not in TERMINAL_ATTEMPT_STATES:
        save_attempt(
            uow,
            transition_attempt(
                attempt,
                AttemptState.OWNERSHIP_LOST,
                now=control_now(uow),
                end_reason=AttemptEndReason.LEASE_LOST,
            ),
        )
        emit(
            uow, run, "attempt-ownership-lost", {"attempt_id": str(attempt.id), "task_id": str(task.id)}, why
        )
    ready = move(uow, ctx, run, task, TaskStatus.READY, why)
    emit(uow, run, "task-ready", {"task_id": str(ready.id), "reason": "lease_recovery"}, why)


def reap_expired(uow: UnitOfWork, ctx: Any, run: Any) -> None:
    recovering = uow.repo(TaskRepository).list_for_run(run.id, blocking_code=BlockingCode.RECOVERING)
    for old in sorted(recovering, key=lambda t: str(t.id)):
        reason = old.blocking_reason
        if reason is None or not reason.refs.get("reap_stage_record_id"):
            continue
        task = uow.repo(TaskRepository).get(old.id, for_update=True)
        if task.current_attempt_id is None:
            # the reap barrier is raised only over a pending attempt, and clearing it clears the barrier
            raise InternalError(ErrorCode.INTERNAL_ERROR, "reap barrier task has no current attempt")
        attempt = uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
        assignments = uow.repo(AssignmentRepository)
        # A leased reap assignment was admitted only after the repository verified
        # every containment proof. Its old barrier must not become an L3 timer.
        confirmed = any(
            a.state is AssignmentState.LEASED
            and str(a.reap_stage_record_id) == str(reason.refs["reap_stage_record_id"])
            and (lease := assignments.lease(a.id)) is not None
            and lease.expires_at > control_now(uow)
            for a in assignments.for_attempt(attempt.id)
        )
        confirmed = confirmed or uow.repo(StageRepository).reap_confirmed(
            StageRecordId(UUID(str(reason.refs["reap_stage_record_id"])))
        )
        if confirmed:
            move(uow, ctx, run, task, task.status, cause("lease_recovery"))
            continue
        if reason.next_check_at is not None and reason.next_check_at <= control_now(uow):
            handoff_lost(uow, ctx, run, task, attempt)
        elif run.status.value == "running":
            rows = assignments.for_attempt(attempt.id)
            if not any(a.state in {AssignmentState.AVAILABLE, AssignmentState.LEASED} for a in rows):
                previous = max(
                    (a for a in rows if a.reap_stage_record_id is not None),
                    key=lambda a: (a.created_at, str(a.id)),
                    default=None,
                )
                if previous:
                    assignments.add(
                        reissue(
                            previous,
                            new_id=ctx.ids.new_id(),
                            now=control_now(uow),
                            reap_stage_record_id=previous.reap_stage_record_id,
                            reap_step_id=previous.reap_step_id,
                        )
                    )


def capability_wait(uow: UnitOfWork, ctx: Any, run: Any) -> None:
    threshold = int(value(ctx.config, "execution.scheduler.capability_wait_seconds", 300))
    workers = workspace.list_online_workers(uow, (run.workspace_id,))
    now = control_now(uow)
    for assignment in assignments_for_run(uow, run.id):
        if (
            assignment.state is not AssignmentState.AVAILABLE
            or assignment.reconcile_effect_id is not None
            or assignment.available_at > now
        ):
            continue
        task = uow.repo(TaskRepository).get(assignment.task_id, for_update=True)
        attempt = uow.repo(AttemptRepository).get(assignment.attempt_id)
        matched = any(
            worker_matches(
                assignment.requirements,
                WorkerOffer(
                    WorkerId(w.worker_id),
                    HostId(w.host_id),
                    frozenset(w.capabilities.runtimes) | {f"runtime:{r}" for r in w.capabilities.runtimes},
                    frozenset(w.capabilities.labels),
                    frozenset(
                        {
                            EnvironmentKind.GIT_WORKTREE,
                            EnvironmentKind.EXISTING_CHECKOUT,
                            EnvironmentKind.MANAGED_CLONE,
                        }
                    ),
                    frozenset(w.capabilities.isolation_profiles),
                    (),
                ),
            )
            and stage_route_available(uow, ctx, run, task, attempt, w)
            for w in workers
        )
        if matched:
            if task.blocking_reason and task.blocking_reason.code is BlockingCode.BLOCKED_BY_CAPABILITY:
                move(uow, ctx, run, task, task.status, cause("wait_changed"))
            continue
        if task.blocking_reason is not None or (now - assignment.created_at).total_seconds() <= threshold:
            continue
        if task.status is TaskStatus.ASSIGNED:
            task = move(uow, ctx, run, task, TaskStatus.READY, cause("wait_changed"))
        if task.status is not TaskStatus.READY:
            continue
        req = assignment.requirements
        reason = blocking_reason(
            BlockingCode.BLOCKED_BY_CAPABILITY,
            task_id=task.id,
            refs={
                "capabilities": sorted(req.capabilities),
                "required_host_id": str(req.required_host_id) if req.required_host_id else None,
                "required_labels": sorted(req.required_labels),
                "environment_kind": req.environment_kind.value,
                "isolation_profiles": sorted(req.isolation_profiles),
            },
            now=now,
            next_check_at=now + timedelta(seconds=threshold),
            message="No online worker meets the stage requirements and fresh host route",
        )
        move(uow, ctx, run, task, task.status, cause("wait_changed"), blocking=reason)


def candidates(uow: UnitOfWork, limit: int) -> Any:
    return uow.repo(AssignmentRepository).expiry_candidates(limit=limit)


def lock_ownership(uow: UnitOfWork, observed: Any) -> Any:
    run = (
        uow.repo(RunRepository).get(observed.run_id, for_update=True)
        if observed.reconcile_effect_id is not None
        else next(iter(uow.repo(RunRepository).lock_active((observed.run_id,))), None)
    )
    if run is None:
        return None
    task = uow.repo(TaskRepository).get(observed.task_id, for_update=True)
    attempt = uow.repo(AttemptRepository).get(observed.attempt_id, for_update=True)
    repo = uow.repo(AssignmentRepository)
    assignment = repo.get(observed.id, for_update=True)
    lease = repo.lease(assignment.id, for_update=True)
    if assignment.state is not AssignmentState.LEASED or lease is None:
        return None
    return SimpleNamespace(
        run=run,
        task=task,
        attempt=attempt,
        assignment=assignment,
        lease=lease,
        now=control_now(uow),
        claim=WorkerClaim(assignment.id, attempt.id, lease.worker_id, lease.fencing_token),
    )


def expired_after_locks(uow: UnitOfWork, fenced: Any) -> bool:
    fenced.now = control_now(uow)
    return fenced.lease.expires_at <= fenced.now


def terminal_stage(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, *, code: str) -> Any:
    steps = uow.repo(StepRepository).for_stage(stage.id)
    closed = close_steps(uow, fenced, stage, steps, successful=False, code=code)
    refusal = close_budgets(uow, fenced, stage, closed)
    error_class = {"RUNTIME_TIMEOUT": "timeout", "LEASE_LOST": "lease_lost"}.get(code, "cancelled")
    record = replace(
        interrupt_stage(stage, now=fenced.now),
        error_code=code,
        outcome_kind=StageOutcomeKind.RUNTIME_ERROR,
        outcome={"error_code": code, "error_class": error_class},
    )
    if code == "RUNTIME_TIMEOUT":
        record = replace(record, state=StageState.FAILED)
    uow.repo(StageRepository).save(record)
    stage_completed(uow, fenced, record, closed)
    if refusal is not None and fenced.run.status.value in {"running", "waiting"}:
        latest = uow.repo(RunRepository).get(fenced.run.id)
        paused = pause(latest, reason="BUDGET_EXHAUSTED", source="system", stop_code="BUDGET_EXHAUSTED")
        uow.repo(RunRepository).save(paused, expected_version=latest.row_version)
        emit(
            uow,
            latest,
            "run-paused",
            {
                "by": str(ctx.actor.principal_id),
                "reason": "BUDGET_EXHAUSTED",
                "pause_source": "system",
                "stop_code": "BUDGET_EXHAUSTED",
            },
            cause("stage_outcome", codes=["BUDGET_EXHAUSTED"]),
        )
        fenced.run = paused
    return record


def lease_recovery(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, had_effect: bool) -> None:
    attempt, task = fenced.attempt, fenced.task
    if attempt.state in TERMINAL_ATTEMPT_STATES:
        return
    why = cause("lease_recovery", codes=["LEASE_LOST"])
    if stage is None:
        # A completed prior runtime is not evidence that this ownership spawned anything.
        if attempt.state is AttemptState.RUNNING:
            attempt = transition_attempt(attempt, AttemptState.WAITING)
            save_attempt(uow, attempt)
        if task.status is TaskStatus.ASSIGNED:
            move(uow, ctx, fenced.run, task, TaskStatus.READY, why)
            emit(uow, fenced.run, "task-ready", {"task_id": str(task.id), "reason": "lease_recovery"}, why)
        process_pending(uow, ctx, attempt.id)
        return
    runtime = stage.runtime_started_at is not None or stage.stage_type == "integrate" or had_effect
    event_id = ctx.ids.new_id()
    pending = defer_trigger(
        attempt,
        DeferredTrigger(
            event_id,
            ContinuationCause(
                "lease_recovery",
                None,
                ("LEASE_LOST",),
                (EntityRef("stage", stage.id),),
                source_event_id=event_id,
            ),
        ),
        continuation_id=ctx.ids.new_id(),
    )
    if not runtime:
        save_attempt(uow, pending)
        process_pending(uow, ctx, attempt.id)
        return
    env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
    if (
        env is None
        or attempt.host_id is None
        or env.host_id != attempt.host_id
        or env.state.value in {"removed", "discarded"}
    ):
        handoff_lost(uow, ctx, fenced.run, task, pending)
        return
    steps = uow.repo(StepRepository).for_stage(stage.id)
    if pending.state is AttemptState.RUNNING:
        pending = transition_attempt(pending, AttemptState.WAITING)
    save_attempt(uow, pending)
    _, values = effective_values(uow, fenced.run.id)
    next_check = fenced.now + timedelta(seconds=int(values.get("execution.lease.reap_wait_seconds", 300)))
    refs = {"stage_record_id": str(stage.id), "reap_stage_record_id": str(stage.id), "recovery_step": "reap"}
    if steps:
        refs["reap_step_id"] = str(steps[0].id)
    reason = blocking_reason(
        BlockingCode.RECOVERING,
        task_id=task.id,
        refs=refs,
        now=fenced.now,
        next_check_at=next_check,
        message="Lease lost; host containment proof required",
    )
    move(uow, ctx, fenced.run, task, task.status, why, blocking=reason)
    uow.repo(AssignmentRepository).add(
        reissue(
            fenced.assignment,
            new_id=ctx.ids.new_id(),
            now=fenced.now,
            requirements=replace(fenced.assignment.requirements, required_host_id=attempt.host_id),
            reap_stage_record_id=stage.id,
            reap_step_id=steps[0].id if steps else None,
        )
    )


def expire_one(uow: UnitOfWork, ctx: Any, fenced: Any) -> None:
    if fenced.assignment.reconcile_effect_id is not None:
        if expired_after_locks(uow, fenced):
            close_admin(uow, ctx, fenced, expired=True, code="LEASE_LOST")
        return
    repo = uow.repo(AssignmentRepository)
    stage = uow.repo(StageRepository).started_without_result(fenced.attempt.id)
    if stage is not None:
        stage = uow.repo(StageRepository).get(stage.id, for_update=True)
        # The active record belongs to the expiring fence; old completed stages are ignored.
        if stage.fencing_token != fenced.lease.fencing_token:
            stage = None
    if not expired_after_locks(uow, fenced):
        return
    effects = objects(uow.repo(ExecutionQueries).attempt_view(fenced.attempt.id).get("effects"), "effects")
    had_effect = any(e.get("state") == "executing" for e in effects)
    expired = transition_assignment(fenced.assignment, AssignmentState.EXPIRED)
    repo.save(expired, expected_version=fenced.assignment.row_version)
    repo.drop_lease(expired.id)
    revoke_authority(uow, ctx, fenced)
    uow.repo(IntegrationSlotRepository).release_for_attempt(fenced.attempt.id)
    if stage is not None:
        terminal_stage(uow, ctx, fenced, stage, code=cancellation_code(stage) or "LEASE_LOST")
    close_effects(uow, ctx, fenced)
    fenced.assignment = expired

    if not schedule_unknown(uow, ctx, fenced.attempt.id):
        lease_recovery(uow, ctx, fenced, stage, had_effect)
    emit(
        uow,
        fenced.run,
        "lease-expired",
        {
            "assignment_id": str(expired.id),
            "attempt_id": str(expired.attempt_id),
            "worker_id": str(fenced.lease.worker_id),
            "fencing_token": fenced.lease.fencing_token,
        },
        cause("lease_recovery", codes=["LEASE_LOST"]),
    )


def handle(cmd: ExpireLeases, ctx: Any, uow: UnitOfWork) -> ExpireLeasesResult:
    system_guard(ctx)
    ctx = server_context(ctx, uow)
    wire: Any = expire_leases_from_json(cmd)
    hints = candidates(uow, wire.get("limit", 100))
    processed = 0
    # All ownership locks acquired in global run order, irrespective of lease expiry order.
    for observed, old_lease in sorted(
        hints, key=lambda p: (str(p[0].run_id), str(p[0].task_id), str(p[0].attempt_id), str(p[0].id))
    ):
        fenced = lock_ownership(uow, observed)
        if (
            fenced is None
            or fenced.lease.fencing_token != old_lease.fencing_token
            or fenced.lease.expires_at != old_lease.expires_at
        ):
            continue
        if not expired_after_locks(uow, fenced):
            continue
        expire_one(uow, ctx, fenced)
        processed += 1
        monitor(
            uow,
            ctx,
            fenced.run,
            name="lease_sweeper",
            rule="L",
            thresholds={},
            verdict="action_required",
            reason="LEASE_LOST",
        )
    return ExpireLeasesResult(expire_leases_result_from_json({"expired": processed}))


SPEC = CommandSpec(
    name="execution.expire_leases",
    dto=ExpireLeases,
    result=ExpireLeasesResult,
    permission="system.internal",
    permissions_of=lambda _cmd: ("run.control",),
    scope_of=None,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
    internal=True,
)
