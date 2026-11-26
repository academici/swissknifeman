"""PostgreSQL row codecs for memory and lessons."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.domain.evidence import EvidenceRef
from skm.modules.knowledge.domain.lesson import (
    ConfidenceTier,
    Lesson,
    LessonApplicability,
    LessonId,
    LessonKind,
    LessonState,
)
from skm.modules.knowledge.domain.memory_entry import MemoryEntry, MemoryEntryId, MemorySource, MemoryState
from skm.modules.knowledge.domain.memory_kind import MemoryKind
from skm.modules.knowledge.domain.memory_scope import MemoryScope, MemoryScopeKind
from skm.modules.knowledge.generated.views import (
    lesson_view_defs_lesson_applicability_from_json,
)

__all__ = ["Row", "lesson_from_row", "memory_from_row", "run", "scope_from_row"]

type Row = tuple[object, ...]


def run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def scope_from_row(row: Row) -> MemoryScope:
    return MemoryScope(
        MemoryScopeKind(cast("str", row[0])),
        cast("ScopeId | None", row[1]),
        cast("str | None", row[2]),
        cast("WorkspaceId | None", row[3]),
    )


def memory_from_row(row: Row) -> MemoryEntry:
    return MemoryEntry(
        id=MemoryEntryId(cast("UUID", row[0])),
        scope=scope_from_row(row[1:5]),
        kind=MemoryKind(cast("str", row[5])),
        body=cast("str", row[6]),
        state=MemoryState(cast("str", row[7])),
        writer=cast("str", row[8]),
        source=cast("MemorySource", row[9]),
        created_by=PrincipalId(cast("UUID", row[10])),
        supersedes_id=cast("MemoryEntryId | None", row[11]),
        created_at=cast("datetime", row[12]),
        expires_at=cast("datetime", row[13]),
        state_changed_at=cast("datetime | None", row[14]),
        row_version=cast("int", row[15]),
    )


def lesson_from_row(row: Row) -> Lesson:
    applicability = cast("JsonObject", lesson_view_defs_lesson_applicability_from_json(row[18]))
    review_after = applicability.get("review_after")
    return Lesson(
        id=LessonId(cast("UUID", row[0])),
        workspace_id=WorkspaceId(cast("UUID", row[1])),
        scope_id=ScopeId(cast("UUID", row[2])),
        kind=LessonKind(cast("str", row[3])),
        trigger=cast("str", row[4]),
        action=cast("str", row[5]),
        evidence=tuple(EvidenceRef(str(e["kind"]), str(e["id"])) for e in cast("list[JsonObject]", row[6])),
        confidence=cast("float", row[7]),
        confidence_tier=ConfidenceTier(cast("str", row[8])),
        state=LessonState(cast("str", row[9])),
        candidate_id=cast("UUID", row[10]),
        promoted_by=PrincipalId(cast("UUID", row[11])),
        promoted_at=cast("datetime", row[12]),
        deprecated_by=cast("PrincipalId | None", row[13]),
        deprecated_at=cast("datetime | None", row[14]),
        deprecation_reason=cast("str | None", row[15]),
        supersedes_id=cast("LessonId | None", row[16]),
        review_flag=cast("Literal['none', 'decay']", row[17]),
        applicability=LessonApplicability(
            cast("str | None", applicability.get("applies_to")),
            tuple(
                (pair[0], pair[1])
                for pair in cast("list[list[str]]", applicability.get("validated_versions", []))
            ),
            datetime.fromisoformat(review_after) if isinstance(review_after, str) else None,
        ),
        row_version=cast("int", row[19]),
    )
