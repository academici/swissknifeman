"""Record a plan intake brief with pinned design-time evidence."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import FileVersionId, PlanId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.domain.brief import DesignBrief, ResearchReference
from skm.modules.planning.domain.plan import require_editable
from skm.modules.planning.generated.commands import DesignPlan
from skm.modules.planning.generated.results import DesignPlanResult
from skm.modules.planning.ports import PlanRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: DesignPlan) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def handle(cmd: DesignPlan, ctx: CommandContext, uow: UnitOfWork) -> DesignPlanResult:
    plans = uow.repo(PlanRepository)
    plan = plans.lock_shared(PlanId(cmd.plan_id))
    require_editable(plan)
    workspace.require_active_project(uow, plan.project_id)
    versions = tuple(sorted(FileVersionId(version) for version in cmd.rag_file_version_ids or ()))
    references = tuple(
        ResearchReference(ref.reference, ref.content_digest)
        for ref in sorted(cmd.research_references or (), key=lambda ref: ref.reference)
    )
    if len(set(versions)) != len(versions) or len({ref.reference for ref in references}) != len(references):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "design brief references must be unique")
    for version in versions:
        artifacts.require_version_read(uow, ctx.actor, ctx.clock, version, default_scope=scope_of(cmd))
    if versions:
        artifacts.require_ready_versions(uow, plan.workspace_id, versions)
    brief = DesignBrief(
        id=ctx.ids.new_id(),
        workspace_id=plan.workspace_id,
        plan_id=plan.id,
        goal=cmd.goal,
        context_md=cmd.context_md,
        constraints=cmd.constraints or (),
        rag_file_version_ids=versions,
        research_references=references,
        created_by=ctx.actor.principal_id,
        created_at=ctx.clock.now(),
        visa_policy=cmd.visa_policy or "optional",
    )
    plans.add_design_brief(brief)
    return DesignPlanResult(brief.plan_id, brief.id, brief.created_at)


SPEC = CommandSpec(
    name="planning.design_plan",
    dto=DesignPlan,
    result=DesignPlanResult,
    permission="plan.edit",
    scope_of=scope_of,
    handler=handle,
)
