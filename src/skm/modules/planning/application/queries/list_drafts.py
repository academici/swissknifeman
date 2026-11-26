"""``planning.list_drafts`` (planning §8): list drafts of a plan filtered by state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_plan
from skm.modules.planning.domain.draft import DraftState
from skm.modules.planning.generated.queries import ListDrafts
from skm.modules.planning.generated.results import ListDraftsResult
from skm.modules.planning.generated.views import DraftSummaryView
from skm.modules.planning.ports import DraftRepository, RevisionRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: ListDrafts) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: ListDrafts, _ctx: QueryContext, uow: UnitOfWork) -> ListDraftsResult:
    plan = require_plan(uow, query.plan_id)
    try:
        state = DraftState(query.state)
    except ValueError as err:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid draft state filter",
            details={"field": "state"},
        ) from err

    drafts = uow.repo(DraftRepository).list_for_plan(plan.id, state=state)
    rev_repo = uow.repo(RevisionRepository)
    items: list[DraftSummaryView] = []
    for draft in drafts:
        base_no = (
            None if draft.base_revision_id is None else rev_repo.get_meta(draft.base_revision_id).revision_no
        )
        stale = draft.state is DraftState.OPEN and draft.base_revision_id != plan.current_revision_id
        items.append(
            DraftSummaryView(
                draft_id=draft.id,
                base_revision_id=draft.base_revision_id,
                base_revision_no=base_no,
                edit_version=draft.edit_version,
                state=draft.state.value,
                created_by=draft.created_by,
                created_at=draft.created_at,
                updated_by=draft.updated_by,
                updated_at=draft.updated_at,
                stale=stale,
            )
        )
    return ListDraftsResult(items=tuple(items))


SPEC = QuerySpec(
    name="planning.list_drafts",
    dto=ListDrafts,
    result=ListDraftsResult,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
