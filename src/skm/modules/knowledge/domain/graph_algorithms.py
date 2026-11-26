"""Directed traversal and statistics over a supplied multigraph."""

from collections import Counter, defaultdict, deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Literal, cast
from uuid import UUID

from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonObject

from .contracts import Adjacency, GraphStats
from .graph import EdgeType, GraphEdge, GraphEdgeId, GraphNode, GraphNodeId, NodeType, project_reference
from .graph_index import GraphBasis, GraphIndexId

type Direction = Literal["in", "out", "both"]


@dataclass(frozen=True, slots=True)
class Traversal:
    direction: Direction = "both"
    edge_types: frozenset[EdgeType] | None = None
    project_id: ProjectId | None = None
    project_visible: Callable[[ProjectId], bool] | None = None


def node_visible(node: GraphNode, project_visible: Callable[[ProjectId], bool]) -> bool:
    return all(
        project_visible(project)
        for project in (node.project_id, project_reference(node))
        if project is not None
    )


DEFAULT_TRAVERSAL = Traversal()


@dataclass(frozen=True, slots=True)
class SubgraphView:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    distances: Mapping[GraphNodeId, int] = field(default_factory=dict[GraphNodeId, int])
    path: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Neighborhood:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    omitted_nodes: int = 0
    beyond_depth: int = 0

    def to_adjacency(self) -> Adjacency:
        # The P00 repository port carries a JSON object. UUIDs are the only non-JSON field values.
        def row(record: GraphNode | GraphEdge) -> JsonObject:
            return cast(
                "JsonObject",
                {
                    key: str(value) if isinstance(value, UUID) else value
                    for key, value in asdict(record).items()
                },
            )

        return {
            "nodes": [row(node) for node in self.nodes],
            "edges": [row(edge) for edge in self.edges],
            "omitted_nodes": self.omitted_nodes,
            "beyond_depth": self.beyond_depth,
            "truncated": bool(self.omitted_nodes),
        }

    @classmethod
    def from_adjacency(cls, value: Adjacency) -> "Neighborhood":
        nodes = tuple(node_from_row(row) for row in cast("list[JsonObject]", value["nodes"]))
        edges = tuple(
            GraphEdge(
                GraphEdgeId(UUID(cast("str", row["id"]))),
                WorkspaceId(UUID(cast("str", row["workspace_id"]))),
                GraphNodeId(UUID(cast("str", row["src_node_id"]))),
                GraphNodeId(UUID(cast("str", row["dst_node_id"]))),
                EdgeType(row["type"]),
                cast("JsonObject", row["attrs"]),
                cast("str", row["source"]),
                RepositoryId(UUID(cast("str", row["repository_id"])))
                if row["repository_id"] is not None
                else None,
                cast("str", row["source_key"]),
                GraphBasis(row["basis"]) if row["basis"] is not None else None,
                _index_id(row),
            )
            for row in cast("list[JsonObject]", value["edges"])
        )
        return cls(nodes, edges, cast("int", value["omitted_nodes"]), cast("int", value["beyond_depth"]))


def _index_id(row: JsonObject) -> GraphIndexId | None:
    value = row.get("index_id")
    return GraphIndexId(UUID(value)) if isinstance(value, str) else None


def node_from_row(row: JsonObject) -> GraphNode:
    return GraphNode(
        GraphNodeId(UUID(cast("str", row["id"]))),
        WorkspaceId(UUID(cast("str", row["workspace_id"]))),
        ProjectId(UUID(cast("str", row["project_id"]))) if row["project_id"] is not None else None,
        cast("str", row["node_key"]),
        NodeType(row["type"]),
        cast("JsonObject", row["attrs"]),
        cast("str", row["source"]),
        RepositoryId(UUID(cast("str", row["repository_id"]))) if row["repository_id"] is not None else None,
        _index_id(row),
    )


@dataclass(frozen=True, slots=True)
class NeighborHit:
    node_id: GraphNodeId
    distance: int
    via_edge_ids: tuple[GraphEdgeId, ...]


def _adjacent(
    edges: Iterable[GraphEdge], traversal: Traversal
) -> dict[GraphNodeId, list[tuple[GraphNodeId, GraphEdgeId]]]:
    adjacent: dict[GraphNodeId, list[tuple[GraphNodeId, GraphEdgeId]]] = defaultdict(list)
    for edge in edges:
        if traversal.edge_types is not None and edge.type not in traversal.edge_types:
            continue
        if traversal.direction != "in":
            adjacent[edge.src_node_id].append((edge.dst_node_id, edge.id))
        if traversal.direction != "out" and (
            traversal.direction == "in" or edge.src_node_id != edge.dst_node_id
        ):
            adjacent[edge.dst_node_id].append((edge.src_node_id, edge.id))
    return adjacent


def neighbors(
    adj: SubgraphView,
    root: GraphNodeId,
    *,
    depth: int,
    edge_types: frozenset[EdgeType] | None = None,
    direction: Direction = "out",
) -> tuple[NeighborHit, ...]:
    adjacent = _adjacent(adj.edges, Traversal(direction, edge_types))
    hits = _distances(adjacent, (root,), depth)
    via: dict[GraphNodeId, list[GraphEdgeId]] = defaultdict(list)
    for parent, distance in hits.items():
        for child, edge_id in adjacent.get(parent, ()):
            if hits.get(child) == distance + 1:
                via[child].append(edge_id)
    return tuple(NeighborHit(node, distance, tuple(via[node])) for node, distance in hits.items())


