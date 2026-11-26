"""``execution.get_readiness_report`` query handler (execution §8)."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import RevisionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.execution.application._start_inputs import prepare_inputs, value
from skm.modules.execution.application.queries import readiness_report_to_json
from skm.modules.execution.domain.ids import ReadinessReportId
from skm.modules.execution.domain.readiness import changed_inputs
from skm.modules.execution.generated.queries import GetReadinessReport
from skm.modules.execution.generated.views import ReadinessReportView
from skm.modules.execution.ports import ReadinessRepository
from skm.modules.planning.public import get_revision_meta

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_scope(query: GetReadinessReport, uow: UnitOfWork) -> ScopeRef | None:
    if (query.report_id is None) == (query.revision_id is None):
        return None
    repo = uow.repo(ReadinessRepository)
    if query.report_id is not None:
        try:
            rep = repo.get(ReadinessReportId(query.report_id))
        except NotFound:
            return None
        return ScopeRef(ScopeKind.PLAN, ScopeId(rep.plan_id))
    if query.revision_id is None:
        return None
    rep_opt = repo.latest_for(RevisionId(query.revision_id))
    if rep_opt is not None:
        return ScopeRef(ScopeKind.PLAN, ScopeId(rep_opt.plan_id))
    try:
        meta = get_revision_meta(uow, RevisionId(query.revision_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.PLAN, ScopeId(meta.plan_id))


def handle(query: GetReadinessReport, ctx: QueryContext, uow: UnitOfWork) -> ReadinessReportView:
    if (query.report_id is None) == (query.revision_id is None):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "provide exactly one of report_id or revision_id")
    repo = uow.repo(ReadinessRepository)
    if query.report_id is not None:
        rep = repo.get(ReadinessReportId(query.report_id))
    elif query.revision_id is not None:
        found = repo.latest_for(RevisionId(query.revision_id))
        if found is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "readiness report not found",
                details={"revision_id": str(query.revision_id)},
            )
        rep = found
    else:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "provide exactly one of report_id or revision_id")
    from skm.kernel.errors import SkmError

    stale_parts: list[str] = []
    if rep.start_request is None:
        stale_parts.append("start_request")
        if rep.work_policies is None:
            stale_parts.append("work_policies")
    else:
        try:
            current = prepare_inputs(
                uow,
                ctx,
                rep.plan_id,
                rep.revision_id,
                rep.start_request.get("overrides", {}),
                rep.start_request.get("selection"),
                read_only=True,
                mode=rep.start_request.get("mode"),
            )
            stale_parts.extend(changed_inputs(rep, current.inputs))
        except SkmError:
            stale_parts.append("inputs_unavailable")
    if (ctx.clock.now() - rep.created_at).total_seconds() > value(
        ctx.config, "execution.readiness.max_age_seconds", 3600
    ):
        stale_parts.append("age")
    rep_doc = deepcopy(dict(readiness_report_to_json(rep)))
    perms = effective_permissions(uow, ctx.actor, ScopeId(rep.plan_id))
    if (
        "config.read" not in perms
        and isinstance(sr := rep_doc.get("start_request"), dict)
        and sr.get("overrides")
    ):
        sr["overrides"] = dict.fromkeys(cast("dict[str, Any]", sr["overrides"]), "[REDACTED]")
    eff_status = "stale" if stale_parts else rep.status.value
    return ReadinessReportView.from_json(
        {"report": rep_doc, "effective_status": eff_status, "stale_parts": stale_parts}
    )


SPEC = QuerySpec(
    name="execution.get_readiness_report",
    dto=GetReadinessReport,
    result=ReadinessReportView,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
