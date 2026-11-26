"""Adaptive count floors, attainable gates and pure candidate recompute."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

from .activity import ConfidenceSettings, LearningSettings
from .candidate import Candidate, CandidateState, Signal
from .confidence import Aggregate, aggregate, calculate_confidence

type EffectiveMinimum = int | Literal["unreachable"]
type NumericReason = Literal["numeric_gate", "source_support_low"]


@dataclass(frozen=True, slots=True)
class AdaptiveThresholds:
    candidate_min_n: int
    curated_min_n: int


def adaptive_thresholds(project_sessions: int, t: LearningSettings) -> AdaptiveThresholds:
    thresholds = t.thresholds
    candidate, curated = thresholds.candidate_min_n, thresholds.curated_min_n
    if project_sessions >= curated:
        return AdaptiveThresholds(candidate, curated)
    lower = min(candidate, max(thresholds.candidate_min_n_floor, project_sessions // 5))
    # Round half up with exact integers.
    scaled = (2 * lower * curated + candidate) // (2 * candidate)
    return AdaptiveThresholds(lower, max(lower, scaled))


def effective_minimum(
    count_floor: int,
    score_floor: float,
    confidence: ConfidenceSettings,
) -> EffectiveMinimum:
    if score_floor >= 1:
        return "unreachable"
    low = high = max(1, count_floor)
    while calculate_confidence(high, high, 0, confidence).support_score < score_floor:
        high *= 2
    while low < high:
        mid = (low + high) // 2
        if calculate_confidence(mid, mid, 0, confidence).support_score >= score_floor:
            high = mid
        else:
            low = mid + 1
    return low


@dataclass(frozen=True, slots=True)
class Gate:
    configured_min_n: int
    adaptive_min_n: int
    effective_min_n_ideal: EffectiveMinimum
    support_min: float
    passrate_min: float | None
    missing_conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Gates:
    candidate: Gate
    curated: Gate


def _missing(inputs: Aggregate, minimum_n: int, support: float, passrate: float | None) -> tuple[str, ...]:
    conditions: list[str] = []
    if inputs.independent_known_total < minimum_n:
        conditions.append("independent_known_total")
    if inputs.score.support_score < support:
        conditions.append("support_score")
    if inputs.tests_total == 0:
        conditions.append("tests_total")
    if passrate is not None and (inputs.passrate is None or inputs.passrate < passrate):
        conditions.append("passrate")
    return tuple(conditions)


def confidence_gates(inputs: Aggregate, project_sessions: int, t: LearningSettings) -> Gates:
    adaptive = adaptive_thresholds(project_sessions, t)
    settings = t.thresholds
    candidate_n, curated_n = adaptive.candidate_min_n, adaptive.curated_min_n
    candidate_score, curated_score = settings.candidate_min_conf, settings.curated_min_conf
    return Gates(
        candidate=Gate(
            settings.candidate_min_n,
            candidate_n,
            effective_minimum(candidate_n, candidate_score, t.confidence),
            candidate_score,
            None,
            _missing(inputs, candidate_n, candidate_score, None),
        ),
        curated=Gate(
            settings.curated_min_n,
            curated_n,
            effective_minimum(curated_n, curated_score, t.confidence),
            curated_score,
            settings.curated_min_passrate,
            _missing(inputs, curated_n, curated_score, settings.curated_min_passrate),
        ),
    )


@dataclass(frozen=True, slots=True)
class Transition:
    state: CandidateState
    reason: NumericReason | None = None
    curated_ready: bool = False
    lesson_decay: bool = False


def decide_transition(
    state: CandidateState,
    inputs: Aggregate,
    project_sessions: int,
    t: LearningSettings,
) -> Transition:
    thresholds = t.thresholds
    adaptive = adaptive_thresholds(project_sessions, t)
    support = inputs.score.support_score
    if state is CandidateState.OBSERVED and not _missing(
        inputs,
        adaptive.candidate_min_n,
        thresholds.candidate_min_conf,
        None,
    ):
        return Transition(CandidateState.CANDIDATE, "numeric_gate")
    if state is CandidateState.CANDIDATE:
        if support < thresholds.deprecate_conf:
            return Transition(CandidateState.DEPRECATED, "source_support_low")
        return Transition(
            state,
            curated_ready=not _missing(
                inputs,
                adaptive.curated_min_n,
                thresholds.curated_min_conf,
                thresholds.curated_min_passrate,
            ),
        )
    if state is CandidateState.PROMOTED:
        return Transition(state, lesson_decay=inputs.stale or support < thresholds.deprecate_conf)
    return Transition(state)


def recompute(
    candidate: Candidate,
    signals: Iterable[Signal],
    *,
    now: datetime,
    project_sessions: int,
    t: LearningSettings,
) -> tuple[Candidate, Transition]:
    rows = tuple(signals)
    if any(signal.candidate_id != candidate.id for signal in rows):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Signals must belong to the candidate being recomputed"
        )
    inputs = aggregate(rows, now, t)
    transition = decide_transition(candidate.state, inputs, project_sessions, t)
    updated = replace(
        candidate,
        state=transition.state,
        s_total=inputs.s_total,
        n_total=inputs.n_total,
        known_outcome_total=inputs.known_outcome_total,
        unknown_outcome_total=inputs.unknown_outcome_total,
        independent_known_total=inputs.independent_known_total,
        independent_success_total=inputs.independent_success_total,
        exposed_total=inputs.exposed_total,
        exposure_unknown_total=inputs.exposure_unknown_total,
        tests_total=inputs.tests_total,
        tests_passed=inputs.tests_passed,
        days_since=inputs.days_since,
        support_score=inputs.score.support_score,
        confidence=inputs.score.confidence,
        confidence_tier=inputs.confidence_tier,
        freshness=inputs.score.freshness,
        stale=inputs.stale,
        curated_ready=transition.curated_ready,
        recomputed_at=now,
    )
    return updated, transition
