"""Client-safe learning wire DTOs and lazy domain re-exports."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, Any, Self

from .generated import commands, queries, results, views


def _model(name: str, urn: str, parse: Callable[[Any], Any]) -> type[Any]:
    class JsonRecord(dict[str, Any]):
        SCHEMA_URN = urn

        @classmethod
        def from_json(cls, data: Any) -> Self:
            return cls(parse(data))

        def to_json(self) -> Any:
            return parse(self)

    JsonRecord.__name__ = name
    return JsonRecord


ReviewCandidate = _model(
    "ReviewCandidate", "urn:skm:learning:command:review-candidate:v1", commands.review_candidate_from_json
)
ReviewCandidateResult = _model(
    "ReviewCandidateResult",
    "urn:skm:learning:result:review-candidate:v1",
    results.review_candidate_result_from_json,
)
PromoteCandidate = _model(
    "PromoteCandidate", "urn:skm:learning:command:promote-candidate:v1", commands.promote_candidate_from_json
)
PromoteCandidateResult = _model(
    "PromoteCandidateResult",
    "urn:skm:learning:result:promote-candidate:v1",
    results.promote_candidate_result_from_json,
)
RecomputeConfidence = _model(
    "RecomputeConfidence",
    "urn:skm:learning:command:recompute-confidence:v1",
    commands.recompute_confidence_from_json,
)
RecomputeConfidenceResult = _model(
    "RecomputeConfidenceResult",
    "urn:skm:learning:result:recompute-confidence:v1",
    results.recompute_confidence_result_from_json,
)
RecordActivity = _model(
    "RecordActivity", "urn:skm:learning:command:record-activity:v1", commands.record_activity_from_json
)
RecordActivityResult = _model(
    "RecordActivityResult",
    "urn:skm:learning:result:record-activity:v1",
    results.record_activity_result_from_json,
)
ExtractCandidates = _model(
    "ExtractCandidates",
    "urn:skm:learning:command:extract-candidates:v1",
    commands.extract_candidates_from_json,
)
ExtractCandidatesResult = _model(
    "ExtractCandidatesResult",
    "urn:skm:learning:result:extract-candidates:v1",
    results.extract_candidates_result_from_json,
)
ListCandidates = _model(
    "ListCandidates", "urn:skm:learning:query:list-candidates:v1", queries.list_candidates_from_json
)
CandidatesView = _model(
    "CandidatesView", "urn:skm:learning:view:candidates:v1", views.candidates_view_from_json
)
GetCandidate = _model(
    "GetCandidate", "urn:skm:learning:query:get-candidate:v1", queries.get_candidate_from_json
)
CandidateView = _model("CandidateView", "urn:skm:learning:view:candidate:v1", views.candidate_view_from_json)
ListSignals = _model("ListSignals", "urn:skm:learning:query:list-signals:v1", queries.list_signals_from_json)
SignalsView = _model("SignalsView", "urn:skm:learning:view:signals:v1", views.signals_view_from_json)
PathologyStats = _model(
    "PathologyStats", "urn:skm:learning:query:pathology-stats:v1", queries.pathology_stats_from_json
)
PathologyStatsView = _model(
    "PathologyStatsView", "urn:skm:learning:view:pathology-stats:v1", views.pathology_stats_view_from_json
)


if TYPE_CHECKING:
    from .domain.activity import (
        ActivityRecord,
        ActivityRecordId,
        ActivitySummary,
        AgentUsage,
        CheckRun,
        ErrorLoop,
        Outcome,
        RereadEntry,
        SourceKind,
        WorkflowRelaunch,
    )
    from .domain.candidate import Candidate, CandidateId, CandidateState, ConfidenceTier, Signal, SignalId
    from .domain.consolidation import ConsolidationAction
    from .domain.detectors import Detector, Observation
    from .domain.evidence import DetectorEvidence, ExposedLessonRef
    from .domain.pathology import PathologyCode, PathologyFinding
    from .domain.review import (
        CandidateProposal,
        CandidateProposalId,
        CandidateReview,
        CandidateReviewId,
        ReviewVerdict,
    )


_LAZY_EXPORTS = {
    **dict.fromkeys(
        (
            "ActivityRecord",
            "ActivityRecordId",
            "ActivitySummary",
            "AgentUsage",
            "CheckRun",
            "ErrorLoop",
            "Outcome",
            "RereadEntry",
            "SourceKind",
            "WorkflowRelaunch",
        ),
        ".domain.activity",
    ),
    **dict.fromkeys(
        (
            "Candidate",
            "CandidateId",
            "CandidateState",
            "ConfidenceTier",
            "Signal",
            "SignalId",
        ),
        ".domain.candidate",
    ),
    **dict.fromkeys(("ConsolidationAction",), ".domain.consolidation"),
    **dict.fromkeys(
        (
            "Detector",
            "Observation",
        ),
        ".domain.detectors",
    ),
    **dict.fromkeys(
        (
            "DetectorEvidence",
            "ExposedLessonRef",
        ),
        ".domain.evidence",
    ),
    **dict.fromkeys(
        (
            "PathologyCode",
            "PathologyFinding",
        ),
        ".domain.pathology",
    ),
    **dict.fromkeys(
        (
            "CandidateProposal",
            "CandidateProposalId",
            "CandidateReview",
            "CandidateReviewId",
            "ReviewVerdict",
        ),
        ".domain.review",
    ),
}


def __getattr__(name: str) -> object:
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "ActivityRecord",
    "ActivityRecordId",
    "ActivitySummary",
    "AgentUsage",
    "Candidate",
    "CandidateId",
    "CandidateProposal",
    "CandidateProposalId",
    "CandidateReview",
    "CandidateReviewId",
    "CandidateState",
    "CandidateView",
    "CandidatesView",
    "CheckRun",
    "ConfidenceTier",
    "ConsolidationAction",
    "Detector",
    "DetectorEvidence",
    "ErrorLoop",
    "ExposedLessonRef",
    "ExtractCandidates",
    "ExtractCandidatesResult",
    "GetCandidate",
    "ListCandidates",
    "ListSignals",
    "Observation",
    "Outcome",
    "PathologyCode",
    "PathologyFinding",
    "PathologyStats",
    "PathologyStatsView",
    "PromoteCandidate",
    "PromoteCandidateResult",
    "RecomputeConfidence",
    "RecomputeConfidenceResult",
    "RecordActivity",
    "RecordActivityResult",
    "RereadEntry",
    "ReviewCandidate",
    "ReviewCandidateResult",
    "ReviewVerdict",
    "Signal",
    "SignalId",
    "SignalsView",
    "SourceKind",
    "WorkflowRelaunch",
]
