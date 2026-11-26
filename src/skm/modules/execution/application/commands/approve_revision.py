"""Sign a fresh readiness report for a revision and its exact start request."""

from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.execution.application._start_inputs import prepare_inputs, value
from skm.modules.execution.domain.ids import ReadinessReportId
from skm.modules.execution.domain.readiness import RevisionVisa, require_fresh
from skm.modules.execution.generated.commands import ApproveRevision
from skm.modules.execution.generated.results import ApproveRevisionResult
from skm.modules.execution.ports import ReadinessRepository
from skm.modules.planning import public as planning

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: ApproveRevision) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def handle(cmd: ApproveRevision, ctx: CommandContext, uow: UnitOfWork) -> ApproveRevisionResult:
    readiness = uow.repo(ReadinessRepository)
    report = readiness.get(ReadinessReportId(cmd.readiness_report_id))
    request = report.start_request
    if report.plan_id != cmd.plan_id or request is None:
        raise error_for(
            ErrorCode.READINESS_REQUIRED, "a readiness report for the authorized plan is required"
        )
    planning.require_active_plan(uow, report.plan_id)
    selection = request.get("selection")
    prepared = prepare_inputs(
        uow,
        ctx,
        report.plan_id,
        report.revision_id,
        request.get("overrides", {}),
        selection,
        mode=request.get("mode"),
        read_only=True,
    )
    now = ctx.clock.now()
    require_fresh(
        report,
        prepared.inputs,
        now=now,
        revision_digest=prepared.meta.digest,
        max_age_seconds=value(prepared.config, "execution.readiness.max_age_seconds", 3600),
        start_request=prepared.request,
    )
    visa = RevisionVisa(
        ctx.ids.new_id(),
        report.workspace_id,
        report.plan_id,
        report.revision_id,
        report.id,
        cast("JsonObject | None", selection),
        ctx.actor.principal_id,
        cmd.reason,
        now,
    )
    readiness.add_visa(visa)
    return ApproveRevisionResult(visa.id, visa.revision_id, visa.readiness_report_id, visa.signed_at)


SPEC = CommandSpec(
    name="execution.approve_revision",
    dto=ApproveRevision,
    result=ApproveRevisionResult,
    permission="plan.approve",
    scope_of=scope_of,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN}),
)
