"""Read the owner's immutable revision and project it to Markdown."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import PlanId, ProjectId, RevisionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.public import latest_run_outcome
from skm.modules.exports.domain.plan_markdown import PhaseExportView, PlanExportView, render_plan
from skm.modules.exports.generated.queries import RenderPlanMarkdown
from skm.modules.exports.generated.views import PlanMarkdownView
from skm.modules.planning import public as planning
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork


def build_plan_view(
    uow: UnitOfWork,
    plan: planning.PlanView,
    *,
    revision_no: int | None = None,
    can_read_run: Callable[[UUID], bool] | None = None,
) -> PlanExportView:
    project_id, plan_id = ProjectId(plan.project_id), PlanId(plan.plan_id)
    project = workspace.get_project(uow, project_id)
    remote = next((mount.canonical_remote for mount in project.mounts if mount.role == "primary"), None)
    view = PlanExportView(
        plan_id=plan_id,
        alias=plan.alias,
        title=plan.title,
        status=plan.lifecycle_state,
        project=project.title,
        repository=remote,
    )
    if revision_no is not None and revision_no != plan.current_revision_no:
        revision_id = planning.find_revision_id(uow, plan_id, revision_no)
        if revision_id is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Plan revision not found")
    else:
        revision_id = RevisionId(plan.current_revision_id) if plan.current_revision_id is not None else None
    if revision_id is None:
        return view
    meta = planning.get_revision_meta(uow, revision_id)
    if meta.plan_id != plan_id:
        raise NotFound(ErrorCode.NOT_FOUND, "Plan revision not found")
    spec = planning.get_revision_specification(uow, revision_id)
    outcome = latest_run_outcome(uow, project_id, plan_id, revision_id=revision_id)
    run_id = UUID(str(outcome["run_id"])) if outcome else None
    if run_id is not None and can_read_run is not None and not can_read_run(run_id):
        outcome, run_id = None, None
    status = outcome.get("items") if outcome else None
    item_statuses = status if isinstance(status, dict) else {}
    items: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for item in spec.items:
        label = str(item_statuses.get(item.key, "—")).replace("_", " ")
        items[item.phase].append((item.key, item.title, item.work_kind.value, label))
    return replace(
        view,
        revision_no=meta.revision_no,
        revision_id=revision_id,
        content_digest=meta.digest,
        title=spec.title,
        goal=spec.goal,
        run_id=run_id,
        phases=tuple(PhaseExportView(p.key, p.title, p.goal, tuple(items[p.key])) for p in spec.phases),
        requirements=tuple((r.key, r.priority.value, r.statement) for r in spec.requirements),
        decisions=tuple((d.key, d.title, d.state.value, d.decision or "—") for d in spec.decisions),
        checks=tuple(
            (c.key, c.category.value, c.kind.value, "yes" if c.required else "no") for c in spec.checks
        ),
    )


def handle(query: RenderPlanMarkdown, ctx: QueryContext, uow: UnitOfWork) -> PlanMarkdownView:
    from .list_pending_notes import holds

    plan = planning.get_plan_summary(uow, PlanId(query.plan_id))
    view = build_plan_view(
        uow,
        plan,
        revision_no=query.revision_no,
        can_read_run=lambda run_id: holds(ctx, uow, "run.read", ScopeKind.RUN, run_id),
    )
    if view.revision_no is None:
        raise NotFound(ErrorCode.NOT_FOUND, "Plan has no published revision")
    doc = render_plan(view)
    return PlanMarkdownView(doc.text(), f"{view.alias}-r{view.revision_no}.md", doc.digest())


SPEC = QuerySpec(
    name="exports.render_plan_markdown",
    dto=RenderPlanMarkdown,
    result=PlanMarkdownView,
    permission="plan.read",
    scope_of=lambda q: ScopeRef(ScopeKind.PLAN, ScopeId(q.plan_id)),
    handler=handle,
)
