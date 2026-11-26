"""HTTP routes for the context module."""

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.modules.context import public as context

__all__ = ["ROUTES"]

_PROJECT = "/api/v1/projects/{project_id}"


ROUTES: tuple[Route, ...] = (
    Route(
        "POST",
        _PROJECT + "/context-manifests",
        context.AssembleContextResult,
        command=context.AssembleContext,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("context",),
    ),
    Route(
        "GET",
        "/api/v1/steps/{step_id}/context",
        context.ContextExplainResponse,
        query=context.ExplainContextRequest,
        path_params={"step_id": "step_id"},
        query_params={"project_id": "project_id"},
        body="none",
        tags=("context",),
        operation_id="context_explain_step_context",
    ),
    Route(
        "GET",
        _PROJECT + "/steps/{step_id}/context/diff",
        context.ContextDiffResponse,
        query=context.DiffContextsRequest,
        path_params={"project_id": "project_id", "step_id": "step_id"},
        query_params={"base_manifest_id": "base_manifest_id"},
        body="none",
        tags=("context",),
        operation_id="context_diff_step_context",
    ),
    Route(
        "GET",
        _PROJECT + "/context-manifests/{target_manifest_id}/diff",
        context.ContextDiffResponse,
        query=context.DiffContextsRequest,
        path_params={"project_id": "project_id", "target_manifest_id": "target_manifest_id"},
        query_params={"base_manifest_id": "base_manifest_id"},
        body="none",
        tags=("context",),
    ),
    Route(
        "GET",
        _PROJECT + "/context-manifests/{manifest_id}",
        context.ContextExplainResponse,
        query=context.ExplainContextRequest,
        path_params={"project_id": "project_id", "manifest_id": "manifest_id"},
        body="none",
        tags=("context",),
    ),
    Route(
        "GET",
        _PROJECT + "/research-access",
        context.ResearchAccessView,
        query=context.CheckResearchAccess,
        path_params={"project_id": "project_id"},
        body="none",
        tags=("context",),
    ),
    Route(
        "GET",
        _PROJECT + "/research-queries",
        context.ResearchCacheView,
        query=context.FindResearchCache,
        path_params={"project_id": "project_id"},
        query_params={
            "source_id": "source_id",
            "cache_key": "cache_key",
            "max_classification": "max_classification",
        },
        body="none",
        tags=("context",),
    ),
    Route(
        "GET",
        _PROJECT + "/context-manifests/{manifest_id}/text",
        context.ContextTextResponse,
        query=context.GetContextTextRequest,
        path_params={"project_id": "project_id", "manifest_id": "manifest_id"},
        query_params={"position": "position"},
        body="none",
        tags=("context",),
    ),
    Route(
        "GET",
        _PROJECT + "/research-queries/{query_id}",
        context.ResearchResultView,
        query=context.GetResearchQuery,
        path_params={"project_id": "project_id", "query_id": "query_id"},
        body="none",
        tags=("context",),
    ),
    Route(
        "GET",
        _PROJECT + "/external-sources",
        context.ExternalSourcesView,
        query=context.ListExternalSources,
        path_params={"project_id": "project_id"},
        query_params={
            "query_id": "query_id",
            "origin_prefix": "origin_prefix",
            "after": "after",
            "limit": "limit",
        },
        body="none",
        tags=("context",),
    ),
    Route(
        "POST",
        _PROJECT + "/research-queries",
        context.RecordResearchResultResult,
        command=context.RecordResearchResult,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("context",),
    ),
)
