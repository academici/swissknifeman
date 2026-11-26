from dataclasses import replace
from datetime import timedelta
from typing import cast
from uuid import UUID

import pytest

from fakes.clock import DEFAULT_START, FrozenClock
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.domain.events import (
    EVENT_TYPES,
    EVENTS,
    GraphImported,
    LessonDeprecated,
    LessonPromoted,
)
from skm.modules.knowledge.domain.evidence import EvidenceRef
from skm.modules.knowledge.domain.lesson import (
    ConfidenceTier,
    Lesson,
    LessonApplicability,
    LessonFreshness,
    LessonId,
    LessonKind,
    LessonState,
    deprecate,
    evaluate_freshness,
    flag_decay,
    new_lesson_from_candidate,
    potential_conflict_ids,
)
from skm.modules.knowledge.domain.promotion import CandidateForPromotion
from support.registries import schemas

_HUMAN = Actor(PrincipalId(UUID(int=1)), PrincipalKind.HUMAN, "Curator")
_CANDIDATE = CandidateForPromotion(
    candidate_id=UUID(int=2),
    workspace_id=WorkspaceId(UUID(int=3)),
    scope_id=ScopeId(UUID(int=4)),
    kind=LessonKind.GOTCHA,
    trigger="CI checks time out",
    action="Check runner capacity before retrying",
    evidence=(EvidenceRef("check_execution", str(UUID(int=5))),),
    confidence=0.85,
    tier=ConfidenceTier.STRONG,
)


def _lesson(
    key: int = 10,
    candidate: CandidateForPromotion = _CANDIDATE,
    *,
    supersedes: Lesson | None = None,
    applicability: LessonApplicability | None = None,
) -> Lesson:
    return new_lesson_from_candidate(
        candidate,
        lesson_id=LessonId(UUID(int=key)),
        actor=_HUMAN,
        now=DEFAULT_START,
        supersedes=supersedes,
        applicability=applicability,
    )


def test_promotion_preserves_scope_evidence_and_applicability_snapshot() -> None:
    applicability = LessonApplicability("  On shared runners  ", (("tool:runner", "v1"),))
    previous = _lesson()
    lesson = _lesson(11, supersedes=previous, applicability=applicability)
    assert lesson.supersedes_id == previous.id
    assert (lesson.workspace_id, lesson.scope_id) == (_CANDIDATE.workspace_id, _CANDIDATE.scope_id)
    assert (lesson.candidate_id, lesson.kind) == (_CANDIDATE.candidate_id, _CANDIDATE.kind)
    assert (lesson.evidence, lesson.confidence, lesson.confidence_tier) == (
        _CANDIDATE.evidence,
        _CANDIDATE.confidence,
        _CANDIDATE.tier,
    )
    assert lesson.applicability is applicability
    assert lesson.applicability.applies_to == "On shared runners"
    assert lesson.promoted_by == _HUMAN.principal_id
    assert lesson.promoted_at == DEFAULT_START
    assert lesson.state is LessonState.CURATED
    assert lesson.row_version == 1
    assert lesson.review_flag == "none"
    assert previous.state is LessonState.CURATED


@pytest.mark.parametrize("kind", [PrincipalKind.WORKER, PrincipalKind.SERVICE])
def test_promotion_and_deprecation_require_humans(kind: PrincipalKind) -> None:
    actor = replace(_HUMAN, kind=kind)
    with pytest.raises(Forbidden) as error:
        new_lesson_from_candidate(
            replace(_CANDIDATE, action=""), lesson_id=LessonId(UUID(int=10)), actor=actor, now=DEFAULT_START
        )
    assert error.value.code is ErrorCode.FORBIDDEN
    assert error.value.details == {"reason": "human_gate"}
    with pytest.raises(Forbidden) as error:
        deprecate(_lesson(), actor=actor, reason="Unsafe guidance", now=DEFAULT_START)
    assert error.value.code is ErrorCode.FORBIDDEN
    assert error.value.details == {"reason": "human_gate"}


def test_supersedes_requires_exact_workspace_and_scope() -> None:
    previous = _lesson()
    for foreign in (
        replace(previous, workspace_id=WorkspaceId(UUID(int=90))),
        replace(previous, scope_id=ScopeId(UUID(int=91))),
    ):
        with pytest.raises(ValidationFailed) as error:
            _lesson(11, supersedes=foreign)
        assert error.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize("trigger", ["", " \t\n", "x" * 501])
def test_promotion_rejects_invalid_trigger(trigger: str) -> None:
    with pytest.raises(ValidationFailed) as error:
        _lesson(candidate=replace(_CANDIDATE, trigger=trigger))
    assert error.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize("action", ["", " \t\n", "x" * 1001])
def test_promotion_rejects_invalid_action(action: str) -> None:
    with pytest.raises(ValidationFailed) as error:
        _lesson(candidate=replace(_CANDIDATE, action=action))
    assert error.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize("confidence", [-0.01, 1, float("nan"), float("inf"), True])
