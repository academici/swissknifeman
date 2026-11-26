"""Recall live memory from the project and its explicitly enabled shared scopes."""

from datetime import datetime, timedelta
from typing import Any, cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import project_memory_scope, project_ref, requested_scope
from skm.modules.knowledge.application.views import memory_view
from skm.modules.knowledge.domain.memory_entry import MemoryEntry
from skm.modules.knowledge.domain.memory_scope import (
    MemoryScope,
    MemoryScopeKind,
    ensure_scope_allowed,
    recall_scopes,
)
from skm.modules.knowledge.domain.recall import rank_entries
from skm.modules.knowledge.generated.queries import SearchMemory
from skm.modules.knowledge.generated.settings import KnowledgeMemorySettings, KnowledgeSettings
from skm.modules.knowledge.generated.views import MemorySearchView, memory_search_view_from_json
from skm.modules.knowledge.ports import MemoryRepository


def search(
    repo: MemoryRepository,
    scopes: tuple[MemoryScope, ...],
    *,
    now: datetime,
    query: str | None,
    settings: KnowledgeMemorySettings,
) -> tuple[tuple[MemoryEntry, ...], bool]:
    selected: list[MemoryEntry] = []
    truncated = False
    created_after = now - timedelta(hours=settings.max_ttl_hours)
    for scope in scopes:
        limit = (
            settings.recall_limit if scope.kind is MemoryScopeKind.PROJECT else settings.recall_shared_limit
        )
        if limit == 0:
            continue
        candidates = repo.search_candidates(scope, now=now, query=query, created_after=created_after)
        ranked = rank_entries(candidates, query, now, settings, limit=limit + 1)
        selected.extend(ranked[:limit])
        truncated = truncated or len(ranked) > limit
    return tuple(selected), truncated


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> MemorySearchView:
    project = project_memory_scope(uow, query["project_id"])
    settings = ctx.config.section(KnowledgeSettings).memory
    scopes = recall_scopes(project, settings.namespaces, include_shared=query.get("include_shared", False))
    if (target := query.get("scope")) is not None:
        scope = requested_scope(target["kind"], target.get("namespace"), project)
        ensure_scope_allowed(scope, scopes)
        scopes = (scope,)
    rows, truncated = search(
        uow.repo(MemoryRepository),
        scopes,
        now=ctx.clock.now(),
        query=query.get("query") or None,
        settings=settings,
    )
    if (limit := query.get("limit")) is not None and len(rows) > limit:
        rows = rows[:limit]
        truncated = True
    return memory_search_view_from_json({"items": [memory_view(row) for row in rows], "truncated": truncated})


SPEC = QuerySpec(
    name="knowledge.search_memory",
    dto=cast("type[dict[str, Any]]", SearchMemory),
    result=MemorySearchView,
    permission="memory.read",
    scope_of=lambda query: project_ref(query["project_id"]),
    handler=handle,
)
