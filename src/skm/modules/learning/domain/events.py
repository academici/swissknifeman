"""Build typed payloads for the candidate stream."""

from typing import Literal, cast
from uuid import UUID

from skm.kernel.ids import PrincipalId, ProjectId
from skm.kernel.json_types import JsonObject
from skm.modules.learning.generated import events as wire

from .candidate import CandidateId, CandidateState
from .consolidation import ConsolidationAction
from .detectors import Detector
from .pathology import PathologyCode
from .review import CandidateReviewId, ReviewVerdict

CANDIDATE_STREAM_KIND = "candidate"
EVENT_TYPES: tuple[str, ...] = (
    "urn:skm:learning:event:candidate-extracted:v1",
    "urn:skm:learning:event:candidate-state-changed:v1",
    "urn:skm:learning:event:candidate-reviewed:v1",
    "urn:skm:learning:event:candidate-promoted:v1",
)


def candidate_extracted_payload(
    candidate_id: CandidateId,
    project_id: ProjectId,
    detector: Detector,
    pathology_code: PathologyCode | None,
    consolidation: ConsolidationAction,
    conflicts_with_id: CandidateId | None,
) -> JsonObject:
    return cast(
        "JsonObject",
        wire.candidate_extracted_from_json(
            {
                "candidate_id": str(candidate_id),
                "project_id": str(project_id),
                "detector": detector.value,
                "pathology_code": pathology_code.value if pathology_code is not None else None,
                "consolidation": consolidation.value,
                "conflicts_with_id": str(conflicts_with_id) if conflicts_with_id is not None else None,
            }
        ),
    )


def candidate_state_changed_payload(
    candidate_id: CandidateId,
    from_state: CandidateState,
    to_state: CandidateState,
    reason: Literal["numeric_gate", "source_support_low", "reobserved", "rejected"],
) -> JsonObject:
    return cast(
        "JsonObject",
        wire.candidate_state_changed_from_json(
            {
                "candidate_id": str(candidate_id),
                "from": from_state.value,
                "to": to_state.value,
                "reason": reason,
            }
        ),
    )


def candidate_reviewed_payload(
    candidate_id: CandidateId,
    review_id: CandidateReviewId,
    verdict: ReviewVerdict,
    reviewer_id: PrincipalId,
) -> JsonObject:
    return cast(
        "JsonObject",
        wire.candidate_reviewed_from_json(
            {
                "candidate_id": str(candidate_id),
                "review_id": str(review_id),
                "verdict": verdict.value,
                "reviewer_id": str(reviewer_id),
            }
        ),
    )


def candidate_promoted_payload(
    candidate_id: CandidateId,
    lesson_id: UUID,
    promoted_by: PrincipalId,
    *,
    override_low_confidence: bool,
) -> JsonObject:
    return cast(
        "JsonObject",
        wire.candidate_promoted_from_json(
            {
                "candidate_id": str(candidate_id),
                "lesson_id": str(lesson_id),
                "promoted_by": str(promoted_by),
                "override_low_confidence": override_low_confidence,
            }
        ),
    )
