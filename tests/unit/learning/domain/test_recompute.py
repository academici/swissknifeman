"""Attainability and state transitions use unrounded support."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.modules.learning.domain.activity import DEFAULT_SETTINGS, ActivityRecordId, Thresholds
from skm.modules.learning.domain.candidate import CandidateId, CandidateState, Signal, SignalId
from skm.modules.learning.domain.confidence import aggregate
from skm.modules.learning.domain.recompute import (
    adaptive_thresholds,
    confidence_gates,
    decide_transition,
    effective_minimum,
)

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def successful_signals(count: int) -> tuple[Signal, ...]:
    return tuple(
        Signal(
            SignalId(UUID(int=i)),
            CandidateId(UUID(int=100)),
            ActivityRecordId(UUID(int=i)),
            "extract",
            1,
            1,
            1,
            "independent",
            1,
            1,
            NOW,
        )
        for i in range(count)
    )


@pytest.mark.parametrize(
    ("sessions", "candidate_n", "curated_n", "effective_curated"),
    [
        (0, 3, 10, 35),
        (14, 3, 10, 35),
        (49, 9, 30, 35),
        (50, 15, 50, 50),
        (500, 15, 50, 50),
    ],
)
def test_adaptive_and_effective_gate(
    sessions: int,
    candidate_n: int,
    curated_n: int,
    effective_curated: int,
) -> None:
    adapt = adaptive_thresholds(sessions, DEFAULT_SETTINGS)
    assert (adapt.candidate_min_n, adapt.curated_min_n) == (candidate_n, curated_n)
    gates = confidence_gates(aggregate((), NOW), sessions, DEFAULT_SETTINGS)
    assert gates.candidate.effective_min_n_ideal == 20
    assert gates.curated.effective_min_n_ideal == effective_curated
    assert gates.candidate.missing_conditions == ("independent_known_total", "support_score", "tests_total")


def test_adaptive_round_half_up_and_unreachable_score() -> None:
    t = replace(
        DEFAULT_SETTINGS, thresholds=Thresholds(candidate_min_n=4, candidate_min_n_floor=2, curated_min_n=5)
    )
    assert adaptive_thresholds(0, t).curated_min_n == 3
    assert effective_minimum(3, 1, t.confidence) == "unreachable"
    with pytest.raises(ValueError, match="exit"):
        Thresholds(deprecate_conf=0.6)


@pytest.mark.parametrize("n", [3, 15, 19, 20])
def test_candidate_entry_uses_support_and_checks(n: int) -> None:
    inputs = aggregate(successful_signals(n), NOW)
    result = decide_transition(CandidateState.OBSERVED, inputs, n, DEFAULT_SETTINGS)
    assert result.state is (CandidateState.CANDIDATE if n == 20 else CandidateState.OBSERVED)
    assert (
        decide_transition(CandidateState.OBSERVED, replace(inputs, tests_total=0), n, DEFAULT_SETTINGS).state
        is CandidateState.OBSERVED
    )


def test_decay_never_deprecates_and_support_is_unrounded() -> None:
    signals = successful_signals(20)
    today = aggregate(signals, NOW)
    aged = aggregate(signals, NOW + timedelta(days=30))
    assert aged.stale
    assert aged.score.support_score == today.score.support_score
    assert aged.score.confidence < 0.4
    assert (
        decide_transition(CandidateState.CANDIDATE, aged, 20, DEFAULT_SETTINGS).state
        is CandidateState.CANDIDATE
    )
    assert decide_transition(CandidateState.PROMOTED, aged, 20, DEFAULT_SETTINGS).lesson_decay
    below = replace(today, score=replace(today.score, support_score=0.599999))
    assert (
        decide_transition(CandidateState.OBSERVED, below, 20, DEFAULT_SETTINGS).state
        is CandidateState.OBSERVED
    )


def test_curated_flag_and_low_support_transition() -> None:
    inputs = aggregate(successful_signals(50), NOW)
    assert decide_transition(CandidateState.CANDIDATE, inputs, 50, DEFAULT_SETTINGS).curated_ready
    assert not decide_transition(
        CandidateState.CANDIDATE,
        replace(inputs, tests_passed=47),
        50,
        DEFAULT_SETTINGS,
    ).curated_ready
    failed = aggregate(tuple(replace(s, sessions_success=0) for s in successful_signals(20)), NOW)
    assert (
        decide_transition(CandidateState.CANDIDATE, failed, 20, DEFAULT_SETTINGS).state
        is CandidateState.DEPRECATED
    )
    for state in (CandidateState.REJECTED, CandidateState.DEPRECATED):
        assert decide_transition(state, inputs, 50, DEFAULT_SETTINGS).state is state
