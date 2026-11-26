"""HTTP routes for integrations."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.integrations.public import (
    AppliedStateView,
    DesiredProjectionView,
    GetAppliedState,
    GetDesiredProjection,
    GetHookPolicy,
    HookDeliveriesView,
    HookPolicyView,
    ListHookDeliveries,
    ListHookSubscriptions,
    ListHookSubscriptionsResult,
    ListProjections,
    ProjectionsView,
    RecordDrift,
    RecordDriftResult,
    RecordProjectionApplied,
    RecordProjectionAppliedResult,
    RemoveProjection,
    RemoveProjectionResult,
    RetryHookDeliveries,
    RetryHookDeliveriesResult,
    TestHookSubscription,
    TestHookSubscriptionResult,
)
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["ROUTES"]


class _CreateProjectionRoute(Route):
    """Create a projection without a prior version."""

    __slots__ = ()

    @override
    def requires_if_match(self, schemas: SchemaRegistry) -> bool:
        return False

    @override
    def bind(
        self,
        body: Mapping[str, Any],
        path: Mapping[str, str],
        query: Mapping[str, str],
        *,
        version: int | None = None,
        **kwargs: Any,
    ) -> RecordProjectionApplied:
        if version is not None or body.get("base_row_version") is not None:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Creating a projection does not accept a version")
        return super().bind({"base_row_version": None, **body}, path, query, **kwargs)


class _TestSubscriptionRoute(Route):
    __slots__ = ()

    @override
    def _dto_body(self, body: Mapping[str, Any], schemas: SchemaRegistry) -> dict[str, Any]:
        return {"project_id": None, **body}


ROUTES: tuple[Route, ...] = (
    Route(
        "GET",
        "/api/v1/projects/{project_id}/integrations/desired-projection",
        DesiredProjectionView,
        query=GetDesiredProjection,
        path_params={"project_id": "project_id"},
        query_params={"checkout_binding_id": "checkout_binding_id", "target": "target"},
        body="none",
        tags=("integrations",),
    ),
    Route(
        "GET",
        "/api/v1/projects/{project_id}/projections",
        ProjectionsView,
        query=ListProjections,
        path_params={"project_id": "project_id"},
        query_params={"after": "after", "limit": "limit"},
        body="none",
        tags=("integrations",),
    ),
    Route(
        "GET",
        "/api/v1/projects/{project_id}/projections/applied",
        AppliedStateView,
        query=GetAppliedState,
        path_params={"project_id": "project_id"},
        query_params={"checkout_binding_id": "checkout_binding_id", "target": "target"},
        body="none",
        tags=("integrations",),
    ),
    _CreateProjectionRoute(
        "POST",
        "/api/v1/projects/{project_id}/projections",
        RecordProjectionAppliedResult,
        command=RecordProjectionApplied,
        path_params={"project_id": "project_id"},
        success_status=201,
        etag_from="row_version",
        if_match_to="base_row_version",
        operation_id="integrations_create_projection",
        idempotency=IdempotencyMode.REQUIRED,
        tags=("integrations",),
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/projections/applied",
        RecordProjectionAppliedResult,
        command=RecordProjectionApplied,
        path_params={"project_id": "project_id"},
        etag_from="row_version",
        if_match_to="base_row_version",
        idempotency=IdempotencyMode.REQUIRED,
        tags=("integrations",),
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/projections/drift",
        RecordDriftResult,
        command=RecordDrift,
        path_params={"project_id": "project_id"},
        if_match_to="base_row_version",
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("integrations",),
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/projections/{projection_id}/removal",
        RemoveProjectionResult,
        command=RemoveProjection,
        path_params={"project_id": "project_id", "projection_id": "projection_id"},
        if_match_to="base_row_version",
        idempotency=IdempotencyMode.REQUIRED,
        tags=("integrations",),
    ),
    Route(
        "GET",
        "/api/v1/projects/{project_id}/integrations/hook-policy",
        HookPolicyView,
        query=GetHookPolicy,
        path_params={"project_id": "project_id"},
        query_params={"target": "target"},
        body="none",
        tags=("integrations",),
    ),
    Route(
        "GET",
        "/api/v1/workspaces/{workspace_id}/hook-subscriptions",
        ListHookSubscriptionsResult,
        query=ListHookSubscriptions,
        path_params={"workspace_id": "workspace_id"},
        query_params={"project_id": "project_id"},
        body="none",
        tags=("integrations",),
    ),
    _TestSubscriptionRoute(
        "POST",
        "/api/v1/workspaces/{workspace_id}/hook-subscriptions/{subscription_id}/test",
        TestHookSubscriptionResult,
        command=TestHookSubscription,
        path_params={"workspace_id": "workspace_id", "subscription_id": "subscription_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("integrations",),
    ),
    Route(
        "GET",
        "/api/v1/workspaces/{workspace_id}/hook-deliveries",
        HookDeliveriesView,
        query=ListHookDeliveries,
        path_params={"workspace_id": "workspace_id"},
        query_params={
            "subscription_id": "subscription_id",
            "state": "state",
            "after": "after",
            "limit": "limit",
        },
        body="none",
        tags=("integrations",),
    ),
    Route(
        "POST",
        "/api/v1/workspaces/{workspace_id}/hook-deliveries/retry",
        RetryHookDeliveriesResult,
        command=RetryHookDeliveries,
        path_params={"workspace_id": "workspace_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("integrations",),
    ),
)
