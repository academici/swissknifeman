"""``planning.list_revisions`` (planning §8): list revisions of a plan ordered by ``revision_no`` desc."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_plan
from skm.modules.planning.generated.queries import ListRevisions
from skm.modules.planning.generated.views import RevisionSummaryView, RevisionsView
from skm.modules.planning.ports import RevisionRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_MAX_LIMIT = 200


def scope_of(query: ListRevisions) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: ListRevisions, _ctx: QueryContext, uow: UnitOfWork) -> RevisionsView:
    plan = require_plan(uow, query.plan_id)
    if isinstance(query.limit, bool) or not 1 <= query.limit <= _MAX_LIMIT:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"limit must be between 1 and {_MAX_LIMIT}",
            details={"field": "limit"},
        )
    if query.before is not None and (isinstance(query.before, bool) or query.before < 1):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "before must be >= 1",
            details={"field": "before"},
        )

    rev_repo = uow.repo(RevisionRepository)
    rows = rev_repo.list_for_plan(
        plan.id,
        before_revision_no=query.before,
        limit=query.limit + 1,
    )
    has_more = len(rows) > query.limit
    sliced = rows[: query.limit]

    items: list[RevisionSummaryView] = []
    for meta in sliced:
        restored_from_no = (
            None
            if meta.restored_from_revision_id is None
            else rev_repo.get_meta(meta.restored_from_revision_id).revision_no
        )
        items.append(
            RevisionSummaryView(
                revision_id=meta.id,
                revision_no=meta.revision_no,
                parent_revision_id=meta.parent_revision_id,
                origin=meta.origin.value,
                restored_from_revision_no=restored_from_no,
                content_digest=meta.content_digest,
                published_by=meta.published_by,
                published_at=meta.published_at,
                change_reason=meta.change_reason,
            )
        )

    next_cursor = str(sliced[-1].revision_no) if has_more and sliced else None
    return RevisionsView(items=tuple(items), next_cursor=next_cursor)


SPEC = QuerySpec(
    name="planning.list_revisions",
    dto=ListRevisions,
    result=RevisionsView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
