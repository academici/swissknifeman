"""Knowledge operations in the caller's unit of work."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from functools import cache
from hashlib import sha256
from typing import cast

from skm.kernel.actor import Actor
from skm.kernel.errors import NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

from .application.lesson_operations import deprecate_in_uow, promote
from .application.queries.search_memory import search
from .application.views import lesson_view, memory_view
from .contracts import DeprecateLesson as DeprecateLesson
from .contracts import DeprecateLessonResult as DeprecateLessonResult
from .contracts import Forget as Forget
from .contracts import ForgetResult as ForgetResult
from .contracts import GetLesson as GetLesson
from .contracts import GetLessonView as GetLessonView
from .contracts import GraphIndexesView as GraphIndexesView
from .contracts import GraphNeighbors as GraphNeighbors
from .contracts import GraphPath as GraphPath
from .contracts import GraphStats as GraphStats
from .contracts import GraphSubgraph as GraphSubgraph
from .contracts import ImportGraph as ImportGraph
from .contracts import ImportGraphResult as ImportGraphResult
from .contracts import LessonsView as LessonsView
from .contracts import ListGraphIndexes as ListGraphIndexes
from .contracts import ListLessons as ListLessons
from .contracts import ListMemory as ListMemory
from .contracts import MemorySearchView as MemorySearchView
from .contracts import MemoryView as MemoryView
from .contracts import Remember as Remember
from .contracts import RememberResult as RememberResult
from .contracts import SearchMemory as SearchMemory
from .domain.contracts import CandidateId, LessonView, MemoryEntryView
from .domain.evidence import EvidenceRef as EvidenceRef
from .domain.graph import EdgeType as EdgeType
from .domain.graph import GraphEdge as GraphEdge
from .domain.graph import GraphEdgeId as GraphEdgeId
from .domain.graph import GraphNode as GraphNode
from .domain.graph import GraphNodeId as GraphNodeId
from .domain.graph import NodeType as NodeType
from .domain.graph_answer import GraphAnswer as GraphAnswer
from .domain.graph_carriers import AnswerEdge as AnswerEdge
from .domain.graph_carriers import AnswerNode as AnswerNode
from .domain.graph_carriers import Freshness as Freshness
from .domain.graph_carriers import GraphSourceRef as GraphSourceRef
from .domain.graph_index import Completeness as Completeness
from .domain.graph_index import FreshnessState as FreshnessState
from .domain.graph_index import GraphBasis as GraphBasis
from .domain.graph_index import GraphIndex as GraphIndex
from .domain.graph_index import GraphIndexId as GraphIndexId
from .domain.graph_index import Limitation as Limitation
from .domain.graph_index import LimitationCode as LimitationCode
from .domain.lesson import ConfidenceTier as ConfidenceTier
from .domain.lesson import Lesson as Lesson
from .domain.lesson import LessonApplicability as LessonApplicability
from .domain.lesson import LessonId as LessonId
from .domain.lesson import LessonKind as LessonKind
from .domain.lesson import LessonState as LessonState
from .domain.lesson import (
    _normalized,  # pyright: ignore[reportPrivateUsage] -- same domain conflict key
    evaluate_freshness,
    flag_decay,
    potential_conflict_ids,
)
from .domain.memory_entry import MemoryEntry as MemoryEntry
from .domain.memory_entry import MemoryEntryId as MemoryEntryId
from .domain.memory_entry import MemoryState as MemoryState
from .domain.memory_kind import MemoryKind as MemoryKind
from .domain.memory_scope import MemoryScope as MemoryScope
from .domain.memory_scope import MemoryScopeKind as MemoryScopeKind
from .domain.promotion import CandidateForPromotion as CandidateForPromotion
from .domain.promotion import LessonRef as LessonRef
from .generated.settings import KnowledgeMemorySettings
from .ports import LessonRepository, MemoryRepository

_CLOCK = SystemClock()
_IDS = Uuid7Generator(_CLOCK)
_CONTEXT_TIERS = frozenset({ConfidenceTier.MODERATE, ConfidenceTier.STRONG, ConfidenceTier.CORE})


def promote_lesson(
    uow: UnitOfWork,
    candidate: CandidateForPromotion,
    *,
    actor: Actor,
    supersedes: LessonId | None,
    applicability: LessonApplicability | None = None,
    now: datetime | None = None,
    lesson_id: LessonId | None = None,
) -> LessonRef:
    row = promote(
        uow,
        candidate,
        actor=actor,
        supersedes=supersedes,
        applicability=applicability,
        now=now if now is not None else _CLOCK.now(),
        lesson_id=lesson_id if lesson_id is not None else LessonId(_IDS.new_id()),
    )
    return LessonRef(row.id)


def list_lessons_for_context(
    uow: UnitOfWork,
    scope_chain: tuple[ScopeRef, ...],
    *,
    limit: int,
    now: datetime | None = None,
    current_versions: Mapping[str, str] | None = None,
    min_confidence: float = 0,
) -> tuple[LessonView, ...]:
    if limit < 1:
        return ()
    rows = uow.repo(LessonRepository).effective(tuple(ref.id for ref in scope_chain))
    groups: dict[tuple[ScopeId, str], list[Lesson]] = {}
    for row in rows:
        groups.setdefault((row.scope_id, _normalized(row.trigger)), []).append(row)
    selected: list[LessonView] = []
    now = now if now is not None else _CLOCK.now()
    for (scope_id, trigger), group in groups.items():
        conflicts = potential_conflict_ids(group)
        atomic_group = (
            None if not conflicts else f"lesson-conflict:{scope_id}:{sha256(trigger.encode()).hexdigest()}"
        )
        eligible = [
            row for row in group if row.confidence_tier in _CONTEXT_TIERS and row.confidence >= min_confidence
        ]
        if not eligible:
            continue
        members = group if conflicts else eligible[: limit - len(selected)]
        if len(members) > limit - len(selected):
            continue
        for row in members:
            view = lesson_view(row)
            conflict_refs: list[JsonValue] = [str(item) for item in conflicts if item != row.id]
            view.update(
                freshness=evaluate_freshness(row, now=now, current_versions=current_versions),
                atomic_group=atomic_group,
                potential_conflict_ids=conflict_refs,
            )
            selected.append(view)
        if len(selected) == limit:
            break
    return tuple(selected)


@cache
def _default_memory_settings() -> KnowledgeMemorySettings:
    section = SchemaRegistry.load_default().get(KnowledgeMemorySettings.SCHEMA_URN)
    memory = cast("JsonObject", cast("JsonObject", section["properties"])["memory"])
    properties = cast("dict[str, JsonObject]", memory["properties"])
    defaults = {key: definition["default"] for key, definition in properties.items()}
    return KnowledgeMemorySettings.from_json(defaults)


def search_memory_for_context(
    uow: UnitOfWork,
    project_scope: ScopeId,
    *,
    now: datetime,
    query: str | None,
    settings: KnowledgeMemorySettings | None = None,
) -> tuple[MemoryEntryView, ...]:
    scope = uow.repo(ScopeRegistry).get(project_scope)
    if scope.kind is not ScopeKind.PROJECT or scope.workspace_id is None:
        return ()
    project = MemoryScope(MemoryScopeKind.PROJECT, scope.id, None, scope.workspace_id)
    settings = settings if settings is not None else _default_memory_settings()
    rows, _ = search(uow.repo(MemoryRepository), (project,), now=now, query=query, settings=settings)
    return tuple(memory_view(row) for row in rows)


def lesson_confidence_inputs(
    uow: UnitOfWork, lesson_ids: tuple[LessonId, ...]
) -> Mapping[LessonId, CandidateId]:
    repo = uow.repo(LessonRepository)
    found: dict[LessonId, CandidateId] = {}
    for lesson_id in lesson_ids:
        try:
            found[lesson_id] = repo.get(lesson_id).candidate_id
        except NotFound:
            continue
    return found


def flag_lesson_decay(
    uow: UnitOfWork,
    lesson_id: LessonId,
    *,
    confidence: float,
    deprecate_conf: float = 0.4,
    stale: bool = False,
    now: datetime | None = None,
) -> None:
    repo = uow.repo(LessonRepository)
    lesson = repo.get(lesson_id)
    updated = flag_decay(lesson, confidence, deprecate_conf)
    if stale and updated.review_flag != "decay":
        updated = replace(updated, review_flag="decay", row_version=lesson.row_version + 1)
    if (updated.confidence, updated.review_flag) != (lesson.confidence, lesson.review_flag):
        repo.save(updated, expected_version=lesson.row_version, now=now if now is not None else _CLOCK.now())


def deprecate_lesson(
    uow: UnitOfWork, lesson_id: LessonId, *, actor: Actor, reason: str, now: datetime | None = None
) -> None:
    lesson = uow.repo(LessonRepository).get(lesson_id)
    deprecate_in_uow(uow, lesson, actor=actor, reason=reason, now=now if now is not None else _CLOCK.now())
