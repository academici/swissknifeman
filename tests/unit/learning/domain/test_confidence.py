"""Only known independent outcomes contribute to empirical support."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.learning.domain.activity import (
    DEFAULT_SETTINGS,
    ActivityRecord,
    ActivityRecordId,
    ActivitySummary,
    CheckRun,
    EvidenceDependency,
    Outcome,
    SourceKind,
)
from skm.modules.learning.domain.candidate import CandidateId, ConfidenceTier, Signal, SignalId
from skm.modules.learning.domain.confidence import aggregate, calculate_confidence, confidence_tier
from skm.modules.learning.domain.detectors import extract_with_evidence

NOW = datetime(2026, 11, 10, tzinfo=UTC)
CANDIDATE_ID = CandidateId(UUID(int=100))


def signal(
    index: int,
    *,
    dependency: EvidenceDependency,
    outcome: Outcome,
    observed_at: datetime,
) -> Signal:
    return Signal(
        SignalId(UUID(int=index)),
        CANDIDATE_ID,
        ActivityRecordId(UUID(int=index)),
        "extract",
        1,
        int(outcome is not Outcome.UNKNOWN),
        int(outcome is Outcome.SUCCESS),
        dependency,
        3,
        1,
        observed_at,
    )


def test_score_formula_and_no_support_without_sources() -> None:
    empty = calculate_confidence(0, 0, 0)
    assert empty.beta_mean == 0.5
    assert empty.support_score == empty.confidence == 0
    score = calculate_confidence(20, 20, 1)
    assert score.beta_mean == 21 / 22
    assert score.volume == pytest.approx(0.6321205588)
    assert score.support_score == pytest.approx(0.6033878061)
    assert score.freshness == 0.95
    assert score.confidence == pytest.approx(score.support_score * 0.95)
    assert calculate_confidence(20, 20, -1).freshness == 1.0


@pytest.mark.parametrize(
    ("score", "tier"),
    [
        (0.299999, ConfidenceTier.NONE),
        (0.3, ConfidenceTier.TENTATIVE),
        (0.5, ConfidenceTier.MODERATE),
        (0.7, ConfidenceTier.STRONG),
        (0.9, ConfidenceTier.CORE),
    ],
)
def test_confidence_tiers(score: float, tier: ConfidenceTier) -> None:
    assert confidence_tier(score) is tier


def test_counters_separate_outcomes_exposure_and_freshness() -> None:
    prior = NOW - timedelta(days=2)
    rows = (
        signal(1, dependency="independent", outcome=Outcome.SUCCESS, observed_at=prior),
        signal(2, dependency="independent", outcome=Outcome.FAILURE, observed_at=prior),
        signal(3, dependency="independent", outcome=Outcome.UNKNOWN, observed_at=NOW),
        signal(4, dependency="exposed", outcome=Outcome.SUCCESS, observed_at=NOW),
        signal(5, dependency="unknown", outcome=Outcome.SUCCESS, observed_at=NOW),
    )
    inputs = aggregate(rows, NOW)
    assert (inputs.s_total, inputs.n_total, inputs.coverage, inputs.source_outcome_rate) == (3, 5, 0.8, 0.75)
    assert (inputs.independent_success_total, inputs.independent_known_total) == (1, 2)
    assert (inputs.tests_total, inputs.tests_passed, inputs.passrate) == (6, 2, 1 / 3)
    assert (inputs.exposed_total, inputs.exposure_unknown_total, inputs.unknown_outcome_total) == (1, 1, 1)
    assert inputs.last_observed_at == prior
    assert inputs.days_since == 2
    assert inputs.score == aggregate(rows[:2], NOW).score


def test_shared_finding_across_ten_audits_adds_zero_independent_support() -> None:
    lineage: tuple[JsonObject, ...] = ({"kind": "finding", "id": "shared"},)
    summary = ActivitySummary(
        SourceKind.ATTEMPT,
        "audit",
        Outcome.SUCCESS,
        NOW,
        exposed_lesson_refs=(),
        checks=(
            CheckRun(None, False, "check_execution", "review"),
            CheckRun(None, True, "check_execution", "review"),
        ),
    )
    signals: list[Signal] = []
    for index in range(10):
        activity = replace(summary, source_key=f"audit-{index}")
        result = extract_with_evidence(activity, {}, DEFAULT_SETTINGS, source_refs=lineage)
        id = UUID(int=index)
        assert all(bundle.source_refs[1] == lineage[0] for bundle in result.evidence)
        record = ActivityRecord.from_summary(
            activity,
            id=ActivityRecordId(id),
            workspace_id=WorkspaceId(id),
            project_id=ProjectId(id),
            scope_id=ScopeId(id),
            pathology_codes=result.pathology_codes,
            detector_evidence=result.evidence,
        )
        assert record.exposure_coverage == "unknown"
        observations = result.observations
        signals.append(
            Signal.from_observations(
                id=SignalId(id),
                candidate_id=CANDIDATE_ID,
                activity=record,
                observations=observations * 2,
            )
        )
    assert all(s.tests_total == 2 and s.tests_passed == 1 for s in signals)
    inputs = aggregate(signals, NOW)
    assert (inputs.n_total, inputs.known_outcome_total, inputs.exposure_unknown_total) == (10, 10, 10)
    assert (inputs.coverage, inputs.source_outcome_rate) == (1.0, 1.0)
    assert (inputs.independent_known_total, inputs.independent_success_total, inputs.tests_total) == (0, 0, 0)
    assert inputs.last_observed_at is None
    assert inputs.score.support_score == inputs.score.confidence == 0.0
    assert inputs.score.freshness == 1.0
