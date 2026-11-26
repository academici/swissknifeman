"""PostgreSQL durable lessons and effective recall."""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_page_limit
from skm.modules.knowledge.domain.contracts import CandidateId
from skm.modules.knowledge.domain.lesson import Lesson, LessonId, LessonKind, LessonState
from skm.modules.knowledge.ports import applicability_json, lesson_filters, page_of, start_after

from .mapping import lesson_from_row, run

__all__ = ["PostgresLessonRepository"]

_COLUMNS: Final = """
id, workspace_id, scope_id, kind, trigger, action, evidence, confidence, confidence_tier, state,
candidate_id, promoted_by, promoted_at, deprecated_by, deprecated_at, deprecation_reason, supersedes_id,
review_flag, applicability, row_version
"""
_SELECT: Final = "SELECT " + _COLUMNS + " FROM skm_knowledge.lessons AS lesson"  # noqa: S608 -- SQL fragments are module constants
_GET: Final = _SELECT + " WHERE id = %s"
_BY_CANDIDATE: Final = _SELECT + " WHERE candidate_id = %s"
_INSERT: Final = (
    "INSERT INTO skm_knowledge.lessons (" + _COLUMNS + ", created_at, updated_at) VALUES "  # noqa: S608 -- SQL fragments are module constants
    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_UPDATE: Final = """
UPDATE skm_knowledge.lessons
SET state = %s, confidence = %s, review_flag = %s, deprecated_by = %s, deprecated_at = %s,
    deprecation_reason = %s, updated_at = greatest(updated_at, %s), row_version = row_version + 1
WHERE id = %s AND row_version = %s
"""
_LIST: Final = (
    "SELECT " + _COLUMNS + ", updated_at FROM skm_knowledge.lessons "  # noqa: S608 -- SQL fragments are module constants
    """
    WHERE (%(workspace)s::uuid IS NULL OR workspace_id = %(workspace)s)
      AND (%(scopes)s::uuid[] IS NULL OR scope_id = ANY(%(scopes)s))
      AND (%(state)s::text IS NULL OR state = %(state)s)
      AND (%(kind)s::text IS NULL OR kind = %(kind)s)
      AND (%(after)s::timestamptz IS NULL OR (updated_at, id) < (%(after)s, %(id)s::uuid))
    ORDER BY updated_at DESC, id DESC
    LIMIT %(limit)s
    """
)
_EFFECTIVE: Final = (
    _SELECT  # noqa: S608 -- SQL fragments are module constants
    + """
WHERE scope_id = ANY(%s::uuid[]) AND state = 'curated'
AND NOT EXISTS (
    SELECT 1 FROM skm_knowledge.lessons AS successor
    WHERE successor.workspace_id = lesson.workspace_id AND successor.scope_id = lesson.scope_id
      AND successor.supersedes_id = lesson.id
)
ORDER BY updated_at DESC, id DESC
"""
)


class PostgresLessonRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, lesson: Lesson) -> None:
        params = (
            lesson.id,
            lesson.workspace_id,
            lesson.scope_id,
            lesson.kind.value,
            lesson.trigger,
            lesson.action,
            Jsonb([{"kind": ref.kind, "id": ref.id} for ref in lesson.evidence]),
            lesson.confidence,
            lesson.confidence_tier.value,
            lesson.state.value,
            lesson.candidate_id,
            lesson.promoted_by,
            lesson.promoted_at,
            lesson.deprecated_by,
            lesson.deprecated_at,
            lesson.deprecation_reason,
            lesson.supersedes_id,
            lesson.review_flag,
            Jsonb(applicability_json(lesson.applicability)),
            lesson.row_version,
            lesson.promoted_at,
            lesson.promoted_at,
        )
        run(lambda: self._conn.execute(_INSERT, params))

    def get(self, lesson_id: LessonId) -> Lesson:
        row = run(lambda: self._conn.execute(_GET, (lesson_id,)).fetchone())
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Lesson not found")
        return lesson_from_row(row)

    def by_candidate(self, candidate_id: CandidateId) -> Lesson | None:
        row = run(lambda: self._conn.execute(_BY_CANDIDATE, (candidate_id,)).fetchone())
        return None if row is None else lesson_from_row(row)

    def save(self, lesson: Lesson, *, expected_version: int, now: datetime | None = None) -> None:
        params = (
            lesson.state.value,
            lesson.confidence,
            lesson.review_flag,
            lesson.deprecated_by,
            lesson.deprecated_at,
            lesson.deprecation_reason,
            now or lesson.deprecated_at,
            lesson.id,
            expected_version,
        )
        if not run(lambda: self._conn.execute(_UPDATE, params).rowcount):
            self.get(lesson.id)
            raise Conflict(ErrorCode.VERSION_CONFLICT, "Lesson version changed")

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
        params = {
            "scopes": None if scope_ids is None else list(scope_ids),
            "workspace": workspace_id,
            "state": state,
            "kind": kind,
            "after": when,
            "id": row_id,
            "limit": limit + 1,
        }
        raw = run(lambda: self._conn.execute(_LIST, params).fetchall())
        rows = [(lesson_from_row(row), cast("datetime", row[20]), cast("UUID", row[0])) for row in raw]
        page = page_of(rows, limit, filters, lambda row: (row[1], row[2]))
        return Page(tuple(row[0] for row in page.items), page.next)

    def effective(self, scope_ids: tuple[ScopeId, ...]) -> tuple[Lesson, ...]:
        rows = run(lambda: self._conn.execute(_EFFECTIVE, (list(scope_ids),)).fetchall())
        return tuple(map(lesson_from_row, rows))
