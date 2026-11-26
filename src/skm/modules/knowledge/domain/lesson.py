"""Durable curated lessons and their applicability, freshness and conflicts."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, NewType
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId

from .contracts import CandidateId
from .evidence import EvidenceRef

if TYPE_CHECKING:
    from .promotion import CandidateForPromotion

LessonId = NewType("LessonId", UUID)
type LessonFreshness = Literal["current", "needs_review", "unvalidated"]
_BINDING_ID = re.compile(r"[^:\s]+:[^:\s]+")


class LessonKind(StrEnum):
    HEURISTIC = "heuristic"
    PROCEDURE = "procedure"
    GOTCHA = "gotcha"


class LessonState(StrEnum):
    CURATED = "curated"
    DEPRECATED = "deprecated"


class ConfidenceTier(StrEnum):
    NONE = "none"
    TENTATIVE = "tentative"
    MODERATE = "moderate"
    STRONG = "strong"
    CORE = "core"


@dataclass(frozen=True, slots=True)
class Lesson:
    id: LessonId
    workspace_id: WorkspaceId
    scope_id: ScopeId
    kind: LessonKind
    trigger: str
    action: str
    evidence: tuple[EvidenceRef, ...]
    confidence: float
    confidence_tier: ConfidenceTier
    state: LessonState
    candidate_id: CandidateId
    promoted_by: PrincipalId
    promoted_at: datetime
    deprecated_by: PrincipalId | None
    deprecated_at: datetime | None
    deprecation_reason: str | None
    supersedes_id: LessonId | None
    review_flag: Literal["none", "decay"]
    applicability: LessonApplicability
    row_version: int


@dataclass(frozen=True, slots=True)
class LessonApplicability:
    applies_to: str | None = None
    validated_versions: tuple[tuple[str, str], ...] = ()
    review_after: datetime | None = None

    def __post_init__(self) -> None:
        if self.applies_to is not None:
            object.__setattr__(self, "applies_to", _required_text(self.applies_to, "Applies to", 1000))
        bindings = self.validated_versions
        if len(bindings) > 32:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "At most 32 validated versions are allowed")
        keys: set[str] = set()
        for key, version in bindings:
            if _BINDING_ID.fullmatch(key) is None:
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected an owner-qualified binding ID")
            if not version.strip() or key in keys:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID, "Expected unique, non-empty version bindings"
                )
            keys.add(key)
        if self.review_after is not None:
            _require_aware(self.review_after)


def _required_text(text: str, name: str, max_chars: int) -> str:
    stripped = text.strip()
    if not 1 <= len(stripped) <= max_chars:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"{name} must have 1 to {max_chars} characters")
    return stripped


def _require_aware(value: datetime) -> None:
    if value.utcoffset() is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Lesson timestamps must be timezone-aware")


def _require_human(actor: Actor) -> None:
    if actor.kind is not PrincipalKind.HUMAN:
        raise Forbidden(
            ErrorCode.FORBIDDEN, "Lesson curation requires a human", details={"reason": "human_gate"}
        )


def _validate_confidence(confidence: float) -> None:
    if isinstance(confidence, bool) or not 0 <= confidence < 1:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Lesson confidence must be in [0, 1)")


def new_lesson_from_candidate(
    c: CandidateForPromotion,
    *,
    lesson_id: LessonId,
    actor: Actor,
    now: datetime,
    supersedes: Lesson | None = None,
    applicability: LessonApplicability | None = None,
) -> Lesson:
    _require_human(actor)
    _require_aware(now)
    trigger = _required_text(c.trigger, "Lesson trigger", 500)
    action = _required_text(c.action, "Lesson action", 1000)
    try:
        kind = LessonKind(c.kind)
    except ValueError as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Unknown lesson kind") from exc
    _validate_confidence(c.confidence)
    if supersedes is not None and (supersedes.workspace_id, supersedes.scope_id) != (
        c.workspace_id,
        c.scope_id,
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "A lesson can supersede only a lesson in its exact scope"
        )
    return Lesson(
        id=lesson_id,
        workspace_id=c.workspace_id,
        scope_id=c.scope_id,
        kind=kind,
        trigger=trigger,
        action=action,
        evidence=c.evidence,
        confidence=c.confidence,
        confidence_tier=c.tier,
        state=LessonState.CURATED,
        candidate_id=c.candidate_id,
        promoted_by=actor.principal_id,
        promoted_at=now,
        deprecated_by=None,
        deprecated_at=None,
        deprecation_reason=None,
        supersedes_id=supersedes.id if supersedes is not None else None,
        review_flag="none",
        applicability=applicability if applicability is not None else LessonApplicability(),
        row_version=1,
    )


def deprecate(lesson: Lesson, *, actor: Actor, reason: str, now: datetime) -> Lesson:
    _require_human(actor)
    reason = _required_text(reason, "Deprecation reason", 500)
    _require_aware(now)
    if lesson.state is LessonState.DEPRECATED:
        return lesson
    return replace(
        lesson,
        state=LessonState.DEPRECATED,
        deprecated_by=actor.principal_id,
        deprecated_at=now,
        deprecation_reason=reason,
        row_version=lesson.row_version + 1,
    )


def flag_decay(lesson: Lesson, confidence: float, deprecate_conf: float) -> Lesson:
    _validate_confidence(confidence)
    review_flag: Literal["none", "decay"] = "decay" if confidence < deprecate_conf else "none"
    if (confidence, review_flag) == (lesson.confidence, lesson.review_flag):
        return lesson
    return replace(lesson, confidence=confidence, review_flag=review_flag, row_version=lesson.row_version + 1)


def evaluate_freshness(
    lesson: Lesson, *, now: datetime, current_versions: Mapping[str, str] | None = None
) -> LessonFreshness:
    _require_aware(now)
    applicability = lesson.applicability
    review_after = applicability.review_after
    if lesson.review_flag == "decay" or (
        review_after is not None and now.astimezone(UTC) >= review_after.astimezone(UTC)
    ):
        return "needs_review"
    if not applicability.validated_versions or current_versions is None:
        return "unvalidated"

    freshness: LessonFreshness = "current"
    for key, validated in applicability.validated_versions:
        current = current_versions.get(key)
        if current is None:
            freshness = "unvalidated"
        elif current != validated:
            return "needs_review"
    return freshness


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def potential_conflict_ids(lessons: Iterable[Lesson]) -> tuple[LessonId, ...]:
    """Return every conflicting curated lesson ID in input order."""
    groups: dict[tuple[WorkspaceId, ScopeId, str], list[tuple[Lesson, str]]] = {}
    curated_ids: dict[LessonId, None] = {}
    conflicts: set[LessonId] = set()
    for lesson in lessons:
        if lesson.state is not LessonState.CURATED:
            continue
        curated_ids[lesson.id] = None
        group = groups.setdefault((lesson.workspace_id, lesson.scope_id, _normalized(lesson.trigger)), [])
        action = _normalized(lesson.action)
        for other, other_action in group:
            if (
                action != other_action
                and lesson.id != other.id
                and lesson.supersedes_id != other.id
                and other.supersedes_id != lesson.id
            ):
                conflicts.update((lesson.id, other.id))
        group.append((lesson, action))
    return tuple(lesson_id for lesson_id in curated_ids if lesson_id in conflicts)
