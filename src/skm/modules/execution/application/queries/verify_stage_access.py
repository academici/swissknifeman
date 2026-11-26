"""Admit one stage-broker request using the exact live assignment credential and fence."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import AttemptId, ScopeId, WorkerId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.execution.application._stage_agent_helpers import live_step_profile_and_permissions
from skm.modules.execution.application._worker_protocol import FencedContext, verify_worker
from skm.modules.execution.domain.ids import AssignmentId, StageRecordId, StepId
from skm.modules.execution.domain.lease import WorkerClaim, verify_fence
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.generated.queries import VerifyStageAccess
from skm.modules.execution.generated.views import StageAccessView
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.policy.public import permissions_digest

__all__ = ["SPEC"]


def _scope(query: VerifyStageAccess, uow: UnitOfWork) -> ScopeRef | None:
    try:
        assignment = uow.repo(AssignmentRepository).get(AssignmentId(query.assignment_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(assignment.run_id))


def handle(query: VerifyStageAccess, ctx: QueryContext, uow: UnitOfWork) -> StageAccessView:
    grant = ctx.actor.grant
    if (
        grant is None
        or grant.kind != "assignment"
        or grant.assignment_id != query.assignment_id
        or grant.step_id != query.step_id
    ):
        raise error_for(ErrorCode.FORBIDDEN, "Stage access requires the exact assignment credential")
    claim = WorkerClaim(
        AssignmentId(query.assignment_id),
        AttemptId(query.attempt_id),
        WorkerId(query.worker_id),
        query.fencing_token,
    )
    assignments = uow.repo(AssignmentRepository)
    assignment = assignments.get(claim.assignment_id)
    if grant.scope_id != assignment.run_id or assignment.reconcile_effect_id is not None:
        raise error_for(ErrorCode.FORBIDDEN, "Stage credential is outside its run")
    worker = verify_worker(
        uow, ctx.actor, claim.worker_id, workspace_id=assignment.workspace_id, assignment_token=True
    )
    runs = uow.repo(RunRepository)
    run = runs.get(assignment.run_id)
    if "project.read" not in access.effective_permissions(uow, ctx.actor, ScopeId(run.project_id)):
        raise error_for(ErrorCode.FORBIDDEN, "The stage credential no longer has project access")
    now = runs.now()
    lease = verify_fence(assignments.lease(claim.assignment_id), assignment, claim, now)
    attempt = uow.repo(AttemptRepository).get(claim.attempt_id)
    task = uow.repo(TaskRepository).get(assignment.task_id)
    stage_repo = uow.repo(StageRepository)
    stage = stage_repo.get(StageRecordId(query.stage_record_id))
    step = uow.repo(StepRepository).get(StepId(query.step_id))
    if (
        assignment.last_fencing_token != claim.fencing_token
        or task.current_attempt_id != attempt.id
        or attempt.worker_id != claim.worker_id
        or attempt.host_id != worker.host_id
        or step.attempt_id != attempt.id
        or step.stage_record_id != stage.id
        or step.state is not StepState.STARTED
        or stage.fencing_token != claim.fencing_token
        or stage.state not in ACTIVE_STAGE_STATES
        or stage.runtime_started_at is None
        or run.status.value != "running"
        or stage_repo.cancel_requested(attempt.id, claim.fencing_token)
    ):
        raise error_for(ErrorCode.LEASE_LOST, "Stage access is no longer held")
    fenced = FencedContext(claim, assignment, lease, attempt, task, run, worker, now)
    _, _, permissions = live_step_profile_and_permissions(uow, ctx, fenced, step)
    if permissions_digest(permissions) != step.session_fingerprint.authority_digest:
        raise error_for(ErrorCode.FORBIDDEN, "Live stage permissions changed")
    return StageAccessView(active=True)


SPEC = QuerySpec(
    name="execution.verify_stage_access",
    dto=VerifyStageAccess,
    result=StageAccessView,
    permission=None,
    scope_of=None,
    scope_resolver=_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
)
