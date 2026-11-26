"""Serialize knowledge values through the existing closed wire contracts."""

import json
from datetime import UTC, datetime
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.domain.lesson import Lesson
from skm.modules.knowledge.domain.memory_entry import MemoryEntry
from skm.modules.knowledge.domain.memory_scope import MemoryScope
from skm.modules.knowledge.ports import applicability_json


def _id(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _stamp(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def memory_view(entry: MemoryEntry) -> JsonObject:
    scope: MemoryScope = entry.scope
    return {
        "id": str(entry.id),
        "scope": {
            "kind": scope.kind.value,
            "scope_id": _id(scope.scope_id),
            "namespace": scope.namespace,
            "workspace_id": _id(scope.workspace_id),
        },
        "kind": entry.kind.value,
        "body": entry.body,
        "created_at": _stamp(entry.created_at),
        "expires_at": _stamp(entry.expires_at),
        "created_by": str(entry.created_by),
        "writer": entry.writer,
        "source": entry.source,
        "state": entry.state.value,
        "state_changed_at": _stamp(entry.state_changed_at),
        "supersedes_id": _id(entry.supersedes_id),
        "row_version": entry.row_version,
    }


def lesson_view(lesson: Lesson) -> JsonObject:
    return {
        "id": str(lesson.id),
        "workspace_id": str(lesson.workspace_id),
        "scope_id": str(lesson.scope_id),
        "kind": lesson.kind.value,
        "trigger": lesson.trigger,
        "action": lesson.action,
        "evidence": [{"kind": ref.kind, "id": ref.id} for ref in lesson.evidence],
        "confidence": lesson.confidence,
        "confidence_tier": lesson.confidence_tier.value,
        "state": lesson.state.value,
        "candidate_id": str(lesson.candidate_id),
        "promoted_by": str(lesson.promoted_by),
        "promoted_at": _stamp(lesson.promoted_at),
        "deprecated_by": _id(lesson.deprecated_by),
        "deprecated_at": _stamp(lesson.deprecated_at),
        "deprecation_reason": lesson.deprecation_reason,
        "supersedes_id": _id(lesson.supersedes_id),
        "review_flag": lesson.review_flag,
        "applicability": applicability_json(lesson.applicability),
        "row_version": lesson.row_version,
    }


def validate_lesson_storage(lesson: Lesson) -> None:
    if len(lesson.evidence) > 50:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "At most 50 evidence references are allowed")
    encoded = json.dumps(applicability_json(lesson.applicability), ensure_ascii=False).encode()
    if len(encoded) > 16384:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Lesson applicability exceeds its storage limit")
