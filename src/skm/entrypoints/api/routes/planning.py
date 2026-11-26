"""HTTP routes for the planning module."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.planning import public as planning

__all__ = ["ROUTES"]

_DRAFT = "/api/v1/plans/{plan_id}/drafts/{draft_id}"
_REVISION = "/api/v1/plans/{plan_id}/revisions/{revision_id}"
_PLAN = "/api/v1/plans/{plan_id}"
_PROJECT_PLANS = "/api/v1/projects/{project_id}/plans"
_DOCUMENT_LIMIT = "planning.drafts.max_document_bytes"


class _SaveDraftRoute(Route):
    """Each HTTP alias selects one of SaveDraft's three mutually exclusive inputs."""

    __slots__ = ()

    @override
    def _dto_body(self, body: Mapping[str, Any], schemas: Any) -> dict[str, Any]:
        fields = super()._dto_body(body, schemas)
        expected = {"PUT": "document", "PATCH": "merge_patch", "POST": "changes"}[self.method]
        if expected not in fields:
            raise error_for(ErrorCode.SCHEMA_INVALID, f"Expected {expected} on this draft route")
        return fields


class _QueryRoute(Route):
    """Decode structured GET parameters before the route validates the complete DTO."""

    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> Any:
        fields = dict(body)
        scalars = dict(query)
        for key, target in self.query_params.items():
            if key not in query:
                continue

            if key == "include":
                if scalars.pop(key) != "tree":
                    raise error_for(ErrorCode.SCHEMA_INVALID, "Expected include=tree")
                value = True
            elif target in {"kinds", "assume_done", "assume_granted"}:
                raw = scalars.pop(key)
                getlist = getattr(query, "getlist", None)
                values: list[str] = [raw] if getlist is None else getlist(key)
                value = [item for group in values for item in group.split(",")]
            else:
                continue
            if target in fields and fields[target] != value:
                raise error_for(ErrorCode.SCHEMA_INVALID, f"Conflicting values for {target}")
            fields[target] = value
        return super().bind(fields, path, scalars, **kwargs)


