"""``planning.abandon_draft`` (planning §7.4): close an open draft without publishing it.

Only the draft is locked: a save-like command takes no plan lock after a draft lock (§7.10). The archive state
of the plan is deliberately not checked (§7.4); the project guard is the one of every mutating authoring
operation (§7).
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import PlanId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain.events import DraftAbandoned
from skm.modules.planning.generated.commands import AbandonDraft
from skm.modules.planning.generated.results import AbandonDraftResult
from skm.modules.planning.ports import DraftRepository, PlanRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: AbandonDraft) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def handle(cmd: AbandonDraft, ctx: CommandContext, uow: UnitOfWork) -> AbandonDraftResult:
    drafts = uow.repo(DraftRepository)
    draft = drafts.lock(draft_rules.DraftId(cmd.draft_id))
    draft_rules.require_in_plan(draft, PlanId(cmd.plan_id))
    draft_rules.require_open(draft)
    draft_rules.require_edit_version(draft, cmd.expected_edit_version)
    plan = uow.repo(PlanRepository).get(draft.plan_id)
    workspace.require_active_project(uow, plan.project_id)
    now = ctx.clock.now()
    abandoned = draft_rules.abandon(draft, cmd.expected_edit_version, now, actor=ctx.actor.principal_id)
    drafts.save(abandoned, expected_edit_version=cmd.expected_edit_version)
    uow.record(
        DraftAbandoned(
            plan_id=draft.plan_id,
            workspace_id=draft.workspace_id,
            draft_id=draft.id,
            edit_version=abandoned.edit_version,
            reason="user",
        )
    )
    return AbandonDraftResult(draft_id=draft.id, state="abandoned", closed_at=now)


SPEC = CommandSpec(
    name="planning.abandon_draft",
    dto=AbandonDraft,
    result=AbandonDraftResult,
    permission="plan.edit",
    scope_of=scope_of,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
