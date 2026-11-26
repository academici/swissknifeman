"""Claim a saved stage template under workspace worker authority."""

from dataclasses import replace
from datetime import timedelta
from functools import partial
from typing import Any
from uuid import UUID

from skm.application_bus.ports import IdempotencyStore
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import HostId, RepositoryId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access import public as access
from skm.modules.execution.application._admission import require_future_admission
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._primitives import move, save_attempt, server_context
from skm.modules.execution.application._stage_agent_helpers import stage_route_available
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_dtos import ClaimAssignment, ClaimAssignmentResult
from skm.modules.execution.application._worker_protocol import (
    FencedContext,
    grant_inputs,
    instruction,
    revoke_authority,
    verify_fenced_replay,
    verify_worker,
    workspace_scope,
)
from skm.modules.execution.application.apply_action import process_pending
from skm.modules.execution.application.commands.reconcile_external_effect import (
    bound_effect,
    claim_admin,
    require_read,
)
from skm.modules.execution.domain.assignment import WorkerOffer
from skm.modules.execution.domain.attempt import AttemptState, StageContinuation, transition_attempt
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    AutopilotRepository,
    DecisionRepository,
    IntegrationSlotRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.runtimes.public import (
    Capability,
    worker_installations,
)
from skm.modules.runtimes.public import capabilities as runtime_capabilities
from skm.modules.workspace import public as workspace


def _require_current_credential(uow: UnitOfWork, ctx: Any, worker_id: WorkerId, *, lock: bool) -> None:
    grant = ctx.actor.grant
    if grant is None or not access.worker_credential_current(
        uow, grant.token_id, worker_id, now=ctx.clock.now, lock=lock
    ):
        raise error_for(ErrorCode.FORBIDDEN, "A new claim requires the current worker credential")


def admit_candidate(  # noqa: PLR0911 -- normal admission plus the bound administrative lane
    uow: UnitOfWork, ctx: Any, worker_offer: WorkerOffer, worker: Any, assignment: Any
) -> bool:
    """Called under the repository's ownership locks, before any lease mutation."""
    run = uow.repo(RunRepository).get(assignment.run_id, for_update=True)
    task = uow.repo(TaskRepository).get(assignment.task_id, for_update=True)
    attempt = uow.repo(AttemptRepository).get(assignment.attempt_id, for_update=True)
    if assignment.reconcile_effect_id is not None:
        if uow.repo(StageRepository).started_without_result(attempt.id) is not None:
            return False
        require_read(uow, ctx, run, worker)
        effect = bound_effect(uow, assignment, worker_offer.host_id)
        if effect.state.value != "outcome_unknown":
            return False
        _require_current_credential(uow, ctx, worker_offer.worker_id, lock=True)
        return True
    if run.status.value != "running" or uow.repo(DecisionRepository).open_for_task(task.id):
        return False
    if assignment.reap_stage_record_id is not None:
        if not uow.repo(StageRepository).confirm_reap(
            assignment.reap_stage_record_id,
            worker_offer,
            uow.repo(RunRepository).now(),
            receipt_id=ctx.ids.new_id(),
        ):
            return False
        process_pending(uow, ctx, attempt.id)
        attempt = uow.repo(AttemptRepository).get(attempt.id)
        task = uow.repo(TaskRepository).get(task.id)
    if not isinstance(attempt.continuation, StageContinuation):
        return False
    if task.current_attempt_id != attempt.id or uow.repo(StageRepository).started_without_result(attempt.id):
        return False
    _, values = effective_values(uow, run.id)
    cursor = attempt.continuation.stage
    if cursor.not_before is not None and cursor.not_before > uow.repo(RunRepository).now():
        return False
    target = str(values.get("execution.integration.branch", "skm/integration/{run}")).replace(
        "{run}", str(run.id)
    )
    slots = uow.repo(IntegrationSlotRepository)
    targets = [
        (RepositoryId(m.repository_id), target) for m in workspace.get_project(uow, run.project_id).mounts
    ]
    pins = {*slots.hosts_for_run(run.id).values(), *slots.target_hosts(targets).values()}
    if pins - {worker_offer.host_id}:
        return False
    # Ownership locks come first. Rotation and model publication use the same token row.
    _require_current_credential(uow, ctx, worker_offer.worker_id, lock=True)
    try:
        return require_future_admission(uow, ctx, run, task, values) and stage_route_available(
            uow, ctx, run, task, attempt, worker, offered_runtimes=worker_offer.offered_runtimes
        )
    except SkmError as exc:
        if exc.code not in {
            ErrorCode.BUDGET_EXHAUSTED,
            ErrorCode.FORBIDDEN,
            ErrorCode.PLAN_ARCHIVED,
            ErrorCode.PROJECT_ARCHIVED,
        }:
            raise
        return False


