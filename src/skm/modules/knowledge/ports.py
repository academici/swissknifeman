"""Persistence and host ports owned by knowledge."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import UUID

from skm.kernel.data_classification import HOST_PRIVATE
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import host_gateway
from skm.kernel.ids import ProjectId, RepositoryId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.pagination import Cursor, Page, validate_cursor
from skm.kernel.ports_uow import repository_port

from .domain.contracts import Adjacency, CandidateId, ReplaceStats
from .domain.graph import GraphEdge, GraphNode, GraphNodeId
from .domain.graph_index import GraphIndex
from .domain.lesson import Lesson, LessonApplicability, LessonId, LessonKind, LessonState
from .domain.memory_entry import MemoryEntry, MemoryEntryId
from .domain.memory_kind import MemoryKind
from .domain.memory_scope import MemoryScope


@dataclass(frozen=True, slots=True)
class EpisodeScope:
    workspace_id: WorkspaceId
    project_id: ProjectId | None


@dataclass(frozen=True, slots=True)
class LocalEpisode:
    id: int
    session_id: UUID
    kind: MemoryKind
    text: str = field(repr=False)
    expires_at: datetime
    classification: Literal["HOST_PRIVATE"] = field(default=HOST_PRIVATE, init=False)


type EpisodeRecordStatus = Literal["recorded", "deduplicated", "rate_limited"]


@host_gateway
class LocalEpisodicMemory(Protocol):
    def record(
        self,
        scope: EpisodeScope,
        session_id: UUID,
        kind: MemoryKind,
        text: str,
        *,
        ttl_seconds: int | None = None,
    ) -> EpisodeRecordStatus: ...

    def search(
        self,
        scope: EpisodeScope,
        session_id: UUID,
        *,
        query: str = "",
        limit: int = 10,
        inherit_workspace: bool = False,
    ) -> tuple[LocalEpisode, ...]: ...

    def summarize_session(
        self, scope: EpisodeScope, session_id: UUID, *, source_session_id: UUID | None = None
    ) -> str: ...

    def prune_expired(self) -> int: ...

    def require_syncable(self, session_id: UUID) -> None: ...


@host_gateway
class GraphCheckoutResolver(Protocol):
    def resolve_graph(self, project_id: ProjectId, mount: str) -> tuple[RepositoryId, str]:
        """Return the repository ID and canonical root of a current host-local checkout."""
        ...


@repository_port
class MemoryRepository(Protocol):
    def lock_scope(self, scope: MemoryScope) -> None: ...

    def add(self, entry: MemoryEntry) -> None: ...

    def get(self, entry_id: MemoryEntryId) -> MemoryEntry: ...

    def save(self, entry: MemoryEntry, *, expected_version: int) -> None: ...

    def count_live(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        exclude_kinds: frozenset[MemoryKind],
        created_after: datetime | None = None,
    ) -> int: ...

    def live_handoff(self, scope: MemoryScope, *, now: datetime) -> MemoryEntry | None: ...

    def search_candidates(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        query: str | None,
        created_after: datetime | None = None,
    ) -> Iterator[MemoryEntry]:
        """Yield matching candidates in descending ID order to break recall ties."""
        ...

    def list(
        self,
        scope: MemoryScope,
        *,
        now: datetime,
        include_expired: bool,
        after: Cursor | None,
        limit: int,
        created_after: datetime | None = None,
    ) -> Page[MemoryEntry]: ...

    def expire_due(self, *, now: datetime, batch: int) -> int: ...

    def purge_older_than(self, *, before: datetime, batch: int) -> int: ...


@repository_port
class LessonRepository(Protocol):
    def add(self, lesson: Lesson) -> None: ...

    def get(self, lesson_id: LessonId) -> Lesson: ...

    def save(self, lesson: Lesson, *, expected_version: int, now: datetime | None = None) -> None: ...

    def list(
        self,
        scope_ids: tuple[ScopeId, ...] | None,
        *,
        state: LessonState | None,
        after: Cursor | None,
        limit: int,
        kind: LessonKind | None = None,
        workspace_id: WorkspaceId | None = None,
    ) -> Page[Lesson]: ...

    def effective(self, scope_ids: tuple[ScopeId, ...]) -> tuple[Lesson, ...]: ...

    def by_candidate(self, candidate_id: CandidateId) -> Lesson | None: ...


@repository_port
class GraphRepository(Protocol):
    def upsert_nodes(self, nodes: tuple[GraphNode, ...]) -> Mapping[str, GraphNodeId]: ...

    def replace_from_source(
        self,
        workspace_id: WorkspaceId,
        source: str,
        repository_id: RepositoryId | None,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
    ) -> ReplaceStats: ...

    def add_index(self, index: GraphIndex) -> None: ...

    def latest_index(
        self, workspace_id: WorkspaceId, source: str, repository_id: RepositoryId | None
    ) -> GraphIndex | None: ...

    def indexes_for(
        self, workspace_id: WorkspaceId, keys: frozenset[tuple[str, RepositoryId | None]]
    ) -> Mapping[tuple[str, RepositoryId | None], GraphIndex]: ...

    def latest_indexes(
        self,
        workspace_id: WorkspaceId,
        *,
        source: str | None,
        repository_id: RepositoryId | None,
    ) -> tuple[GraphIndex, ...]: ...

    def neighborhood(
        self, workspace_id: WorkspaceId, roots: tuple[GraphNodeId, ...], *, depth: int, max_nodes: int
    ) -> Adjacency: ...

    def node_by_key(self, workspace_id: WorkspaceId, node_key: str) -> GraphNode | None: ...


@host_gateway
class CodeGraphReader(Protocol):
    def read_symbols(self, root: Path) -> Iterator[JsonObject]: ...
    def read_references(self, root: Path) -> Iterator[JsonObject]: ...


@host_gateway
class ManifestReader(Protocol):
    def dependencies(self, root: Path) -> tuple[JsonObject, ...]: ...


type SortKey = tuple[datetime, UUID]


def start_after(after: Cursor | None, filters: str) -> tuple[datetime | None, UUID | None]:
    if after is None:
        return None, None
    try:
        data: object = json.loads(base64.b64decode(validate_cursor(after), altchars=b"-_", validate=True))
        if not isinstance(data, list):
            raise ValueError
        items = cast("list[object]", data)
        if len(items) != 3:
            raise ValueError
        fingerprint, timestamp, row_id = items
        if fingerprint != filters or not isinstance(timestamp, str) or not isinstance(row_id, str):
            raise ValueError
        when = datetime.fromisoformat(timestamp)
        if when.utcoffset() is None:
            raise ValueError
        return when, UUID(row_id)
    except (ValueError, binascii.Error):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Invalid page cursor", details={"field": "after"}
        ) from None


def page_of[T](rows: Sequence[T], limit: int, filters: str, key_of: Callable[[T], SortKey]) -> Page[T]:
    items = tuple(rows[:limit])
    if len(rows) <= limit:
        return Page(items, None)
    when, row_id = key_of(items[-1])
    payload = json.dumps([filters, when.astimezone(UTC).isoformat(), str(row_id)], separators=(",", ":"))
    return Page(items, validate_cursor(base64.urlsafe_b64encode(payload.encode()).decode()))


def lesson_filters(
    scopes: tuple[ScopeId, ...] | None,
    state: LessonState | None,
    kind: LessonKind | None,
    workspace: WorkspaceId | None,
) -> str:
    scope_key = "*" if scopes is None else ",".join(sorted({str(scope) for scope in scopes}))
    return hashlib.sha256(f"lessons:{workspace}:{state}:{kind}:{scope_key}".encode()).hexdigest()[:16]


def applicability_json(value: LessonApplicability) -> JsonObject:
    return {
        "applies_to": value.applies_to,
        "validated_versions": [[binding, version] for binding, version in value.validated_versions],
        "review_after": value.review_after.astimezone(UTC).isoformat()
        if value.review_after is not None
        else None,
    }
