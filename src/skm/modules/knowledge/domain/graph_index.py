"""Index generations and graph evidence quality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId

GraphIndexId = NewType("GraphIndexId", UUID)


class GraphBasis(StrEnum):
    DECLARED = "declared"
    LSP = "lsp"
    AST = "ast"
    TEXT = "text"
    HEURISTIC = "heuristic"

    @property
    def rank(self) -> int:
        return _BASIS_RANK[self]


_BASIS_RANK = {
    GraphBasis.DECLARED: 4,
    GraphBasis.LSP: 3,
    GraphBasis.AST: 2,
    GraphBasis.TEXT: 1,
    GraphBasis.HEURISTIC: 0,
}


class Completeness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"


class FreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class LimitationCode(StrEnum):
    DEPTH_LIMIT = "depth_limit"
    NODE_LIMIT = "node_limit"
    LANGUAGE_UNSUPPORTED = "language_unsupported"
    DYNAMIC_DISPATCH = "dynamic_dispatch"
    GENERATED_EXCLUDED = "generated_excluded"
    PARSE_ERRORS = "parse_errors"
    INDEX_STALE = "index_stale"
    INDEX_OLD = "index_old"
    INDEX_DIRTY = "index_dirty"
    NO_INDEX = "no_index"
    CROSS_REPOSITORY_UNRESOLVED = "cross_repository_unresolved"


@dataclass(frozen=True, slots=True)
class Limitation:
    code: LimitationCode
    message: str
    count: int | None


@dataclass(frozen=True, slots=True)
class GraphIndex:
    id: GraphIndexId
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    repository_id: RepositoryId | None
    source: str
    generation: int
    revision: str | None
    dirty: bool
    languages: tuple[str, ...]
    basis_default: GraphBasis
    tool_name: str
    tool_version: str
    indexed_at: datetime
    completeness: Completeness
    limitations: tuple[Limitation, ...]
    files_indexed: int
    files_skipped: int
    nodes: int
    edges: int

    def same_snapshot(self, other: GraphIndex) -> bool:
        return (self.project_id, self.revision, self.dirty) == (
            other.project_id,
            other.revision,
            other.dirty,
        ) and ((self.revision is not None and not self.dirty) or self.indexed_at == other.indexed_at)


def next_generation(previous: GraphIndex | None) -> int:
    return 1 if previous is None else previous.generation + 1
