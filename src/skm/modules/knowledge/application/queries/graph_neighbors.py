"""Workspace-authorized graph traversal and shared presentation for graph queries."""

from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any, Protocol, cast, override
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.public import effective_permissions
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.domain.contracts import Adjacency, GraphQueryEcho
from skm.modules.knowledge.domain.graph import EdgeType, GraphNode, GraphNodeId
from skm.modules.knowledge.domain.graph_algorithms import (
    DEFAULT_TRAVERSAL,
    Direction,
    Neighborhood,
    SubgraphView,
    Traversal,
    node_visible,
    subgraph,
)
from skm.modules.knowledge.domain.graph_answer import build_answer, contributing_index_ids
from skm.modules.knowledge.domain.graph_index import GraphIndex, GraphIndexId, LimitationCode
from skm.modules.knowledge.generated.documents import GraphAnswer
from skm.modules.knowledge.generated.queries import GraphNeighbors
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import GraphRepository
from skm.modules.workspace.public import workspace_of_project


class _GraphReader(GraphRepository, Protocol):
    def indexes_by_id(
        self, workspace_id: WorkspaceId, ids: frozenset[GraphIndexId]
    ) -> Mapping[GraphIndexId, GraphIndex]: ...

    @override
    def neighborhood(
        self,
        workspace_id: WorkspaceId,
        roots: tuple[GraphNodeId, ...],
        *,
        depth: int,
        max_nodes: int,
        traversal: Traversal = DEFAULT_TRAVERSAL,
    ) -> Adjacency: ...


def project_visible(uow: UnitOfWork, ctx: QueryContext, workspace: WorkspaceId, project: ProjectId) -> bool:
    try:
        return workspace_of_project(uow, project) == workspace and "project.read" in effective_permissions(
            uow, ctx.actor, ScopeId(project)
        )
    except NotFound:
        return False


def graph_visibility(
    uow: UnitOfWork, ctx: QueryContext, workspace: WorkspaceId
) -> Callable[[ProjectId], bool]:
    allowed: dict[ProjectId, bool] = {}

    def holds(project: ProjectId) -> bool:
        if project not in allowed:
            allowed[project] = project_visible(uow, ctx, workspace, project)
        return allowed[project]

    return holds


def require_root(
    repo: GraphRepository, workspace: WorkspaceId, key: str, visible: Callable[[ProjectId], bool]
) -> GraphNode:
    node = repo.node_by_key(workspace, key)
    if node is None or not node_visible(node, visible):
        raise NotFound(ErrorCode.NOT_FOUND, "Graph node not found", details={"node_key": key})
    return node


def read_neighborhood(
    repo: GraphRepository,
    workspace: WorkspaceId,
    roots: tuple[GraphNodeId, ...],
    *,
    depth: int,
    max_nodes: int,
    traversal: Traversal,
) -> Neighborhood:
    return Neighborhood.from_adjacency(
        cast("_GraphReader", repo).neighborhood(
            workspace, roots, depth=depth, max_nodes=max_nodes, traversal=traversal
        )
    )


def answer(
    repo: GraphRepository,
    ctx: QueryContext,
    workspace: WorkspaceId,
    echo: GraphQueryEcho,
    hits: SubgraphView,
    loaded: Neighborhood,
    *,
    depth_capped: bool = False,
) -> GraphAnswer:
    counts: dict[LimitationCode, int] = {}
    if loaded.omitted_nodes:
        counts[LimitationCode.NODE_LIMIT] = loaded.omitted_nodes
    if depth_capped and loaded.beyond_depth:
        counts[LimitationCode.DEPTH_LIMIT] = loaded.beyond_depth
    settings = ctx.config.section(KnowledgeSettings)
    return build_answer(
        echo,
        hits,
        cast("_GraphReader", repo).indexes_by_id(workspace, contributing_index_ids(hits)),
        now=ctx.clock.now(),
        stale_after=timedelta(hours=settings.code_graph.stale_after_hours),
        limits_hit=frozenset(counts),
        limit_counts=counts,
    ).to_document()


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> GraphAnswer:
    repo = uow.repo(GraphRepository)
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    visible = graph_visibility(uow, ctx, workspace)
    root = require_root(repo, workspace, query["node_key"], visible)
    limits = ctx.config.section(KnowledgeSettings).graph
    requested = query.get("depth", 1)
    depth = min(requested, limits.max_depth)
    direction: Direction = query.get("direction", "out")
    edge_types = frozenset(map(EdgeType, query["edge_types"])) if "edge_types" in query else None
    traversal = Traversal(direction, edge_types, project_visible=visible)
    loaded = read_neighborhood(
        repo,
        workspace,
        (root.id,),
        depth=depth,
        max_nodes=limits.max_nodes,
        traversal=traversal,
    )
    hits = subgraph(
        SubgraphView(loaded.nodes, loaded.edges),
        (root.id,),
        depth=depth,
        direction=direction,
        edge_types=edge_types,
    )
    edges = tuple(
        edge
        for edge in hits.edges
        if (direction != "in" and hits.distances[edge.src_node_id] < depth)
        or (direction != "out" and hits.distances[edge.dst_node_id] < depth)
    )
    echo: GraphQueryEcho = {
        "op": "neighbors",
        "root": root.node_key,
        "depth": requested,
        "direction": direction,
    }
    if "edge_types" in query:
        echo["edge_types"] = list(query["edge_types"])
    if "at_revision" in query:
        echo["at_revision"] = query["at_revision"]
    return answer(
        repo,
        ctx,
        workspace,
        echo,
        SubgraphView(hits.nodes, edges, hits.distances),
        loaded,
        depth_capped=requested > depth,
    )


SPEC = QuerySpec(
    name="knowledge.graph_neighbors",
    dto=cast("type[dict[str, Any]]", GraphNeighbors),
    result=GraphAnswer,
    permission="memory.read",
    scope_of=lambda query: workspace_ref(query["workspace_id"]),
    handler=handle,
)
