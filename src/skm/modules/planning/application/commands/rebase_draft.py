"""``planning.rebase_draft`` (planning §7.8): three-way rebase of an open draft onto the current revision.

Locks are acquired in the canonical order ``plans -> drafts`` (§7.10) after a preliminary draft existence
and plan-ownership check. If the draft is already based on ``plan.current_revision_id`` and no resolutions
are supplied, the command returns ``changed=False`` without writing or recording an event. If unresolved
conflicts remain, ``REBASE_CONFLICTS`` is raised with the conflict list and nothing is persisted.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import PlanId, RevisionId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import document_bytes
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.events import DraftRebased
from skm.modules.planning.domain.rebase import (
    ABSENT,
    RebaseConflict,
    RebaseResolution,
    rebase_document,
)
from skm.modules.planning.domain.specification import SPECIFICATION_URN, from_document
from skm.modules.planning.domain.validation.findings import Severity
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.commands import (
    RebaseDraft,
    RebaseDraftResolutionsItemVariant1,
    RebaseDraftResolutionsItemVariant2,
)
from skm.modules.planning.generated.results import RebaseDraftResult, RebaseDraftResultCounts
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import (
    DraftRepository,
    PlanRepository,
    RevisionRepository,
    SpecificationDoc,
)
from skm.modules.workspace import public as workspace
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.planning.domain.plan import Plan

__all__ = ["SPEC", "handle", "scope_of"]


@lru_cache(maxsize=1)
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def scope_of(cmd: RebaseDraft) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def _to_domain_resolution(
    item: RebaseDraftResolutionsItemVariant1 | RebaseDraftResolutionsItemVariant2,
) -> RebaseResolution:
    if isinstance(item, RebaseDraftResolutionsItemVariant1):
        return RebaseResolution(conflict_id=item.conflict_id, keep=item.keep, new_key=None)
    return RebaseResolution(conflict_id=item.conflict_id, keep=None, new_key=item.new_key)


def _conflict_to_json(conflict: RebaseConflict) -> JsonObject:
    out: dict[str, JsonValue] = {
        "conflict_id": conflict.conflict_id,
        "kind": conflict.kind.value,
        "entity_id": None if conflict.entity_id is None else str(conflict.entity_id),
        "entity_kind": None if conflict.entity_kind is None else conflict.entity_kind.value,
        "key": conflict.key,
        "field": conflict.field,
        "pointer": conflict.pointer,
        "resolutions": list(conflict.resolutions),
    }
    for name in ("base", "yours", "theirs"):
        value = getattr(conflict, name)
        if value is not ABSENT:
            out[name] = value
    if conflict.colliding_entity_id is not None:
        out["colliding_entity_id"] = str(conflict.colliding_entity_id)
    if conflict.children_kept:
        out["children_kept"] = [str(item) for item in conflict.children_kept]
    if conflict.issues:
        out["issues"] = list(conflict.issues)
    return out


def _validate_counts(
    uow: UnitOfWork,
    ctx: CommandContext,
    plan: Plan,
    document: SpecificationDoc,
    *,
    settings: PlanningSettings,
    now: datetime,
) -> RebaseDraftResultCounts:
    spec, _ = from_document(document)
    vctx = build_validation_context(
        uow,
        ctx,
        plan,
        spec,
        document,
        settings=settings,
        now=now,
    )
    counts = validate(vctx).counts()
    return RebaseDraftResultCounts(
        error=counts[Severity.ERROR],
        warning=counts[Severity.WARNING],
        info=counts[Severity.INFO],
    )


def handle(cmd: RebaseDraft, ctx: CommandContext, uow: UnitOfWork) -> RebaseDraftResult:
    plan_id = PlanId(cmd.plan_id)
    draft_id = DraftId(cmd.draft_id)
    drafts = uow.repo(DraftRepository)

    # Preliminary draft check before taking the plan lock so unknown/foreign drafts fail fast.
    prelim = drafts.get(draft_id)
    draft_rules.require_in_plan(prelim, plan_id)

    # Canonical lock order (§7.10): plan first, then draft.
    plan = uow.repo(PlanRepository).lock(plan_id)
    plan_rules.require_editable(plan)
    workspace.require_active_project(uow, plan.project_id)

    draft = drafts.lock(draft_id)
    draft_rules.require_in_plan(draft, plan.id)
    if draft.workspace_id != plan.workspace_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "draft not found",
            details={"kind": "draft", "ref": str(draft_id)},
        )
    draft_rules.require_open(draft)
    draft_rules.require_edit_version(draft, cmd.expected_edit_version)

    if cmd.onto_revision_id is not None and RevisionId(cmd.onto_revision_id) != plan.current_revision_id:
        raise Conflict(
            ErrorCode.BASE_REVISION_CHANGED,
            "the plan current revision does not match onto_revision_id",
            details={
                "base_revision_id": (None if draft.base_revision_id is None else str(draft.base_revision_id)),
                "current_revision_id": (
                    None if plan.current_revision_id is None else str(plan.current_revision_id)
                ),
                "onto_revision_id": str(cmd.onto_revision_id),
            },
        )

    settings = ctx.config.section(PlanningSettings)
    now = ctx.clock.now()
    raw_resolutions = cmd.resolutions or ()

    if draft.base_revision_id == plan.current_revision_id:
        if raw_resolutions:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                f"Unknown rebase conflict_id {raw_resolutions[0].conflict_id!r}.",
                details={"conflict_id": raw_resolutions[0].conflict_id},
            )
        counts = _validate_counts(uow, ctx, plan, draft.document, settings=settings, now=now)
        return RebaseDraftResult(
            draft_id=draft.id,
            plan_id=plan.id,
            changed=False,
            edit_version=draft.edit_version,
            previous_base_revision_id=draft.base_revision_id,
            base_revision_id=draft.base_revision_id,
            taken_from_current=0,
            kept_from_draft=0,
            resolved=0,
            counts=counts,
        )

    if plan.current_revision_id is None:
        raise Conflict(
            ErrorCode.BASE_REVISION_CHANGED,
            "cannot rebase onto a plan without a current revision",
            details={"base_revision_id": str(draft.base_revision_id), "current_revision_id": None},
        )

    revisions = uow.repo(RevisionRepository)
    base_doc = None if draft.base_revision_id is None else revisions.get_document(draft.base_revision_id)
    theirs_doc = revisions.get_document(plan.current_revision_id)

    resolutions = [_to_domain_resolution(item) for item in raw_resolutions]
    outcome = rebase_document(
        base_doc,
        draft.document,
        theirs_doc,
        resolutions,
        schema=_schemas().validator(SPECIFICATION_URN),
    )

    if outcome.conflicts or outcome.document is None:
        raise Conflict(
            ErrorCode.REBASE_CONFLICTS,
            f"Draft rebase stopped with {len(outcome.conflicts)} conflict(s); pass resolutions and retry.",
            details={
                "plan_id": str(plan.id),
                "draft_id": str(draft.id),
                "edit_version": draft.edit_version,
                "base_revision_id": (None if draft.base_revision_id is None else str(draft.base_revision_id)),
                "current_revision_id": str(plan.current_revision_id),
                "taken_from_current": outcome.taken_from_current,
                "kept_from_draft": outcome.kept_from_draft,
                "conflicts": [_conflict_to_json(c) for c in outcome.conflicts],
            },
        )

    rebased_doc = outcome.document
    size = document_bytes(rebased_doc)
    limit = settings.drafts.max_document_bytes
    if size > limit:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "draft document exceeds planning.drafts.max_document_bytes",
            details={
                "issues": [
                    {"pointer": "", "message": f"document exceeds {limit} bytes", "schema_pointer": ""}
                ],
                "bytes": size,
                "limit": limit,
            },
        )

    rebased = draft_rules.rebase(
        draft,
        rebased_doc,
        plan.current_revision_id,
        cmd.expected_edit_version,
        ctx.actor.principal_id,
        now,
    )
    drafts.save(rebased, expected_edit_version=cmd.expected_edit_version)
    counts = _validate_counts(uow, ctx, plan, rebased.document, settings=settings, now=now)
    uow.record(
        DraftRebased(
            plan_id=plan.id,
            workspace_id=plan.workspace_id,
            draft_id=draft.id,
            edit_version=rebased.edit_version,
            previous_base_revision_id=draft.base_revision_id,
            base_revision_id=rebased.base_revision_id,
            taken_from_current=outcome.taken_from_current,
            kept_from_draft=outcome.kept_from_draft,
            resolved=outcome.resolved,
        )
    )
    return RebaseDraftResult(
        draft_id=draft.id,
        plan_id=plan.id,
        changed=True,
        edit_version=rebased.edit_version,
        previous_base_revision_id=draft.base_revision_id,
        base_revision_id=rebased.base_revision_id,
        taken_from_current=outcome.taken_from_current,
        kept_from_draft=outcome.kept_from_draft,
        resolved=outcome.resolved,
        counts=counts,
    )


SPEC = CommandSpec(
    name="planning.rebase_draft",
    dto=RebaseDraft,
    result=RebaseDraftResult,
    permission="plan.edit",
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
