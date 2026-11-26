"""Artifacts HTTP declarations (API §3)."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.artifacts import public as artifacts

__all__ = ["ROUTES"]


class _WorkspaceFileRoute(Route):
    __slots__ = ()

    @override
    def _dto_body(self, body: Mapping[str, Any], schemas: Any) -> dict[str, Any]:
        if body.get("project_id") is not None:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Workspace files require project_id=null")
        return super()._dto_body(body, schemas)


ROUTES = (
    Route(
        "GET",
        "/api/v1/files",
        artifacts.ListFilesView,
        query=artifacts.ListFiles,
        query_params={
            "workspace_id": "workspace_id",
            "project_id": "project_id",
            "state": "state",
            "origin": "origin",
            "after": "after",
            "limit": "limit",
        },
        body="none",
        tags=("artifacts",),
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/files",
        artifacts.AddFileResult,
        command=artifacts.AddFile,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        operation_id="artifacts_add_project_file",
        tags=("artifacts",),
    ),
    _WorkspaceFileRoute(
        "POST",
        "/api/v1/workspaces/{workspace_id}/files",
        artifacts.AddFileResult,
        command=artifacts.AddFile,
        path_params={"workspace_id": "workspace_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        operation_id="artifacts_add_workspace_file",
        tags=("artifacts",),
    ),
    Route(
        "GET",
        "/api/v1/files/{file_id}",
        artifacts.GetFileView,
        query=artifacts.GetFile,
        path_params={"file_id": "file_id"},
        body="none",
        etag_from="row_version",
        tags=("artifacts",),
    ),
    Route(
        "POST",
        "/api/v1/files/{file_id}/versions",
        artifacts.AddFileVersionResult,
        command=artifacts.AddFileVersion,
        path_params={"file_id": "file_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        tags=("artifacts",),
    ),
    Route(
        "GET",
        "/api/v1/files/{file_id}/versions",
        artifacts.ListFileVersionsView,
        query=artifacts.ListFileVersions,
        path_params={"file_id": "file_id"},
        query_params={"after": "after", "limit": "limit"},
        body="none",
        tags=("artifacts",),
    ),
    Route(
        "GET",
        "/api/v1/file-versions/{file_version_id}",
        artifacts.GetFileVersionView,
        query=artifacts.GetFileVersion,
        path_params={"file_version_id": "file_version_id"},
        body="none",
        tags=("artifacts",),
    ),
    Route(
        "POST",
        "/api/v1/files/{file_id}/trash",
        artifacts.TrashFileResult,
        command=artifacts.TrashFile,
        path_params={"file_id": "file_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        etag_from="row_version",
        tags=("artifacts",),
    ),
    Route(
        "POST",
        "/api/v1/files/{file_id}/restore",
        artifacts.RestoreFileResult,
        command=artifacts.RestoreFile,
        path_params={"file_id": "file_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        etag_from="row_version",
        tags=("artifacts",),
    ),
    Route(
        "GET",
        "/api/v1/admin/orphan-blobs",
        artifacts.FindOrphanBlobsView,
        query=artifacts.FindOrphanBlobs,
        query_params={"workspace_id": "workspace_id", "backend_id": "backend_id"},
        body="none",
        tags=("artifacts",),
    ),
    Route(
        "POST",
        "/api/v1/admin/orphan-blobs/prune",
        artifacts.PruneOrphanObjectsResult,
        command=artifacts.PruneOrphanObjects,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("artifacts",),
    ),
)
