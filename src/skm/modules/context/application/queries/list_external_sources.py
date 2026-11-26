"""Cursor-paginated external sources with live per-result disclosure checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context.application.queries.find_research_cache import load_result, research_scope
from skm.modules.context.domain.research_rules import invalid
from skm.modules.context.generated.queries import ListExternalSources
from skm.modules.context.generated.views import ExternalSourcesView, external_sources_view_from_json
from skm.modules.context.ports import ResearchRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

_FIELDS = (
    "document_id",
    "origin",
    "url",
    "title",
    "retrieved_at",
    "content_digest",
    "trust_class",
    "classification",
    "captured_file_version_id",
    "query_id",
)


def scope_of(query: ListExternalSources) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def handle(query: ListExternalSources, ctx: QueryContext, uow: UnitOfWork) -> ExternalSourcesView:
    data = cast("dict[str, Any]", query)
    wid, pid = research_scope(ctx, uow, data["project_id"])
    limit = data.get("limit", 50)
    if not 1 <= limit <= 200:
        raise invalid("invalid_limit")
    if "query_id" in query:
        load_result(ctx, uow, data["project_id"], data["query_id"])
    after = data.get("after")
    items: list[JsonObject] = []
    checked: dict[str, bool] = {}
    while len(items) <= limit:
        page = uow.repo(ResearchRepository).list_documents(
            workspace_id=wid,
            project_id=pid,
            query_id=data.get("query_id"),
            origin_prefix=data.get("origin_prefix"),
            after=after,
            limit=limit + 1 if limit < 200 else 200,
        )
        rows = cast("list[JsonObject]", page["items"])
        for doc in rows:
            qid = str(doc["query_id"])
            if qid not in checked:
                try:
                    load_result(ctx, uow, data["project_id"], qid)
                    checked[qid] = True
                except NotFound:
                    checked[qid] = False
            if checked[qid]:
                items.append({key: doc.get(key) for key in _FIELDS})
                if len(items) > limit:
                    return external_sources_view_from_json(
                        {"items": items[:limit], "next_after": items[limit - 1]["document_id"]}
                    )
        after = cast("str | None", page["next_after"])
        if after is None:
            break
    return external_sources_view_from_json({"items": items, "next_after": None})


SPEC = QuerySpec(
    name="context.list_external_sources",
    dto=ListExternalSources,
    result=ExternalSourcesView,
    permission="context.read",
    scope_of=scope_of,
    handler=handle,
)
