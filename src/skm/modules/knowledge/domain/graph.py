"""Workspace-scoped identities for the knowledge multigraph."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType
from uuid import UUID

from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonValue

from .graph_index import GraphBasis, GraphIndexId

GraphEdgeId = NewType("GraphEdgeId", UUID)

GraphNodeId = NewType("GraphNodeId", UUID)


class NodeType(StrEnum):
    PROJECT = "project"
    AGENT = "agent"
    MEMORY = "memory"
    SKILL = "skill"
    ENTITY = "entity"
    TOOL = "tool"
    PACKAGE = "package"
    DOC = "doc"
    SYMBOL = "symbol"


class EdgeType(StrEnum):
    USES = "uses"
    KNOWS = "knows"
    RELATES_TO = "relates_to"
    BELONGS_TO = "belongs_to"
    DEPENDS_ON = "depends_on"
    PROVIDED_BY = "provided_by"
    REQUIRES = "requires"
    REFERENCES = "references"


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: GraphNodeId
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    node_key: str
    type: NodeType
    attrs: Mapping[str, JsonValue]
    source: str
    repository_id: RepositoryId | None
    index_id: GraphIndexId | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: GraphEdgeId
    workspace_id: WorkspaceId
    src_node_id: GraphNodeId
    dst_node_id: GraphNodeId
    type: EdgeType
    attrs: Mapping[str, JsonValue]
    source: str
    repository_id: RepositoryId | None
    source_key: str
    basis: GraphBasis | None
    index_id: GraphIndexId | None = None


def node_key(kind: NodeType, key: str) -> str:
    if not 1 <= len(key) <= 300 or "\x00" in key:
        raise ValueError("Graph node key must contain 1 to 300 characters and no NUL")
    return f"{kind}:{key}"


def parse_node_key(value: str) -> tuple[NodeType, str]:
    prefix, _, key = value.partition(":")
    kind = NodeType(prefix)
    node_key(kind, key)
    return kind, key


type EdgeIdentity = tuple[GraphNodeId, GraphNodeId, EdgeType, str, str]


def edge_identity(edge: GraphEdge) -> EdgeIdentity:
    return edge.src_node_id, edge.dst_node_id, edge.type, edge.source, edge.source_key


def source_payload_matches(
    workspace_id: WorkspaceId,
    source: str,
    repository_id: RepositoryId | None,
    nodes: tuple[GraphNode, ...],
    edges: tuple[GraphEdge, ...],
) -> bool:
    return all(
        (item.workspace_id, item.source, item.repository_id) == (workspace_id, source, repository_id)
        for item in (*nodes, *edges)
    )


def project_reference(node: GraphNode) -> ProjectId | None:
    if node.type is not NodeType.PROJECT:
        return None
    return project_key_reference(node.node_key)


def project_key_reference(key: str) -> ProjectId | None:
    try:
        return ProjectId(UUID(key.partition(":")[2]))
    except ValueError:
        return None
