"""A trusted human verdict on the current output and an already committed manual wait."""

from dataclasses import replace
from typing import Any, cast

from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.execution.application._control import lock_task, require_permission
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application.apply_action import commit_trigger, prepare_trigger
from skm.modules.execution.domain.decision_request import DecisionKind, DecisionState
from skm.modules.execution.domain.ids import CheckExecutionId
from skm.modules.execution.domain.manual_verdict import record_manual_verdict
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.commands import RecordManualVerdict
from skm.modules.execution.generated.results import RecordManualVerdictResult
from skm.modules.execution.ports import CheckRepository, DecisionRepository, TaskRepository
from skm.modules.planning import public as planning


def scope(cmd: RecordManualVerdict, uow: UnitOfWork) -> ScopeRef | None:
    try:
        check = uow.repo(CheckRepository).get(CheckExecutionId(cmd.check_execution_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(check.run_id))


def handle(cmd: RecordManualVerdict, ctx: Any, uow: UnitOfWork) -> RecordManualVerdictResult:
    checks = uow.repo(CheckRepository)
    observed = checks.get(CheckExecutionId(cmd.check_execution_id))
    run, task, attempt = lock_task(uow, observed.task_id)
    require_permission(uow, ctx, run, "check.verdict", human=True)
    if task.status is not TaskStatus.MANUAL_PENDING or attempt is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "the manual wait boundary has not committed")
    check = checks.get(CheckExecutionId(cmd.check_execution_id))
    spec = planning.get_revision_specification(uow, run.revision_id)
    definition = next((c for c in spec.checks if c.id == check.check_spec_id), None)
    if definition is None:
        raise error_for(ErrorCode.INVALID_REFERENCE, "check is absent from the pinned revision")
    required_role = getattr(definition.definition, "actor_role", None)
    # Permission was checked on the real token above. The role proof reads the
    # principal's memberships without confusing token narrowing with membership.
    permissions = access.effective_permissions(uow, replace(ctx.actor, grant=None), ScopeId(run.id))
    roles = [role.value for role in access.Role if access.role_permissions(role) <= permissions]
    vid = ctx.ids.new_id()
    why = cause("manual_verdict", refs=[{"kind": "check", "id": str(check.id)}])
    pending = prepare_trigger(uow, ctx, attempt, vid, why)
    verdict, updated = record_manual_verdict(
        check,
        checks.verdicts(check.id),
        actor=ctx.actor,
        actor_roles=roles,
        required_role=required_role,
        current_output_id=attempt.current_output_id,
        verdict=cmd.verdict,
        comment=cmd.comment,
        supersedes_id=cast("Any", cmd.supersedes_verdict_id),
        verdict_id=vid,
        now=ctx.clock.now(),
    )
    checks.add_verdict(verdict)
    checks.save(updated)
    for request in uow.repo(DecisionRepository).open_for_task(task.id):
        if request.kind is DecisionKind.MANUAL_CHECK and request.payload.get("check_execution_id") == str(
            check.id
        ):
            uow.repo(DecisionRepository).save(replace(request, state=DecisionState.APPLIED))
    emit(
        uow,
        run,
        "manual-verdict-recorded",
        {
            "check_execution_id": str(check.id),
            "check_key": check.check_key,
            "verdict": cmd.verdict,
            "by": str(ctx.actor.principal_id),
        },
        why,
    )
    kind = commit_trigger(uow, ctx, run, pending)

    return RecordManualVerdictResult(vid, uow.repo(TaskRepository).get(task.id).status.value, kind)


SPEC = CommandSpec(
    name="execution.record_manual_verdict",
    dto=RecordManualVerdict,
    result=RecordManualVerdictResult,
    permission="check.verdict",
    scope_of=None,
    scope_resolver=scope,
    handler=handle,
    allowed_kinds=frozenset({access.PrincipalKind.HUMAN}),
)
