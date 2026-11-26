"""``planning.open_draft`` (planning §7.2): a new draft of an editable plan, at most ``max_open`` of them.

The plan lock comes first: it serialises two ``open_draft`` calls (count and insert cannot race) and
``open_draft`` against ``archive_plan`` (a draft opened first is abandoned by the archive, one opened later
is refused). A skeleton opened with ``base = "empty"`` still rests on the current revision: publishing it
replaces the specification as a whole.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PlanId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.events import DraftOpened
from skm.modules.planning.domain.plan import Plan
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.commands import OpenDraft
from skm.modules.planning.generated.results import OpenDraftResult
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import DraftRepository, PlanRepository, RevisionRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: OpenDraft) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def _skeleton(plan: Plan) -> JsonObject:
    return {"schema": SPECIFICATION_URN, "title": plan.title, "goal": plan.title, "phases": [], "items": []}


def handle(cmd: OpenDraft, ctx: CommandContext, uow: UnitOfWork) -> OpenDraftResult:
    plan = uow.repo(PlanRepository).lock(PlanId(cmd.plan_id))
    plan_rules.require_editable(plan)
    workspace.require_active_project(uow, plan.project_id)
    drafts = uow.repo(DraftRepository)
    limit = ctx.config.section(PlanningSettings).drafts.max_open
    open_drafts = drafts.count_open(plan.id)
    if open_drafts >= limit:
        raise Conflict(
            ErrorCode.ALREADY_EXISTS,
            "the plan has as many open drafts as it may have",
            details={"open_drafts": open_drafts, "limit": limit},
        )
    base_revision_id = plan.current_revision_id
    document = (
        uow.repo(RevisionRepository).get_document(base_revision_id)
        if cmd.base == "current" and base_revision_id is not None
        else _skeleton(plan)
    )
    draft = draft_rules.open_draft(
        draft_rules.DraftId(ctx.ids.new_id()),
        plan,
        base_revision_id,
        document,
        ctx.actor.principal_id,
        ctx.clock.now(),
    )
    drafts.add(draft)
    uow.record(
        DraftOpened(
            plan_id=plan.id,
            workspace_id=plan.workspace_id,
            draft_id=draft.id,
            base_revision_id=base_revision_id,
            source=cmd.base,
            edit_version=draft.edit_version,
        )
    )
    return OpenDraftResult(
        draft_id=draft.id,
        plan_id=plan.id,
        base_revision_id=base_revision_id,
        edit_version=draft.edit_version,
        document_digest=specification_digest(draft.document),
    )


SPEC = CommandSpec(
    name="planning.open_draft",
    dto=OpenDraft,
    result=OpenDraftResult,
    permission="plan.edit",
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
