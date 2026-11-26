"""Read the latest recorded signature for a revision in the authorized plan."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RevisionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.generated.queries import GetRevisionVisa
from skm.modules.execution.generated.results import ApproveRevisionResult
from skm.modules.execution.generated.views import RevisionVisaStatus
from skm.modules.execution.ports import ReadinessRepository
from skm.modules.planning import public as planning

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC"]


def scope_of(query: GetRevisionVisa) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: GetRevisionVisa, _ctx: QueryContext, uow: UnitOfWork) -> RevisionVisaStatus:
    revision_id = RevisionId(query.revision_id)
    meta = planning.get_revision_meta(uow, revision_id)
    if meta.plan_id != query.plan_id:
        raise error_for(ErrorCode.NOT_FOUND, "revision not found")
    visa = uow.repo(ReadinessRepository).latest_visa_for(revision_id)
    return RevisionVisaStatus(
        None
        if visa is None
        else ApproveRevisionResult(
            visa.id,
            visa.revision_id,
            visa.readiness_report_id,
            visa.signed_at,
        )
    )


SPEC = QuerySpec(
    name="execution.get_revision_visa",
    dto=GetRevisionVisa,
    result=RevisionVisaStatus,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
