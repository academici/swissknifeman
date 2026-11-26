"""Bound administrative observations, independent of the stopped workflow cursor."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from uuid import UUID, uuid5

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RepositoryId, ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._primitives import schemas
from skm.modules.execution.application._worker_dtos import (
    BeginStageResult,
    ClaimAssignmentResult,
    RecordStageResultResult,
    RenewLeaseResult,
    WireRecord,
    digest,
    document,
)
from skm.modules.execution.application._worker_protocol import (
    FencedContext,
    locked_stage,
    parse_worker_claim,
    process_identity,
    revoke_authority,
    verify_completed_assignment,
    verify_current_lease,
    verify_worker,
)
from skm.modules.execution.application.commands.record_external_effect import attempt_effects, validate_target
from skm.modules.execution.domain.assignment import Assignment, AssignmentState, WorkerRequirements
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.external_effect import EffectState, validate_observation
from skm.modules.execution.domain.ids import ExternalEffectId, StageRecordId
from skm.modules.execution.domain.lease import renew_lease
from skm.modules.execution.domain.stage_record import (
    ACTIVE_STAGE_STATES,
    StageOutcomeKind,
    StageState,
    begin_stage_record,
    complete_stage,
    interrupt_stage,
    record_process_identity,
)
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    DecisionRepository,
    EffectRepository,
    EnvironmentRepository,
    IntegrationSlotRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.policy.public import record_outcome
from skm.modules.workspace import public as workspace


class ReconcileExternalEffect(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:reconcile-external-effect:v1"


class ReconcileExternalEffectResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:reconcile-external-effect:v1"


LIVE = {AssignmentState.AVAILABLE, AssignmentState.LEASED}
RELEASE = {"kind": "release", "release_reason": "waiting"}


def pinned_host(uow: UnitOfWork, effect: Any) -> Any:
    slots = uow.repo(IntegrationSlotRepository)
    pins = slots.hosts_for_run(effect.run_id)
    request = effect.request
    repository = request.get("repository_id")
    if repository is None:
        hosts = set(pins.values())
        return next(iter(hosts)) if len(hosts) == 1 else None
    repository = RepositoryId(UUID(repository))
    host = pins.get(repository)
    branch = request.get("target_branch")
    if branch and slots.target_hosts(((repository, branch),)).get((repository, branch)) != host:
        return None
    identity = request.get("binding_identity")
    if identity and (identity["host_id"] != str(host) or identity["repository_id"] != str(repository)):
        return None
    return host


def require_read(uow: UnitOfWork, ctx: Any, run: Any, worker: Any) -> None:
    access.RbacAuthorizer(ctx.clock).admit(uow, ctx.actor)
    permissions = access.effective_permissions(uow, ctx.actor, ScopeId(run.id))
    if not {"worker.claim", "checkout.read_locator"} <= permissions:
        raise error_for(ErrorCode.FORBIDDEN, "reconciliation requires current repository read authority")
    # Retired/unbound restored hosts cannot inherit the old writer's authority.
    if workspace.get_host(uow, worker.host_id).state != "active":
        raise error_for(ErrorCode.FORBIDDEN, "writer host requires activation and fresh binding")


def bound_effect(uow: UnitOfWork, assignment: Any, host_id: Any, *, for_update: bool = True) -> Any:
    effect = uow.repo(EffectRepository).get(assignment.reconcile_effect_id, for_update=for_update)
    if (
        (effect.run_id, effect.task_id, effect.attempt_id, effect.workspace_id)
        != (assignment.run_id, assignment.task_id, assignment.attempt_id, assignment.workspace_id)
        or assignment.requirements.required_host_id != host_id
        or pinned_host(uow, effect) != host_id
    ):
        raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "administrative effect/host binding changed")
    if effect.state not in {EffectState.OUTCOME_UNKNOWN, EffectState.SUCCEEDED, EffectState.FAILED}:
        raise error_for(ErrorCode.INVALID_TRANSITION, "administrative observation requires an unknown effect")
    return effect


def admin_instruction(assignment: Any, effect: Any) -> dict[str, Any]:
    params = {"effect_id": str(effect.id), "request_digest": effect.request_digest}
    return {
        "kind": "run_stage",
        "stage_id": "reconcile_" + assignment.id.hex[-22:],
        "stage_type": "integrate",
        "mode": "reconcile",
        "round_no": 1,
        "params": params,
        "input_digest": digest({"assignment_id": str(assignment.id), **params}),
        "environment": None,
        "not_before": None,
        "route_override": None,
    }


def admin_context(uow: UnitOfWork, ctx: Any, raw: Any, *, allow_closed: bool = False) -> Any:
    claim = parse_worker_claim(raw)
    repo = uow.repo(AssignmentRepository)
    observed = repo.get(claim.assignment_id)
    if observed.reconcile_effect_id is None:
        return None
    run = uow.repo(RunRepository).get(observed.run_id, for_update=True)
    task = uow.repo(TaskRepository).get(observed.task_id, for_update=True)
    attempt = uow.repo(AttemptRepository).get(observed.attempt_id, for_update=True)
    assignment = repo.get(observed.id, for_update=True)
    lease = repo.lease(assignment.id, for_update=True)
    worker = verify_worker(uow, ctx.actor, claim.worker_id, workspace_id=assignment.workspace_id)
    require_read(uow, ctx, run, worker)
    now = uow.repo(RunRepository).now()
    if claim.attempt_id != attempt.id or assignment.last_fencing_token != claim.fencing_token:
        raise error_for(ErrorCode.LEASE_LOST, "administrative claim changed")
    # Stage before effect, including replay after the result closed its lease.
    stages = uow.repo(StageRepository)
    history = stages.history(attempt.id)
    owned = next(
        (e.record for e in history.entries if e.record.stage_id == "reconcile_" + assignment.id.hex[-22:]),
        None,
    )
    if owned is not None:
        owned = stages.get(owned.id, for_update=True)
    if allow_closed and assignment.state is AssignmentState.COMPLETED and lease is None:
        metadata: Any = {} if owned is None else owned.outcome or {}
        if owned is None or metadata.get("admin_worker_id") != str(claim.worker_id):
            raise error_for(ErrorCode.LEASE_LOST, "administrative replay has no owned terminal record")
    else:
        verify_current_lease(uow, assignment, lease, claim, now)
    effect = bound_effect(uow, assignment, worker.host_id)
    if effect.request.get("binding_identity"):
        from types import SimpleNamespace

        validate_target(uow, SimpleNamespace(worker=worker, run=run, now=now), effect.request)
    return FencedContext(claim, assignment, lease, attempt, task, run, worker, now)


def claim_admin(uow: UnitOfWork, ctx: Any, assignment: Any, lease: Any, worker: Any, ttl: int) -> Any:
    run = uow.repo(RunRepository).get(assignment.run_id)
    require_read(uow, ctx, run, worker)
    effect = bound_effect(uow, assignment, worker.host_id)
    task = uow.repo(TaskRepository).get(assignment.task_id)
    return ClaimAssignmentResult(
        assignment_id=str(assignment.id),
        attempt_id=str(assignment.attempt_id),
        task_id=str(task.id),
        run_id=str(run.id),
        fencing_token=lease.fencing_token,
        lease_expires_at=lease.expires_at.isoformat(),
        lease_ttl_seconds=ttl,
        renew_every_seconds=int(ctx.config.get("execution.lease.renew_every_seconds") or 30),
        instruction=admin_instruction(assignment, effect),
        task={
            "revision_id": str(run.revision_id) if run.revision_id is not None else None,
            "entity_id": str(task.spec_entity_id) if task.spec_entity_id is not None else None,
            "display_key": task.display_key,
            "kind": task.kind.value,
            "declared_write_scope": [],
        },
        reaped=[],
    )


def begin_admin(cmd: Any, ctx: Any, uow: UnitOfWork, fenced: Any) -> Any:
    repo = uow.repo(StageRepository)
    history = tuple(e.record for e in repo.history(fenced.attempt.id).entries)
    effect = bound_effect(uow, fenced.assignment, fenced.worker.host_id)
    expected = admin_instruction(fenced.assignment, effect)
    if any(cmd[k] != expected[k] for k in ("stage_id", "round_no", "input_digest")):
        raise error_for(ErrorCode.INVALID_REFERENCE, "administrative instruction differs from its binding")
    found = repo.find(fenced.attempt.id, cmd["stage_id"], cmd["round_no"], cmd["input_digest"])
    if found is not None and found.state is StageState.COMPLETED:
        prior = document(found.outcome or {})
        prior.pop("admin_worker_id", None)
        return BeginStageResult(
            outcome="already_completed",
            stage_record_id=str(found.id),
            already_completed=True,
            prior_outcome=prior,
        )
    if found is not None and found.state not in ACTIVE_STAGE_STATES:
        raise error_for(ErrorCode.LEASE_LOST, "administrative stage is no longer live")
    if found is None:
        if effect.state is not EffectState.OUTCOME_UNKNOWN:
            raise error_for(ErrorCode.INVALID_TRANSITION, "effect already resolved")
        found = begin_stage_record(
            history,
            record_id=ctx.ids.new_id(),
            attempt_id=fenced.attempt.id,
            run_id=fenced.run.id,
            task_id=fenced.task.id,
            stage_id=expected["stage_id"],
            stage_type="integrate",
            round_no=1,
            mode=StageMode.RECONCILE,
            input_digest=expected["input_digest"],
            fencing_token=fenced.claim.fencing_token,
            now=fenced.now,
        )
        repo.add(found)
    return BeginStageResult(
        outcome="ready",
        stage_record_id=str(found.id),
        already_completed=False,
        integrate={
            "effect_id": str(effect.id),
            "kind": effect.kind.value,
            "request_digest": effect.request_digest,
            "request": document(effect.request),
            "inspection_claim": {
                "assignment_id": str(fenced.assignment.id),
                "attempt_id": str(fenced.attempt.id),
                "worker_id": str(fenced.claim.worker_id),
                "fencing_token": fenced.claim.fencing_token,
                "host_id": str(fenced.worker.host_id),
                "stage_record_id": str(found.id),
            },
        },
    )


def renew_admin(cmd: Any, ctx: Any, uow: UnitOfWork, fenced: Any) -> Any:
    progress = cmd.get("progress", {})
    if (
        any(progress.get(k) for k in ("step_id", "usage_so_far", "snapshot"))
        or progress.get("phase") == "runtime_started"
    ):
        raise error_for(ErrorCode.FORBIDDEN, "administrative read cannot start runtime or spend")
    stage = None
    if progress.get("stage_record_id"):
        stage = locked_stage(uow, fenced, progress["stage_record_id"])
        if (
            stage.stage_id != "reconcile_" + fenced.assignment.id.hex[-22:]
            or stage.state not in ACTIVE_STAGE_STATES
        ):
            raise error_for(ErrorCode.LEASE_LOST, "progress is not the bound administrative stage")
    identity = None
    if progress.get("process"):
        if stage is None:
            raise error_for(ErrorCode.INVALID_REFERENCE, "inspect process requires its administrative stage")
        identity = process_identity(progress["process"], fenced, stage, ())
        effect_id = fenced.assignment.reconcile_effect_id
        owner = identity.ownership["owner"]
        helper_id = uuid5(effect_id, str(owner["owner_nonce"]))
        if identity.unit_key not in {("git_effect", str(effect_id)), ("git_effect", str(helper_id))}:
            raise error_for(ErrorCode.FORBIDDEN, "inspect process is not bound to this effect")
        uow.repo(StageRepository).save(record_process_identity(stage, identity))
    updated = renew_lease(
        fenced.lease,
        fenced.assignment,
        fenced.claim,
        now=fenced.now,
        ttl=timedelta(seconds=int(ctx.config.get("execution.lease.ttl_seconds") or 120)),
        process_identity=identity,
    )
    uow.repo(AssignmentRepository).renew(
        fenced.lease, expires_at=updated.expires_at, heartbeat_at=fenced.now, identity=identity
    )
    return RenewLeaseResult(
        lease_expires_at=updated.expires_at.isoformat(), cancel_requested=False, snapshot_requested=False
    )


def close_admin(
    uow: UnitOfWork, ctx: Any, fenced: Any, *, expired: bool = False, code: str | None = None
) -> None:
    """Interrupt/revoke only the bound read; no workflow, budgets or writer slot mutation."""
    repo = uow.repo(AssignmentRepository)
    if fenced.assignment.state is not AssignmentState.LEASED:
        return
    for entry in uow.repo(StageRepository).history(fenced.attempt.id).entries:
        stage = entry.record
        if (
            stage.stage_id == "reconcile_" + fenced.assignment.id.hex[-22:]
            and stage.state in ACTIVE_STAGE_STATES
        ):
            uow.repo(StageRepository).save(
                replace(
                    interrupt_stage(stage, now=fenced.now),
                    error_code=code,
                    outcome={"admin_worker_id": str(fenced.claim.worker_id)},
                )
            )
    state = AssignmentState.EXPIRED if expired else AssignmentState.COMPLETED
    repo.save(replace(fenced.assignment, state=state), expected_version=fenced.assignment.row_version)
    repo.drop_lease(fenced.assignment.id)
    revoke_authority(uow, ctx, fenced)


def escalate_unknown(uow: UnitOfWork, ctx: Any, run: Any, effect: Any, reason: str) -> None:
    repo = uow.repo(DecisionRepository)
    if any(
        r.kind is DecisionKind.ESCALATION
        and isinstance(refs := r.payload.get("refs"), Mapping)
        and refs.get("effect_id") == str(effect.id)
        for r in repo.open_for_task(effect.task_id)
    ):
        return
    request = DecisionRequest(
        ctx.ids.new_id(),
        run.workspace_id,
        run.id,
        effect.task_id,
        DecisionKind.ESCALATION,
        Audience.OWNER,
        None,
        frozenset(),
        None,
        None,
        1,
        {"code": reason, "refs": {"effect_id": str(effect.id)}, "options": ["reconcile", "inspect"]},
        None,
        {"attempt_id": str(effect.attempt_id), "input_part_digest": effect.request_digest},
        DecisionState.OPEN,
        None,
        None,
        uow.repo(RunRepository).now(),
    )
    repo.add(request)
    emit(
        uow,
        run,
        "decision-requested",
        {
            "request_id": str(request.id),
            "task_id": str(effect.task_id),
            "kind": "escalation",
            "audience": "owner",
            "blocking_code": "WAITING_OWNER",
        },
        cause("lease_recovery"),
    )


def verify_admin_result_replay(
    cmd: Any, ctx: Any, uow: UnitOfWork, claim: Any, assignment: Any, worker: Any
) -> None:
    verify_completed_assignment(uow, assignment, claim)
    run = uow.repo(RunRepository).get(assignment.run_id)
    require_read(uow, ctx, run, worker)
    effect = bound_effect(uow, assignment, worker.host_id, for_update=False)
    if effect.request.get("binding_identity"):
        from types import SimpleNamespace

        validate_target(
            uow, SimpleNamespace(worker=worker, run=run, now=uow.repo(RunRepository).now()), effect.request
        )
    stage = uow.repo(StageRepository).get(StageRecordId(UUID(cmd["stage_record_id"])))
    expected = admin_instruction(assignment, effect)
    if (
        stage.attempt_id != claim.attempt_id
        or stage.fencing_token != claim.fencing_token
        or stage.stage_id != expected["stage_id"]
        or stage.input_digest != expected["input_digest"]
        or stage.state is not StageState.COMPLETED
        or (stage.outcome or {}).get("admin_worker_id") != str(claim.worker_id)
    ):
        raise error_for(ErrorCode.LEASE_LOST, "Administrative receipt belongs to a different execution")


def record_admin(cmd: Any, ctx: Any, uow: UnitOfWork, fenced: Any) -> Any:
    repo = uow.repo(StageRepository)
    stage = repo.get(StageRecordId(UUID(cmd["stage_record_id"])), for_update=True)
    expected = admin_instruction(
        fenced.assignment, bound_effect(uow, fenced.assignment, fenced.worker.host_id)
    )
    if (
        stage.stage_id != expected["stage_id"]
        or stage.input_digest != expected["input_digest"]
        or stage.fencing_token != fenced.claim.fencing_token
        or stage.attempt_id != fenced.attempt.id
    ):
        raise error_for(ErrorCode.LEASE_LOST, "result is not the bound administrative stage")
    if any(cmd.get(k) for k in ("usage", "evidence", "observations", "activity")):
        raise error_for(ErrorCode.FORBIDDEN, "administrative reads cannot submit runtime facts or artifacts")
    outcome = cmd["outcome"]
    schemas().require_valid("urn:skm:execution:stage-outcome-integrate:v1", outcome)
    raw = outcome.get("reconciled_effect")
    if set(outcome) != {"reconciled_effect"} or not isinstance(raw, dict):
        raise error_for(ErrorCode.INVALID_REFERENCE, "administrative result requires only reconciled_effect")
    raw = cast("dict[str, Any]", raw)
    effect = bound_effect(uow, fenced.assignment, fenced.worker.host_id)
    if raw["effect_id"] != str(effect.id) or raw["request_digest"] != effect.request_digest:
        raise error_for(ErrorCode.INVALID_REFERENCE, "administrative result changed effect/request")
    state = EffectState(raw["state"])
    kind = "outcome_unknown" if state is EffectState.OUTCOME_UNKNOWN else "success"
    if cmd["outcome_kind"] != kind:
        raise error_for(ErrorCode.INVALID_REFERENCE, "administrative stage outcome contradicts observation")
    if stage.state is StageState.COMPLETED:
        prior = document(stage.outcome or {})
        prior.pop("admin_worker_id", None)
        if prior != outcome:
            raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "administrative result replay changed")
        return RecordStageResultResult(task_status=fenced.task.status.value, next=RELEASE)
    if stage.state not in ACTIVE_STAGE_STATES or fenced.assignment.state is not AssignmentState.LEASED:
        raise error_for(ErrorCode.LEASE_LOST, "administrative stage lost its lease")
    validate_observation(effect, state, raw.get("receipt"), raw.get("reason_code"))
    if effect.state is not EffectState.OUTCOME_UNKNOWN:
        raise error_for(ErrorCode.INVALID_TRANSITION, "effect already resolved by another observation")
    if state is not EffectState.OUTCOME_UNKNOWN:
        receipt = document(raw["receipt"])
        uow.repo(EffectRepository).save(replace(effect, state=state, receipt=receipt, updated_at=fenced.now))
        if effect.intent_id is not None:
            record_outcome(
                uow, ctx, intent_id=ToolIntentId(effect.intent_id), outcome=state.value, receipt=receipt
            )
        emit(
            uow,
            fenced.run,
            "external-effect-recorded",
            {
                "effect_id": str(effect.id),
                "kind": effect.kind.value,
                "state": state.value,
                "attempt_id": str(effect.attempt_id),
                "output_ids": document(effect.request.get("output_ids", [])),
                "request_digest": effect.request_digest,
            },
            cause("lease_recovery"),
        )
    else:
        escalate_unknown(uow, ctx, fenced.run, effect, raw.get("reason_code", "OUTCOME_UNKNOWN"))
    repo.save(
        complete_stage(
            stage,
            now=fenced.now,
            outcome_kind=StageOutcomeKind(kind),
            outcome={**outcome, "admin_worker_id": str(fenced.claim.worker_id)},
        )
    )
    close_admin(uow, ctx, fenced)
    return RecordStageResultResult(task_status=fenced.task.status.value, next=RELEASE)


def effect_scope(cmd: Any, uow: UnitOfWork) -> ScopeRef:
    effect = uow.repo(EffectRepository).get(ExternalEffectId(UUID(cmd["effect_id"])))
    return ScopeRef(ScopeKind.RUN, ScopeId(effect.run_id))


def handle(cmd: ReconcileExternalEffect, ctx: Any, uow: UnitOfWork) -> ReconcileExternalEffectResult:
    repo = uow.repo(EffectRepository)
    observed = repo.get(ExternalEffectId(UUID(cmd["effect_id"])))
    run = uow.repo(RunRepository).get(observed.run_id, for_update=True)
    uow.repo(TaskRepository).get(observed.task_id, for_update=True)
    uow.repo(AttemptRepository).get(observed.attempt_id, for_update=True)
    assignments = uow.repo(AssignmentRepository)
    rows = [assignments.get(a.id, for_update=True) for a in assignments.for_attempt(observed.attempt_id)]
    stages = uow.repo(StageRepository)
    for entry in stages.history(observed.attempt_id).entries:
        stages.get(entry.record.id, for_update=True)
    effect = repo.get(observed.id, for_update=True)
    if effect.state in {EffectState.SUCCEEDED, EffectState.FAILED}:
        return ReconcileExternalEffectResult(effect_id=str(effect.id), state=effect.state.value)
    if effect.state is not EffectState.OUTCOME_UNKNOWN:
        raise error_for(ErrorCode.INVALID_TRANSITION, "only unknown effects can be reconciled")
    live = [a for a in rows if a.state in LIVE]
    if live:
        if len(live) != 1 or live[0].reconcile_effect_id != effect.id:
            raise error_for(ErrorCode.INVALID_TRANSITION, "normal assignment still owns the attempt")
        return ReconcileExternalEffectResult(
            effect_id=str(effect.id), state=effect.state.value, assignment_id=str(live[0].id)
        )
    if stages.started_without_result(effect.attempt_id) is not None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "an active normal stage prevents reconciliation")
    host = pinned_host(uow, effect)
    if (
        host is None
        or workspace.get_host(uow, host).state != "active"
        or not any(w.host_id == host for w in workspace.list_online_workers(uow, (run.workspace_id,)))
    ):
        escalate_unknown(uow, ctx, run, effect, "INTEGRATION_HOST_MISMATCH")
        return ReconcileExternalEffectResult(effect_id=str(effect.id), state="outcome_unknown")
    now = uow.repo(RunRepository).now()
    # One new row per tick, a fixed backoff after an interrupted/unknown observation.
    admin = [a for a in rows if a.reconcile_effect_id == effect.id]
    available = max([now, *(a.created_at + timedelta(seconds=30) for a in admin)])
    env = uow.repo(EnvironmentRepository).for_attempt(effect.attempt_id)
    assignment = Assignment(
        ctx.ids.new_id(),
        effect.run_id,
        effect.task_id,
        effect.attempt_id,
        effect.workspace_id,
        AssignmentState.AVAILABLE,
        available,
        WorkerRequirements(
            frozenset(),
            host,
            frozenset(),
            EnvironmentKind.GIT_WORKTREE if env is None else env.kind,
            frozenset(),
        ),
        0,
        max((a.last_fencing_token for a in rows), default=0),
        effect.id,
        None,
        None,
        now,
        1,
    )
    assignments.add(assignment)
    return ReconcileExternalEffectResult(
        effect_id=str(effect.id), state="outcome_unknown", assignment_id=str(assignment.id)
    )


def schedule_unknown(uow: UnitOfWork, ctx: Any, attempt_id: Any) -> bool:
    effects = [e for e in attempt_effects(uow, attempt_id) if e.state is EffectState.OUTCOME_UNKNOWN]
    if not effects:
        return False
    # One attempt has one live observation; subsequent targets are observed on later ticks.
    handle(ReconcileExternalEffect(effect_id=str(sorted(effects, key=lambda e: str(e.id))[0].id)), ctx, uow)
    return True


SPEC = CommandSpec(
    name="execution.reconcile_external_effect",
    dto=ReconcileExternalEffect,
    result=ReconcileExternalEffectResult,
    permission="run.control",
    scope_of=None,
    scope_resolver=effect_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),
    idempotency=IdempotencyMode.OPTIONAL,
)
