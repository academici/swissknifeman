"""Read a bounded, induced graph around one or more visible nodes."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.domain.contracts import GraphQueryEcho
from skm.modules.knowledge.domain.graph import EdgeType, GraphNode
from skm.modules.knowledge.domain.graph_algorithms import Direction, SubgraphView, Traversal, subgraph
from skm.modules.knowledge.generated.documents import GraphAnswer
from skm.modules.knowledge.generated.queries import GraphSubgraph
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import GraphRepository

from .graph_neighbors import answer, graph_visibility, read_neighborhood, require_root
from .graph_path import _path_hits  # pyright: ignore[reportPrivateUsage] -- shared path projection


def project_graph(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> GraphAnswer:
    """Read neighbors or paths wholly within the project selected by the caller."""
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    project = ProjectId(UUID(query["project_id"]))
    if ctx.scope_chain[-1].workspace_id != workspace:
        raise NotFound(ErrorCode.NOT_FOUND, "Graph project not found in this workspace")
    repo = uow.repo(GraphRepository)
    visible = graph_visibility(uow, ctx, workspace)

    def require_project_root(key: str) -> GraphNode:
        node = require_root(repo, workspace, key, visible)
        if node.project_id != project:
            raise NotFound(ErrorCode.NOT_FOUND, "Graph node not found", details={"node_key": key})
        return node

    is_path = "src_key" in query
    root = require_project_root(query["src_key"] if is_path else query["node_key"])
    destination = require_project_root(query["dst_key"]) if is_path else None
    limits = ctx.config.section(KnowledgeSettings).graph
    requested = query.get("depth", 1) if destination is None else limits.max_depth
    depth = min(requested, limits.max_depth)
    direction: Direction = query.get("direction", "out")
    edge_types = frozenset(map(EdgeType, query["edge_types"])) if "edge_types" in query else None
    traversal = Traversal(direction, edge_types, project_id=project, project_visible=visible)
    loaded = read_neighborhood(
        repo, workspace, (root.id,), depth=depth, max_nodes=limits.max_nodes, traversal=traversal
    )
    graph = SubgraphView(loaded.nodes, loaded.edges)
    if destination is not None:
        hits = _path_hits(graph, root, destination.id, traversal, depth)
        echo: GraphQueryEcho = {"op": "path", "src": root.node_key, "dst": destination.node_key}
        depth_capped = hits.path is None
    else:
        neighborhood = subgraph(graph, (root.id,), depth=depth, direction=direction, edge_types=edge_types)
        edges = tuple(
            edge
            for edge in neighborhood.edges
            if (direction != "in" and neighborhood.distances[edge.src_node_id] < depth)
            or (direction != "out" and neighborhood.distances[edge.dst_node_id] < depth)
        )
        hits = SubgraphView(neighborhood.nodes, edges, neighborhood.distances)
        echo = {"op": "neighbors", "root": root.node_key, "depth": requested}
        depth_capped = requested > depth
    echo["direction"] = direction
    if "edge_types" in query:
        echo["edge_types"] = list(query["edge_types"])
    if "at_revision" in query:
        echo["at_revision"] = query["at_revision"]
    return answer(repo, ctx, workspace, echo, hits, loaded, depth_capped=depth_capped)


def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> GraphAnswer:
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    repo = uow.repo(GraphRepository)
    visible = graph_visibility(uow, ctx, workspace)
    root_nodes = tuple(require_root(repo, workspace, key, visible) for key in dict.fromkeys(query["roots"]))
    roots = tuple(node.id for node in root_nodes)
    limits = ctx.config.section(KnowledgeSettings).graph
    requested = query.get("depth", 1)
    depth = min(requested, limits.max_depth)
    direction: Direction = query.get("direction", "both")
    edge_types = frozenset(map(EdgeType, query["edge_types"])) if "edge_types" in query else None
    loaded = read_neighborhood(
        repo,
        workspace,
        roots,
        depth=depth,
        max_nodes=limits.max_nodes,
        traversal=Traversal(direction, edge_types, project_visible=visible),
    )
    hits = subgraph(
        SubgraphView(loaded.nodes, loaded.edges),
        roots,
        depth=depth,
        direction=direction,
        edge_types=edge_types,
    )
    echo: GraphQueryEcho = {
        "op": "subgraph",
        "roots": list(query["roots"]),
        "depth": requested,
        "direction": direction,
    }
    repositories = {node.repository_id for node in root_nodes}
    if len(repositories) == 1 and None not in repositories:
        primary = next((node for node in root_nodes if node.index_id is not None), None)
        if primary is not None:
            echo["root"] = primary.node_key
    if "edge_types" in query:
        echo["edge_types"] = list(query["edge_types"])
    if "at_revision" in query:
        echo["at_revision"] = query["at_revision"]
    return answer(repo, ctx, workspace, echo, hits, loaded, depth_capped=requested > depth)


SPEC = QuerySpec(
    name="knowledge.graph_subgraph",
    dto=cast("type[dict[str, Any]]", GraphSubgraph),
    result=GraphAnswer,
    permission="memory.read",
    scope_of=lambda query: workspace_ref(query["workspace_id"]),
    handler=handle,
)
