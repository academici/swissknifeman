"""Handler for ``integrations.record_projection_applied`` (integrations §7.4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId, ProjectId
from skm.modules.artifacts import public as artifacts
from skm.modules.integrations.application.projection_views import (
    project_scope,
    require_safe_relative_path,
    require_tagged_digest,
    resolve_project_binding_host,
)
from skm.modules.integrations.domain.events import FailedProjectionFile, ProjectionApplied
from skm.modules.integrations.domain.merged_json import OwnedKeyPath
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership
from skm.modules.integrations.domain.projection import (
    Projection,
    ProjectionId,
    ProjectionState,
    can_transition_projection,
    next_state_after_apply,
)
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.commands import (
    RecordProjectionApplied,
    RecordProjectionAppliedDefsAppliedFileInput,
)
from skm.modules.integrations.generated.results import RecordProjectionAppliedResult
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.workspace import public as workspace
from skm.modules.workspace.public import CheckoutBindingId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from skm.application_bus.context import CommandContext
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _validate_path_sets(
    cmd: RecordProjectionApplied,
    prior_files: Sequence[AppliedFileRecord],
) -> None:
    file_paths: list[str] = []
    seen_files: set[str] = set()
    for item in cmd.files:
        rel = require_safe_relative_path(item.relative_path, field="files.relative_path")
        if rel in seen_files:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "duplicate relative_path in files",
                details={"field": "files", "path": rel},
            )
        seen_files.add(rel)
        file_paths.append(rel)

    removed_set = {require_safe_relative_path(p, field="removed") for p in cmd.removed}
    left_set = {require_safe_relative_path(p, field="left_modified") for p in cmd.left_modified}
    for p in cmd.conflicts:
        require_safe_relative_path(p, field="conflicts")
    for p in cmd.adopted:
        require_safe_relative_path(p, field="adopted")
    for item in cmd.failed:
        require_safe_relative_path(item.relative_path, field="failed.relative_path")

    overlap = (seen_files & removed_set) | (seen_files & left_set) | (removed_set & left_set)
    if overlap:
        overlap_paths: list[JsonValue] = [*sorted(overlap)]
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "files, removed, and left_modified sets must be pairwise disjoint",
            details={"paths": overlap_paths},
        )

    accounted = seen_files | removed_set | left_set
    prior_paths = {rec.relative_path for rec in prior_files}
    unaccounted: list[JsonValue] = [*sorted(prior_paths - accounted)]
    if unaccounted:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "unaccounted prior applied paths",
            details={"unaccounted_paths": unaccounted},
        )


def _to_applied_record(
    projection_id: ProjectionId,
    item: RecordProjectionAppliedDefsAppliedFileInput,
    prior_by_path: dict[str, AppliedFileRecord],
    *,
    now: datetime,
) -> AppliedFileRecord:
    require_tagged_digest(item.applied_managed_digest, field="files.applied_managed_digest")
    require_tagged_digest(item.applied_whole_digest, field="files.applied_whole_digest")
    boundary = ManagedBoundary(
        ownership=Ownership(item.ownership),
        block_ids=item.block_ids,
        owned_keys=tuple(OwnedKeyPath(path=k.path, mode=k.mode) for k in item.owned_keys),
    )
    pre_image_id = (
        None if item.pre_image_file_version_id is None else FileVersionId(item.pre_image_file_version_id)
    )
    prior = prior_by_path.get(item.relative_path)
    applied_at = (
        prior.applied_at
        if prior is not None
        and prior.applied_managed_digest == item.applied_managed_digest
        and prior.applied_whole_digest == item.applied_whole_digest
        and prior.boundary == boundary
        and prior.pre_image_file_version_id == pre_image_id
        and prior.renderer == item.renderer
        else now
    )
    return AppliedFileRecord(
        projection_id=projection_id,
        relative_path=item.relative_path,
        surface=Surface(item.surface),
        boundary=boundary,
        applied_managed_digest=item.applied_managed_digest,
        applied_whole_digest=item.applied_whole_digest,
        pre_image_file_version_id=pre_image_id,
        renderer=item.renderer,
        applied_at=applied_at,
    )


def _check_cas(projection: Projection | None, base_row_version: int | None) -> None:
    if projection is None:
        if base_row_version is not None:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                "projection does not exist when base_row_version is provided",
                details={"expected": None, "actual": base_row_version},
            )
        return
    if base_row_version is None or base_row_version != projection.row_version:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "projection base_row_version mismatch",
            details={"expected": projection.row_version, "actual": base_row_version},
        )


def handle(
    cmd: RecordProjectionApplied,
    ctx: CommandContext,
    uow: UnitOfWork,
) -> RecordProjectionAppliedResult:
    project_id = ProjectId(cmd.project_id)
    checkout_binding_id = CheckoutBindingId(cmd.checkout_binding_id)
    target = TargetId(cmd.target)
    now = ctx.clock.now()

    require_tagged_digest(cmd.desired_digest, field="desired_digest")
    require_tagged_digest(cmd.inputs_digest, field="inputs_digest")

    workspace.require_active_project(uow, project_id)
    workspace_id, _host_id = resolve_project_binding_host(uow, project_id, checkout_binding_id, now=now)

    pre_image_ids = [
        FileVersionId(item.pre_image_file_version_id)
        for item in cmd.files
        if item.pre_image_file_version_id is not None
    ]
    if pre_image_ids:
        artifacts.require_ready_versions(uow, workspace_id, pre_image_ids)

    repo = uow.repo(ProjectionRepository)
    existing = repo.find(project_id, checkout_binding_id, target)
    _check_cas(existing, cmd.base_row_version)

    prior_files = () if existing is None else repo.files(existing.id)
    _validate_path_sets(cmd, prior_files)

    next_state = next_state_after_apply(
        conflicts=cmd.conflicts,
        failed=cmd.failed,
        left_modified=cmd.left_modified,
    )
    from_state = (
        ProjectionState.PENDING
        if existing is None or existing.state is ProjectionState.REMOVED
        else existing.state
    )
    if not can_transition_projection(from_state, next_state):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            f"cannot transition projection from {from_state.value} to {next_state.value}",
            details={"from": from_state.value, "to": next_state.value},
        )

    prior_by_path = {rec.relative_path: rec for rec in prior_files}
    if existing is None:
        projection_id = ProjectionId(ctx.ids.new_id())
        applied_digest = cmd.desired_digest if next_state is ProjectionState.IN_SYNC else None
        saved = Projection(
            id=projection_id,
            workspace_id=workspace_id,
            project_id=project_id,
            checkout_binding_id=checkout_binding_id,
            target=target,
            state=next_state,
            desired_digest=cmd.desired_digest,
            applied_desired_digest=applied_digest,
            renderer_version=cmd.renderer_version,
            applied_at=now,
            drift_checked_at=None,
            row_version=1,
        )
        records = tuple(_to_applied_record(projection_id, item, prior_by_path, now=now) for item in cmd.files)
        repo.add(saved)
        repo.replace_files(projection_id, records)
    else:
        projection_id = existing.id
        applied_digest = (
            cmd.desired_digest if next_state is ProjectionState.IN_SYNC else existing.applied_desired_digest
        )
        saved = replace(
            existing,
            state=next_state,
            desired_digest=cmd.desired_digest,
            applied_desired_digest=applied_digest,
            renderer_version=cmd.renderer_version,
            applied_at=now,
            row_version=existing.row_version + 1,
        )
        records = tuple(_to_applied_record(projection_id, item, prior_by_path, now=now) for item in cmd.files)
        repo.replace_files(projection_id, records)
        repo.save(saved, expected_version=existing.row_version)

    uow.record(
        ProjectionApplied(
            projection_id=saved.id,
            workspace_id=workspace_id,
            state=saved.state,
            applied=len(records),
            conflicts=cmd.conflicts,
            failed=tuple(
                FailedProjectionFile(relative_path=item.relative_path, error_code=item.error_code)
                for item in cmd.failed
            ),
            adopted=cmd.adopted,
            removed=cmd.removed,
        )
    )
    return RecordProjectionAppliedResult(
        projection_id=UUID(str(saved.id)),
        state=cast("Any", saved.state.value),
        row_version=saved.row_version,
    )


SPEC = CommandSpec(
    name="integrations.record_projection_applied",
    dto=RecordProjectionApplied,
    result=RecordProjectionAppliedResult,
    permission="integration.apply",
    scope_of=project_scope,
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
