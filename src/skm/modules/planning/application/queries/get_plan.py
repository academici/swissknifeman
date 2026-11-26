"""``planning.get_plan`` (planning §8): return ``PlanView`` with aliases and current revision metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_plan
from skm.modules.planning.generated.queries import GetPlan
from skm.modules.planning.generated.views import PlanSummaryView, PlanView, PlanViewAliasesItem
from skm.modules.planning.ports import PlanningQueries, PlanRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.planning.domain.plan import Plan

__all__ = ["SPEC", "handle", "plan_view", "scope_of"]


def scope_of(query: GetPlan) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def plan_view(uow: UnitOfWork, plan: Plan) -> PlanView:
    """``PlanView`` of an already authorized ``plan``: its summary row, aliases and plan record."""
    plan_repo = uow.repo(PlanRepository)
    summary = PlanSummaryView.from_json(uow.repo(PlanningQueries).plan_summary(plan.id))
    aliases = tuple(
        PlanViewAliasesItem(alias=alias, kind=kind.value) for alias, kind in plan_repo.list_aliases(plan.id)
    )
    return PlanView(
        plan_id=summary.plan_id,
        alias=summary.alias,
        title=summary.title,
        purpose=summary.purpose,
        lifecycle_state=summary.lifecycle_state,
        current_revision_id=summary.current_revision_id,
        current_revision_no=summary.current_revision_no,
        open_drafts=summary.open_drafts,
        updated_at=summary.updated_at,
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        aliases=aliases,
        created_by=plan.created_by,
        created_at=plan.created_at,
        archived_at=plan.archived_at,
        row_version=plan.row_version,
        next_revision_no=plan.next_revision_no,
    )


def handle(query: GetPlan, _ctx: QueryContext, uow: UnitOfWork) -> PlanView:
    return plan_view(uow, require_plan(uow, query.plan_id))


SPEC = QuerySpec(
    name="planning.get_plan",
    dto=GetPlan,
    result=PlanView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
