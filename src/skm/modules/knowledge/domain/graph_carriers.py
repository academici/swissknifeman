"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from skm.kernel.ids import RepositoryId
from skm.kernel.json_types import JsonObject

from .graph import EdgeType, NodeType
from .graph_index import FreshnessState, GraphBasis


@dataclass(frozen=True, slots=True)
class Freshness:
    state: FreshnessState
    indexed_at: datetime | None
    index_revision: str | None
    at_revision: str | None
    age_seconds: int | None


@dataclass(frozen=True, slots=True)
class GraphSourceRef:
    source: str
    repository_id: RepositoryId | None
    generation: int
    revision: str | None
    dirty: bool
    indexed_at: datetime
    tool_name: str
    tool_version: str


@dataclass(frozen=True, slots=True)
class AnswerNode:
    node_key: str
    type: NodeType
    attrs: JsonObject
    source: str
    distance: int | None = None


@dataclass(frozen=True, slots=True)
class AnswerEdge:
    src_key: str
    dst_key: str
    type: EdgeType
    source: str
    basis: GraphBasis
    attrs: JsonObject
