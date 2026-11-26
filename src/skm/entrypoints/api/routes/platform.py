"""HTTP routes for platform."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.platform.generated.commands import RepairStorageSafe, RetryOutbox
from skm.platform.generated.queries import Doctor, ListDeadOutbox, MigrationStatus, VerifyStorage
from skm.platform.generated.results import (
    DoctorResult,
    ListDeadOutboxResult,
    MigrationStatusResult,
    RepairStorageSafeResult,
    RetryOutboxResult,
    VerifyStorageResult,
)

__all__ = ["ROUTES"]


class _ListQueryRoute(Route):
    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> Any:
        params = dict(query)
        fields = dict(body)
        for key, field in self.query_params.items():
            if key not in params:
                continue
            raw = params.pop(key)
            getlist = getattr(query, "getlist", None)
            groups: list[str] = [raw] if getlist is None else getlist(key)
            values = [value for group in groups for value in group.split(",")]
            if field in fields and fields[field] != values:
                raise error_for(ErrorCode.SCHEMA_INVALID, f"Conflicting {key}")
            fields[field] = values
        return super().bind(fields, path, params, **kwargs)


ROUTES: tuple[Route, ...] = (
    _ListQueryRoute(
        "GET",
        "/api/v1/doctor",
        DoctorResult,
        query=Doctor,
        query_params={"only": "only"},
        operation_id="platform_doctor",
        body="none",
        tags=("platform",),
    ),
    Route(
        "GET",
        "/health/details",
        DoctorResult,
        query=Doctor,
        operation_id="platform_health_details",
        body="none",
        tags=("platform",),
    ),
    Route(
        "GET",
        "/api/v1/admin/migrations",
        MigrationStatusResult,
        query=MigrationStatus,
        body="none",
        tags=("platform",),
    ),
    _ListQueryRoute(
        "GET",
        "/api/v1/admin/storage/verify",
        VerifyStorageResult,
        query=VerifyStorage,
        query_params={"level": "levels"},
        body="none",
        tags=("platform",),
    ),
    Route(
        "POST",
        "/api/v1/admin/storage/repair",
        RepairStorageSafeResult,
        command=RepairStorageSafe,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("platform",),
    ),
    Route(
        "GET",
        "/api/v1/admin/outbox/dead",
        ListDeadOutboxResult,
        query=ListDeadOutbox,
        query_params={"after": "after", "limit": "limit"},
        body="none",
        tags=("platform",),
    ),
    Route(
        "POST",
        "/api/v1/admin/outbox/{outbox_id}/retry",
        RetryOutboxResult,
        command=RetryOutbox,
        path_params={"outbox_id": "outbox_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("platform",),
    ),
)
