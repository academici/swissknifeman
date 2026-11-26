"""Paginate memory in one authorized scope."""

from datetime import timedelta
from typing import Any, cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT, Cursor
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import project_memory_scope, project_ref, requested_scope
from skm.modules.knowledge.application.views import memory_view
from skm.modules.knowledge.domain.memory_scope import allowed_scopes, ensure_scope_allowed
from skm.modules.knowledge.generated.queries import ListMemory
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.generated.views import MemoryView, memory_view_from_json
from skm.modules.knowledge.ports import MemoryRepository


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> MemoryView:
    project = project_memory_scope(uow, query["project_id"])
    settings = ctx.config.section(KnowledgeSettings).memory
    target = query.get("scope")
    scope = project if target is None else requested_scope(target["kind"], target.get("namespace"), project)
    ensure_scope_allowed(scope, allowed_scopes(project, settings.namespaces))
    after = query.get("after")
    now = ctx.clock.now()
    page = uow.repo(MemoryRepository).list(
        scope,
        now=now,
        include_expired=query.get("include_expired", False),
        after=Cursor(after) if after is not None else None,
        limit=query.get("limit", DEFAULT_PAGE_LIMIT),
        created_after=now - timedelta(hours=settings.max_ttl_hours),
    )
    return memory_view_from_json(
        {
            "items": [memory_view(row) for row in page.items],
            "next_cursor": page.next,
            "has_more": page.next is not None,
        }
    )


SPEC = QuerySpec(
    name="knowledge.list_memory",
    dto=cast("type[dict[str, Any]]", ListMemory),
    result=MemoryView,
    permission="memory.read",
    scope_of=lambda query: project_ref(query["project_id"]),
    handler=handle,
)
