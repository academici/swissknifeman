"""HTTP routes for learning intake, queries and curation."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.modules.learning import public as learning

__all__ = ["ROUTES"]

_CANDIDATES = "/api/v1/workspaces/{workspace_id}/lesson-candidates"
_CANDIDATE = _CANDIDATES + "/{candidate_id}"
_WORKSPACE = {"workspace_id": "workspace_id"}
_PROJECT = {"project_id": "project_id"}
_BY_CANDIDATE = {**_WORKSPACE, "candidate_id": "candidate_id"}
_TAGS = ("learning",)


class _CandidateListRoute(Route):
    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> Any:
        params = dict(query)
        fields = dict(body)
        if "states" in params:
            raw = params.pop("states")
            getlist = getattr(query, "getlist", None)
            states = getlist("states") if getlist is not None else [raw]
            fields["states"] = [value for group in states for value in group.split(",")]
        return super().bind(fields, path, params, **kwargs)


ROUTES = (
    _CandidateListRoute(
        "GET",
        _CANDIDATES,
        learning.CandidatesView,
        query=learning.ListCandidates,
        path_params=_WORKSPACE,
        query_params={key: key for key in ("project_id", "states", "detector", "min_tier", "after", "limit")},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        _CANDIDATE,
        learning.CandidateView,
        query=learning.GetCandidate,
        path_params=_BY_CANDIDATE,
        query_params={key: key for key in ("proposals_after", "proposals_limit")},
        etag_from="row_version",
        body="none",
        tags=_TAGS,
    ),
    Route(
        "POST",
        _CANDIDATE + "/reviews",
        learning.ReviewCandidateResult,
        command=learning.ReviewCandidate,
        path_params=_BY_CANDIDATE,
        if_match_to="expected_row_version",
        idempotency=IdempotencyMode.REQUIRED,
        tags=_TAGS,
    ),
    Route(
        "POST",
        _CANDIDATE + "/promote",
        learning.PromoteCandidateResult,
        command=learning.PromoteCandidate,
        path_params=_BY_CANDIDATE,
        if_match_to="expected_row_version",
        idempotency=IdempotencyMode.REQUIRED,
        success_status=201,
        tags=_TAGS,
    ),
    Route(
        "GET",
        _CANDIDATE + "/signals",
        learning.SignalsView,
        query=learning.ListSignals,
        path_params=_BY_CANDIDATE,
        query_params={key: key for key in ("after", "limit")},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/learning/activity",
        learning.RecordActivityResult,
        command=learning.RecordActivity,
        path_params=_PROJECT,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=_TAGS,
    ),
    Route(
        "POST",
        "/api/v1/workspaces/{workspace_id}/learning/recompute",
        learning.RecomputeConfidenceResult,
        command=learning.RecomputeConfidence,
        path_params=_WORKSPACE,
        idempotency=IdempotencyMode.REQUIRED,
        tags=_TAGS,
    ),
    Route(
        "GET",
        "/api/v1/projects/{project_id}/learning/pathology-stats",
        learning.PathologyStatsView,
        query=learning.PathologyStats,
        path_params=_PROJECT,
        query_params={"window": "window"},
        body="none",
        tags=_TAGS,
    ),
)