def handle(  # noqa: PLR0912, PLR0915 -- one atomic worker protocol transition
    cmd: ClaimAssignment, ctx: Any, uow: UnitOfWork
) -> ClaimAssignmentResult:
    ctx = server_context(ctx, uow)
    worker_id, host_id, ws_id = (UUID(cmd[k]) for k in ("worker_id", "host_id", "workspace_id"))
    worker_id, host_id = WorkerId(worker_id), HostId(host_id)
    worker = verify_worker(uow, ctx.actor, worker_id, workspace_id=ws_id, host_id=host_id)
    _require_current_credential(uow, ctx, worker_id, lock=False)
    offer = cmd["offer"]
    registered = worker.capabilities
    offered_version = cmd.get("worker_version") or registered.skm_version
    minimum = str(value(ctx.config, "execution.worker.min_version", "0.1.0"))
    try:
        too_old = tuple(map(int, offered_version.split("."))) < tuple(map(int, minimum.split(".")))
    except ValueError:
        too_old = True
    if too_old:
        raise error_for(ErrorCode.CLIENT_TOO_OLD, "worker version is below the current minimum")
    offered_capabilities = frozenset(offer["capabilities"])
    capabilities = set(registered.runtimes) | {f"runtime:{r}" for r in registered.runtimes}
    if offered_capabilities - capabilities:
        installations = {
            item.runtime_id: item
            for item in worker_installations(uow, worker_id, as_of=ctx.clock.now())
            if item.host_id == host_id
        }
        for runtime in registered.runtimes:
            install = installations.get(runtime)
            if install is not None:
                supported = runtime_capabilities(uow, ctx.gateways, runtime, install.version)
                capabilities.update(c.value for c in Capability if supported.supports(c))
    for key, available in (
        ("capabilities", capabilities),
        ("labels", registered.labels),
        ("isolation_profiles", registered.isolation_profiles),
    ):
        if not set(offer[key]) <= set(available):
            raise error_for(ErrorCode.FORBIDDEN, "worker offer exceeds registration", details={"field": key})
    offered_kinds = frozenset(EnvironmentKind(k) for k in offer["environment_kinds"])
    offered_runtimes = frozenset(
        runtime
        for runtime in registered.runtimes
        if runtime in offered_capabilities or f"runtime:{runtime}" in offered_capabilities
    )
    ttl = int(ctx.config.get("execution.lease.ttl_seconds") or 120)
    offered = WorkerOffer(
        worker_id,
        host_id,
        offered_capabilities | {f"runtime:{r}" for r in offered_runtimes},
        frozenset(offer["labels"]),
        offered_kinds,
        frozenset(offer["isolation_profiles"]),
        tuple(cmd.get("reaped_steps", ())),
        offered_runtimes,
    )
    claimed = uow.repo(AssignmentRepository).claim(
        worker=offered,
        workspace_ids=frozenset({WorkspaceId(ws_id)}),
        blocked_project_ids=uow.repo(AutopilotRepository).emergency_project_ids(),
        now=ctx.clock.now(),
        ttl=timedelta(seconds=ttl),
        admit=partial(admit_candidate, uow, ctx, offered, worker),
    )
    if claimed is None:
        return ClaimAssignmentResult(outcome="nothing_to_claim")
    assignment, lease = claimed
    if assignment.reconcile_effect_id is not None:
        return claim_admin(uow, ctx, assignment, lease, worker, ttl)
    run = uow.repo(RunRepository).get(assignment.run_id, for_update=True)
    task = uow.repo(TaskRepository).get(assignment.task_id, for_update=True)
    attempt = uow.repo(AttemptRepository).get(assignment.attempt_id, for_update=True)
    if assignment.reconcile_effect_id is not None or not isinstance(attempt.continuation, StageContinuation):
        raise error_for(ErrorCode.INVALID_TRANSITION, "normal claim requires a server-selected stage")
    if uow.repo(StageRepository).started_without_result(attempt.id) is not None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "an unfinished stage prevents claim")
    _, values = effective_values(uow, run.id)
    now = lease.last_heartbeat_at
    if task.blocking_reason and task.blocking_reason.code.value in {
        "RECOVERING",
        "WAITING_PROVIDER",
        "BLOCKED_BY_CAPABILITY",
    }:
        task = move(
            uow,
            ctx,
            run,
            task,
            task.status,
            cause("lease_recovery" if assignment.reap_stage_record_id else "wait_changed"),
        )
    target = str(values.get("execution.integration.branch", "skm/integration/{run}")).replace(
        "{run}", str(run.id)
    )
    project = workspace.get_project(uow, run.project_id)
    targets = sorted(
        {(RepositoryId(m.repository_id), target) for m in project.mounts},
        key=lambda p: (str(p[0]), p[1].encode()),
    )
    slots = uow.repo(IntegrationSlotRepository)
    for repository_id, branch in targets:
        pinned, _ = slots.pin_target_host(repository_id, branch, host_id, now)
        if pinned != host_id:
            raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "target branch belongs to another host")
    for repository_id, _ in targets:
        if slots.pin_host(run.id, repository_id, host_id, now) != host_id:
            raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "run repository belongs to another host")
    attempt = replace(attempt, worker_id=worker_id, host_id=host_id)
    if attempt.state is AttemptState.WAITING:
        attempt = transition_attempt(attempt, AttemptState.RUNNING)
    save_attempt(uow, attempt)
    why = cause("manual_start")
    if task.status is TaskStatus.READY:
        task = move(uow, ctx, run, task, TaskStatus.ASSIGNED, why)
        emit(
            uow,
            run,
            "task-assigned",
            {
                "task_id": str(task.id),
                "attempt_id": str(attempt.id),
                "assignment_id": str(assignment.id),
                "attempt_no": attempt.attempt_no,
                "attempt_state": attempt.state.value,
            },
            why,
        )
    if task.required_host_id is None:
        updated = replace(task, required_host_id=host_id, row_version=task.row_version + 1)
        uow.repo(TaskRepository).save(updated, expected_version=task.row_version)
        task = updated
    fenced = FencedContext(
        WorkerClaim(assignment.id, attempt.id, worker_id, lease.fencing_token),
        assignment,
        lease,
        attempt,
        task,
        run,
        worker,
        now,
    )
    revoke_authority(uow, ctx, fenced)
    grant_inputs(uow, ctx, fenced)
    emit(
        uow,
        run,
        "assignment-leased",
        {
            "assignment_id": str(assignment.id),
            "task_id": str(task.id),
            "attempt_id": str(attempt.id),
            "worker_id": str(worker_id),
            "host_id": str(host_id),
            "fencing_token": lease.fencing_token,
        },
        why,
    )
    return ClaimAssignmentResult(
        assignment_id=str(assignment.id),
        attempt_id=str(attempt.id),
        task_id=str(task.id),
        run_id=str(run.id),
        fencing_token=lease.fencing_token,
        lease_expires_at=lease.expires_at.isoformat(),
        lease_ttl_seconds=ttl,
        renew_every_seconds=int(ctx.config.get("execution.lease.renew_every_seconds") or 30),
        instruction=instruction(uow, attempt),
        task={
            "project_id": str(run.project_id),
            "integration_branch": target,
            "revision_id": str(run.revision_id) if run.revision_id is not None else None,
            "entity_id": str(task.spec_entity_id) if task.spec_entity_id is not None else None,
            "display_key": task.display_key,
            "kind": task.kind.value,
            "declared_write_scope": [f"{p.mount}:{p.pattern}" for p in task.granted_write_scope],
        },
        reaped=[],
    )


def replay_guard(cmd: ClaimAssignment, ctx: Any, uow: UnitOfWork) -> None:
    worker_id = WorkerId(UUID(cmd["worker_id"]))
    workspace_id = WorkspaceId(UUID(cmd["workspace_id"]))
    verify_worker(uow, ctx.actor, worker_id, workspace_id=workspace_id, host_id=HostId(UUID(cmd["host_id"])))
    receipt = uow.repo(IdempotencyStore).get(
        workspace_id, ctx.actor.principal_id, "execution.claim_assignment", ctx.meta.idempotency_key
    )
    if receipt is not None and receipt.result.get("assignment_id") is not None:
        verify_fenced_replay(
            {
                "claim": {
                    "assignment_id": receipt.result["assignment_id"],
                    "attempt_id": receipt.result["attempt_id"],
                    "worker_id": str(worker_id),
                    "fencing_token": receipt.result["fencing_token"],
                }
            },
            ctx,
            uow,
        )


SPEC = CommandSpec(
    name="execution.claim_assignment",
    dto=ClaimAssignment,
    result=ClaimAssignmentResult,
    permission="worker.claim",
    scope_of=workspace_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
    replay_guard=replay_guard,
)
