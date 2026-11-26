"""Settings HTTP declarations (API §3)."""

from collections.abc import Mapping
from typing import Any, override
from uuid import UUID

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.settings import public as settings

__all__ = ["ROUTES"]


class _ExplainRoute(Route):
    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> settings.ExplainConfig:
        detail = "value" if self.operation_id == "settings_get_effective_config" else "full"
        values = {**body, "detail": detail}
        params = dict(query)
        selector = "keys" if detail == "value" else "key"
        if selector in params:
            raw = params.pop(selector)
            values["keys"] = raw.split(",") if detail == "value" else [raw]
        return super().bind(values, path, params, **kwargs)


class _ProjectConfigRoute(Route):
    """Bind ``/api/v1/projects/{project_id}/config`` onto project-scoped settings DTOs."""

    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> Any:
        raw_id = path.get("project_id", "")
        try:
            project_id = str(UUID(raw_id))
        except ValueError:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid project_id") from None
        target_scope = {"level": "project", "scope_id": project_id}
        values = dict(body)
        if "scope" in values:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Project config scope comes from the path")
        values["scope"] = target_scope
        return super().bind(values, {}, query, **kwargs)


ROUTES = (
    Route(
        "GET",
        "/api/v1/config/schema",
        settings.GetSchemaView,
        query=settings.GetSchema,
        query_params={"section": "section", "scope": "scope"},
        body="none",
        etag_from="registry_digest",
        tags=("settings",),
    ),
    _ExplainRoute(
        "GET",
        "/api/v1/config/effective",
        settings.ExplainConfigResult,
        query=settings.ExplainConfig,
        query_params={
            "scope": "scope",
            "section": "section",
            "keys": "keys",
            "include_defaults_only": "include_defaults_only",
        },
        body="none",
        etag_from="digest",
        operation_id="settings_get_effective_config",
        tags=("settings",),
    ),
    _ExplainRoute(
        "GET",
        "/api/v1/config/explain",
        settings.ExplainConfigResult,
        query=settings.ExplainConfig,
        query_params={
            "scope": "scope",
            "section": "section",
            "key": "keys",
            "include_defaults_only": "include_defaults_only",
        },
        body="none",
        operation_id="settings_explain_config",
        tags=("settings",),
    ),
    Route(
        "GET",
        "/api/v1/config/entries",
        settings.ListEntriesView,
        query=settings.ListEntries,
        query_params={
            "scope": "scope",
            "level": "level",
            "key_prefix": "key_prefix",
            "after": "after",
            "limit": "limit",
        },
        body="none",
        tags=("settings",),
    ),
    Route(
        "GET",
        "/api/v1/config/entries/{scope}/{key}",
        settings.GetValueView,
        query=settings.GetValue,
        path_params={"scope": "scope", "key": "key"},
        body="none",
        tags=("settings",),
    ),
    Route(
        "PUT",
        "/api/v1/config/entries/{scope}/{key}",
        settings.SetValueResult,
        command=settings.SetValue,
        path_params={"scope": "scope", "key": "key"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        tags=("settings",),
    ),
    Route(
        "DELETE",
        "/api/v1/config/entries/{scope}/{key}",
        settings.RemoveValueResult,
        command=settings.RemoveValue,
        path_params={"scope": "scope", "key": "key"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        tags=("settings",),
    ),
    Route(
        "POST",
        "/api/v1/config/entries/{scope}/{key}/unset",
        settings.UnsetValueResult,
        command=settings.UnsetValue,
        path_params={"scope": "scope", "key": "key"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        tags=("settings",),
    ),
    Route(
        "POST",
        "/api/v1/config/entries/{scope}/{key}/lock",
        settings.LockValueResult,
        command=settings.LockValue,
        path_params={"scope": "scope", "key": "key"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        tags=("settings",),
    ),
    Route(
        "POST",
        "/api/v1/config/entries/{scope}/{key}/unlock",
        settings.UnlockValueResult,
        command=settings.UnlockValue,
        path_params={"scope": "scope", "key": "key"},
        idempotency=IdempotencyMode.OPTIONAL,
        if_match_to="expected_row_version",
        tags=("settings",),
    ),
    Route(
        "POST",
        "/api/v1/config/import",
        settings.ImportConfigResult,
        command=settings.ImportConfig,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("settings",),
    ),
    Route(
        "GET",
        "/api/v1/config/export",
        settings.ExportConfigView,
        query=settings.ExportConfig,
        query_params={"scope": "scope", "format": "format", "portable_only": "portable_only"},
        body="none",
        tags=("settings",),
    ),
    Route(
        "GET",
        "/api/v1/config/history",
        settings.GetHistoryView,
        query=settings.GetHistory,
        query_params={"scope": "scope", "key": "key", "after": "after", "limit": "limit"},
        body="none",
        tags=("settings",),
    ),
    Route(
        "GET",
        "/api/v1/config/generation",
        settings.GetGenerationResult,
        query=settings.GetGeneration,
        query_params={"scope": "scope"},
        body="none",
        tags=("settings",),
    ),
    _ProjectConfigRoute(
        "GET",
        "/api/v1/projects/{project_id}/config",
        settings.ExportConfigView,
        query=settings.ExportConfig,
        path_params={"project_id": "scope.scope_id"},
        query_params={"format": "format", "portable_only": "portable_only"},
        body="none",
        etag_from="digest",
        operation_id="settings_get_project_config",
        tags=("settings",),
    ),
    _ProjectConfigRoute(
        "PUT",
        "/api/v1/projects/{project_id}/config",
        settings.ImportConfigResult,
        command=settings.ImportConfig,
        path_params={"project_id": "scope.scope_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        operation_id="settings_put_project_config",
        tags=("settings",),
    ),
)
