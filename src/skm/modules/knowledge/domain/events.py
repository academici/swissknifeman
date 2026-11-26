"""Knowledge event contracts. Memory events carry metadata only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, cast, override
from uuid import NAMESPACE_URL, UUID, uuid5

from skm.kernel.events import DomainEvent
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.generated import events as wire

from .contracts import CandidateId
from .lesson import LessonId
from .memory_entry import MemoryEntryId
from .memory_kind import MemoryKind
from .memory_scope import MemoryScope


@dataclass(frozen=True, slots=True)
class _MemoryEvent(DomainEvent):
    scope: MemoryScope

    @override
    def stream_id(self) -> UUID:
        if self.scope.scope_id is not None:
            return self.scope.scope_id
        return uuid5(
            NAMESPACE_URL,
            f"urn:skm:memory:{self.scope.kind}:{self.scope.workspace_id}:{self.scope.namespace}",
        )

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.scope.workspace_id


@dataclass(frozen=True, slots=True)
class MemoryRemembered(_MemoryEvent):
    event_type: ClassVar[str] = "urn:skm:knowledge:event:memory-remembered:v1"
    stream_kind: ClassVar[str] = "memory"
    entry_id: MemoryEntryId
    kind: MemoryKind
    expires_at: datetime

    @override
    def payload(self) -> JsonObject:
        scope = self.scope
        payload = wire.memory_remembered_from_json(
            {
                "entry_id": str(self.entry_id),
                "scope": {
                    "kind": scope.kind.value,
                    "scope_id": str(scope.scope_id) if scope.scope_id is not None else None,
                    "namespace": scope.namespace,
                    "workspace_id": str(scope.workspace_id) if scope.workspace_id is not None else None,
                },
                "kind": self.kind.value,
                "expires_at": self.expires_at.isoformat(),
            }
        )
        return cast("JsonObject", payload)


@dataclass(frozen=True, slots=True)
class MemoryForgotten(_MemoryEvent):
    event_type: ClassVar[str] = "urn:skm:knowledge:event:memory-forgotten:v1"
    stream_kind: ClassVar[str] = "memory"
    entry_ids: tuple[MemoryEntryId, ...]

    @override
    def payload(self) -> JsonObject:
        payload = wire.MemoryForgotten(entry_ids=[str(entry_id) for entry_id in self.entry_ids])
        return cast("JsonObject", wire.memory_forgotten_to_json(payload))


@dataclass(frozen=True, slots=True)
class _LessonEvent(DomainEvent):
    lesson_id: LessonId
    workspace_id: WorkspaceId

    @override
    def stream_id(self) -> UUID:
        return self.lesson_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id


@dataclass(frozen=True, slots=True)
class LessonPromoted(_LessonEvent):
    event_type: ClassVar[str] = "urn:skm:knowledge:event:lesson-promoted:v1"
    stream_kind: ClassVar[str] = "lesson"
    candidate_id: CandidateId

    @override
    def payload(self) -> JsonObject:
        payload = wire.LessonPromoted(lesson_id=str(self.lesson_id), candidate_id=str(self.candidate_id))
        return cast("JsonObject", wire.lesson_promoted_to_json(payload))


@dataclass(frozen=True, slots=True)
class LessonDeprecated(_LessonEvent):
    event_type: ClassVar[str] = "urn:skm:knowledge:event:lesson-deprecated:v1"
    stream_kind: ClassVar[str] = "lesson"
    reason: str

    @override
    def payload(self) -> JsonObject:
        payload = wire.LessonDeprecated(lesson_id=str(self.lesson_id), reason=self.reason)
        return cast("JsonObject", wire.lesson_deprecated_to_json(payload))


@dataclass(frozen=True, slots=True)
class GraphImported(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:knowledge:event:graph-imported:v1"
    stream_kind: ClassVar[str] = "workspace"
    workspace_id: WorkspaceId
    source: str
    counts: wire.GraphImportedCounts

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        payload = wire.GraphImported(
            workspace_id=str(self.workspace_id), source=self.source, counts=self.counts
        )
        return cast("JsonObject", wire.graph_imported_to_json(payload))


EVENTS: tuple[type[DomainEvent], ...] = (
    MemoryRemembered,
    MemoryForgotten,
    LessonPromoted,
    LessonDeprecated,
    GraphImported,
)
EVENT_TYPES: tuple[str, ...] = tuple(event.event_type for event in EVENTS)