def test_promotion_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValidationFailed) as error:
        _lesson(candidate=replace(_CANDIDATE, confidence=confidence))
    assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_promotion_accepts_text_limits_and_zero_confidence_and_rejects_unknown_kind() -> None:
    lesson = _lesson(candidate=replace(_CANDIDATE, trigger="x" * 500, action="y" * 1000, confidence=0))
    assert len(lesson.trigger) == 500
    assert len(lesson.action) == 1000
    assert lesson.confidence == 0
    with pytest.raises(ValidationFailed) as error:
        _lesson(candidate=replace(_CANDIDATE, kind=cast("LessonKind", "unknown")))
    assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_applicability_boundaries_and_unique_exact_bindings() -> None:
    bindings = tuple((f"tool:tool-{i}", "v1") for i in range(32))
    assert LessonApplicability("x" * 1000, bindings, DEFAULT_START).validated_versions == bindings
    for invalid in (
        (*bindings, ("tool:extra", "v1")),
        (("tool:runner", "v1"), ("tool:runner", "v1")),
        (("tool:runner", "v1"), ("tool:runner", "v2")),
        (("", "v1"),),
        (("tool:runner", " \t"),),
    ):
        with pytest.raises(ValidationFailed) as error:
            LessonApplicability(validated_versions=invalid)
        assert error.value.code is ErrorCode.SCHEMA_INVALID
    for description in ("", " \t\n", "x" * 1001):
        with pytest.raises(ValidationFailed):
            LessonApplicability(applies_to=description)
    with pytest.raises(ValidationFailed):
        LessonApplicability(review_after=DEFAULT_START.replace(tzinfo=None))


@pytest.mark.parametrize("key", ["runner", ":runner", "tool:", "tool: runner"])
def test_applicability_requires_owner_qualified_binding_ids(key: str) -> None:
    with pytest.raises(ValidationFailed) as error:
        LessonApplicability(validated_versions=((key, "v1"),))
    assert error.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize(
    ("versions", "freshness"),
    [
        (None, "unvalidated"),
        ({}, "unvalidated"),
        ({"tool:runner": "v1"}, "unvalidated"),
        ({"tool:cache": "sha2"}, "needs_review"),
        ({"tool:runner": "v2", "tool:cache": "sha1"}, "needs_review"),
        ({"tool:runner": "V1", "tool:cache": "sha1"}, "needs_review"),
        ({"tool:runner": "v1", "tool:cache": "sha1", "tool:other": "v5"}, "current"),
    ],
)
def test_freshness_requires_known_exact_bindings_and_mismatch_wins_over_unknown(
    versions: dict[str, str] | None, freshness: LessonFreshness
) -> None:
    lesson = _lesson(
        applicability=LessonApplicability(validated_versions=(("tool:runner", "v1"), ("tool:cache", "sha1")))
    )
    assert evaluate_freshness(lesson, now=DEFAULT_START, current_versions=versions) == freshness
    assert lesson.state is LessonState.CURATED


def test_current_lesson_remains_curated_when_review_becomes_due_after_a_year() -> None:
    clock = FrozenClock()
    review_after = clock.now() + timedelta(days=365)
    versions = {"tool:runner": "v1"}
    lesson = _lesson(
        applicability=LessonApplicability("Shared runners", tuple(versions.items()), review_after)
    )
    assert evaluate_freshness(_lesson(), now=clock.now(), current_versions=versions) == "unvalidated"
    assert (
        evaluate_freshness(_lesson(applicability=LessonApplicability("Runners")), now=clock.now())
        == "unvalidated"
    )
    clock.set(review_after - timedelta(microseconds=1))
    assert evaluate_freshness(lesson, now=clock.now(), current_versions=versions) == "current"
    clock.set(review_after)
    assert evaluate_freshness(lesson, now=clock.now(), current_versions=versions) == "needs_review"
    assert lesson.state is LessonState.CURATED
    assert lesson.row_version == 1
    assert lesson.deprecated_at is None
    assert set(LessonState) == {LessonState.CURATED, LessonState.DEPRECATED}


def test_confidence_decay_flags_review_without_deprecating_and_clears_at_threshold() -> None:
    lesson = _lesson(applicability=LessonApplicability(validated_versions=(("tool:runner", "v1"),)))
    decayed = flag_decay(lesson, 0.49, 0.5)
    assert decayed == replace(lesson, confidence=0.49, review_flag="decay", row_version=2)
    assert (
        evaluate_freshness(decayed, now=DEFAULT_START, current_versions={"tool:runner": "v1"})
        == "needs_review"
    )
    assert flag_decay(decayed, 0.49, 0.5) is decayed
    restored = flag_decay(decayed, 0.5, 0.5)
    assert restored == replace(decayed, confidence=0.5, review_flag="none", row_version=3)
    assert (
        evaluate_freshness(restored, now=DEFAULT_START, current_versions={"tool:runner": "v1"}) == "current"
    )


