"""``planning.preview_publication`` (planning §8.3): read-only publication candidate preview."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application import publication_candidate
from skm.modules.planning.application.source_reader import require_plan
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.diff import diff_specifications
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.domain.validation.findings import Severity
from skm.modules.planning.generated.queries import PreviewPublication
from skm.modules.planning.generated.views import (
    PublicationPreviewView,
    PublicationPreviewViewDefsSourceViewVariant2,
    PublicationPreviewViewDiff,
    PublicationPreviewViewDiffEntitiesItem,
    PublicationPreviewViewDiffEntitiesItemFieldsItem,
    PublicationPreviewViewDiffPlanFieldsItem,
    PublicationPreviewViewPinnedMaterialsItem,
    PublicationPreviewViewValidation,
    PublicationPreviewViewValidationCounts,
    PublicationPreviewViewValidationFindingsItem,
    PublicationPreviewViewValidationGraphVariant1,
    PublicationPreviewViewValidationRuleFailuresItem,
)
from skm.modules.planning.ports import DraftRepository, RevisionRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: PreviewPublication) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: PreviewPublication, ctx: QueryContext, uow: UnitOfWork) -> PublicationPreviewView:
    plan = require_plan(uow, query.plan_id)
    draft = uow.repo(DraftRepository).get(DraftId(query.draft_id))
    candidate = publication_candidate.prepare(
        uow,
        ctx,
        plan,
        draft,
        expected_edit_version=query.expected_edit_version,
    )

    if draft.base_revision_id is not None:
        base_doc = normalize_document(uow.repo(RevisionRepository).get_document(draft.base_revision_id))
    else:
        base_doc = cast("JsonObject", {"schema": SPECIFICATION_URN})

    spec_diff = diff_specifications(base_doc, candidate.document)

    graph_view: PublicationPreviewViewValidationGraphVariant1 | None = None
    try:
        compiled = compile_execution_graph(candidate.spec)
        graph_view = PublicationPreviewViewValidationGraphVariant1(
            tasks=len(compiled.tasks),
            edges=len(compiled.edges),
        )
    except SkmError:
        graph_view = None

    diff_view = PublicationPreviewViewDiff(
        from_digest=spec_diff.from_digest,
        to_digest=spec_diff.to_digest,
        summary=dict(spec_diff.summary),
        plan_fields=tuple(
            PublicationPreviewViewDiffPlanFieldsItem(
                pointer=f.pointer,
                op=f.op,
                before=f.before,
                after=f.after,
            )
            for f in spec_diff.plan_fields
        ),
        entities=tuple(
            PublicationPreviewViewDiffEntitiesItem(
                entity_id=e.entity_id,
                entity_kind=e.entity_kind.value,
                change=e.change,
                key_before=e.key_before,
                key_after=e.key_after,
                rekeyed=e.rekeyed,
                moved=e.moved,
                fields=tuple(
                    PublicationPreviewViewDiffEntitiesItemFieldsItem(
                        pointer=f.pointer,
                        op=f.op,
                        before=f.before,
                        after=f.after,
                    )
                    for f in e.fields
                ),
            )
            for e in spec_diff.entities
        ),
    )

    validation_view = PublicationPreviewViewValidation(
        findings=tuple(
            PublicationPreviewViewValidationFindingsItem(
                code=f.code,
                severity=f.severity.value,
                message=f.message,
                entity_key=f.entity_key,
                entity_id=f.entity_id,
                pointer=f.pointer,
                details=dict(f.details),
            )
            for f in candidate.report.findings
        ),
        rule_failures=tuple(
            PublicationPreviewViewValidationRuleFailuresItem(
                rule=rf.rule,
                error_type=rf.error_type,
                message=rf.message,
                plugin=rf.plugin,
            )
            for rf in candidate.report.rule_failures
        ),
        counts=PublicationPreviewViewValidationCounts(
            error=candidate.counts[Severity.ERROR],
            warning=candidate.counts[Severity.WARNING],
            info=candidate.counts[Severity.INFO],
        ),
        graph=graph_view,
    )

    return PublicationPreviewView(
        source=PublicationPreviewViewDefsSourceViewVariant2(
            kind="draft",
            plan_id=plan.id,
            document_digest=candidate.document_digest,
            draft_id=draft.id,
            edit_version=draft.edit_version,
        ),
        base_revision_id=draft.base_revision_id,
        document_digest=candidate.document_digest,
        content_digest=candidate.content_digest,
        pinned_materials=tuple(
            PublicationPreviewViewPinnedMaterialsItem(
                material_key=pm.material_key,
                file_version_id=pm.file_version_id,
                resolved_from=pm.resolved_from,
            )
            for pm in candidate.pinned_materials
        ),
        diff=diff_view,
        validation=validation_view,
        no_changes=candidate.no_changes,
        publishable=candidate.publishable,
    )


SPEC = QuerySpec(
    name="planning.preview_publication",
    dto=PreviewPublication,
    result=PublicationPreviewView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
