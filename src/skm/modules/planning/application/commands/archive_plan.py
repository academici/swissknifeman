"""``planning.archive_plan`` (planning §7.6): retire a plan and abandon its open drafts.

Locks follow the planning order, plan first and then the open drafts by id, so a concurrent ``open_draft``
either is abandoned here or is refused afterwards. Published revisions and published drafts stay as they are;
runs are not looked at, because they execute immutable revisions to their end.

Archiving an archived plan changes nothing and records nothing. It is answered before the guards, so a retry
keeps working once the project has been archived too. The system plan is never archived (§4.4).
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PlanId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.events import DraftAbandoned, PlanArchived
from skm.modules.planning.generated.commands import ArchivePlan
from skm.modules.planning.generated.results import ArchivePlanResult
from skm.modules.planning.ports import DraftRepository, PlanRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: ArchivePlan) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def handle(cmd: ArchivePlan, ctx: CommandContext, uow: UnitOfWork) -> ArchivePlanResult:
    plans = uow.repo(PlanRepository)
    plan = plans.lock(PlanId(cmd.plan_id))
    if cmd.expected_row_version is not None and cmd.expected_row_version != plan.row_version:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "the plan was changed by another command",
            details={"expected": cmd.expected_row_version, "actual": plan.row_version},
        )
    now = ctx.clock.now()
    archived = plan_rules.archive(plan, now)
    if archived is plan:
        return ArchivePlanResult(
            plan_id=plan.id,
            lifecycle_state="archived",
            changed=False,
            abandoned_draft_ids=(),
            row_version=plan.row_version,
        )
    plan_rules.require_editable(plan)
    workspace.require_active_project(uow, plan.project_id)
    drafts = uow.repo(DraftRepository)
    abandoned: list[DraftId] = []
    for draft in drafts.lock_open_for_plan(plan.id):
        closed = draft_rules.abandon(draft, draft.edit_version, now, actor=ctx.actor.principal_id)
        drafts.save(closed, expected_edit_version=draft.edit_version)
        uow.record(
            DraftAbandoned(
                plan_id=plan.id,
                workspace_id=plan.workspace_id,
                draft_id=draft.id,
                edit_version=closed.edit_version,
                reason="plan_archived",
            )
        )
        abandoned.append(draft.id)
    plans.save(archived, expected_version=plan.row_version)
    uow.record(
        PlanArchived(
            plan_id=plan.id,
            workspace_id=plan.workspace_id,
            project_id=plan.project_id,
            alias=plan.alias,
            abandoned_draft_ids=tuple(abandoned),
        )
    )
    return ArchivePlanResult(
        plan_id=plan.id,
        lifecycle_state="archived",
        changed=True,
        abandoned_draft_ids=tuple(abandoned),
        row_version=archived.row_version,
    )


SPEC = CommandSpec(
    name="planning.archive_plan",
    dto=ArchivePlan,
    result=ArchivePlanResult,
    permission="plan.archive",
    scope_of=scope_of,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
