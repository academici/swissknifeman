"""Accept an explicit deviation with human authority on an established owner wait."""

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import lock_task, require_permission, task_scope
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application.apply_action import commit_trigger, prepare_trigger
from skm.modules.execution.domain.decision_request import DecisionState
from skm.modules.execution.domain.deviation import accept_deviation
from skm.modules.execution.domain.finding import FindingState
from skm.modules.execution.domain.ids import DecisionRequestId
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.commands import AcceptDeviation
from skm.modules.execution.generated.results import AcceptDeviationResult
from skm.modules.execution.ports import (
    AcceptanceRepository,
    DecisionRepository,
    ReviewRepository,
    TaskRepository,
)


def handle(cmd: AcceptDeviation, ctx: Any, uow: UnitOfWork) -> AcceptDeviationResult:
    run, task, attempt = lock_task(uow, cmd.task_id)
    require_permission(uow, ctx, run, "deviation.accept", human=True)
    if task.status is not TaskStatus.AWAITING_DECISION or attempt is None or task.blocking_reason is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "the corresponding owner wait has not committed")
    if task.blocking_reason.refs.get("stop_code") != "NOT_ACCEPTABLE":
        raise error_for(ErrorCode.INVALID_TRANSITION, "this wait does not request a deviation")
    did = ctx.ids.new_id()
    request_id = task.blocking_reason.refs.get("decision_request_id")
    request = (
        None
        if request_id is None
        else uow.repo(DecisionRepository).get(DecisionRequestId(UUID(str(request_id))), for_update=True)
    )
    why = cause(
        "policy_resolved",
        refs=[{"kind": "task", "id": str(task.id)}]
        if request is None
        else [{"kind": "decision_request", "id": str(request.id)}],
    )
    pending = prepare_trigger(uow, ctx, attempt, did, why)
    finding = None
    if cmd.finding_id is not None:
        finding = next(
            (f for f in uow.repo(ReviewRepository).findings_for_task(task.id) if f.id == cmd.finding_id), None
        )
        if finding is None:
            raise error_for(ErrorCode.INVALID_REFERENCE, "finding belongs to another task")
    deviation = accept_deviation(
        task,
        actor=ctx.actor,
        scope=cmd.scope,
        criterion_id=cast("Any", cmd.criterion_id),
        finding_id=cast("Any", cmd.finding_id),
        reason=cmd.reason,
        deviation_id=did,
        now=ctx.clock.now(),
    )
    uow.repo(AcceptanceRepository).add_deviation(deviation)
    if request is not None:
        uow.repo(DecisionRepository).save(
            replace(
                request, state=DecisionState.APPLIED, payload={**request.payload, "deviation_id": str(did)}
            )
        )
    if finding is not None:
        uow.repo(ReviewRepository).save_finding(replace(finding, state=FindingState.WAIVED))
    emit(
        uow,
        run,
        "deviation-accepted",
        {
            "deviation_id": str(did),
            "task_id": str(task.id),
            "scope": cmd.scope,
            "by": str(ctx.actor.principal_id),
        },
        why,
    )
    commit_trigger(uow, ctx, run, pending)
    return AcceptDeviationResult(did, uow.repo(TaskRepository).get(task.id).status.value)


SPEC = CommandSpec(
    name="execution.accept_deviation",
    dto=AcceptDeviation,
    result=AcceptDeviationResult,
    permission="deviation.accept",
    scope_of=None,
    scope_resolver=task_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN}),
)