def test_deprecate_preserves_previous_snapshot_and_is_idempotent() -> None:
    lesson = _lesson()
    now = DEFAULT_START + timedelta(days=365)
    retired = deprecate(lesson, actor=_HUMAN, reason="  Unsafe guidance  ", now=now)
    assert retired == replace(
        lesson,
        state=LessonState.DEPRECATED,
        deprecated_by=_HUMAN.principal_id,
        deprecated_at=now,
        deprecation_reason="Unsafe guidance",
        row_version=2,
    )
    assert lesson.state is LessonState.CURATED
    assert lesson.row_version == 1
    assert deprecate(retired, actor=_HUMAN, reason="Other reason", now=now + timedelta(days=1)) is retired
    assert deprecate(lesson, actor=_HUMAN, reason="x" * 500, now=now).deprecation_reason == "x" * 500
    for reason in ("", " \t\n", "x" * 501):
        with pytest.raises(ValidationFailed) as error:
            deprecate(lesson, actor=_HUMAN, reason=reason, now=now)
        assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_conflicts_keep_all_ids_regardless_of_confidence_and_ignore_other_scopes() -> None:
    first = replace(_lesson(), trigger="  Cafe\u0301\r\n is down  ", action=" Retry\rThe check  ")
    same = replace(_lesson(11), trigger="Café\n is down", action="Retry\nThe check")
    opposite = replace(_lesson(12), trigger="Café\r is down", action="Do not retry", confidence=0.1)
    foreign_workspace = replace(opposite, id=LessonId(UUID(int=13)), workspace_id=WorkspaceId(UUID(int=90)))
    foreign_scope = replace(opposite, id=LessonId(UUID(int=14)), scope_id=ScopeId(UUID(int=91)))
    retired = deprecate(opposite, actor=_HUMAN, reason="Unsafe", now=DEFAULT_START)
    assert potential_conflict_ids([first, same, foreign_workspace, foreign_scope, retired]) == ()
    assert potential_conflict_ids([opposite, same, foreign_workspace, first]) == (
        opposite.id,
        same.id,
        first.id,
    )
    assert potential_conflict_ids([first, replace(opposite, supersedes_id=first.id)]) == ()


@pytest.mark.parametrize(
    "trigger", ["test build fails", "Test  build fails", "Test build succeeds", "build fails Test"]
)
def test_conflict_normalization_preserves_case_spaces_negation_and_order(trigger: str) -> None:
    first = replace(_lesson(), trigger="Test build fails", action="Retry")
    second = replace(_lesson(11), trigger=trigger, action="Do not retry")
    assert potential_conflict_ids([first, second]) == ()


def test_lesson_and_graph_events_match_registered_payloads() -> None:
    lesson = _lesson()
    promoted = LessonPromoted(lesson.id, lesson.workspace_id, lesson.candidate_id)
    deprecated = LessonDeprecated(lesson.id, lesson.workspace_id, "Unsafe guidance")
    graph = GraphImported(
        lesson.workspace_id,
        "manual",
        {"nodes_upserted": 1, "nodes_removed": 0, "edges_added": 1, "edges_removed": 0},
    )
    assert promoted.stream_kind == deprecated.stream_kind == "lesson"
    assert promoted.stream_id() == deprecated.stream_id() == lesson.id
    assert promoted.scope_workspace_id() == deprecated.scope_workspace_id() == lesson.workspace_id
    assert graph.stream_kind == "workspace"
    assert graph.stream_id() == lesson.workspace_id
    assert graph.event_type in EVENT_TYPES
    assert tuple(event.event_type for event in EVENTS) == EVENT_TYPES
    for event in (promoted, deprecated, graph):
        event.validate(schemas())
    assert graph.payload()["counts"] == graph.counts
    assert promoted.payload() == {"lesson_id": str(lesson.id), "candidate_id": str(lesson.candidate_id)}
    assert deprecated.payload() == {"lesson_id": str(lesson.id), "reason": "Unsafe guidance"}
    assert schemas().validate(promoted.event_type, {"lesson_id": str(lesson.id)})


def test_lesson_promotion_schema_fixtures() -> None:
    candidate: JsonObject = {
        "candidate_id": str(_CANDIDATE.candidate_id),
        "workspace_id": str(_CANDIDATE.workspace_id),
        "scope_id": str(_CANDIDATE.scope_id),
        "kind": _CANDIDATE.kind.value,
        "trigger": _CANDIDATE.trigger,
        "action": _CANDIDATE.action,
        "confidence": _CANDIDATE.confidence,
        "tier": _CANDIDATE.tier.value,
        "evidence": [{"kind": ref.kind, "id": ref.id} for ref in _CANDIDATE.evidence],
    }
    urn = "urn:skm:knowledge:command:promote-lesson:v1"
    request: JsonObject = {
        "candidate": candidate,
        "applicability": {
            "validated_versions": [["tool:runner", "v1"]],
            "review_after": DEFAULT_START.isoformat(),
        },
    }
    schemas().require_valid(urn, request)
    for invalid in (
        {"validated_versions": [["tool:runner", "v1"], ["tool:runner", "v1"]]},
        {"review_after": "2026-10-25T16:00:00"},
    ):
        assert schemas().validate(urn, {**request, "applicability": invalid})
    assert schemas().validate(urn, {**request, "candidate": {**candidate, "confidence": "0.85"}})
