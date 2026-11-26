"""List the latest visible graph index for each source and repository."""

from typing import Any
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import RepositoryId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.contracts import GraphIndexesView, ListGraphIndexes
from skm.modules.knowledge.domain.graph_index import GraphIndex
from skm.modules.knowledge.ports import GraphRepository
from skm.modules.workspace.public import require_repository

from .graph_neighbors import graph_visibility


def _view(index: GraphIndex) -> dict[str, Any]:
    return {
        "id": str(index.id),
        "workspace_id": str(index.workspace_id),
        "project_id": str(index.project_id) if index.project_id is not None else None,
        "repository_id": str(index.repository_id) if index.repository_id is not None else None,
        "source": index.source,
        "generation": index.generation,
        "revision": index.revision,
        "dirty": index.dirty,
        "languages": list(index.languages),
        "basis_default": index.basis_default.value,
        "tool_name": index.tool_name,
        "tool_version": index.tool_version,
        "indexed_at": index.indexed_at.isoformat(),
        "completeness": index.completeness.value,
        "limitations": [
            {"code": item.code.value, "message": item.message, "count": item.count}
            for item in index.limitations
        ],
        "files_indexed": index.files_indexed,
        "files_skipped": index.files_skipped,
        "nodes": index.nodes,
        "edges": index.edges,
    }


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> GraphIndexesView:
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    repository = RepositoryId(UUID(query["repository_id"])) if "repository_id" in query else None
    if repository is not None:
        require_repository(uow, workspace, repository)
    source = query.get("source")
    indexes = uow.repo(GraphRepository).latest_indexes(workspace, source=source, repository_id=repository)
    visible = graph_visibility(uow, ctx, workspace)
    items = [
        _view(index)
        for index in sorted(indexes, key=lambda item: (item.source, str(item.repository_id or "")))
        if index.project_id is None or visible(index.project_id)
    ]
    return GraphIndexesView.from_json({"items": items})


SPEC = QuerySpec(
    name="knowledge.list_graph_indexes",
    dto=ListGraphIndexes,
    result=GraphIndexesView,
    permission="memory.read",
    scope_of=lambda query: workspace_ref(query["workspace_id"]),
    handler=handle,
)
