"""Fetch a ledger result only after checking the current project and policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context.application.queries.find_research_cache import load_result
from skm.modules.context.domain.research import result_to_json
from skm.modules.context.generated.queries import GetResearchQuery
from skm.modules.context.generated.views import ResearchResultView, research_result_view_from_json

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork


def scope_of(query: GetResearchQuery) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def handle(query: GetResearchQuery, ctx: QueryContext, uow: UnitOfWork) -> ResearchResultView:
    data = cast("dict[str, Any]", query)
    _, result = load_result(ctx, uow, data["project_id"], data["query_id"])
    return research_result_view_from_json({"result": result_to_json(result)})


SPEC = QuerySpec(
    name="context.get_research_query",
    dto=GetResearchQuery,
    result=ResearchResultView,
    permission="context.read",
    scope_of=scope_of,
    handler=handle,
)
