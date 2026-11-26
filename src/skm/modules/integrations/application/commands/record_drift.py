"""Handler for ``integrations.record_drift`` (integrations §7.5)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.kernel.ids import ProjectId
from skm.modules.integrations.application.projection_views import (
    project_scope,
    require_safe_relative_path,
    require_tagged_digest,
    resolve_project_binding_host,
)
from skm.modules.integrations.domain.decisions import FileDecisionKind
from skm.modules.integrations.domain.events import DriftedProjectionFile, ProjectionDriftDetected
from skm.modules.integrations.domain.projection import ProjectionState, can_transition_projection
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.commands import RecordDrift
from skm.modules.integrations.generated.results import RecordDriftResult
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.workspace import public as workspace
from skm.modules.workspace.public import CheckoutBindingId

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(cmd: RecordDrift, ctx: CommandContext, uow: UnitOfWork) -> RecordDriftResult:
    project_id = ProjectId(cmd.project_id)
    checkout_binding_id = CheckoutBindingId(cmd.checkout_binding_id)
    target = TargetId(cmd.target)
    now = ctx.clock.now()

    require_tagged_digest(cmd.desired_digest, field="desired_digest")
    for item in cmd.files:
        require_safe_relative_path(item.relative_path, field="files.relative_path")

    workspace.require_active_project(uow, project_id)
    workspace_id, _host_id = resolve_project_binding_host(uow, project_id, checkout_binding_id, now=now)

    repo = uow.repo(ProjectionRepository)
    projection = repo.find(project_id, checkout_binding_id, target)
    if projection is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "projection not found",
            details={
                "kind": "projection",
                "project_id": str(project_id),
                "checkout_binding_id": str(checkout_binding_id),
            },
        )
    if cmd.base_row_version != projection.row_version:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "projection base_row_version mismatch",
            details={"expected": projection.row_version, "actual": cmd.base_row_version},
        )

    has_drift = len(cmd.files) > 0
    if has_drift:
        next_state = ProjectionState.DRIFTED
    elif (
        projection.applied_desired_digest is not None
        and cmd.desired_digest == projection.applied_desired_digest
    ):
        next_state = ProjectionState.IN_SYNC
    else:
        next_state = ProjectionState.PENDING

    if not can_transition_projection(projection.state, next_state):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            f"cannot transition projection from {projection.state.value} to {next_state.value}",
            details={"from": projection.state.value, "to": next_state.value},
        )

    updated = replace(
        projection,
        state=next_state,
        desired_digest=cmd.desired_digest,
        drift_checked_at=now,
        row_version=projection.row_version + 1,
    )
    repo.save(updated, expected_version=projection.row_version)

    if has_drift:
        uow.record(
            ProjectionDriftDetected(
                projection_id=projection.id,
                workspace_id=workspace_id,
                files=tuple(
                    DriftedProjectionFile(
                        path=item.relative_path,
                        decision=FileDecisionKind(item.decision),
                    )
                    for item in cmd.files
                ),
            )
        )

    return RecordDriftResult(
        projection_id=UUID(str(projection.id)),
        state=cast("Any", next_state.value),
        drifted=len(cmd.files),
    )


SPEC = CommandSpec(
    name="integrations.record_drift",
    dto=RecordDrift,
    result=RecordDriftResult,
    permission="integration.read",
    scope_of=project_scope,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
