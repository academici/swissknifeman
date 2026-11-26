"""Summarize the bounded graph in a workspace or one of its projects."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.domain.graph_algorithms import SubgraphView, Traversal
from skm.modules.knowledge.generated.documents import GraphAnswer
from skm.modules.knowledge.generated.queries import GraphStats
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import GraphRepository

from .graph_neighbors import answer, graph_visibility, project_visible, read_neighborhood


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> GraphAnswer:
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    project = ProjectId(UUID(query["project_id"])) if "project_id" in query else None
    if project is not None and not project_visible(uow, ctx, workspace, project):
        raise NotFound(ErrorCode.NOT_FOUND, "Graph project not found")
    repo = uow.repo(GraphRepository)
    loaded = read_neighborhood(
        repo,
        workspace,
        (),
        depth=0,
        max_nodes=ctx.config.section(KnowledgeSettings).graph.max_nodes,
        traversal=Traversal(project_id=project, project_visible=graph_visibility(uow, ctx, workspace)),
    )
    return answer(repo, ctx, workspace, {"op": "stats"}, SubgraphView(loaded.nodes, loaded.edges), loaded)


SPEC = QuerySpec(
    name="knowledge.graph_stats",
    dto=cast("type[dict[str, Any]]", GraphStats),
    result=GraphAnswer,
    permission="memory.read",
    scope_of=lambda query: workspace_ref(query["workspace_id"]),
    handler=handle,
)
