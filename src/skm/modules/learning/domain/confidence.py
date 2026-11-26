"""Source-association scores and empirical counters."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import expm1

from .activity import DEFAULT_SETTINGS, ActivityRecordId, ConfidenceSettings, LearningSettings
from .candidate import CandidateId, ConfidenceTier, Signal


@dataclass(frozen=True, slots=True)
class Confidence:
    beta_mean: float
    volume: float
    support_score: float
    freshness: float
    confidence: float


def calculate_confidence(
    successes: int,
    known: int,
    days: int,
    settings: ConfidenceSettings = DEFAULT_SETTINGS.confidence,
) -> Confidence:
    beta_mean = (successes + settings.alpha) / (known + settings.alpha + settings.beta)
    volume = -expm1(-known / settings.volume_k)
    freshness = settings.decay_lambda ** max(0, days)
    support = beta_mean * volume
    return Confidence(beta_mean, volume, support, freshness, support * freshness)


def confidence_tier(confidence: float) -> ConfidenceTier:
    for threshold, tier in (
        (0.9, ConfidenceTier.CORE),
        (0.7, ConfidenceTier.STRONG),
        (0.5, ConfidenceTier.MODERATE),
        (0.3, ConfidenceTier.TENTATIVE),
    ):
        if confidence >= threshold:
            return tier
    return ConfidenceTier.NONE


@dataclass(frozen=True, slots=True)
class Aggregate:
    s_total: int
    n_total: int
    known_outcome_total: int
    unknown_outcome_total: int
    independent_known_total: int
    independent_success_total: int
    exposed_total: int
    exposure_unknown_total: int
    tests_total: int
    tests_passed: int
    last_observed_at: datetime | None
    days_since: int
    score: Confidence
    confidence_tier: ConfidenceTier
    stale: bool

    @property
    def coverage(self) -> float | None:
        return self.known_outcome_total / self.n_total if self.n_total else None

    @property
    def source_outcome_rate(self) -> float | None:
        return self.s_total / self.known_outcome_total if self.known_outcome_total else None

    @property
    def passrate(self) -> float | None:
        return self.tests_passed / self.tests_total if self.tests_total else None


def aggregate(signals: Iterable[Signal], now: datetime, t: LearningSettings = DEFAULT_SETTINGS) -> Aggregate:
    by_activity: dict[ActivityRecordId, Signal] = {}
    candidate_id: CandidateId | None = None
    for signal in signals:
        if candidate_id is None:
            candidate_id = signal.candidate_id
        elif signal.candidate_id != candidate_id:
            raise ValueError("Cannot aggregate signals from multiple candidates")
        previous = by_activity.setdefault(signal.activity_record_id, signal)
        if previous != signal:
            raise ValueError("Expected one signal per activity for a single candidate")
    observed = by_activity.values()
    known = tuple(signal for signal in observed if signal.sessions_known == 1)
    independent = tuple(signal for signal in known if signal.evidence_dependency == "independent")
    last = max((signal.observed_at for signal in independent), default=None)
    days = max(0, (now - last).days) if last is not None else 0
    successes = sum(signal.sessions_success for signal in independent)
    score = calculate_confidence(successes, len(independent), days, t.confidence)
    return Aggregate(
        s_total=sum(signal.sessions_success for signal in known),
        n_total=len(observed),
        known_outcome_total=len(known),
        unknown_outcome_total=len(observed) - len(known),
        independent_known_total=len(independent),
        independent_success_total=successes,
        exposed_total=sum(signal.evidence_dependency == "exposed" for signal in observed),
        exposure_unknown_total=sum(signal.evidence_dependency == "unknown" for signal in observed),
        tests_total=sum(signal.tests_total for signal in independent),
        tests_passed=sum(signal.tests_passed for signal in independent),
        last_observed_at=last,
        days_since=days,
        score=score,
        confidence_tier=confidence_tier(score.confidence),
        stale=bool(independent) and score.confidence < t.thresholds.deprecate_conf,
    )
