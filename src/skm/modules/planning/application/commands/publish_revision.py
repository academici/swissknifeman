"""``planning.publish_revision`` (planning §7.5): publish an open draft as an immutable revision.

Locks ``Plan`` then ``Draft`` in canonical order (§7.10), checks draft state, ``expected_edit_version``
and ``base_revision_id == plan.current_revision_id``, verifies the project is active, prepares and
validates the publication candidate (including ``latest_at_publish`` material pin resolution), checks
``expected_content_digest`` and ``NO_CHANGES``, and writes the immutable revision, material pins,
updated plan, closed draft, and ``PlanRevisionPublished`` event in one unit of work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import PlanId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.publication_candidate import (
    prepare_publication_candidate,
    require_publishable,
)
from skm.modules.planning.application.revision_writer import write_revision
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.domain.validation.findings import Severity
from skm.modules.planning.generated.commands import PublishRevision
from skm.modules.planning.generated.results import (
    PublishRevisionResult,
    PublishRevisionResultCounts,
    PublishRevisionResultPinnedMaterialsItem,
)
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import DraftRepository, PlanRepository

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: PublishRevision) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def handle(cmd: PublishRevision, ctx: CommandContext, uow: UnitOfWork) -> PublishRevisionResult:
    plan_id = PlanId(cmd.plan_id)
    draft_id = draft_rules.DraftId(cmd.draft_id)
    drafts = uow.repo(DraftRepository)

    # Preliminary draft check before taking locks (planning §7.5 step 1).
    prelim_draft = drafts.get(draft_id)
    draft_rules.require_in_plan(prelim_draft, plan_id)

    # Canonical locking order: Plan first, then Draft (planning §7.10).
    plans = uow.repo(PlanRepository)
    plan = plans.lock(plan_id)
    plan_rules.require_editable(plan)

    draft = drafts.lock(draft_id)

    settings = ctx.config.section(PlanningSettings)
    candidate = prepare_publication_candidate(
        uow,
        ctx,
        plan,
        draft,
        expected_edit_version=cmd.expected_edit_version,
        settings=settings,
    )
    require_publishable(
        candidate,
        plan=plan,
        expected_content_digest=cmd.expected_content_digest,
    )

    written = write_revision(
        uow,
        ctx,
        plan,
        candidate.spec,
        candidate.document,
        candidate.content_digest,
        origin=RevisionOrigin.DRAFT,
        reason=cmd.reason,
        pinned_materials=candidate.pinned_materials,
        draft=draft,
        emit_event=True,
    )

    return PublishRevisionResult(
        plan_id=plan.id,
        revision_id=written.revision_id,
        revision_no=written.revision_no,
        parent_revision_id=written.meta.parent_revision_id,
        content_digest=written.content_digest,
        pinned_materials=tuple(
            PublishRevisionResultPinnedMaterialsItem(
                material_key=pin.material_key,
                file_version_id=pin.file_version_id,
                resolved_from=pin.resolved_from,
            )
            for pin in written.pinned_materials
        ),
        counts=PublishRevisionResultCounts(
            warning=candidate.counts[Severity.WARNING],
            info=candidate.counts[Severity.INFO],
        ),
    )


SPEC = CommandSpec(
    name="planning.publish_revision",
    dto=PublishRevision,
    result=PublishRevisionResult,
    permission="plan.publish",
    permissions_of=lambda _cmd: ("plan.read",),
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
