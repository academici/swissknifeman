"""Ownership locks, current fencing and immutable continuation materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import AttemptId, WorkerId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._worker_dtos import (
    digest,
    document,
    parse_datetime,
)
from skm.modules.execution.application.loaders import build_attempt_activity, load_effective_bundle
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.domain.attempt import TERMINAL_ATTEMPT_STATES, StageContinuation
from skm.modules.execution.domain.ids import AssignmentId, StageRecordId, StepId
from skm.modules.execution.domain.lease import Lease, ProcessIdentity, WorkerClaim, verify_fence
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.workspace import public as workspace


@dataclass
class FencedContext:
    claim: WorkerClaim
    assignment: Any
    lease: Any
    attempt: Any
    task: Any
    run: Any
    worker: Any
    now: Any


def parse_worker_claim(raw: Any) -> WorkerClaim:
    try:
        token = raw["fencing_token"]
        if isinstance(token, bool) or not isinstance(token, int):
            raise ValueError("invalid fencing token")
        return WorkerClaim(
            AssignmentId(UUID(raw["assignment_id"])),
            AttemptId(UUID(raw["attempt_id"])),
            WorkerId(UUID(raw["worker_id"])),
            token,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, "invalid worker claim") from exc


def workspace_scope(cmd: Any) -> ScopeRef:
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(UUID(cmd["workspace_id"])))


def fenced_scope(cmd: Any, uow: UnitOfWork) -> ScopeRef | None:
    try:
        row = uow.repo(AssignmentRepository).get(AssignmentId(UUID(cmd["claim"]["assignment_id"])))
        return ScopeRef(ScopeKind.RUN, ScopeId(row.run_id))
    except NotFound:
        return None


def step_scope(cmd: Any, uow: UnitOfWork) -> ScopeRef | None:
    try:
        step = uow.repo(StepRepository).get(StepId(UUID(cmd["step_id"])))
        attempt = uow.repo(AttemptRepository).get(step.attempt_id)
        return ScopeRef(ScopeKind.RUN, ScopeId(attempt.run_id))
    except NotFound:
        return None


def verify_worker(
    uow: UnitOfWork,
    actor: Any,
    worker_id: Any,
    *,
    workspace_id: Any,
    host_id: Any = None,
    assignment_token: bool = False,
) -> Any:
    registration = workspace.worker_for_principal(uow, actor.principal_id)
    if actor.kind is not PrincipalKind.WORKER or registration is None or registration.worker_id != worker_id:
        raise error_for(ErrorCode.FORBIDDEN, "worker principal does not match worker_id")
    if actor.grant is None or actor.grant.kind != ("assignment" if assignment_token else "worker"):
        raise error_for(ErrorCode.FORBIDDEN, "worker credential has the wrong kind")
    if actor.grant.worker_id is not None and actor.grant.worker_id != worker_id:
        raise error_for(ErrorCode.FORBIDDEN, "credential is bound to another worker")
    worker = workspace.get_worker(uow, worker_id)
    if worker.workspace_id != workspace_id:
        raise error_for(ErrorCode.NOT_FOUND, "worker workspace does not match")
    if worker.state not in ({"online", "draining"} if host_id is None else {"online"}):
        raise error_for(ErrorCode.FORBIDDEN, "worker is not available")
    if host_id is not None and worker.host_id != host_id:
        raise error_for(ErrorCode.FORBIDDEN, "worker host does not match")
    return worker


def verify_fenced_replay(cmd: Any, ctx: Any, uow: UnitOfWork) -> None:
    """Authorize reusing an existing receipt against the same pending lease without advancing it."""
    claim = parse_worker_claim(cmd["claim"])
    assignments = uow.repo(AssignmentRepository)
    assignment = assignments.get(claim.assignment_id)
    worker = verify_worker(uow, ctx.actor, claim.worker_id, workspace_id=assignment.workspace_id)
    verify_fence(assignments.lease(claim.assignment_id), assignment, claim, uow.repo(RunRepository).now())
    if assignment.last_fencing_token != claim.fencing_token:
        raise error_for(ErrorCode.LEASE_LOST, "Assignment fencing token changed")
    if assignment.reconcile_effect_id is None:
        task = uow.repo(TaskRepository).get(assignment.task_id)
        attempt = uow.repo(AttemptRepository).get(assignment.attempt_id)
        if (task.current_attempt_id, attempt.worker_id, attempt.host_id) != (
            attempt.id,
            claim.worker_id,
            worker.host_id,
        ):
            raise error_for(ErrorCode.LEASE_LOST, "Attempt ownership changed")


def verify_completed_assignment(uow: UnitOfWork, assignment: Any, claim: WorkerClaim) -> None:
    """Only a completed assignment can return its outcome without a current lease."""
    if (
        assignment.state is not AssignmentState.COMPLETED
        or assignment.attempt_id != claim.attempt_id
        or assignment.last_fencing_token != claim.fencing_token
        or uow.repo(AssignmentRepository).lease(assignment.id) is not None
    ):
        raise error_for(ErrorCode.LEASE_LOST, "Completed assignment does not match the original claim")


def verify_current_lease(
    uow: UnitOfWork, assignment: Any, lease: Lease | None, claim: Any, now: Any
) -> Lease:
    # The repository's renewal predicate samples clock_timestamp() after its row locks.
    # A value-preserving renewal also gives result/context guards that authoritative predicate,
    # without extending the lease or advancing its heartbeat (memory uses the injected clock).
    held = verify_fence(lease, assignment, claim, min(now, lease.last_heartbeat_at) if lease else now)
    uow.repo(AssignmentRepository).renew(
        held,
        expires_at=held.expires_at,
        heartbeat_at=held.last_heartbeat_at,
        identity=held.process_identity,
    )
    return verify_fence(held, assignment, claim, max(now, held.last_heartbeat_at))


def lock_fenced_context(
    uow: UnitOfWork,
    ctx: Any,
    raw_claim: Any,
    *,
    assignment_token: bool = False,
    allow_terminal: bool = False,
    heartbeat: bool = False,
    owner_guard: bool = False,
) -> FencedContext:
    claim = parse_worker_claim(raw_claim)
    repo = uow.repo(AssignmentRepository)
    observed = repo.get(claim.assignment_id)
    if heartbeat:
        assignment = repo.get(claim.assignment_id, for_update=True)
        lease = repo.lease(claim.assignment_id, for_update=True)
        run = uow.repo(RunRepository).get(observed.run_id)
        task = uow.repo(TaskRepository).get(observed.task_id)
        attempt = uow.repo(AttemptRepository).get(observed.attempt_id)
    else:
        run = uow.repo(RunRepository).get(observed.run_id, for_update=True)
        task = uow.repo(TaskRepository).get(observed.task_id, for_update=True)
        attempt = uow.repo(AttemptRepository).get(observed.attempt_id, for_update=True)
        assignment = repo.get(claim.assignment_id, for_update=True)
        lease = repo.lease(claim.assignment_id, for_update=True)
    now = uow.repo(RunRepository).now()
    if owner_guard and ctx.actor.kind is not PrincipalKind.WORKER:
        if "run.control" not in access.effective_permissions(uow, ctx.actor, ScopeId(run.id)):
            raise error_for(ErrorCode.FORBIDDEN, "context owner requires run.control")
        worker = workspace.get_worker(uow, claim.worker_id)
        if worker.workspace_id != assignment.workspace_id:
            raise error_for(ErrorCode.NOT_FOUND, "worker workspace differs")
    else:
        worker = verify_worker(
            uow,
            ctx.actor,
            claim.worker_id,
            workspace_id=assignment.workspace_id,
            assignment_token=assignment_token,
        )
    if assignment.reconcile_effect_id is not None:
        raise error_for(
            ErrorCode.INVALID_TRANSITION, "administrative reconciliation is not a normal worker claim"
        )
    if (assignment.run_id, assignment.task_id, assignment.attempt_id) != (run.id, task.id, attempt.id):
        raise error_for(ErrorCode.LEASE_LOST, "assignment ownership changed")
    if (
        attempt.worker_id != claim.worker_id
        or attempt.host_id != worker.host_id
        or task.current_attempt_id != attempt.id
    ):
        raise error_for(ErrorCode.LEASE_LOST, "attempt ownership changed")
    held = verify_current_lease(uow, assignment, lease, claim, now)
    access.RbacAuthorizer(ctx.clock).admit(uow, ctx.actor)
    if not allow_terminal and attempt.state in TERMINAL_ATTEMPT_STATES:
        raise error_for(ErrorCode.LEASE_LOST, "attempt is terminal")
    return FencedContext(
        claim, assignment, held, attempt, task, run, worker, max(now, held.last_heartbeat_at)
    )


def locked_stage(uow: UnitOfWork, fenced: FencedContext, stage_id: Any) -> Any:
    stage = uow.repo(StageRepository).get(StageRecordId(UUID(str(stage_id))), for_update=True)
    if stage.attempt_id != fenced.attempt.id or stage.fencing_token != fenced.claim.fencing_token:
        raise error_for(ErrorCode.LEASE_LOST, "stage is not owned by this claim")
    fenced.now = uow.repo(RunRepository).now()
    verify_current_lease(uow, fenced.assignment, fenced.lease, fenced.claim, fenced.now)
    return stage


def instruction(uow: UnitOfWork, attempt: Any) -> dict[str, Any]:
    cursor = attempt.continuation
    if not isinstance(cursor, StageContinuation):
        raise error_for(ErrorCode.INVALID_TRANSITION, "claim requires a saved stage template")
    selected = cursor.stage
    loaded = load_effective_bundle(uow, attempt.run_id)
    binding = {
        "attempt_id": str(attempt.id),
        "continuation": document(cursor),
        "effective_config_digest": loaded.effective_config_digest,
    }
    return {
        "kind": "run_stage",
        "stage_id": selected.stage_id,
        "stage_type": selected.stage_type,
        "mode": selected.mode.value,
        "round_no": selected.round_no,
        "params": {**document(selected.params), "feedback_refs": document(selected.feedback_refs)},
        "not_before": None if selected.not_before is None else selected.not_before.isoformat(),
        "route_override": document(selected.route_override),
        "input_digest": digest(binding),
        "environment": {
            "environment_id": None if attempt.environment_id is None else str(attempt.environment_id),
            "reopen": attempt.environment_id is not None,
        },
    }


def next_instruction(uow: UnitOfWork, fenced: Any) -> dict[str, Any]:
    run = uow.repo(RunRepository).get(fenced.run.id)
    attempt = uow.repo(AttemptRepository).get(fenced.attempt.id)
    if run.status.value != "running":
        return {"kind": "release", "release_reason": "paused" if run.status.value == "paused" else "waiting"}
    if isinstance(attempt.continuation, StageContinuation):
        return instruction(uow, attempt)
    return {
        "kind": "release",
        "release_reason": "done" if attempt.state in TERMINAL_ATTEMPT_STATES else "waiting",
    }


def revoke_authority(uow: UnitOfWork, ctx: Any, fenced: Any, *, step_id: Any = None) -> None:
    access.revoke_assignment_tokens(
        uow, assignment_id=fenced.assignment.id, step_id=step_id, by=ctx.actor.principal_id, now=fenced.now
    )
    if step_id is None:
        artifacts.revoke_grants(
            uow, reason=artifacts.GrantReason.ASSIGNMENT, ref=str(fenced.assignment.id), now=fenced.now
        )


def grant_inputs(uow: UnitOfWork, ctx: Any, fenced: Any, extra: Any = ()) -> None:
    from skm.modules.planning import public as planning

    refs = set(extra)
    if fenced.run.inline_spec_file_version_id is not None:
        refs.add(fenced.run.inline_spec_file_version_id)
    materials = (
        () if fenced.run.revision_id is None else planning.revision_materials(uow, fenced.run.revision_id)
    )
    for material in materials:
        version = material.get("file_version_id")
        targets = material.get("applies_to", ())
        if version is not None and (material.get("global") is True or fenced.task.display_key in targets):
            refs.add(UUID(str(version)))
    for entry in uow.repo(StageRepository).history(fenced.attempt.id).entries:
        for step in entry.steps:
            refs.update(
                v for v in (step.raw_result_file_version_id, step.transcript_file_version_id) if v is not None
            )
    if refs:
        artifacts.require_ready_versions(uow, fenced.run.workspace_id, tuple(refs))
        artifacts.grant_access(
            uow,
            principal_id=ctx.actor.principal_id,
            version_ids=tuple(sorted(refs, key=str)),
            reason=artifacts.GrantReason.ASSIGNMENT,
            ref=str(fenced.assignment.id),
            expires_at=fenced.lease.expires_at
            + timedelta(seconds=int(value(ctx.config, "execution.supervisor.grace_seconds", 60) or 60)),
            ids=ctx.ids,
            now=fenced.now,
        )


def require_context_owner(uow: UnitOfWork, actor: Any, owner_ref: str, raw_claim: Any, *, now: Any) -> None:
    from types import SimpleNamespace

    if not owner_ref.startswith("step:"):
        raise error_for(ErrorCode.FORBIDDEN, "context owner must be a step")
    try:
        step_id = UUID(owner_ref[5:])
    except ValueError as exc:
        raise error_for(ErrorCode.FORBIDDEN, "invalid context step owner") from exc
    step = uow.repo(StepRepository).get(StepId(step_id))
    ctx = SimpleNamespace(actor=actor, clock=SimpleNamespace(now=lambda: now))
    fenced = lock_fenced_context(uow, ctx, raw_claim, owner_guard=True)
    stage = locked_stage(uow, fenced, step.stage_record_id)
    step = uow.repo(StepRepository).get(step.id)
    if (
        fenced.run.status.value != "running"
        or step.attempt_id != fenced.attempt.id
        or step.state is not StepState.STARTED
        or stage.state.value not in {"context_draft", "running"}
    ):
        raise error_for(ErrorCode.LEASE_LOST, "context no longer has a current active owner")
    permissions = access.effective_permissions(uow, actor, ScopeId(fenced.run.id))
    if not {"run.control", "worker.claim"} & permissions:
        raise error_for(ErrorCode.FORBIDDEN, "context ownership requires worker authority")


def require_live_attempt_claim(
    uow: UnitOfWork, actor: Any, *, attempt_id: UUID, raw_claim: Any, now: Any
) -> None:
    from types import SimpleNamespace

    ctx = SimpleNamespace(actor=actor, clock=SimpleNamespace(now=lambda: now))
    fenced = lock_fenced_context(uow, ctx, raw_claim, heartbeat=True)
    if fenced.attempt.id != attempt_id:
        raise error_for(ErrorCode.SCHEMA_INVALID, "claim.attempt_id does not match path attempt_id")
    if fenced.run.status.value != "running":
        raise error_for(ErrorCode.LEASE_LOST, "run is no longer active")


def attempt_activity(uow: UnitOfWork, attempt_id: Any) -> Any:
    from skm.kernel.errors import NotFound
    from skm.modules.context.public import (
        ManifestState,
        get_manifest,
    )

    result = build_attempt_activity(uow, attempt_id)
    lessons: dict[tuple[str, str, str], JsonObject] = {}
    sources: dict[tuple[str, str | None, str | None], JsonObject] = {}
    known = True
    steps = [step for entry in uow.repo(StageRepository).history(attempt_id).entries for step in entry.steps]
    for step in steps:
        try:
            manifest = get_manifest(uow, step.context_manifest_id)
        except NotFound:
            known = False
            continue
        if manifest.state is not ManifestState.FINAL or step.session_mode == "resume":
            known = False
        for block in manifest.blocks:
            if block.included is not True:
                continue
            key = (block.source_ref, block.source_version, block.content_digest)
            sources[key] = {"source_ref": key[0], "source_version": key[1], "content_digest": key[2]}
            if block.block_type.value == "memory":
                if (
                    block.source_ref.startswith("knowledge:")
                    and block.source_version
                    and block.content_digest
                ):
                    lessons[(block.source_ref, block.source_version, block.content_digest)] = {
                        "id": block.source_ref,
                        "version": block.source_version,
                        "content_digest": block.content_digest,
                    }
                elif not block.source_ref.startswith("memory:"):
                    known = False
            if block.block_type.value in {"review_feedback", "history", "context_map", "research"}:
                known = False
    result["exposed_lesson_refs"] = list(lessons.values())
    result["source_refs"] = list(sources.values())
    result["exposure_coverage"] = "complete" if known and steps else "unknown"
    return result


def process_identity(raw: Any, fenced: Any, stage: Any, steps: Any) -> Any:
    if raw is None:
        return None
    owner = raw["ownership"]["owner"]
    for field, expected in (
        ("host_id", fenced.worker.host_id),
        ("worker_id", fenced.claim.worker_id),
        ("attempt_id", fenced.attempt.id),
        ("stage_record_id", stage.id),
    ):
        if str(owner.get(field)) != str(expected):
            raise error_for(
                ErrorCode.FORBIDDEN, "process identity has foreign ownership", details={"field": field}
            )
    kind, unit_id = owner["unit_kind"], UUID(owner["unit_id"])
    if kind == "step":
        if unit_id not in {s.id for s in steps}:
            raise error_for(ErrorCode.INVALID_REFERENCE, "process unit is not a stage step")
    elif kind == "check":
        if (uow_check := owner.get("check_execution_id")) and str(uow_check) != str(unit_id):
            raise error_for(ErrorCode.INVALID_REFERENCE, "check unit identity differs")
    elif kind != "git_effect":
        raise error_for(ErrorCode.SCHEMA_INVALID, "invalid process unit kind")
    return ProcessIdentity(
        raw.get("pid"),
        raw.get("pgid"),
        parse_datetime(raw["started_at"]),
        raw["ownership"],
        raw.get("boot_id"),
        raw.get("session_ref"),
        raw.get("start_ticks"),
    )
