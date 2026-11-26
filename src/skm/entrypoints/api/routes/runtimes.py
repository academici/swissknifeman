"""HTTP routes for runtimes."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.runtimes.public import (
    ExplainRouting,
    GetCapabilities,
    ListModels,
    ListRuntimes,
    ListRuntimesResult,
    ModelsView,
    RecordCapabilityVerification,
    RecordCapabilityVerificationResult,
    RecordHostRuntimes,
    RecordHostRuntimesResult,
    RouteExplainView,
    RuntimeCapabilitiesView,
)

__all__ = ["ROUTES"]


class _RoutingRoute(Route):
    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> ExplainRouting:
        params = dict(query)
        fields = dict(body)
        if "required_capabilities" in params:
            raw = params.pop("required_capabilities")
            getlist = getattr(query, "getlist", None)
            groups: list[str] = [raw] if getlist is None else getlist("required_capabilities")
            values = [value for group in groups for value in group.split(",")]
            if "required_capabilities" in fields and fields["required_capabilities"] != values:
                raise error_for(ErrorCode.SCHEMA_INVALID, "Conflicting required_capabilities")
            fields["required_capabilities"] = values
        return super().bind(fields, path, params, **kwargs)


ROUTES: tuple[Route, ...] = (
    Route(
        "GET",
        "/api/v1/runtimes",
        ListRuntimesResult,
        query=ListRuntimes,
        query_params={"host_id": "host_id"},
        body="none",
        tags=("runtimes",),
    ),
    Route(
        "GET",
        "/api/v1/runtimes/{runtime_id}/capabilities",
        RuntimeCapabilitiesView,
        query=GetCapabilities,
        path_params={"runtime_id": "runtime_id"},
        query_params={"runtime_version": "runtime_version"},
        body="none",
        tags=("runtimes",),
    ),
    Route(
        "GET",
        "/api/v1/runtimes/models",
        ModelsView,
        query=ListModels,
        query_params={
            "runtime_id": "runtime_id",
            "model_class": "model_class",
            "prepare_for": "prepare_for",
            "host_id": "host_id",
        },
        body="none",
        tags=("runtimes",),
    ),
    _RoutingRoute(
        "GET",
        "/api/v1/runtimes/routing",
        RouteExplainView,
        query=ExplainRouting,
        query_params={
            "role": "role",
            "scope": "scope",
            "host_id": "host_id",
            "operation": "operation",
            "profile_key": "profile_key",
            "model_class": "model_class",
            "effort": "effort",
            "explicit_runtime": "explicit_runtime",
            "explicit_model": "explicit_model",
            "required_capabilities": "required_capabilities",
            "task_min_class": "task_min_class",
        },
        body="none",
        tags=("runtimes",),
    ),
    Route(
        "POST",
        "/api/v1/hosts/{host_id}/runtimes",
        RecordHostRuntimesResult,
        command=RecordHostRuntimes,
        path_params={"host_id": "host_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("runtimes",),
    ),
    Route(
        "POST",
        "/api/v1/runtimes/{runtime_id}/capability-verifications",
        RecordCapabilityVerificationResult,
        command=RecordCapabilityVerification,
        path_params={"runtime_id": "runtime_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("runtimes",),
    ),
)
