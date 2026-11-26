"""Bus registrations for learning and its JSON wire records."""

from dataclasses import replace
from typing import Any

from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec
from skm.modules.learning import public as learning

from .commands import (
    extract_candidates,
    promote_candidate,
    recompute_confidence,
    record_activity,
    review_candidate,
)
from .queries import get_candidate, list_candidates, list_signals, pathology_stats
from .queries.list_candidates import require_project_workspace

type OperationSpec = AnyCommandSpec | AnyQuerySpec


def _bind[S: OperationSpec](spec: S, dto: type[Any], result: type[Any]) -> S:
    def handle(cmd: Any, ctx: Any, uow: Any) -> Any:
        if dto is learning.RecomputeConfidence and "project_id" in cmd:
            require_project_workspace(uow, cmd["project_id"], cmd["workspace_id"])
        return result.from_json(spec.handler(cmd, ctx, uow))

    return replace(spec, dto=dto, result=result, handler=handle)


COMMANDS = (
    _bind(
        review_candidate.SPEC,
        learning.ReviewCandidate,
        learning.ReviewCandidateResult,
    ),
    _bind(
        promote_candidate.SPEC,
        learning.PromoteCandidate,
        learning.PromoteCandidateResult,
    ),
    _bind(
        # The system principal is admitted only for system permissions. Human
        # and token callers still need lesson.curate through the alternative.
        replace(
            recompute_confidence.SPEC,
            permission="system.internal",
            permission_alternatives=("lesson.curate",),
        ),
        learning.RecomputeConfidence,
        learning.RecomputeConfidenceResult,
    ),
    _bind(
        record_activity.SPEC,
        learning.RecordActivity,
        learning.RecordActivityResult,
    ),
    _bind(
        extract_candidates.SPEC,
        learning.ExtractCandidates,
        learning.ExtractCandidatesResult,
    ),
)
QUERIES = (
    _bind(
        list_candidates.SPEC,
        learning.ListCandidates,
        learning.CandidatesView,
    ),
    _bind(
        get_candidate.SPEC,
        learning.GetCandidate,
        learning.CandidateView,
    ),
    _bind(
        list_signals.SPEC,
        learning.ListSignals,
        learning.SignalsView,
    ),
    _bind(
        pathology_stats.SPEC,
        learning.PathologyStats,
        learning.PathologyStatsView,
    ),
)
