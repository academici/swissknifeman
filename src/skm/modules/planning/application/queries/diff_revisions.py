"""``planning.diff_revisions`` (planning §5.8, §8): structural diff by stable ``entity_id``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import RevisionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_plan, require_revision_in_plan
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.diff import diff_specifications
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.queries import DiffRevisions
from skm.modules.planning.generated.views import (
    SpecDiffView,
    SpecDiffViewEntitiesItem,
    SpecDiffViewEntitiesItemFieldsItem,
    SpecDiffViewPlanFieldsItem,
)
from skm.modules.planning.ports import DraftRepository, RevisionRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: DiffRevisions) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: DiffRevisions, _ctx: QueryContext, uow: UnitOfWork) -> SpecDiffView:
    plan = require_plan(uow, query.plan_id)
    rev_repo = uow.repo(RevisionRepository)

    if query.to_revision_id is not None and query.draft_id is None and query.expected_edit_version is None:
        to_meta = rev_repo.get_meta(RevisionId(query.to_revision_id))
        require_revision_in_plan(to_meta, plan.id)
        to_doc = normalize_document(rev_repo.get_document(to_meta.id))
        to_info: JsonObject = {
            "kind": "revision",
            "id": str(to_meta.id),
            "revision_no": to_meta.revision_no,
        }
        from_rev_id = (
            to_meta.parent_revision_id
            if query.from_revision_id is None
            else RevisionId(query.from_revision_id)
        )
        from_kind = "revision"
    elif (
        query.draft_id is not None
        and query.expected_edit_version is not None
        and query.to_revision_id is None
        and not isinstance(query.expected_edit_version, bool)
        and query.expected_edit_version >= 1
    ):
        draft = uow.repo(DraftRepository).get(DraftId(query.draft_id))
        draft_rules.require_in_plan(draft, plan.id)
        if draft.workspace_id != plan.workspace_id:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "draft not found",
                details={"kind": "draft", "ref": str(query.draft_id)},
            )
        draft_rules.require_edit_version(draft, query.expected_edit_version)
        to_doc = normalize_document(draft.document)
        to_info = {
            "kind": "draft",
            "id": str(draft.id),
            "edit_version": draft.edit_version,
        }
        from_rev_id = (
            draft.base_revision_id if query.from_revision_id is None else RevisionId(query.from_revision_id)
        )
        from_kind = "draft_base" if query.from_revision_id is None else "revision"
    else:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "specify either to_revision_id or (draft_id, expected_edit_version >= 1)",
            details={
                "issues": [
                    {
                        "pointer": "",
                        "message": "invalid diff target selector",
                        "schema_pointer": "",
                    }
                ]
            },
        )

    if from_rev_id is not None:
        from_meta = rev_repo.get_meta(from_rev_id)
        require_revision_in_plan(from_meta, plan.id)
        from_doc = normalize_document(rev_repo.get_document(from_meta.id))
        from_info: JsonObject = {
            "kind": from_kind,
            "revision_id": str(from_meta.id),
            "revision_no": from_meta.revision_no,
        }
    else:
        from_doc: JsonObject = {"schema": SPECIFICATION_URN}
        from_info = {
            "kind": from_kind,
            "revision_id": None,
            "revision_no": None,
        }

    spec_diff = diff_specifications(from_doc, to_doc)

    return SpecDiffView(
        from_digest=spec_diff.from_digest,
        to_digest=spec_diff.to_digest,
        summary=dict(spec_diff.summary),
        plan_fields=tuple(
            SpecDiffViewPlanFieldsItem(
                pointer=f.pointer,
                op=f.op,
                before=f.before,
                after=f.after,
            )
            for f in spec_diff.plan_fields
        ),
        entities=tuple(
            SpecDiffViewEntitiesItem(
                entity_id=e.entity_id,
                entity_kind=e.entity_kind.value,
                change=e.change,
                key_before=e.key_before,
                key_after=e.key_after,
                rekeyed=e.rekeyed,
                moved=e.moved,
                fields=tuple(
                    SpecDiffViewEntitiesItemFieldsItem(
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
        from_=from_info,
        to=to_info,
    )


SPEC = QuerySpec(
    name="planning.diff_revisions",
    dto=DiffRevisions,
    result=SpecDiffView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
