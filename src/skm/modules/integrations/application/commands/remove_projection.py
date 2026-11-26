"""Handler for ``integrations.remove_projection`` (integrations §7.6)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.modules.integrations.application.projection_views import (
    project_scope,
    require_safe_relative_path,
)
from skm.modules.integrations.domain.events import ProjectionRemoved
from skm.modules.integrations.domain.projection import (
    ProjectionId,
    ProjectionState,
    can_transition_projection,
)
from skm.modules.integrations.generated.commands import RemoveProjection
from skm.modules.integrations.generated.results import RemoveProjectionResult
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(cmd: RemoveProjection, _ctx: CommandContext, uow: UnitOfWork) -> RemoveProjectionResult:
    project_id = ProjectId(cmd.project_id)
    projection_id = ProjectionId(cmd.projection_id)

    removed_set = {require_safe_relative_path(p, field="removed") for p in cmd.removed}
    left_set = {require_safe_relative_path(p, field="left_modified") for p in cmd.left_modified}
    for item in cmd.failed:
        require_safe_relative_path(item.relative_path, field="failed.relative_path")
    if removed_set & left_set:
        overlap_paths: list[JsonValue] = [*sorted(removed_set & left_set)]
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "removed and left_modified sets must be disjoint",
            details={"paths": overlap_paths},
        )

    workspace.require_active_project(uow, project_id)

    repo = uow.repo(ProjectionRepository)
    projection = repo.get(projection_id)
    if projection.project_id != project_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "projection not found",
            details={"kind": "projection", "ref": str(projection_id)},
        )

    if projection.state is ProjectionState.REMOVED:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "projection is already removed",
            details={"projection_id": str(projection_id), "state": projection.state.value},
        )

    if cmd.base_row_version != projection.row_version:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "projection base_row_version mismatch",
            details={"expected": projection.row_version, "actual": cmd.base_row_version},
        )

    next_state = ProjectionState.FAILED if cmd.failed else ProjectionState.REMOVED
    if not can_transition_projection(projection.state, next_state):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            f"cannot transition projection from {projection.state.value} to {next_state.value}",
            details={"from": projection.state.value, "to": next_state.value},
        )

    to_delete = removed_set | left_set
    existing_files = repo.files(projection.id)
    remaining_files = tuple(rec for rec in existing_files if rec.relative_path not in to_delete)
    repo.replace_files(projection.id, remaining_files)

    updated = replace(
        projection,
        state=next_state,
        row_version=projection.row_version + 1,
    )
    repo.save(updated, expected_version=projection.row_version)

    uow.record(
        ProjectionRemoved(
            projection_id=projection.id,
            workspace_id=projection.workspace_id,
            removed=cmd.removed,
            left_modified=cmd.left_modified,
        )
    )
    return RemoveProjectionResult(
        projection_id=UUID(str(projection.id)),
        state=cast("Any", next_state.value),
    )


SPEC = CommandSpec(
    name="integrations.remove_projection",
    dto=RemoveProjection,
    result=RemoveProjectionResult,
    permission="integration.apply",
    scope_of=project_scope,
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
