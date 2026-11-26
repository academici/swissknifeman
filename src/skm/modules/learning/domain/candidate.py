"""Candidate lifecycle and empirical signals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, NewType, Self
from uuid import UUID

from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.modules.knowledge.public import EvidenceRef, LessonId, LessonKind

from .activity import ActivityRecord, ActivityRecordId, EvidenceDependency, Outcome
from .contracts import CandidateProposalView
from .detectors import CheckIdentity, Detector, Observation
from .pathology import PathologyCode
from .tokens import norm

SignalId = NewType("SignalId", UUID)

CandidateId = NewType("CandidateId", UUID)


class CandidateState(StrEnum):
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class ConfidenceTier(StrEnum):
    NONE = "none"
    TENTATIVE = "tentative"
    MODERATE = "moderate"
    STRONG = "strong"
    CORE = "core"


CANDIDATE_TRANSITIONS: Mapping[CandidateState, frozenset[CandidateState]] = {
    CandidateState.OBSERVED: frozenset(
        {CandidateState.CANDIDATE, CandidateState.PROMOTED, CandidateState.REJECTED}
    ),
    CandidateState.CANDIDATE: frozenset(
        {CandidateState.PROMOTED, CandidateState.REJECTED, CandidateState.DEPRECATED}
    ),
    CandidateState.DEPRECATED: frozenset({CandidateState.OBSERVED, CandidateState.REJECTED}),
    CandidateState.PROMOTED: frozenset(),
    CandidateState.REJECTED: frozenset(),
}

type ReviewStatus = Literal["unreviewed", "approved", "edited", "rejected"]


@dataclass(frozen=True, slots=True)
class Candidate:
    id: CandidateId
    workspace_id: WorkspaceId
    project_id: ProjectId
    scope_id: ScopeId
    display_key: str
    detector: Detector
    pathology_code: PathologyCode | None
    kind: LessonKind
    trigger: str
    action: str
    review_hint: str | None
    meta: Mapping[str, JsonValue]
    evidence: tuple[EvidenceRef, ...]
    fingerprint: str
    state: CandidateState
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
    days_since: int
    support_score: float
    freshness: float
    stale: bool
    review_status: ReviewStatus
    confidence: float
    confidence_tier: ConfidenceTier
    curated_ready: bool
    conflicts_with_id: CandidateId | None
    proposed_update: CandidateProposalView | None
    lesson_id: LessonId | None
    recomputed_at: datetime | None
    row_version: int


@dataclass(frozen=True, slots=True)
class Signal:
    id: SignalId
    candidate_id: CandidateId
    activity_record_id: ActivityRecordId
    source: Literal["extract"]
    sessions_total: int
    sessions_known: int
    sessions_success: int
    evidence_dependency: EvidenceDependency
    tests_total: int
    tests_passed: int
    observed_at: datetime

    @classmethod
    def from_observations(
        cls,
        *,
        id: SignalId,
        candidate_id: CandidateId,
        activity: ActivityRecord,
        observations: tuple[Observation, ...],
    ) -> Self:
        """Make one signal for all observations of the same wording in this activity."""
        if not observations:
            raise ValueError("A signal requires an observation")
        first = observations[0]
        identity = (first.kind, norm(first.trigger), norm(first.action))
        checks: dict[CheckIdentity, tuple[int, int]] = {}
        for observation in observations:
            if (observation.kind, norm(observation.trigger), norm(observation.action)) != identity:
                raise ValueError("A signal can only combine observations of the same wording")
            counts = (observation.tests_total, observation.tests_passed)
            check = observation.check_identity
            if check is None:
                if counts != (0, 0):
                    raise ValueError("Check counts require a check identity")
                continue
            if not 0 <= counts[1] <= counts[0] or checks.setdefault(check, counts) != counts:
                raise ValueError("Inconsistent counts for one check identity")
        return cls(
            id=id,
            candidate_id=candidate_id,
            activity_record_id=activity.id,
            source="extract",
            sessions_total=1,
            sessions_known=int(activity.outcome in (Outcome.SUCCESS, Outcome.FAILURE)),
            sessions_success=int(activity.outcome is Outcome.SUCCESS),
            evidence_dependency=activity.evidence_dependency,
            tests_total=sum(total for total, _ in checks.values()),
            tests_passed=sum(passed for _, passed in checks.values()),
            observed_at=activity.observed_at,
        )
