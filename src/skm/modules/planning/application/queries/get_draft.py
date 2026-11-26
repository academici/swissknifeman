"""``planning.get_draft`` (planning §8): return ``DraftView`` with canonical document and digest."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_plan
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.generated.documents import specification_doc_from_json
from skm.modules.planning.generated.queries import GetDraft
from skm.modules.planning.generated.views import DraftView
from skm.modules.planning.ports import DraftRepository, RevisionRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: GetDraft) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: GetDraft, _ctx: QueryContext, uow: UnitOfWork) -> DraftView:
    plan = require_plan(uow, query.plan_id)
    draft = uow.repo(DraftRepository).get(DraftId(query.draft_id))
    draft_rules.require_in_plan(draft, plan.id)
    if draft.workspace_id != plan.workspace_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "draft not found",
            details={"kind": "draft", "ref": str(query.draft_id)},
        )

    base_revision_no: int | None = None
    if draft.base_revision_id is not None:
        base_revision_no = uow.repo(RevisionRepository).get_meta(draft.base_revision_id).revision_no

    stale = draft.state is DraftState.OPEN and draft.base_revision_id != plan.current_revision_id
    canonical_doc = normalize_document(draft.document)
    digest = specification_digest(canonical_doc)

    return DraftView(
        draft_id=draft.id,
        base_revision_id=draft.base_revision_id,
        base_revision_no=base_revision_no,
        edit_version=draft.edit_version,
        state=draft.state.value,
        created_by=draft.created_by,
        created_at=draft.created_at,
        updated_by=draft.updated_by,
        updated_at=draft.updated_at,
        stale=stale,
        document=specification_doc_from_json(canonical_doc),
        document_digest=digest,
        published_revision_id=draft.published_revision_id,
        closed_at=draft.closed_at,
    )


SPEC = QuerySpec(
    name="planning.get_draft",
    dto=GetDraft,
    result=DraftView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
