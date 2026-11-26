"""Release a terminal stage while preserving its durable continuation."""

from dataclasses import replace
from datetime import timedelta
from typing import Any

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._primitives import move, save_attempt
from skm.modules.execution.application._worker_dtos import ReleaseAssignment, ReleaseAssignmentResult
from skm.modules.execution.application._worker_protocol import (
    fenced_scope,
    lock_fenced_context,
    revoke_authority,
)
from skm.modules.execution.application.apply_action import process_pending
from skm.modules.execution.application.commands.reconcile_external_effect import (
    admin_context,
    close_admin,
    schedule_unknown,
)
from skm.modules.execution.domain.assignment import AssignmentState, retry_later, transition_assignment
from skm.modules.execution.domain.attempt import TERMINAL_ATTEMPT_STATES, AttemptState, transition_attempt
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import (
    AssignmentRepository,
    IntegrationSlotRepository,
    StageRepository,
    TaskRepository,
)


def handle(cmd: ReleaseAssignment, ctx: Any, uow: UnitOfWork) -> ReleaseAssignmentResult:
    admin = admin_context(uow, ctx, cmd["claim"], allow_closed=True)
    if admin is not None:
        close_admin(uow, ctx, admin, code="WORKER_SHUTDOWN")
        return ReleaseAssignmentResult(released=True)
    fenced = lock_fenced_context(uow, ctx, cmd["claim"], allow_terminal=True)
    stages = uow.repo(StageRepository)
    if stages.started_without_result(fenced.attempt.id) is not None:
        raise error_for(
            ErrorCode.INVALID_TRANSITION, "finish the active stage before releasing its assignment"
        )
    if (
        not cmd["retain_environment"]
        and fenced.attempt.environment_id is not None
        and fenced.attempt.state not in TERMINAL_ATTEMPT_STATES
    ):
        raise error_for(ErrorCode.INVALID_TRANSITION, "continuation requires the retained environment")
    assignment = (
        retry_later(fenced.assignment, available_at=fenced.now + timedelta(seconds=5))
        if cmd["reason"] == "retry_later"
        else transition_assignment(fenced.assignment, AssignmentState.COMPLETED)
    )
    repo = uow.repo(AssignmentRepository)
    repo.save(assignment, expected_version=fenced.assignment.row_version)
    repo.drop_lease(assignment.id)
    revoke_authority(uow, ctx, fenced)
    uow.repo(IntegrationSlotRepository).release_for_attempt(fenced.attempt.id)

    if schedule_unknown(uow, ctx, fenced.attempt.id):
        return ReleaseAssignmentResult(released=True)
    attempt = fenced.attempt
    if attempt.state is AttemptState.RUNNING:
        attempt = transition_attempt(attempt, AttemptState.WAITING)
        save_attempt(uow, attempt)
    if fenced.task.required_host_id != attempt.host_id:
        task = replace(fenced.task, required_host_id=attempt.host_id, row_version=fenced.task.row_version + 1)
        uow.repo(TaskRepository).save(task, expected_version=fenced.task.row_version)
        fenced.task = task
    if (
        cmd["reason"] == "paused"
        and fenced.task.status is TaskStatus.ASSIGNED
        and not stages.history(attempt.id).entries
    ):
        task = move(uow, ctx, fenced.run, fenced.task, TaskStatus.READY, cause("operator_resume"))
        emit(
            uow,
            fenced.run,
            "task-ready",
            {"task_id": str(task.id), "reason": "pause"},
            cause("operator_resume"),
        )
    if (
        cmd["reason"] != "retry_later"
        and fenced.run.status.value == "running"
        and attempt.state not in TERMINAL_ATTEMPT_STATES
    ):
        process_pending(uow, ctx, attempt.id)
    return ReleaseAssignmentResult(released=True)


SPEC = CommandSpec(
    name="execution.release_assignment",
    dto=ReleaseAssignment,
    result=ReleaseAssignmentResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