def _distances(
    adjacent: Mapping[GraphNodeId, list[tuple[GraphNodeId, GraphEdgeId]]],
    roots: Iterable[GraphNodeId],
    depth: int,
) -> dict[GraphNodeId, int]:
    distances = dict.fromkeys(roots, 0)
    pending = deque(distances)
    while pending:
        current = pending.popleft()
        if distances[current] >= depth:
            continue
        for node, _ in adjacent.get(current, ()):
            if node not in distances:
                distances[node] = distances[current] + 1
                pending.append(node)
    return distances


def shortest_path(
    adj: SubgraphView,
    src: GraphNodeId,
    dst: GraphNodeId,
    *,
    edge_types: frozenset[EdgeType] | None = None,
    direction: Direction = "out",
) -> tuple[GraphEdgeId, ...] | None:
    if src == dst:
        return ()
    adjacent = _adjacent(adj.edges, Traversal(direction, edge_types))
    pending = deque([src])
    parents: dict[GraphNodeId, tuple[GraphNodeId, GraphEdgeId]] = {}
    while pending:
        current = pending.popleft()
        for node, edge_id in adjacent.get(current, ()):
            if node == src or node in parents:
                continue
            parents[node] = current, edge_id
            if node == dst:
                path: list[GraphEdgeId] = []
                step = dst
                while step != src:
                    step, via = parents[step]
                    path.append(via)
                return tuple(reversed(path))
            pending.append(node)
    return None


def subgraph(
    adj: SubgraphView,
    roots: Iterable[GraphNodeId],
    *,
    depth: int,
    direction: Direction = "both",
    edge_types: frozenset[EdgeType] | None = None,
) -> SubgraphView:
    known = {node.id for node in adj.nodes}
    adjacent = _adjacent(
        (edge for edge in adj.edges if edge.src_node_id in known and edge.dst_node_id in known),
        Traversal(direction, edge_types),
    )
    distances = _distances(adjacent, (root for root in roots if root in known), depth)
    return SubgraphView(
        tuple(node for node in adj.nodes if node.id in distances),
        tuple(
            edge
            for edge in adj.edges
            if edge.src_node_id in distances
            and edge.dst_node_id in distances
            and (edge_types is None or edge.type in edge_types)
        ),
        distances,
    )


def components(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> tuple[frozenset[GraphNodeId], ...]:
    remaining = dict.fromkeys(node.id for node in nodes)
    adjacent = _adjacent(
        (edge for edge in edges if edge.src_node_id in remaining and edge.dst_node_id in remaining),
        Traversal(),
    )
    groups: list[frozenset[GraphNodeId]] = []
    while remaining:
        group = frozenset(_distances(adjacent, (next(iter(remaining)),), len(remaining)))
        for node in group:
            del remaining[node]
        groups.append(group)
    return tuple(groups)


def stats(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]) -> GraphStats:
    referenced = {endpoint for edge in edges for endpoint in (edge.src_node_id, edge.dst_node_id)}
    return {
        "nodes_by_type": dict(Counter(node.type.value for node in nodes)),
        "edges_by_type": dict(Counter(edge.type.value for edge in edges)),
        "components": len(components(nodes, edges)),
        "isolated": sum(node.id not in referenced for node in nodes),
    }


def bounded_neighborhood(
    graph: SubgraphView,
    roots: tuple[GraphNodeId, ...],
    *,
    depth: int,
    max_nodes: int,
    traversal: Traversal = DEFAULT_TRAVERSAL,
) -> Neighborhood:
    nodes = {
        node.id: node
        for node in graph.nodes
        if (traversal.project_id is None or node.project_id == traversal.project_id)
        and (traversal.project_visible is None or node_visible(node, traversal.project_visible))
    }
    edges = tuple(
        edge
        for edge in graph.edges
        if edge.src_node_id in nodes
        and edge.dst_node_id in nodes
        and (traversal.edge_types is None or edge.type in traversal.edge_types)
    )
    seeds = sorted(nodes.keys() & set(roots)) if roots else sorted(nodes)
    frontier = seeds[:max_nodes]
    visited = dict.fromkeys(frontier)
    omitted = len(seeds) - len(frontier)
    beyond_depth = 0
    if roots:
        adjacent = _adjacent(edges, traversal)
        for distance in range(depth + 1):
            if not frontier or omitted:
                break
            candidates = {
                child for parent in frontier for child, _ in adjacent.get(parent, ()) if child not in visited
            }
            if distance == depth:
                beyond_depth = len(candidates)
                break
            frontier = sorted(candidates)[: max_nodes - len(visited)]
            omitted = len(candidates) - len(frontier)
            visited.update(dict.fromkeys(frontier))
    return Neighborhood(
        tuple(nodes[node_id] for node_id in sorted(visited)),
        tuple(edge for edge in edges if edge.src_node_id in visited and edge.dst_node_id in visited),
        omitted,
        beyond_depth,
    )
