"""``planning.get_revision`` (planning §8): return ``RevisionView`` by id, number, or current."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import PlanId, RevisionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import (
    build_tree,
    require_plan,
    require_revision_in_plan,
)
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.revision import RevisionMeta
from skm.modules.planning.domain.specification import from_document
from skm.modules.planning.generated.documents import SpecificationDoc, specification_doc_from_json
from skm.modules.planning.generated.queries import GetRevision
from skm.modules.planning.generated.views import RevisionView
from skm.modules.planning.ports import RevisionRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: GetRevision) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def _resolve_revision_meta(
    rev_repo: RevisionRepository, query: GetRevision, plan_id: PlanId, current_revision_id: RevisionId | None
) -> RevisionMeta:
    selectors = (
        query.revision_id is not None,
        query.revision_no is not None,
        query.current is True,
    )
    if sum(1 for flag in selectors if flag) != 1:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "specify exactly one of revision_id, revision_no, or current=True",
            details={
                "issues": [
                    {
                        "pointer": "",
                        "message": "invalid revision selector",
                        "schema_pointer": "",
                    }
                ]
            },
        )

    if query.revision_id is not None:
        meta = rev_repo.get_meta(RevisionId(query.revision_id))
        require_revision_in_plan(meta, plan_id)
        return meta

    if query.revision_no is not None:
        if isinstance(query.revision_no, bool) or query.revision_no < 1:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "revision_no must be >= 1",
                details={"field": "revision_no"},
            )
        found = rev_repo.find_by_number(plan_id, query.revision_no)
        if found is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "revision not found",
                details={"kind": "revision", "ref": str(query.revision_no)},
            )
        return found

    if current_revision_id is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "plan has no current revision",
            details={"kind": "revision", "ref": "current"},
        )
    return rev_repo.get_meta(current_revision_id)


def handle(query: GetRevision, _ctx: QueryContext, uow: UnitOfWork) -> RevisionView:
    plan = require_plan(uow, query.plan_id)
    rev_repo = uow.repo(RevisionRepository)
    meta = _resolve_revision_meta(rev_repo, query, plan.id, plan.current_revision_id)

    restored_from_no: int | None = None
    if meta.restored_from_revision_id is not None:
        restored_from_no = rev_repo.get_meta(meta.restored_from_revision_id).revision_no

    include_doc = bool(query.include_document)
    include_tree = bool(query.include_tree)

    doc_view: SpecificationDoc | None = None
    tree_view: JsonObject | None = None
    if include_doc or include_tree:
        raw_doc = normalize_document(rev_repo.get_document(meta.id))
        if include_doc:
            doc_view = specification_doc_from_json(raw_doc)
        if include_tree:
            spec, _ = from_document(raw_doc)
            tree_view = build_tree(spec)

    return RevisionView(
        revision_id=meta.id,
        revision_no=meta.revision_no,
        parent_revision_id=meta.parent_revision_id,
        origin=meta.origin.value,
        restored_from_revision_no=restored_from_no,
        content_digest=meta.content_digest,
        published_by=meta.published_by,
        published_at=meta.published_at,
        change_reason=meta.change_reason,
        plan_id=meta.plan_id,
        schema_version=meta.schema_version,
        canonicalization_version=meta.canonicalization_version,
        compiler_version=meta.compiler_version,
        document=doc_view,
        tree=tree_view,
    )


SPEC = QuerySpec(
    name="planning.get_revision",
    dto=GetRevision,
    result=RevisionView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
