"""Wire declarations for the worker claim protocol."""

from collections.abc import Mapping
from typing import Any, override
from uuid import UUID

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.context import public as context
from skm.modules.execution import public as execution
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace

__all__ = ["ROUTES"]

_ASSIGNMENT = "/api/v1/worker/assignments/{assignment_id}"
_CLAIM_PATH = {"assignment_id": "claim.assignment_id"}
_SLOTS = "/api/v1/worker/integration-slots"


class _StepNoteRoute(Route):
    __slots__ = ()

    @override
    def bind(
        self,
        body: Mapping[str, Any],
        path: Mapping[str, str],
        query: Mapping[str, str],
        *,
        actor: Actor | None = None,
        **kwargs: Any,
    ) -> execution.RecordStepNote:
        dto = super().bind(body, path, query, actor=actor, **kwargs)
        grant = actor.grant if actor is not None else None
        if grant is not None and grant.kind == "assignment" and grant.step_id != UUID(dto["step_id"]):
            raise error_for(ErrorCode.NOT_FOUND, "Step not found")
        return dto


ROUTES = (
    Route(
        "GET",
        "/api/v1/worker/hosts/{host_id}/config",
        settings.GetHostConfigResult,
        query=settings.GetHostConfig,
        path_params={"host_id": "host_id"},
        body="none",
        tags=("worker",),
    ),
    Route(
        "POST",
        "/api/v1/worker/heartbeat",
        workspace.RecordWorkerHeartbeatResult,
        command=workspace.RecordWorkerHeartbeat,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("worker",),
    ),
    Route(
        "POST",
        "/api/v1/worker/assignments/claim",
        execution.ClaimAssignmentResult,
        command=execution.ClaimAssignment,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/heartbeat",
        execution.RenewLeaseResult,
        command=execution.RenewLease,
        path_params=_CLAIM_PATH,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/stages",
        execution.BeginStageResult,
        command=execution.BeginStage,
        path_params=_CLAIM_PATH,
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        "/api/v1/context-manifests/{manifest_id}/finalize",
        context.FinalizeManifestResult,
        command=context.FinalizeManifest,
        path_params={"manifest_id": "manifest_id"},
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/outputs",
        execution.SealOutputResult,
        command=execution.SealOutput,
        path_params=_CLAIM_PATH,
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/stages/{stage_record_id}/result",
        execution.RecordStageResultResult,
        command=execution.RecordStageResult,
        path_params={**_CLAIM_PATH, "stage_record_id": "stage_record_id"},
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    _StepNoteRoute(
        "POST",
        "/api/v1/runs/{run_id}/steps/{step_id}/notes",
        execution.RecordStepNoteResult,
        command=execution.RecordStepNote,
        path_params={"step_id": "step_id"},
        path_guards={"run_id": "actor.grant.scope_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/release",
        execution.ReleaseAssignmentResult,
        command=execution.ReleaseAssignment,
        path_params=_CLAIM_PATH,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/failure",
        execution.ReportAttemptFailureResult,
        command=execution.ReportAttemptFailure,
        path_params=_CLAIM_PATH,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _SLOTS,
        execution.AcquireIntegrationSlotResult,
        command=execution.AcquireIntegrationSlot,
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "DELETE",
        _SLOTS + "/{slot_id}",
        execution.ReleaseIntegrationSlotResult,
        command=execution.ReleaseIntegrationSlot,
        path_params={"slot_id": "slot_id"},
        body="json",
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
    Route(
        "POST",
        _ASSIGNMENT + "/external-effects",
        execution.RecordExternalEffectResult,
        command=execution.RecordExternalEffect,
        path_params=_CLAIM_PATH,
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("worker",),
    ),
)
