"""Current research ownership, shared by writes and cache disclosures through execution.public."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access import public as access
from skm.modules.execution.application._worker_protocol import (
    lock_fenced_context,
    locked_stage,
    verify_worker,
)
from skm.modules.execution.application.loaders import load_effective_bundle
from skm.modules.execution.domain.attempt import TERMINAL_ATTEMPT_STATES
from skm.modules.execution.domain.ids import AssignmentId, StepId
from skm.modules.execution.domain.lease import WorkerClaim, verify_fence
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


def require_step_scope(uow: UnitOfWork, project_id: ProjectId, step_ref: str) -> None:
    """Human provenance may reference only a step of the authorized project and workspace."""
    try:
        sid = StepId(UUID(step_ref.removeprefix("step:")))
        step = uow.repo(StepRepository).get(sid)
        attempt = uow.repo(AttemptRepository).get(step.attempt_id)
        run = uow.repo(RunRepository).get(attempt.run_id)
        project = workspace.get_project(uow, project_id)
        if run.project_id != project_id or run.workspace_id != project.workspace_id:
            raise error_for(ErrorCode.NOT_FOUND, "research step not found")
    except (ValueError, NotFound) as exc:
        raise error_for(ErrorCode.NOT_FOUND, "research step not found") from exc


def require_assignment(  # noqa: PLR0912 -- bind every ownership edge before disclosing the policy snapshot
    uow: UnitOfWork,
    actor: Actor,
    project_id: ProjectId,
    *,
    step_ref: str | None,
    for_update: bool,
    now: datetime,
    permission: str = "context.read",
) -> JsonObject:
    if actor.kind is not PrincipalKind.WORKER or actor.grant is None:
        raise error_for(ErrorCode.FORBIDDEN, "research ownership requires a worker credential")
    access.RbacAuthorizer(cast("Clock", SimpleNamespace(now=lambda: now))).admit(uow, actor)
    grant = actor.grant
    assignment_token = grant.kind == "assignment"
    if not assignment_token and (grant.kind != "worker" or step_ref is None):
        raise error_for(ErrorCode.FORBIDDEN, "research reads require an assignment credential")
    try:
        try:
            sid = (
                StepId(UUID(step_ref.removeprefix("step:")))
                if step_ref
                else StepId(cast("UUID", grant.step_id))
            )
        except ValueError as exc:
            raise error_for(ErrorCode.FORBIDDEN, "invalid research assignment step") from exc
        step = uow.repo(StepRepository).get(sid)
        observed = uow.repo(AttemptRepository).get(step.attempt_id)
        run = uow.repo(RunRepository).get(observed.run_id)
        if run.project_id != project_id:
            raise error_for(ErrorCode.NOT_FOUND, "research step not found")
        if assignment_token:
            if grant.step_id != sid or grant.scope_id != run.id:
                raise error_for(ErrorCode.FORBIDDEN, "research step differs from the assignment token")
            assignment = uow.repo(AssignmentRepository).get(AssignmentId(cast("UUID", grant.assignment_id)))
        else:
            registration = workspace.worker_for_principal(uow, actor.principal_id)
            if registration is None:
                raise error_for(ErrorCode.FORBIDDEN, "research worker is not registered")
            candidates = uow.repo(AssignmentRepository).for_attempt(observed.id)
            assignment = next((a for a in candidates if a.state.value == "leased"), None)
            if assignment is None:
                raise error_for(ErrorCode.LEASE_LOST, "research assignment is no longer active")
        worker_id = observed.worker_id
        if worker_id is None:
            raise error_for(ErrorCode.LEASE_LOST, "research attempt has no worker")
        claim = WorkerClaim(assignment.id, observed.id, worker_id, assignment.last_fencing_token)
        if for_update:
            fenced = lock_fenced_context(
                uow,
                SimpleNamespace(actor=actor, clock=SimpleNamespace(now=lambda: now)),
                {
                    "assignment_id": str(claim.assignment_id),
                    "attempt_id": str(claim.attempt_id),
                    "worker_id": str(claim.worker_id),
                    "fencing_token": claim.fencing_token,
                },
                assignment_token=assignment_token,
            )
            stage = locked_stage(uow, fenced, step.stage_record_id)
            run, attempt, task, assignment, lease = (
                fenced.run,
                fenced.attempt,
                fenced.task,
                fenced.assignment,
                fenced.lease,
            )
            checked_now = fenced.now
        else:
            attempt = uow.repo(AttemptRepository).get(observed.id)
            task = uow.repo(TaskRepository).get(assignment.task_id)
            lease = uow.repo(AssignmentRepository).lease(assignment.id)
            stage = uow.repo(StageRepository).get(step.stage_record_id)
            checked_now = max(now, uow.repo(RunRepository).now())
            worker = verify_worker(
                uow, actor, worker_id, workspace_id=assignment.workspace_id, assignment_token=assignment_token
            )
            if attempt.host_id != worker.host_id:
                raise error_for(ErrorCode.LEASE_LOST, "research worker host changed")
        verify_fence(lease, assignment, claim, checked_now)
        step = uow.repo(StepRepository).get(sid)
        if (
            run.status.value != "running"
            or run.project_id != project_id
            or assignment.run_id != run.id
            or assignment.attempt_id != attempt.id
            or assignment.task_id != task.id
            or assignment.workspace_id != run.workspace_id
            or task.current_attempt_id != attempt.id
            or attempt.worker_id != worker_id
            or attempt.state in TERMINAL_ATTEMPT_STATES
            or step.attempt_id != attempt.id
            or step.stage_record_id != stage.id
            or step.state is not StepState.STARTED
            or stage.attempt_id != attempt.id
            or stage.fencing_token != claim.fencing_token
            or stage.state.value not in {"context_draft", "running"}
            or assignment.reconcile_effect_id is not None
        ):
            raise error_for(ErrorCode.LEASE_LOST, "research step no longer has a current active owner")
        chain_scope = ScopeId(run.id)
        held = access.effective_permissions(uow, actor, chain_scope)
        allowed = {permission}
        if permission == "context.research" and grant.kind == "worker":
            allowed.add("worker.claim")
        if not held.intersection(allowed):
            raise error_for(ErrorCode.FORBIDDEN, "worker lacks the research operation permission in this run")
        return {
            "run_id": str(run.id),
            "host_id": str(attempt.host_id),
            "config_snapshot": load_effective_bundle(uow, run.id).effective_snapshot,
        }
    except NotFound as exc:
        raise error_for(ErrorCode.NOT_FOUND, "research step not found") from exc