ROUTES: tuple[Route, ...] = (
    Route(
        "GET",
        "/api/v1/plans/resolve",
        planning.PlanRefView,
        query=planning.ResolvePlanRef,
        query_params={"project_id": "project_id", "ref": "ref", "follow_supersedes": "follow_supersedes"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "GET",
        _PROJECT_PLANS,
        planning.PlansView,
        query=planning.ListPlans,
        path_params={"project_id": "project_id"},
        query_params={"state": "state", "purpose": "purpose", "after": "after", "limit": "limit"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "POST",
        _PROJECT_PLANS,
        planning.CreatePlanResult,
        command=planning.CreatePlan,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        etag_from="row_version",
        tags=("planning",),
    ),
    Route(
        "GET",
        _PLAN,
        planning.PlanView,
        query=planning.GetPlan,
        path_params={"plan_id": "plan_id"},
        body="none",
        etag_from="row_version",
        tags=("planning",),
    ),
    Route(
        "POST",
        _PLAN + "/design-briefs",
        planning.DesignPlanResult,
        command=planning.DesignPlan,
        path_params={"plan_id": "plan_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("planning",),
    ),
    Route(
        "POST",
        _PLAN + "/archive",
        planning.ArchivePlanResult,
        command=planning.ArchivePlan,
        path_params={"plan_id": "plan_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="row_version",
        if_match_to="expected_row_version",
        tags=("planning",),
    ),
    Route(
        "GET",
        _PLAN + "/drafts",
        planning.ListDraftsResult,
        query=planning.ListDrafts,
        path_params={"plan_id": "plan_id"},
        query_params={"state": "state"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "POST",
        _PLAN + "/drafts",
        planning.OpenDraftResult,
        command=planning.OpenDraft,
        path_params={"plan_id": "plan_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        etag_from="edit_version",
        tags=("planning",),
    ),
    Route(
        "GET",
        _DRAFT,
        planning.DraftView,
        query=planning.GetDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        body="none",
        etag_from="edit_version",
        tags=("planning",),
    ),
    _SaveDraftRoute(
        "PATCH",
        _DRAFT,
        planning.SaveDraftResult,
        command=planning.SaveDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        body="merge_patch",
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="edit_version",
        if_match_to="expected_edit_version",
        body_limit_key=_DOCUMENT_LIMIT,
        tags=("planning",),
    ),
    _SaveDraftRoute(
        "PUT",
        _DRAFT,
        planning.SaveDraftResult,
        command=planning.SaveDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="edit_version",
        if_match_to="expected_edit_version",
        body_limit_key=_DOCUMENT_LIMIT,
        operation_id="planning_save_draft_document",
        tags=("planning",),
    ),
    _SaveDraftRoute(
        "POST",
        _DRAFT + "/changes",
        planning.SaveDraftResult,
        command=planning.SaveDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="edit_version",
        if_match_to="expected_edit_version",
        body_limit_key=_DOCUMENT_LIMIT,
        operation_id="planning_save_draft_changes",
        tags=("planning",),
    ),
    Route(
        "POST",
        _DRAFT + "/validate",
        planning.ValidationReportView,
        query=planning.ValidateDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        body_limit_key=_DOCUMENT_LIMIT,
        tags=("planning",),
    ),
    Route(
        "POST",
        _DRAFT + "/publication-preview",
        planning.PublicationPreviewView,
        query=planning.PreviewPublication,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        tags=("planning",),
    ),
    Route(
        "POST",
        _DRAFT + "/publish",
        planning.PublishRevisionResult,
        command=planning.PublishRevision,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        etag_from="content_digest",
        if_match_to="expected_edit_version",
        tags=("planning",),
    ),
    Route(
        "POST",
        _DRAFT + "/rebase",
        planning.RebaseDraftResult,
        command=planning.RebaseDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        idempotency=IdempotencyMode.REQUIRED,
        etag_from="edit_version",
        if_match_to="expected_edit_version",
        tags=("planning",),
    ),
    Route(
        "POST",
        _DRAFT + "/abandon",
        planning.AbandonDraftResult,
        command=planning.AbandonDraft,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_edit_version",
        tags=("planning",),
    ),
    Route(
        "POST",
        _PLAN + "/restore",
        planning.RestoreRevisionResult,
        command=planning.RestoreRevision,
        path_params={"plan_id": "plan_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        etag_from="content_digest",
        tags=("planning",),
    ),
    Route(
        "GET",
        _PLAN + "/revisions",
        planning.RevisionsView,
        query=planning.ListRevisions,
        path_params={"plan_id": "plan_id"},
        query_params={"before": "before", "limit": "limit"},
        body="none",
        tags=("planning",),
    ),
    _QueryRoute(
        "GET",
        _REVISION,
        planning.RevisionView,
        query=planning.GetRevision,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        query_params={
            "include_document": "include_document",
            "include_tree": "include_tree",
            "include": "include_tree",
        },
        body="none",
        etag_from="content_digest",
        tags=("planning",),
    ),
    Route(
        "GET",
        _REVISION + "/diff",
        planning.SpecDiffView,
        query=planning.DiffRevisions,
        path_params={"plan_id": "plan_id", "revision_id": "to_revision_id"},
        query_params={"against": "from_revision_id"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "GET",
        _DRAFT + "/diff",
        planning.SpecDiffView,
        query=planning.DiffRevisions,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        query_params={"against": "from_revision_id", "expected_edit_version": "expected_edit_version"},
        body="none",
        operation_id="planning_diff_revisions_draft",
        tags=("planning",),
    ),
    Route(
        "GET",
        _REVISION + "/entities/{ref}",
        planning.EntityView,
        query=planning.GetEntity,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id", "ref": "ref"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "GET",
        _DRAFT + "/entities/{ref}",
        planning.EntityView,
        query=planning.GetEntity,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id", "ref": "ref"},
        query_params={"expected_edit_version": "expected_edit_version"},
        body="none",
        operation_id="planning_get_entity_draft",
        tags=("planning",),
    ),
    _QueryRoute(
        "GET",
        _PLAN + "/entities",
        planning.EntityPageView,
        query=planning.ListEntities,
        path_params={"plan_id": "plan_id"},
        query_params={
            "revision_id": "revision_id",
            "draft_id": "draft_id",
            "expected_edit_version": "expected_edit_version",
            "kinds": "kinds",
            "after": "after",
            "limit": "limit",
        },
        body="none",
        tags=("planning",),
    ),
    Route(
        "GET",
        _PLAN + "/text",
        planning.TextFragmentView,
        query=planning.ReadText,
        path_params={"plan_id": "plan_id"},
        query_params={
            "revision_id": "revision_id",
            "draft_id": "draft_id",
            "expected_edit_version": "expected_edit_version",
            "target": "target",
            "pointer": "pointer",
            "offset_bytes": "offset_bytes",
            "max_bytes": "max_bytes",
        },
        body="none",
        tags=("planning",),
    ),
    _QueryRoute(
        "GET",
        _REVISION + "/ready-preview",
        planning.ReadyPreviewView,
        query=planning.ReadyPreview,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        query_params={"assume_done": "assume_done", "assume_granted": "assume_granted", "limit": "limit"},
        body="none",
        tags=("planning",),
    ),
    _QueryRoute(
        "GET",
        _DRAFT + "/ready-preview",
        planning.ReadyPreviewView,
        query=planning.ReadyPreview,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        query_params={
            "expected_edit_version": "expected_edit_version",
            "assume_done": "assume_done",
            "assume_granted": "assume_granted",
            "limit": "limit",
        },
        body="none",
        operation_id="planning_ready_preview_draft",
        tags=("planning",),
    ),
    Route(
        "GET",
        _REVISION + "/simulate",
        planning.SimulationView,
        query=planning.Simulate,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        query_params={"tokens_per_second": "tokens_per_second"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "GET",
        _DRAFT + "/simulate",
        planning.SimulationView,
        query=planning.Simulate,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        query_params={
            "expected_edit_version": "expected_edit_version",
            "tokens_per_second": "tokens_per_second",
        },
        body="none",
        operation_id="planning_simulate_draft",
        tags=("planning",),
    ),
    Route(
        "GET",
        _REVISION + "/stats",
        planning.PlanStatsView,
        query=planning.PlanStats,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "GET",
        _DRAFT + "/stats",
        planning.PlanStatsView,
        query=planning.PlanStats,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        query_params={"expected_edit_version": "expected_edit_version"},
        body="none",
        operation_id="planning_plan_stats_draft",
        tags=("planning",),
    ),
    Route(
        "GET",
        _DRAFT + "/export",
        planning.SpecificationExportView,
        query=planning.ExportSpecification,
        path_params={"plan_id": "plan_id", "draft_id": "draft_id"},
        query_params={"expected_edit_version": "expected_edit_version"},
        body="none",
        operation_id="planning_export_specification_draft",
        tags=("planning",),
    ),
    Route(
        "GET",
        _REVISION + "/export",
        planning.SpecificationExportView,
        query=planning.ExportSpecification,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        body="none",
        tags=("planning",),
    ),
    Route(
        "POST",
        _PROJECT_PLANS + "/import",
        planning.ImportSpecificationResult,
        command=planning.ImportSpecification,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        body_limit_key=_DOCUMENT_LIMIT,
        tags=("planning",),
    ),
)
