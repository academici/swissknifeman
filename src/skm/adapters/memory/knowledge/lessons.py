"""In-memory durable lesson repository."""

from dataclasses import replace
from datetime import UTC, datetime

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_page_limit
from skm.modules.knowledge.domain.contracts import CandidateId
from skm.modules.knowledge.domain.lesson import Lesson, LessonId, LessonKind, LessonState
from skm.modules.knowledge.ports import SortKey, lesson_filters, page_of, start_after

from .mapping import knowledge_state

__all__ = ["MemoryLessonRepository"]


class MemoryLessonRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        tables = knowledge_state(state)
        self._rows = tables.lessons
        self._updates = tables.lesson_updates

    def add(self, lesson: Lesson) -> None:
        self._state.core.require_writable()
        if lesson.id in self._rows or self.by_candidate(lesson.candidate_id) is not None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Lesson already exists")
        self._rows[lesson.id] = lesson
        self._updates[lesson.id] = lesson.promoted_at

    def get(self, lesson_id: LessonId) -> Lesson:
        row = self._rows.get(lesson_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Lesson not found")
        return row

    def by_candidate(self, candidate_id: CandidateId) -> Lesson | None:
        return next((row for row in self._rows.values() if row.candidate_id == candidate_id), None)

    def save(self, lesson: Lesson, *, expected_version: int, now: datetime | None = None) -> None:
        self._state.core.require_writable()
        current = self.get(lesson.id)
        if current.row_version != expected_version:
            raise Conflict(ErrorCode.VERSION_CONFLICT, "Lesson version changed")
        self._rows[lesson.id] = replace(
            current,
            state=lesson.state,
            confidence=lesson.confidence,
            review_flag=lesson.review_flag,
            deprecated_at=lesson.deprecated_at,
            deprecated_by=lesson.deprecated_by,
            deprecation_reason=lesson.deprecation_reason,
            row_version=expected_version + 1,
        )
        updated = self._updates[lesson.id]
        self._updates[lesson.id] = max(updated, now or lesson.deprecated_at or updated)

    def _key(self, lesson: Lesson) -> SortKey:
        return self._updates[lesson.id].astimezone(UTC), lesson.id

    def list(
        self,
        scope_ids: tuple[ScopeId, ...] | None,
        *,
        state: LessonState | None,
        after: Cursor | None,
        limit: int,
        kind: LessonKind | None = None,
        workspace_id: WorkspaceId | None = None,
    ) -> Page[Lesson]:
        limit = validate_page_limit(limit)
        filters = lesson_filters(scope_ids, state, kind, workspace_id)
        when, row_id = start_after(after, filters)
        rows = [
            row
            for row in self._rows.values()
            if (scope_ids is None or row.scope_id in scope_ids)
            and (workspace_id is None or row.workspace_id == workspace_id)
            and (state is None or row.state == state)
            and (kind is None or row.kind == kind)
            and (when is None or row_id is None or self._key(row) < (when, row_id))
        ]
        return page_of(sorted(rows, key=self._key, reverse=True), limit, filters, self._key)

    def effective(self, scope_ids: tuple[ScopeId, ...]) -> tuple[Lesson, ...]:
        shadowed = {
            (row.workspace_id, row.scope_id, row.supersedes_id)
            for row in self._rows.values()
            if row.scope_id in scope_ids and row.supersedes_id is not None
        }
        rows = (
            row
            for row in self._rows.values()
            if row.state is LessonState.CURATED
            and row.scope_id in scope_ids
            and (row.workspace_id, row.scope_id, row.id) not in shadowed
        )
        return tuple(sorted(rows, key=self._key, reverse=True))
