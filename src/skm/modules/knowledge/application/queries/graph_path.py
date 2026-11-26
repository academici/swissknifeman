"""Find the shortest directed path in the bounded, visible graph."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.domain.contracts import GraphQueryEcho
from skm.modules.knowledge.domain.graph import EdgeType, GraphNode, GraphNodeId
from skm.modules.knowledge.domain.graph_algorithms import Direction, SubgraphView, Traversal, shortest_path
from skm.modules.knowledge.generated.documents import GraphAnswer
from skm.modules.knowledge.generated.queries import GraphPath
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import GraphRepository

from .graph_neighbors import answer, graph_visibility, read_neighborhood, require_root


def _path_hits(
    graph: SubgraphView, source: GraphNode, destination: GraphNodeId, traversal: Traversal, depth: int
) -> SubgraphView:
    path = shortest_path(
        graph, source.id, destination, direction=traversal.direction, edge_types=traversal.edge_types
    )
    if path is None or len(path) > depth:
        return SubgraphView((source,), ())
    by_id = {edge.id: edge for edge in graph.edges}
    nodes = {node.id: node for node in graph.nodes}
    edges = tuple(by_id[edge_id] for edge_id in path)
    ordered = [source]
    for edge in edges:
        current = ordered[-1].id
        ordered.append(nodes[edge.dst_node_id if edge.src_node_id == current else edge.src_node_id])
    return SubgraphView(tuple(ordered), edges, path=tuple(node.node_key for node in ordered))


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> GraphAnswer:
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    repo = uow.repo(GraphRepository)
    visible = graph_visibility(uow, ctx, workspace)
    src = require_root(repo, workspace, query["src_key"], visible)
    dst = require_root(repo, workspace, query["dst_key"], visible)
    direction: Direction = query.get("direction", "out")
    kinds = frozenset(map(EdgeType, query["edge_types"])) if "edge_types" in query else None
    traversal = Traversal(direction, kinds, project_visible=visible)
    limits = ctx.config.section(KnowledgeSettings).graph
    loaded = read_neighborhood(
        repo,
        workspace,
        (src.id,),
        depth=limits.max_depth,
        max_nodes=limits.max_nodes,
        traversal=traversal,
    )
    hits = _path_hits(SubgraphView(loaded.nodes, loaded.edges), src, dst.id, traversal, limits.max_depth)
    echo: GraphQueryEcho = {"op": "path", "src": src.node_key, "dst": dst.node_key, "direction": direction}
    if "edge_types" in query:
        echo["edge_types"] = list(query["edge_types"])
    if "at_revision" in query:
        echo["at_revision"] = query["at_revision"]
    return answer(repo, ctx, workspace, echo, hits, loaded, depth_capped=hits.path is None)


SPEC = QuerySpec(
    name="knowledge.graph_path",
    dto=cast("type[dict[str, Any]]", GraphPath),
    result=GraphAnswer,
    permission="memory.read",
    scope_of=lambda query: workspace_ref(query["workspace_id"]),
    handler=handle,
)
