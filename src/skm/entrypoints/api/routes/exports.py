"""HTTP routes for Markdown projections and vault delivery."""

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.ids import HostId
from skm.kernel.ports_uow import RequestMeta
from skm.modules.exports import public as exports

__all__ = ["ROUTES"]

_NOTES = "/api/v1/projects/{project_id}/vault-notes"
_NOTE = _NOTES + "/{note_id}"
_PROJECT = {"project_id": "project_id"}
_BY_NOTE = {**_PROJECT, "note_id": "note_id"}
_TAGS = ("exports",)


def _host_metadata(meta: RequestMeta, host_id: HostId) -> RequestMeta:
    return exports.VaultRequestMeta(
        meta.request_id,
        meta.surface,
        meta.idempotency_key,
        meta.received_at,
        client=meta.client,
        host_id=host_id,
    )


ROUTES = (
    Route(
        "GET",
        "/api/v1/plans/{plan_id}/export.md",
        exports.PlanMarkdownView,
        query=exports.RenderPlanMarkdown,
        etag_from="digest",
        path_params={"plan_id": "plan_id"},
        query_params={"revision_no": "revision_no"},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        "/api/v1/runs/{run_id}/report.md",
        exports.RunReportView,
        query=exports.RenderRunReport,
        etag_from="digest",
        path_params={"run_id": "run_id"},
        query_params={"variant": "variant"},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        _NOTES,
        exports.VaultNotesView,
        query=exports.ListVaultNotes,
        path_params=_PROJECT,
        query_params={"after": "after", "limit": "limit"},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        "/api/v1/workspaces/{workspace_id}/vault-notes/pending",
        exports.PendingNotesView,
        query=exports.ListPendingNotes,
        path_params={"workspace_id": "workspace_id"},
        query_params={key: key for key in ("host_id", "vault_id", "after", "limit")},
        body="none",
        tags=_TAGS,
        host_metadata=_host_metadata,
    ),
    Route(
        "POST",
        _NOTE + "/writes",
        exports.RecordNoteWrittenResult,
        command=exports.RecordNoteWritten,
        path_params=_BY_NOTE,
        idempotency=IdempotencyMode.REQUIRED,
        success_status=201,
        tags=_TAGS,
        host_metadata=_host_metadata,
    ),
    Route(
        "POST",
        _NOTE + "/requeue",
        exports.RequeueNoteResult,
        command=exports.RequeueNote,
        path_params=_BY_NOTE,
        idempotency=IdempotencyMode.REQUIRED,
        tags=_TAGS,
    ),
)
