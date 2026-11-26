"""Persisted supervisor evaluations; server deadlines and containment facts stay separate."""

from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.execution.application._control import assignments_for_run
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._primitives import server_context
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application._worker_protocol import revoke_authority
from skm.modules.execution.application._worker_result import advance_terminal
from skm.modules.execution.application.commands.enforce_timeouts import pause_for, stage_deadline
from skm.modules.execution.application.commands.expire_leases import (
    control_now,
    lease_recovery,
    lock_ownership,
    system_guard,
    terminal_stage,
)
from skm.modules.execution.application.commands.report_attempt_failure import close_effects
from skm.modules.execution.domain.assignment import AssignmentState, transition_assignment
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.health import classify_run_health
from skm.modules.execution.domain.recovery import RecoveryRecord, RecoveryStep, plan_recovery
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.generated.commands import detect_stalls_from_json
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    DecisionRepository,
    ExecutionQueries,
    IntegrationSlotRepository,
    RecoveryRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, ScopeTree


class DetectStalls(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:detect-stalls:v1"


class DetectStallsResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:detect-stalls:v1"


def evaluate(
    uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, record: Any, facts: Any, action: str
) -> None:
    now = control_now(uow).isoformat()
    emit(
        uow,
        fenced.run,
        "monitor-evaluated",
        {
            "evaluation_id": ctx.meta.request_id,
            "monitor_id": "stall_detector",
            "rule_id": "safe_recovery",
            "rule_version": "1",
            "config_digest": ctx.config.digest,
            "config_generation": ctx.config.generation,
            "target_stage_record_id": str(stage.id),
            "fencing_token": stage.fencing_token,
            "input_watermark": facts["input_watermark"],
            "input_coverage": "partial",
            "last_signal_at": facts["last_heartbeat_at"],
            "thresholds": [
                {
                    "key": (
                        "execution.stall.idle_seconds" if k == "idle_seconds" else "execution.health." + k
                    ),
                    "value": v,
                }
                for k, v in facts["thresholds"].items()
            ],
            "scheduled_at": ctx.meta.received_at.isoformat(),
            "started_at": facts.get("evaluation_started_at", now),
            "finished_at": now,
            "verdict": "waiting" if record.outcome == "not_needed" else "action_required",
            "action": action,
            "action_request_id": ctx.meta.request_id if action == "cancel" else None,
            "recovery_record_id": str(record.id),
            "recovery_mode": value(ctx.config, "execution.supervisor.recover", "notify"),
            "reason_code": record.reason_codes[-1] if record.reason_codes else "STALL_SUSPECTED",
        },
        cause("lease_recovery"),
    )


def finish(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, record: Any, mode: str) -> Any:
    """Step six shares ordinary emergency budget, effects, revoke and fencing closure."""
    terminal = terminal_stage(uow, ctx, fenced, stage, code="RUNTIME_TIMEOUT")
    close_effects(uow, ctx, fenced, code="RUNTIME_TIMEOUT")
    revoke_authority(uow, ctx, fenced)
    uow.repo(IntegrationSlotRepository).release_for_attempt(fenced.attempt.id)
    repo = uow.repo(AssignmentRepository)
    closed = transition_assignment(fenced.assignment, AssignmentState.COMPLETED)
    repo.save(closed, expected_version=fenced.assignment.row_version)
    repo.drop_lease(closed.id)
    fenced.assignment = closed
    record = replace(record, steps_done=(*record.steps_done, RecoveryStep.RECONCILE))
    # count_since is inclusive; PostgreSQL and datetime store microsecond instants.
    count = uow.repo(RecoveryRepository).count_since(
        fenced.run.id,
        fenced.now
        - timedelta(seconds=int(value(ctx.config, "execution.supervisor.window_seconds", 3600)))
        + timedelta(microseconds=1),
        frozenset({"retried", "new_attempt"}),
    )
    circuit = count >= int(value(ctx.config, "execution.supervisor.max_recoveries", 2))
    if circuit or mode == "stop_only" or not uow.repo(StageRepository).reap_confirmed(stage.id):
        code = "RECOVERY_CIRCUIT_OPEN" if circuit else "RUNTIME_TIMEOUT"
        pause_for(uow, ctx, fenced.run, code)
        request = DecisionRequest(
            ctx.ids.new_id(),
            fenced.run.workspace_id,
            fenced.run.id,
            fenced.task.id,
            DecisionKind.ESCALATION,
            Audience.OWNER,
            None,
            frozenset(),
            None,
            None,
            1,
            {"code": code, "options": ["resume_run", "cancel_run"]},
            None,
            {},
            DecisionState.OPEN,
            None,
            None,
            fenced.now,
        )
        uow.repo(DecisionRepository).add(request)
        if circuit:
            emit(
                uow,
                fenced.run,
                "recovery-circuit-opened",
                {
                    "window_seconds": int(value(ctx.config, "execution.supervisor.window_seconds", 3600)),
                    "max_recoveries": int(value(ctx.config, "execution.supervisor.max_recoveries", 2)),
                    "recoveries_in_window": count,
                },
                cause("lease_recovery", codes=[code]),
            )
        record = replace(record, outcome="escalated", reason_codes=(*record.reason_codes, code))
    else:
        advance_terminal(uow, ctx, fenced, terminal)
        task = uow.repo(TaskRepository).get(fenced.task.id)
        attempt = uow.repo(AttemptRepository).get(fenced.attempt.id)
        new_attempt = task.current_attempt_id is not None and task.current_attempt_id != fenced.attempt.id
        advanced = new_attempt or (attempt.continuation is not None and attempt.continuation.kind == "stage")
        record = replace(
            record,
            steps_done=(*record.steps_done, RecoveryStep.RETRY_STEP) if advanced else record.steps_done,
            outcome="new_attempt" if new_attempt else "retried" if advanced else "escalated",
        )
    uow.repo(RecoveryRepository).save(record)
    fenced.run = uow.repo(RunRepository).get(fenced.run.id)
    if not uow.repo(StageRepository).reap_confirmed(stage.id):
        lease_recovery(uow, ctx, fenced, stage, False)
    return record


def identity_bound(fenced: Any, stage: Any) -> bool:
    if not stage.process_identities or stage.fencing_token != fenced.lease.fencing_token:
        return False
    expected = {
        "attempt_id": fenced.attempt.id,
        "stage_record_id": stage.id,
        "worker_id": fenced.lease.worker_id,
        "host_id": fenced.attempt.host_id,
    }
    for identity in stage.process_identities:
        owner = identity.ownership.get("owner")
        if not isinstance(owner, dict) or any(
            str(cast("dict[str, Any]", owner).get(k)) != str(v) for k, v in expected.items()
        ):
            return False
    return True


def recover(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, values: Any) -> bool:
    now = fenced.now = control_now(uow)
    deadline, _ = stage_deadline(uow, ctx, fenced.attempt, stage, values)
    policy = {
        k: value(ctx.config, f"execution.supervisor.{k}", default)
        for k, default in (("recover", "notify"), ("grace_seconds", 60))
    }
    grace = int(policy["grace_seconds"])
    steps = uow.repo(StepRepository).for_stage(stage.id)
    facts: Any = {
        "status": fenced.run.status.value,
        "active_units": 1,
        "last_heartbeat_at": fenced.lease.last_heartbeat_at.isoformat(),
        "input_watermark": uow.repo(ExecutionQueries).head_run_seq(fenced.run.id),
        "deadline_at": deadline.isoformat() if deadline else None,
        "waiting_tool": stage.stage_type == "run_checks",
        "heartbeat_available": True,
        "thresholds": {"hung_after_seconds": value(ctx.config, "execution.health.hung_after_seconds", 300)},
        "deadline_expired": deadline is not None and deadline < now,
        "evaluation_started_at": now.isoformat(),
    }
    if steps:
        step = steps[-1]
        activity: Any = step.activity or {}
        facts.update(
            last_progress_at=step.last_progress_at.isoformat() if step.last_progress_at else None,
            cpu_active=activity.get("cpu_active"),
            repeated_command_count=activity.get("repeated_command_count", 0),
        )
    facts["thresholds"].update(
        {
            "idle_seconds": value(ctx.config, "execution.stall.idle_seconds", 5400),
            "stall_repeat_n": value(ctx.config, "execution.health.stall_repeat_n", 5),
            "wait_grace_seconds": value(ctx.config, "execution.health.wait_grace_seconds", 60),
        }
    )
    repo = uow.repo(RecoveryRepository)
    record = repo.open_for_stage(stage.id)
    health = classify_run_health(facts, now)
    if record is None and health.health.value not in {"hung", "suspected_stall"}:
        return False
    observation = {
        "heartbeat": facts["last_heartbeat_at"],
        "progress": facts.get("last_progress_at"),
        "config_digest": ctx.config.digest,
        "config_generation": ctx.config.generation,
        "deadline_expired": facts["deadline_expired"],
    }
    prior_outcome: Any = stage.outcome or {}
    if record is None and prior_outcome.get("supervisor_notified") == observation:
        return False
    if record is None:
        record = RecoveryRecord(
            ctx.ids.new_id(),
            fenced.run.id,
            fenced.task.id,
            fenced.attempt.id,
            stage.id,
            steps[0].id if steps else None,
            "hung" if health.health.value == "hung" else "suspected_stall",
            (RecoveryStep.VERIFY_LEGIT,),
            None,
            None,
            (),
            now,
        )
        repo.add(record)
        evaluate(uow, ctx, fenced, stage, record, facts, "snapshot")
        return True
    if record.snapshot_file_version_id is None and now < record.at + timedelta(seconds=grace):
        return False
    done = list(record.steps_done)
    if RecoveryStep.SNAPSHOT not in done:
        done.extend((RecoveryStep.SNAPSHOT, RecoveryStep.VERIFY_IDENTITY))
        record = replace(
            record,
            steps_done=tuple(done),
            reason_codes=record.reason_codes
            + (() if record.snapshot_file_version_id else ("SNAPSHOT_MISSING",)),
        )
    # A saved binding is evidence for the worker to verify against the live containment;
    # it is never treated as OS-empty proof by this control-plane command.
    facts["identity_verified"] = identity_bound(fenced, stage)
    activity: Any = steps[-1].activity if steps else None
    facts["legitimate_wait"] = (
        deadline is not None
        and deadline > now
        and isinstance(activity, dict)
        and cast("dict[str, Any]", activity).get("tool_running") is True
        and cast("dict[str, Any]", activity).get("cpu_active") is True
    )
    plan = plan_recovery(facts, policy)
    if RecoveryStep.RECONCILE not in plan:
        record = replace(record, outcome="not_needed")
        uow.repo(StageRepository).save(
            replace(stage, outcome={**(stage.outcome or {}), "supervisor_notified": observation})
        )
    elif RecoveryStep.COOPERATIVE_CANCEL in plan:
        outcome: Any = stage.outcome or {}
        requested = outcome.get("timeout_requested_at")
        if requested is None:
            if deadline is None:
                # plan_recovery cancels only for an expired deadline; no other cancel fact is set here
                raise InternalError(ErrorCode.INTERNAL_ERROR, "cooperative cancel planned without a deadline")
            uow.repo(StageRepository).request_cancel(
                stage.id,
                fenced.assignment.id,
                fenced.lease.fencing_token,
                deadline,
                now,
                grace_deadline_at=now + timedelta(seconds=grace * 2),
            )
            record = replace(record, steps_done=(*record.steps_done, RecoveryStep.COOPERATIVE_CANCEL))
        elif now >= datetime.fromisoformat(outcome["timeout_grace_deadline_at"]):
            record = replace(
                record,
                steps_done=record.steps_done,
                reason_codes=(*record.reason_codes, "STOP_UNCONFIRMED"),
            )
            record = finish(uow, ctx, fenced, stage, record, str(policy["recover"]))
    else:
        record = replace(record, reason_codes=(*record.reason_codes, "OWNERSHIP_UNKNOWN"))
        record = finish(uow, ctx, fenced, stage, record, str(policy["recover"]))
    if repo.open_for_stage(stage.id) is not None:
        repo.save(record)
    evaluate(
        uow,
        ctx,
        fenced,
        stage,
        record,
        facts,
        "none" if record.outcome == "not_needed" else "recover" if record.outcome else "cancel",
    )
    return True


def close_completed(uow: UnitOfWork, ctx: Any, run: Any) -> None:
    """A worker may finish while snapshot/cancel is in flight; do not leave an open barrier."""
    recoveries = uow.repo(RecoveryRepository)
    stages = uow.repo(StageRepository)
    for task in sorted(uow.repo(TaskRepository).list_for_run(run.id), key=lambda row: str(row.id)):
        uow.repo(TaskRepository).get(task.id, for_update=True)
        for attempt in uow.repo(AttemptRepository).list_for_task(task.id):
            uow.repo(AttemptRepository).get(attempt.id, for_update=True)
            for entry in stages.history(attempt.id).entries:
                stage = entry.record
                if stage.state in ACTIVE_STAGE_STATES:
                    continue
                record = recoveries.open_for_stage(stage.id)
                if record is None:
                    continue
                stage = stages.get(stage.id, for_update=True)
                record = replace(
                    record,
                    outcome="not_needed",
                    reason_codes=(*record.reason_codes, "STAGE_ALREADY_COMPLETED"),
                )
                recoveries.save(record)
                evaluate(
                    uow,
                    ctx,
                    SimpleNamespace(run=run),
                    stage,
                    record,
                    {
                        "input_watermark": uow.repo(ExecutionQueries).head_run_seq(run.id),
                        "last_heartbeat_at": None,
                        "thresholds": {},
                    },
                    "none",
                )


def handle(cmd: DetectStalls, ctx: Any, uow: UnitOfWork) -> DetectStallsResult:
    system_guard(ctx)
    ctx = server_context(ctx, uow)
    wire: Any = detect_stalls_from_json(cmd)
    limit = wire.get("limit", 100)
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be positive")
    runs = uow.repo(RunRepository)
    ids = (RunId(UUID(wire["run_id"])),) if wire.get("run_id") else runs.list_active_ids(limit=2**31 - 1)
    detected = 0
    loader = ConfigLoader(ctx.config.registry, EmptyPackConfigSource())
    for run in runs.lock_active(ids):
        config = loader.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.RUN, ScopeId(run.id))
        )
        ctx = replace(ctx, config=config)
        close_completed(uow, ctx, run)
        _, values = effective_values(uow, run.id)
        for assignment in assignments_for_run(uow, run.id):
            if detected >= limit:
                break
            fenced = lock_ownership(uow, assignment)
            if fenced is None:
                continue
            stage = uow.repo(StageRepository).started_without_result(assignment.attempt_id)
            if stage is None:
                continue
            stage = uow.repo(StageRepository).get(stage.id, for_update=True)
            if stage.state in ACTIVE_STAGE_STATES and stage.fencing_token == fenced.lease.fencing_token:
                detected += recover(uow, ctx, fenced, stage, values)
    return DetectStallsResult(detected=detected)


SPEC = CommandSpec(
    name="execution.detect_stalls",
    dto=DetectStalls,
    result=DetectStallsResult,
    permission="run.control",
    permissions_of=lambda _cmd: ("system.internal",),
    scope_of=None,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
    internal=True,
)
