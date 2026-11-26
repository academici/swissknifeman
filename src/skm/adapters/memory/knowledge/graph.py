"""Transactional in-memory multigraph storage."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Self

from skm.adapters.memory.core.state import MemoryBackendState, copy_tables
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import RepositoryId, WorkspaceId
from skm.modules.knowledge.domain.contracts import Adjacency, ReplaceStats
from skm.modules.knowledge.domain.graph import (
    EdgeIdentity,
    GraphEdge,
    GraphNode,
    GraphNodeId,
    edge_identity,
    source_payload_matches,
)
from skm.modules.knowledge.domain.graph_algorithms import (
    DEFAULT_TRAVERSAL,
    SubgraphView,
    Traversal,
    bounded_neighborhood,
)
from skm.modules.knowledge.domain.graph_answer import IndexKey
from skm.modules.knowledge.domain.graph_index import GraphIndex, GraphIndexId

__all__ = ["MemoryGraphRepository"]


@dataclass
class _GraphState:
    nodes: dict[tuple[WorkspaceId, str], GraphNode] = field(
        default_factory=dict[tuple[WorkspaceId, str], GraphNode]
    )
    edges: dict[EdgeIdentity, GraphEdge] = field(default_factory=dict[EdgeIdentity, GraphEdge])
    indexes: dict[tuple[WorkspaceId, str, RepositoryId | None, int], GraphIndex] = field(
        default_factory=dict[tuple[WorkspaceId, str, RepositoryId | None, int], GraphIndex]
    )

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return copy_tables(self, memo, shared_rows=frozenset({"nodes", "edges", "indexes"}))


def _upsert(
    table: dict[tuple[WorkspaceId, str], GraphNode], nodes: tuple[GraphNode, ...]
) -> dict[str, GraphNodeId]:
    existing_ids = {node.id for node in table.values()}
    ids: dict[str, GraphNodeId] = {}
    for node in {(item.workspace_id, item.node_key): item for item in nodes}.values():
        identity = node.workspace_id, node.node_key
        current = table.get(identity)
        if current is None:
            if node.id in existing_ids:
                raise Conflict(ErrorCode.ALREADY_EXISTS, "Graph node ID already exists")
            table[identity] = deepcopy(node)
            existing_ids.add(node.id)
        elif (node.project_id, node.source, node.repository_id) == (
            current.project_id,
            current.source,
            current.repository_id,
        ):
            table[identity] = replace(current, attrs=deepcopy(dict(node.attrs)), index_id=node.index_id)
        ids[node.node_key] = table[identity].id
    return ids


class MemoryGraphRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        graph = state.modules.setdefault("knowledge.graph", _GraphState())
        if not isinstance(graph, _GraphState):
            raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid graph backend state")
        self._graph = graph

    def lock_workspace(self, workspace_id: WorkspaceId) -> None:  # noqa: ARG002 -- the UoW holds the writer lock
        self._state.core.require_writable()

    def upsert_nodes(self, nodes: tuple[GraphNode, ...]) -> Mapping[str, GraphNodeId]:
        self._state.core.require_writable()
        table = self._graph.nodes.copy()
        result = _upsert(table, tuple(replace(node, index_id=None) for node in nodes))
        self._graph.nodes = table
        return result

    def replace_from_source(
        self,
        workspace_id: WorkspaceId,
        source: str,
        repository_id: RepositoryId | None,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
    ) -> ReplaceStats:
        return self.write_source(workspace_id, source, repository_id, nodes, edges, replace_existing=True)

    def write_source(
        self,
        workspace_id: WorkspaceId,
        source: str,
        repository_id: RepositoryId | None,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
        *,
        replace_existing: bool,
        index: GraphIndex | None = None,
    ) -> ReplaceStats:
        self.lock_workspace(workspace_id)
        if not source_payload_matches(workspace_id, source, repository_id, nodes, edges):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Graph payload is outside its source partition")
        node_table = self._graph.nodes.copy()
        edge_table = self._graph.edges.copy()
        index_id = index.id if index is not None else None
        ids = _upsert(node_table, tuple(replace(node, index_id=index_id) for node in nodes))
        remapped = {node.id: ids[node.node_key] for node in nodes}
        known = {node.id for node in node_table.values() if node.workspace_id == workspace_id}
        incoming: dict[EdgeIdentity, GraphEdge] = {}
        for draft in edges:
            edge = replace(
                draft,
                src_node_id=remapped.get(draft.src_node_id, draft.src_node_id),
                dst_node_id=remapped.get(draft.dst_node_id, draft.dst_node_id),
                index_id=index_id,
            )
            if edge.src_node_id not in known or edge.dst_node_id not in known:
                raise NotFound(ErrorCode.NOT_FOUND, "Graph edge endpoint not found in workspace")
            incoming[edge_identity(edge)] = edge

        added = 0
        edge_ids = {edge.id for edge in edge_table.values()}
        for identity, draft in incoming.items():
            edge = draft
            current = edge_table.get(identity)
            if current is None:
                if edge.id in edge_ids:
                    raise Conflict(ErrorCode.ALREADY_EXISTS, "Graph edge ID already exists")
                edge_ids.add(edge.id)
                added += 1
            elif current.repository_id != repository_id:
                raise Conflict(ErrorCode.ALREADY_EXISTS, "Graph edge identity belongs to another repository")
            else:
                edge = replace(edge, id=current.id)
            edge_table[identity] = deepcopy(edge)

        removed_nodes = removed_edges = 0
        if replace_existing:
            partition = (workspace_id, source, repository_id)
            stale_edges = [
                identity
                for identity, edge in edge_table.items()
                if (edge.workspace_id, edge.source, edge.repository_id) == partition
                and identity not in incoming
            ]
            for identity in stale_edges:
                del edge_table[identity]
            referenced = {
                node for edge in edge_table.values() for node in (edge.src_node_id, edge.dst_node_id)
            }
            stale_nodes = [
                key
                for key, node in node_table.items()
                if (node.workspace_id, node.source, node.repository_id) == partition
                and node.node_key not in ids
                and node.id not in referenced
            ]
            for key in stale_nodes:
                del node_table[key]
            removed_edges, removed_nodes = len(stale_edges), len(stale_nodes)

        if index is not None:
            self.add_index(index)
        self._graph.nodes, self._graph.edges = node_table, edge_table
        return {
            "nodes_upserted": len(ids),
            "nodes_removed": removed_nodes,
            "edges_added": added,
            "edges_removed": removed_edges,
        }

    def add_index(self, index: GraphIndex) -> None:
        self.lock_workspace(index.workspace_id)
        key = index.workspace_id, index.source, index.repository_id, index.generation
        if key in self._graph.indexes or any(row.id == index.id for row in self._graph.indexes.values()):
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Graph index generation already exists")
        self._graph.indexes[key] = index

    def latest_index(
        self, workspace_id: WorkspaceId, source: str, repository_id: RepositoryId | None
    ) -> GraphIndex | None:
        return self.indexes_for(workspace_id, frozenset({(source, repository_id)})).get(
            (source, repository_id)
        )

    def indexes_for(
        self, workspace_id: WorkspaceId, keys: frozenset[IndexKey]
    ) -> Mapping[IndexKey, GraphIndex]:
        latest: dict[IndexKey, GraphIndex] = {}
        for row in self._graph.indexes.values():
            key = row.source, row.repository_id
            if row.workspace_id == workspace_id and key in keys:
                current = latest.get(key)
                if current is None or row.generation > current.generation:
                    latest[key] = row
        return latest

    def indexes_by_id(
        self, workspace_id: WorkspaceId, ids: frozenset[GraphIndexId]
    ) -> Mapping[GraphIndexId, GraphIndex]:
        return {
            row.id: row
            for row in self._graph.indexes.values()
            if row.workspace_id == workspace_id and row.id in ids
        }

    def latest_indexes(
        self, workspace_id: WorkspaceId, *, source: str | None, repository_id: RepositoryId | None
    ) -> tuple[GraphIndex, ...]:
        keys = frozenset(
            (key_source, key_repository)
            for workspace, key_source, key_repository, _ in self._graph.indexes
            if workspace == workspace_id
            and (source is None or source == key_source)
            and (repository_id is None or repository_id == key_repository)
        )
        return tuple(self.indexes_for(workspace_id, keys).values())

    def neighborhood(
        self,
        workspace_id: WorkspaceId,
        roots: tuple[GraphNodeId, ...],
        *,
        depth: int,
        max_nodes: int,
        traversal: Traversal = DEFAULT_TRAVERSAL,
    ) -> Adjacency:
        graph = SubgraphView(
            tuple(node for node in self._graph.nodes.values() if node.workspace_id == workspace_id),
            tuple(
                sorted(
                    (edge for edge in self._graph.edges.values() if edge.workspace_id == workspace_id),
                    key=lambda edge: edge.id,
                )
            ),
        )
        result = bounded_neighborhood(graph, roots, depth=depth, max_nodes=max_nodes, traversal=traversal)
        return result.to_adjacency()

    def nodes_by_keys(self, workspace_id: WorkspaceId, keys: frozenset[str]) -> Mapping[str, GraphNode]:
        return {
            key: deepcopy(node)
            for key in keys
            if (node := self._graph.nodes.get((workspace_id, key))) is not None
        }

    def node_by_key(self, workspace_id: WorkspaceId, node_key: str) -> GraphNode | None:
        return deepcopy(self._graph.nodes.get((workspace_id, node_key)))
