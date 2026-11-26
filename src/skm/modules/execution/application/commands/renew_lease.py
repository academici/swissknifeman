"""Lease heartbeat and atomic final-context runtime admission."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from skm.application_bus.ports import IdempotencyStore
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.context.public import (
    require_final,
)
from skm.modules.execution.application._admission import require_run_admission
from skm.modules.execution.application._json_reads import obj, optional_text, text, texts
from skm.modules.execution.application._live_control import cancellation_code
from skm.modules.execution.application._stage_agent_helpers import estimate, live_step_profile_and_permissions
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._tool_calls import record_calls
from skm.modules.execution.application._worker_budget import amounts, priced_usage, replace_runtime_reserve
from skm.modules.execution.application._worker_dtos import RenewLease, RenewLeaseResult
from skm.modules.execution.application._worker_events import runtime_admitted
from skm.modules.execution.application._worker_evidence import register
from skm.modules.execution.application._worker_protocol import (
    FencedContext,
    fenced_scope,
    lock_fenced_context,
    locked_stage,
    next_instruction,
    parse_worker_claim,
    process_identity,
    verify_completed_assignment,
    verify_current_lease,
    verify_worker,
)
from skm.modules.execution.application._worker_result import committed_refusal, interrupt_paused_handoff
from skm.modules.execution.application.commands.reconcile_external_effect import (
    admin_context,
    bound_effect,
    renew_admin,
    require_read,
)
from skm.modules.execution.application.commands.record_external_effect import validate_target
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.domain.ids import CheckExecutionId, ExternalEffectId, StageRecordId, StepId
from skm.modules.execution.domain.lease import renew_lease, verify_fence
from skm.modules.execution.domain.stage_record import (
    ACTIVE_STAGE_STATES,
    AGENT_STAGE_TYPES,
    TERMINAL_STAGE_STATES,
    StageState,
    mark_runtime_started,
    record_process_identity,
)
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    CheckRepository,
    EffectRepository,
    IntegrationSlotRepository,
    RecoveryRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.policy.public import (
    permissions_digest,
)
from skm.modules.runtimes.public import Effort, RouteKey, host_route_is_fresh


def _require_runtime_authority(uow: UnitOfWork, ctx: Any, fenced: FencedContext, step: Any) -> Any:
    _, values = effective_values(uow, fenced.run.id)
    require_run_admission(uow, ctx, fenced.run, values)
    _, profile, perms = live_step_profile_and_permissions(uow, ctx, fenced, step)
    if permissions_digest(perms) != step.session_fingerprint.authority_digest:
        raise error_for(ErrorCode.FORBIDDEN, "live authority narrowed after context assembly")
    raw_binding = step.admission.get("runtime_token")
    if not raw_binding:
        raise error_for(ErrorCode.FORBIDDEN, "runtime token binding is missing")
    binding = obj(raw_binding, "admission.runtime_token")
    runtime_actor = Actor(
        ctx.actor.principal_id,
        PrincipalKind.WORKER,
        ctx.actor.display_name,
        TokenGrant(
            UUID(text(binding["token_id"], "runtime_token.token_id")),
            "assignment",
            ScopeId(fenced.run.id),
            frozenset(texts(binding["permissions"], "runtime_token.permissions")),
            fenced.assignment.id,
            step.id,
            tuple(
                ScopeId(UUID(v)) for v in texts(binding["scope_ancestors"], "runtime_token.scope_ancestors")
            ),
        ),
    )
    access.RbacAuthorizer(cast("Any", SimpleNamespace(now=lambda: fenced.now))).admit(uow, runtime_actor)
    return profile


def _require_current_worker(uow: UnitOfWork, ctx: Any, fenced: FencedContext, *, lock: bool = False) -> None:
    grant = ctx.actor.grant
    now = uow.repo(RunRepository).now if lock else fenced.now
    if grant is None or not access.worker_credential_current(
        uow, grant.token_id, fenced.worker.worker_id, now=now, lock=lock
    ):
        raise error_for(ErrorCode.FORBIDDEN, "Runtime handoff requires the current worker credential")


def _require_runtime_offer(uow: UnitOfWork, ctx: Any, fenced: FencedContext, step: Any) -> None:
    snapshot: JsonObject = step.route_snapshot or {}
    if (
        step.effort is None
        or step.runtime_id not in fenced.worker.capabilities.runtimes
        or step.runtime_id not in fenced.lease.offered_runtimes
        or not host_route_is_fresh(
            uow,
            ctx.config,
            fenced.worker.host_id,
            RouteKey(step.runtime_id, step.model, Effort(step.effort)),
            as_of=fenced.now,
            worker_id=fenced.worker.worker_id,
            runtime_version=optional_text(
                snapshot.get("runtime_version"),
                "route_snapshot.runtime_version",
            ),
            binary_sha256=optional_text(
                snapshot.get("executable_sha256"),
                "route_snapshot.executable_sha256",
            ),
        )
    ):
        raise error_for(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "the pinned host route offer expired or was disabled",
        )


def handle(  # noqa: PLR0912, PLR0915 -- one atomic worker protocol transition
    cmd: RenewLease, ctx: Any, uow: UnitOfWork
) -> RenewLeaseResult:
    progress = cmd.get("progress", {})
    handoff = progress.get("phase") == "runtime_started"
    calls = progress.get("tool_calls")

    admin = admin_context(uow, ctx, cmd["claim"])
    if admin is not None:
        if calls is not None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "reconciliation has no runtime tool calls")
        return renew_admin(cmd, ctx, uow, admin)
    fenced = lock_fenced_context(uow, ctx, cmd["claim"], heartbeat=not handoff and calls is None)
    stage: Any = None
    steps = ()
    if progress.get("stage_record_id"):
        stage = locked_stage(uow, fenced, progress["stage_record_id"])
        steps = uow.repo(StepRepository).for_stage(stage.id)
        if stage.state not in ACTIVE_STAGE_STATES:
            raise error_for(ErrorCode.INVALID_TRANSITION, "terminal stage cannot renew progress")
    elif progress.get("step_id") or handoff or progress.get("process"):
        raise error_for(ErrorCode.INVALID_TRANSITION, "stage identity is required")
    step = next((s for s in steps if str(s.id) == progress.get("step_id")), None)
    if progress.get("step_id") and (step is None or step.state is not StepState.STARTED):
        raise error_for(ErrorCode.INVALID_TRANSITION, "progress step is foreign or terminal")
    cancel = fenced.run.status.value in {"paused", "cancelled"} or uow.repo(StageRepository).cancel_requested(
        fenced.attempt.id, fenced.claim.fencing_token
    )
    if calls is not None:
        if handoff or stage is None or step is None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "tool observations require an owned runtime step")
        cancel = record_calls(uow, ctx, fenced, stage, step, calls) or cancel
    if handoff:
        if stage is None or step is None or stage.stage_type not in AGENT_STAGE_TYPES:
            raise error_for(ErrorCode.INVALID_TRANSITION, "runtime handoff requires an agent stage and step")
        # A first handoff may grant launch authority. Replays and heartbeats never lock this row.
        _require_current_worker(uow, ctx, fenced, lock=stage.runtime_started_at is None)
        if stage.runtime_started_at is not None:
            raise error_for(
                ErrorCode.INVALID_TRANSITION, "Runtime handoff requires its original idempotency key"
            )
        # The token lock may have waited. The offer and lease use the resulting server time.
        fenced.now = max(fenced.now, uow.repo(RunRepository).now())
        verify_current_lease(uow, fenced.assignment, fenced.lease, fenced.claim, fenced.now)
        if cancel or fenced.run.status.value != "running":
            code = cancellation_code(stage) or "RUN_NOT_ACTIVE"
            if fenced.run.status.value == "paused":
                interrupt_paused_handoff(uow, ctx, fenced, stage)
            else:
                committed_refusal(uow, ctx, fenced, stage, code=code)
            return RenewLeaseResult(
                lease_expires_at=fenced.lease.expires_at.isoformat(),
                cancel_requested=True,
                snapshot_requested=False,
                refusal={"code": code, "details": {}},
                next=next_instruction(uow, fenced),
            )
        manifest = require_final(uow, step.context_manifest_id)
        if manifest.owner_ref != f"step:{step.id}":
            raise error_for(ErrorCode.FORBIDDEN, "manifest belongs to another step")
        try:
            profile = _require_runtime_authority(uow, ctx, fenced, step)
            _require_runtime_offer(uow, ctx, fenced, step)
            if manifest.total_tokens_estimate is None:
                raise error_for(ErrorCode.CONTEXT_NOT_FINALIZED, "final prompt estimate is unavailable")
            estimate_usage = estimate(
                uow,
                ctx,
                fenced,
                step,
                manifest.total_tokens_estimate,
                profile.limits.max_output_tokens or 0,
            )
            replace_runtime_reserve(
                uow, ctx, fenced, step, amounts(estimate_usage, review=step.role.value == "reviewer")
            )
        except SkmError as exc:
            if exc.code not in {
                ErrorCode.BUDGET_EXHAUSTED,
                ErrorCode.FORBIDDEN,
                ErrorCode.UNAUTHENTICATED,
                ErrorCode.PROJECT_ARCHIVED,
                ErrorCode.PLAN_ARCHIVED,
                ErrorCode.EMERGENCY_STOPPED,
                ErrorCode.CAPABILITY_UNAVAILABLE,
            }:
                raise
            code = (
                exc.code.value
                if exc.code in {ErrorCode.BUDGET_EXHAUSTED, ErrorCode.CAPABILITY_UNAVAILABLE}
                else "POLICY_DENIES"
            )
            committed_refusal(uow, ctx, fenced, stage, code=code)
            return RenewLeaseResult(
                lease_expires_at=fenced.lease.expires_at.isoformat(),
                cancel_requested=False,
                snapshot_requested=False,
                refusal={"code": code, "details": exc.details or {}},
                next={"kind": "release", "release_reason": "waiting"},
            )
        stage = mark_runtime_started(stage, now=fenced.now)
        uow.repo(StageRepository).save(stage)
        runtime_admitted(uow, fenced, stage, step)
    if stage is not None and stage.stage_type not in AGENT_STAGE_TYPES and stage.state is StageState.STARTED:
        stage = mark_runtime_started(stage, now=fenced.now)
        uow.repo(StageRepository).save(stage)
    identity = process_identity(progress.get("process"), fenced, stage, steps)
    if identity is not None:
        if stage is None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "process identity requires a stage")
        if identity.unit_key[0] == "check":
            check = uow.repo(CheckRepository).get(CheckExecutionId(UUID(identity.unit_key[1])))
            if check.attempt_id != fenced.attempt.id:
                raise error_for(ErrorCode.INVALID_REFERENCE, "foreign check process")
        if identity.unit_key[0] == "git_effect":
            effect = uow.repo(EffectRepository).get(ExternalEffectId(UUID(identity.unit_key[1])))
            if effect.attempt_id != fenced.attempt.id:
                raise error_for(ErrorCode.INVALID_REFERENCE, "foreign Git process unit")
        stage = record_process_identity(stage, identity)
        if stage.state is StageState.STARTED:
            stage = mark_runtime_started(stage, now=fenced.now)
        uow.repo(StageRepository).save(stage)
    if step is not None:
        uow.repo(StepRepository).touch_progress(
            step.id,
            fenced.now,
            usage_so_far=priced_usage(uow, ctx, fenced, step, progress.get("usage_so_far")),
            identity=identity
            if identity is not None and identity.unit_key == ("step", str(step.id))
            else None,
        )
    recovery = None if stage is None else uow.repo(RecoveryRepository).open_for_stage(stage.id)
    if progress.get("snapshot") is not None:
        if recovery is None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "snapshot requires an open recovery")

        version = register(uow, ctx, fenced, {**progress["snapshot"], "role": "diagnostic"})
        uow.repo(RecoveryRepository).save(replace(recovery, snapshot_file_version_id=version))
    ttl = timedelta(seconds=int(ctx.config.get("execution.lease.ttl_seconds") or 120))
    updated = renew_lease(
        fenced.lease, fenced.assignment, fenced.claim, now=fenced.now, ttl=ttl, process_identity=identity
    )
    uow.repo(AssignmentRepository).renew(
        fenced.lease, expires_at=updated.expires_at, heartbeat_at=fenced.now, identity=identity
    )
    uow.repo(IntegrationSlotRepository).extend(fenced.attempt.id, updated.expires_at)
    access.extend_assignment_tokens(
        uow, assignment_id=fenced.assignment.id, expires_at=updated.expires_at, now=fenced.now
    )
    artifacts.extend_grants(
        uow,
        reason=artifacts.GrantReason.ASSIGNMENT,
        ref=str(fenced.assignment.id),
        expires_at=updated.expires_at
        + timedelta(seconds=int(value(ctx.config, "execution.supervisor.grace_seconds", 60) or 60)),
        now=fenced.now,
    )
    return RenewLeaseResult(
        lease_expires_at=updated.expires_at.isoformat(),
        cancel_requested=cancel,
        snapshot_requested=recovery is not None,
    )


def replay_guard(cmd: Any, ctx: Any, uow: UnitOfWork) -> None:
    """Also runs in the bus's read-only concurrent-receipt UoW: never lock or renew."""
    claim = parse_worker_claim(cmd["claim"])
    repo = uow.repo(AssignmentRepository)
    assignment, lease = repo.get(claim.assignment_id), repo.lease(claim.assignment_id)
    now = uow.repo(RunRepository).now()
    worker = verify_worker(uow, ctx.actor, claim.worker_id, workspace_id=assignment.workspace_id)
    progress = cmd.get("progress", {})
    handoff = progress.get("phase") == "runtime_started"
    receipt = (
        uow.repo(IdempotencyStore).get(
            assignment.workspace_id, ctx.actor.principal_id, "execution.renew_lease", ctx.meta.idempotency_key
        )
        if handoff
        else None
    )
    refused = receipt is not None and receipt.result.get("refusal") is not None
    held = None
    if refused and assignment.state is AssignmentState.COMPLETED:
        verify_completed_assignment(uow, assignment, claim)
    else:
        held = verify_fence(lease, assignment, claim, now)
    if assignment.last_fencing_token != claim.fencing_token:
        raise error_for(ErrorCode.LEASE_LOST, "assignment fencing token changed")
    run = uow.repo(RunRepository).get(assignment.run_id)
    if assignment.reconcile_effect_id is not None:
        require_read(uow, ctx, run, worker)
        effect = bound_effect(uow, assignment, worker.host_id, for_update=False)
        if effect.request.get("binding_identity"):
            validate_target(uow, SimpleNamespace(worker=worker, run=run, now=now), effect.request)
    else:
        task = uow.repo(TaskRepository).get(assignment.task_id)
        attempt = uow.repo(AttemptRepository).get(assignment.attempt_id)
        if (task.current_attempt_id, attempt.worker_id, attempt.host_id) != (
            attempt.id,
            claim.worker_id,
            worker.host_id,
        ):
            raise error_for(ErrorCode.LEASE_LOST, "attempt ownership changed")
        access.RbacAuthorizer(ctx.clock).admit(uow, ctx.actor)
        if handoff:
            stages = uow.repo(StageRepository)
            stage_id = StageRecordId(UUID(progress["stage_record_id"]))
            step_id = StepId(UUID(progress["step_id"]))
            stage = stages.get(stage_id)
            step = uow.repo(StepRepository).get(step_id)
            if (
                stage.attempt_id != attempt.id
                or stage.fencing_token != claim.fencing_token
                or step.stage_record_id != stage.id
            ):
                raise error_for(ErrorCode.LEASE_LOST, "Runtime handoff belongs to a different execution")
            if refused:
                if stage.state not in TERMINAL_STAGE_STATES or stage.runtime_started_at is not None:
                    raise error_for(ErrorCode.LEASE_LOST, "Runtime refusal is no longer bound to its outcome")
                return
            if (
                stage.state not in ACTIVE_STAGE_STATES
                or run.status.value != "running"
                or stages.cancel_requested(attempt.id, claim.fencing_token)
                or step.state is not StepState.STARTED
            ):
                raise error_for(ErrorCode.LEASE_LOST, "Runtime handoff is no longer pending")
            fenced = FencedContext(claim, assignment, held, attempt, task, run, worker, now)
            _require_current_worker(uow, ctx, fenced)
            _require_runtime_authority(uow, ctx, fenced, step)
            _require_runtime_offer(uow, ctx, fenced, step)


SPEC = CommandSpec(
    name="execution.renew_lease",
    dto=RenewLease,
    result=RenewLeaseResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
    replay_guard=replay_guard,
)
