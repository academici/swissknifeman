"""Server-origin emergency deadlines; warning intensity is diagnostic only."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.ids import RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import assignments_for_run, close_attempt
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._live_control import cancellation_code
from skm.modules.execution.application._primitives import move, server_context
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application._worker_protocol import revoke_authority
from skm.modules.execution.application.commands.expire_leases import (
    control_now,
    lease_recovery,
    lock_ownership,
    monitor,
    system_guard,
    terminal_stage,
)
from skm.modules.execution.application.commands.report_attempt_failure import close_effects
from skm.modules.execution.application.loaders import find_task_work_policy
from skm.modules.execution.domain.assignment import AssignmentState, transition_assignment
from skm.modules.execution.domain.attempt import AttemptEndReason
from skm.modules.execution.domain.decision_request import DecisionState
from skm.modules.execution.domain.run import RunStatus, pause
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, TaskStatus
from skm.modules.execution.generated.commands import enforce_timeouts_from_json
from skm.modules.execution.generated.results import enforce_timeouts_result_from_json
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    CheckRepository,
    DecisionRepository,
    IntegrationSlotRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)


class EnforceTimeouts(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:enforce-timeouts:v1"


class EnforceTimeoutsResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:enforce-timeouts:v1"


def ceilings(*values: Any) -> int | None:
    positive = [int(v) for v in values if v is not None and not isinstance(v, bool) and int(v) > 0]
    return min(positive) if positive else None


def stage_deadline(
    uow: UnitOfWork, ctx: Any, attempt: Any, stage: Any, values: Any
) -> tuple[Any, dict[str, int]]:
    limits: dict[str, int] = {}
    duration = ceilings(
        value(ctx.config, "execution.timeouts.attempt_wall_seconds", 0),
        values.get("execution.timeouts.attempt_wall_seconds", 0),
    )
    deadlines: list[Any] = []
    clock = uow.repo(RunRepository)
    now = clock.now()
    elapsed = clock.active_seconds(attempt.run_id, now, stage_id=stage.id)
    if duration:
        spent = clock.active_seconds(attempt.run_id, now, attempt_id=attempt.id)
        deadlines.append(now + timedelta(seconds=duration - spent))
        limits["attempt_wall_seconds"] = duration
    if stage.stage_type in {"agent_step", "agent_review", "advisor_consult"}:
        policy = find_task_work_policy(uow, attempt.task_id)
        roles: Any = value(ctx.config, "execution.timeouts.role_wall_seconds", {}) or {}
        for step in uow.repo(StepRepository).for_stage(stage.id):
            # runtime admission stores explicit limits; provider observed times are ignored.
            admission = step.admission
            bound = ceilings(
                None if policy is None else policy.emergency_role_seconds.get(step.role.value),
                roles.get(step.role.value, 0),
                value(ctx.config, "execution.timeouts.step_wall_seconds", 0),
                admission.get("timeout_seconds"),
                1800 if step.role.value == "reviewer" else 0,
            )
            if bound:
                deadlines.append(now + timedelta(seconds=bound - elapsed))
                limits[f"{step.role.value}_hard_seconds"] = bound
    else:
        defaults = {"prepare_environment": 900, "integrate": 1800}
        frozen: Any = values.get("execution.timeouts.stage_seconds", {}) or {}
        live: Any = value(ctx.config, "execution.timeouts.stage_seconds", {}) or {}
        bound = ceilings(
            frozen.get(stage.stage_type), live.get(stage.stage_type), defaults.get(stage.stage_type)
        )
        if stage.stage_type == "run_checks":
            from skm.modules.planning import public as planning

            revision_id = uow.repo(RunRepository).get(attempt.run_id).revision_id
            definitions = (
                planning.get_revision_specification(uow, revision_id).checks
                if revision_id is not None
                else ()
            )
            checks = (
                uow.repo(CheckRepository).for_output(attempt.current_output_id)
                if attempt.current_output_id
                else ()
            )
            durations = [
                int(dict[str, Any](c.definition).get("timeout_seconds", 0))
                for c in definitions
                if isinstance(c.definition, dict)
            ]
            bound = (
                max(
                    durations,
                    default=int(value(ctx.config, "execution.checks.default_timeout_seconds", 7200)),
                )
                + 60
            )
            if checks:
                limits["checks_count"] = len(checks)
        if bound:
            deadlines.append(now + timedelta(seconds=bound - elapsed))
            limits["stage_seconds"] = bound
    return min(deadlines) if deadlines else None, limits


def pause_for(uow: UnitOfWork, ctx: Any, run: Any, code: str) -> Any:
    current = uow.repo(RunRepository).get(run.id)
    if current.status not in {RunStatus.RUNNING, RunStatus.WAITING}:
        return current
    paused = pause(current, reason=code, source="system", stop_code=code)
    uow.repo(RunRepository).save(paused, expected_version=current.row_version)
    emit(
        uow,
        run,
        "run-paused",
        {"reason": code, "by": str(ctx.actor.principal_id), "pause_source": "system", "stop_code": code},
        cause("wait_changed", codes=[code]),
    )
    return paused


def warnings(uow: UnitOfWork, ctx: Any, run: Any, attempt: Any, stage: Any, now: Any) -> list[Any]:
    policy = find_task_work_policy(uow, attempt.task_id)
    if policy is None:
        return []
    diagnostics: list[Any] = []
    for step in uow.repo(StepRepository).for_stage(stage.id):
        expected = policy.role_warn_seconds.get(step.role.value, 0)
        actual = max(0, int((now - (stage.runtime_started_at or stage.started_at)).total_seconds()))
        if expected > 0 and actual > expected:
            diagnostics.append(
                {
                    "stage_record_id": str(stage.id),
                    "step_id": str(step.id),
                    "role": step.role.value,
                    "actual_seconds": actual,
                    "expected_seconds": expected,
                }
            )
            monitor(
                uow,
                ctx,
                run,
                name="timeout_enforcer",
                rule="soft_warning",
                stage=stage,
                thresholds={"actual_seconds": actual, "expected_seconds": expected},
                verdict="suspected",
                reason="SOFT_DURATION_WARNING",
            )
    return diagnostics


def timeout_stage(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, deadline: Any, thresholds: Any) -> bool:
    grace = int(value(ctx.config, "execution.supervisor.grace_seconds", 60))
    outcome = dict(stage.outcome or {})
    requested = outcome.get("timeout_requested_at")
    if requested is None:
        uow.repo(StageRepository).request_cancel(
            stage.id,
            fenced.assignment.id,
            fenced.lease.fencing_token,
            deadline,
            fenced.now,
            grace_deadline_at=fenced.now + timedelta(seconds=grace),
        )
        monitor(
            uow,
            ctx,
            fenced.run,
            name="timeout_enforcer",
            rule="emergency",
            stage=stage,
            thresholds=thresholds,
            verdict="action_required",
            action="cancel",
            reason="RUNTIME_TIMEOUT",
        )
        return False
    grace_deadline = outcome.get("timeout_grace_deadline_at")
    expires = (
        datetime.fromisoformat(grace_deadline)
        if grace_deadline is not None
        else datetime.fromisoformat(requested) + timedelta(seconds=grace)
    )
    if fenced.now < expires:
        return False
    terminal_stage(uow, ctx, fenced, stage, code=cancellation_code(stage) or "RUNTIME_TIMEOUT")
    close_effects(uow, ctx, fenced)
    revoke_authority(uow, ctx, fenced)
    uow.repo(IntegrationSlotRepository).release_for_attempt(fenced.attempt.id)
    repo = uow.repo(AssignmentRepository)
    completed = transition_assignment(fenced.assignment, AssignmentState.COMPLETED)
    repo.save(completed, expected_version=fenced.assignment.row_version)
    repo.drop_lease(completed.id)
    fenced.assignment = completed
    fenced.run = uow.repo(RunRepository).get(fenced.run.id)
    lease_recovery(uow, ctx, fenced, stage, False)
    return True


def expire_decisions(uow: UnitOfWork, ctx: Any, run: Any, values: Any, limit: int) -> int:
    count = 0
    for candidate in sorted(uow.repo(TaskRepository).list_for_run(run.id), key=lambda t: str(t.id)):
        task = uow.repo(TaskRepository).get(candidate.id, for_update=True)
        for request in uow.repo(DecisionRepository).open_for_task(task.id):
            if count >= limit or request.deadline_at is None or request.deadline_at >= control_now(uow):
                continue
            uow.repo(DecisionRepository).save(replace(request, state=DecisionState.EXPIRED))
            count += 1
            if (
                values.get("execution.questions.on_expired", "keep_waiting") == "fail_task"
                and task.status not in TERMINAL_TASK_STATUSES
            ):
                if task.current_attempt_id:
                    attempt = uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
                    close_attempt(
                        uow, ctx, run, attempt, code="DECISION_EXPIRED", reason=AttemptEndReason.FAILED
                    )
                move(
                    uow, ctx, run, task, TaskStatus.FAILED, cause("wait_changed", codes=["DECISION_EXPIRED"])
                )
                emit(
                    uow,
                    run,
                    "task-failed",
                    {"task_id": str(task.id), "code": "DECISION_EXPIRED"},
                    cause("wait_changed"),
                )
    return count


def handle(cmd: EnforceTimeouts, ctx: Any, uow: UnitOfWork) -> EnforceTimeoutsResult:
    system_guard(ctx)
    ctx = server_context(ctx, uow)
    wire: Any = enforce_timeouts_from_json(cmd)
    limit = wire.get("limit", 100)
    repo = uow.repo(RunRepository)
    ids = (RunId(UUID(wire["run_id"])),) if wire.get("run_id") else repo.list_active_ids(limit=2**31 - 1)
    failed = requested = expired = 0
    diagnostics: list[Any] = []
    for candidate_run in repo.lock_active(ids):
        run = candidate_run
        _, values = effective_values(uow, run.id)
        # Expire deadlines even while paused; pause never destroys saved continuations.
        expired += expire_decisions(uow, ctx, run, values, max(0, limit - expired))
        wall = ceilings(
            value(ctx.config, "budgets.run.max_wall_seconds", 0),
            values.get("budgets.run.max_wall_seconds", 0),
        )
        if wall and run.status in {RunStatus.RUNNING, RunStatus.WAITING}:
            spent = repo.active_seconds(run.id, control_now(uow))
            if spent > wall:
                run = pause_for(uow, ctx, run, "BUDGET_EXHAUSTED")
                monitor(
                    uow,
                    ctx,
                    run,
                    name="timeout_enforcer",
                    rule="active_wall",
                    thresholds={"active_seconds": spent, "max_wall_seconds": wall},
                    verdict="action_required",
                    action="pause",
                    reason="BUDGET_EXHAUSTED",
                )
        for assignment in sorted(
            assignments_for_run(uow, run.id), key=lambda a: (str(a.task_id), str(a.attempt_id), str(a.id))
        ):
            if assignment.state is not AssignmentState.LEASED or requested + failed >= limit:
                continue
            fenced = lock_ownership(uow, assignment)
            if fenced is None:
                continue
            stage = uow.repo(StageRepository).started_without_result(assignment.attempt_id)
            if stage is None:
                continue
            stage = uow.repo(StageRepository).get(stage.id, for_update=True)
            if stage.state not in ACTIVE_STAGE_STATES:
                continue
            now = control_now(uow)
            fenced.now = now
            deadline, thresholds = stage_deadline(uow, ctx, fenced.attempt, stage, values)
            cancellation: Any = stage.outcome or {}
            if cancellation.get("timeout_requested_at"):
                saved_deadline = datetime.fromisoformat(cancellation["timeout_deadline_at"])
                deadline = min(deadline, saved_deadline) if deadline is not None else saved_deadline
            diagnostics.extend(warnings(uow, ctx, run, fenced.attempt, stage, now))
            if deadline is None or deadline >= now:
                continue
            if timeout_stage(uow, ctx, fenced, stage, deadline, thresholds):
                failed += 1
            else:
                requested += 1
    return EnforceTimeoutsResult(
        enforce_timeouts_result_from_json(
            {
                "cancel_requested": requested,
                "failed": failed,
                "decisions_expired": expired,
                "diagnostics": diagnostics[:100],
            }
        )
    )


SPEC = CommandSpec(
    name="execution.enforce_timeouts",
    dto=EnforceTimeouts,
    result=EnforceTimeoutsResult,
    permission="run.control",
    permissions_of=lambda _cmd: ("system.internal",),
    scope_of=None,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
    internal=True,
)
