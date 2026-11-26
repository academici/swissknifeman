"""Atomic stage cursor consumption and pinned agent preparation."""

from typing import Any

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.context.public import get_manifest
from skm.modules.execution.application._admission import require_run_admission
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._incident_gate import is_repair, verify_repair
from skm.modules.execution.application._integration_inputs import prepare_integration
from skm.modules.execution.application._primitives import move, save_attempt
from skm.modules.execution.application._stage_preparation import (
    issue_step_token,
    prepare_agent_step,
    ready_step,
)
from skm.modules.execution.application._state import effective_values, load_state
from skm.modules.execution.application._worker_dtos import BeginStage, BeginStageResult, document
from skm.modules.execution.application._worker_events import stage_started
from skm.modules.execution.application._worker_host_stages import (
    prepare_checks,
    prepare_review,
    resume_review,
)
from skm.modules.execution.application._worker_protocol import (
    fenced_scope,
    instruction,
    lock_fenced_context,
    locked_stage,
    next_instruction,
    revoke_authority,
    verify_fenced_replay,
)
from skm.modules.execution.application._worker_result import committed_refusal
from skm.modules.execution.application.commands.reconcile_external_effect import admin_context, begin_admin
from skm.modules.execution.application.commands.record_external_effect import prepare_external
from skm.modules.execution.domain.attempt import StageContinuation, bind_executor_route, consume_stage
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.stage_record import (
    ACTIVE_STAGE_STATES,
    AGENT_STAGE_TYPES,
    StageState,
    begin_stage_record,
)
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import StageRepository, StepRepository


def store_host_content(uow: UnitOfWork, step: Any) -> bool:
    snapshot = get_manifest(uow, step.context_manifest_id).route.get("render_snapshot")
    return isinstance(snapshot, dict) and snapshot.get("store_host_content") is True


def refuse(code: str, *, stage: Any = None, reason: str = "paused", details: Any = None) -> BeginStageResult:
    return BeginStageResult(
        outcome="refused",
        stage_record_id=None if stage is None else str(stage.id),
        already_completed=False,
        refusal={"code": code, "details": details or {}},
        next={"kind": "release", "release_reason": reason},
    )


def handle(  # noqa: PLR0912, PLR0915 -- one atomic worker protocol transition
    cmd: BeginStage, ctx: Any, uow: UnitOfWork
) -> BeginStageResult:
    admin = admin_context(uow, ctx, cmd["claim"], allow_closed=True)
    if admin is not None:
        return begin_admin(cmd, ctx, uow, admin)
    fenced = lock_fenced_context(uow, ctx, cmd["claim"], allow_terminal=True)
    repo = uow.repo(StageRepository)
    found = repo.find(fenced.attempt.id, cmd["stage_id"], cmd["round_no"], cmd["input_digest"])
    if found is not None:
        found = locked_stage(uow, fenced, found.id)
        if found.state is StageState.COMPLETED:
            return BeginStageResult(
                outcome="already_completed",
                stage_record_id=str(found.id),
                already_completed=True,
                prior_outcome=document(found.outcome or {}),
            )
        if found.state not in ACTIVE_STAGE_STATES:
            result = refuse(found.error_code or "INVALID_TRANSITION", stage=found, reason="waiting")
            result["next"] = next_instruction(uow, fenced)
            return result
    if fenced.run.status.value != "running":
        return refuse(
            "RUN_NOT_ACTIVE", reason="paused" if fenced.run.status.value == "paused" else "cancelled"
        )
    loaded, values = effective_values(uow, fenced.run.id)
    try:
        require_run_admission(uow, ctx, fenced.run, values)
    except SkmError as exc:
        return refuse("POLICY_DENIES" if exc.code is not ErrorCode.BUDGET_EXHAUSTED else "BUDGET_EXHAUSTED")
    if found is not None:
        result = BeginStageResult(outcome="ready", stage_record_id=str(found.id), already_completed=False)
        steps = uow.repo(StepRepository).for_stage(found.id)
        if found.stage_type == "integrate":
            found_metadata: Any = found.outcome or {}
            result["integrate"] = (
                prepare_external(uow, fenced, found)
                if found_metadata.get("external_effect_id")
                else prepare_integration(uow, fenced, found)
            )
        if steps:
            token = issue_step_token(uow, ctx, fenced, steps[0], cmd.get("runtime_token_secret"))
            result["step"] = ready_step(uow, ctx, fenced, steps[0], token=token)
            result["step"]["context"]["store_host_content"] = store_host_content(uow, steps[0])
            if found.stage_type == "agent_review":
                result["review"] = resume_review(uow, fenced, steps[0])
        return result
    cursor = fenced.attempt.continuation
    if not isinstance(cursor, StageContinuation):
        raise error_for(ErrorCode.INVALID_TRANSITION, "no pending stage template")
    expected = instruction(uow, fenced.attempt)
    if (cmd["stage_id"], cmd["round_no"], cmd["input_digest"]) != (
        expected["stage_id"],
        expected["round_no"],
        expected["input_digest"],
    ):
        raise error_for(ErrorCode.INVALID_TRANSITION, "stage template or input digest changed")
    selected = cursor.stage
    if fenced.run.autopilot and is_repair(selected):
        state, _ = load_state(uow, fenced.task.id)
        selected = verify_repair(uow, ctx, state, selected)
    if selected.not_before is not None and selected.not_before > fenced.now:
        raise error_for(ErrorCode.INVALID_TRANSITION, "stage backoff has not elapsed")
    history = tuple(e.record for e in repo.history(fenced.attempt.id).entries)
    stage = begin_stage_record(
        history,
        record_id=ctx.ids.new_id(),
        attempt_id=fenced.attempt.id,
        run_id=fenced.run.id,
        task_id=fenced.task.id,
        stage_id=selected.stage_id,
        stage_type=selected.stage_type,
        round_no=selected.round_no,
        mode=selected.mode,
        input_digest=cmd["input_digest"],
        fencing_token=fenced.claim.fencing_token,
        now=fenced.now,
        retry_of_id=selected.retry_of_id,
    )
    attempt, _ = consume_stage(fenced.attempt, continuation_id=cursor.continuation_id)
    save_attempt(uow, attempt)
    fenced.attempt = attempt
    repo.add(stage)
    if fenced.task.status in {TaskStatus.ASSIGNED, TaskStatus.REWORK_REQUIRED}:
        fenced.task = move(uow, ctx, fenced.run, fenced.task, TaskStatus.EXECUTING, cause("stage_outcome"))
        emit(
            uow,
            fenced.run,
            "attempt-started",
            {
                "task_id": str(fenced.task.id),
                "attempt_id": str(attempt.id),
                "attempt_no": attempt.attempt_no,
                "worker_id": str(fenced.claim.worker_id),
                "host_id": str(fenced.worker.host_id),
            },
            cause("manual_start"),
        )
    result = BeginStageResult(outcome="ready", stage_record_id=str(stage.id), already_completed=False)
    steps = ()
    if selected.stage_type in AGENT_STAGE_TYPES:
        revoke_authority(uow, ctx, fenced)
        try:
            step, payload = prepare_agent_step(
                uow, ctx, fenced, stage, selected, cmd.get("runtime_token_secret")
            )
            result["step"], steps = payload, (step,)
            payload["context"]["store_host_content"] = store_host_content(uow, step)
            if step.role.value == "executor":
                fenced.attempt = bind_executor_route(
                    fenced.attempt, RouteRef(step.runtime_id, step.model, step.effort)
                )
                save_attempt(uow, fenced.attempt)
            if selected.stage_type == "agent_review":
                result["review"] = prepare_review(uow, ctx, fenced, stage, step, selected)
        except SkmError as exc:
            if exc.code not in {
                ErrorCode.BUDGET_EXHAUSTED,
                ErrorCode.ADMISSION_REFUSED,
                ErrorCode.CAPABILITY_UNAVAILABLE,
                ErrorCode.ROUTE_UNDERSHOOT,
                ErrorCode.EXTENSION_INCOMPATIBLE,
                ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH,
            }:
                raise

            committed_refusal(uow, ctx, fenced, stage, code=exc.code.value)
            result = refuse(exc.code.value, stage=stage, reason="waiting")
            result["next"] = next_instruction(uow, fenced)
            return result
    if selected.stage_type == "run_checks":
        result["checks"] = prepare_checks(uow, ctx, fenced, stage, selected)
    if selected.stage_type == "integrate":
        result["integrate"] = (
            prepare_external(uow, fenced, stage, selected.params["effect_id"])
            if selected.params.get("effect_id")
            else prepare_integration(uow, fenced, stage)
        )
    stage_started(uow, fenced, stage, selected, loaded, steps)
    return result


SPEC = CommandSpec(
    name="execution.begin_stage",
    dto=BeginStage,
    result=BeginStageResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
    replay_guard=verify_fenced_replay,
)
