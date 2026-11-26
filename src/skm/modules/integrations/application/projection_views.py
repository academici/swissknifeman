"""Shared scope, ownership validation, and view assembly for ``integrations`` handlers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.projection import Projection
from skm.modules.integrations.generated.views import (
    AppliedStateViewDefsAppliedFileRecord,
    AppliedStateViewDefsManagedBoundary,
    AppliedStateViewDefsOwnedKeyPath,
    ProjectionSummaryView,
)
from skm.modules.workspace import public as workspace
from skm.modules.workspace.public import CheckoutBindingId
from skm.platform.jsonc.digest import is_tagged_digest

if TYPE_CHECKING:
    from skm.kernel.ports_uow import UnitOfWork

__all__ = [
    "host_map_for_project",
    "project_scope",
    "require_safe_relative_path",
    "require_tagged_digest",
    "resolve_project_binding_host",
    "to_applied_file_view",
    "to_projection_summary_view",
]

_MAX_RELATIVE_PATH_LEN: Final = 1024
_SCOPE_PAGE_SIZE: Final = 500


class _HasProjectId(Protocol):
    @property
    def project_id(self) -> UUID: ...


def project_scope(dto: _HasProjectId) -> ScopeRef:
    """Resolve bus authorization scope from the DTO's ``project_id``."""
    return ScopeRef(ScopeKind.PROJECT, ScopeId(dto.project_id))


def require_tagged_digest(value: str, *, field: str) -> str:
    """Require a canonical ``sha256:<64 lowercase hex>`` digest."""
    if not is_tagged_digest(value):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"{field} must be a canonical sha256 digest",
            details={"field": field},
        )
    return value


def require_safe_relative_path(path: str, *, field: str) -> str:
    """Require a safe, normalized checkout-relative path without traversal or control characters."""
    if (
        not (1 <= len(path) <= _MAX_RELATIVE_PATH_LEN)
        or "\n" in path
        or "\r" in path
        or not is_safe_relative_path(path)
        or ".git" in path.split("/")
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"{field} contains an unsafe relative path",
            details={"field": field, "path": path},
        )
    return path


def _registered_host_ids(uow: UnitOfWork) -> tuple[HostId, ...]:
    registry = uow.repo(ScopeRegistry)
    hosts: list[HostId] = []
    after: ScopeId | None = None
    while True:
        batch = registry.list_scopes(after=after, limit=_SCOPE_PAGE_SIZE)
        hosts.extend(HostId(UUID(str(rec.id))) for rec in batch if rec.kind is ScopeKind.HOST)
        if len(batch) < _SCOPE_PAGE_SIZE:
            break
        after = batch[-1].id
    return tuple(hosts)


def host_map_for_project(
    uow: UnitOfWork,
    project_id: ProjectId,
    *,
    now: datetime,
) -> dict[CheckoutBindingId, HostId]:
    """Map every checkout binding attached to ``project_id``'s mounts to its owning ``HostId``."""
    mounts = workspace.project_repositories(uow, project_id)
    if not mounts:
        return {}
    hosts = _registered_host_ids(uow)
    mapping: dict[CheckoutBindingId, HostId] = {}
    for mount in mounts:
        for host_id in hosts:
            try:
                loc = workspace.resolve_checkout(uow, project_id, mount.mount_name, host_id, now=now)
                mapping[CheckoutBindingId(loc.binding_id)] = host_id
            except PreconditionFailed as exc:
                if exc.code is ErrorCode.CHECKOUT_MISMATCH and exc.details and "binding_id" in exc.details:
                    raw_id = exc.details["binding_id"]
                    if isinstance(raw_id, str):
                        mapping[CheckoutBindingId(UUID(raw_id))] = host_id
                elif exc.code is ErrorCode.CHECKOUT_UNBOUND:
                    continue
                else:
                    raise
    return mapping


def resolve_project_binding_host(
    uow: UnitOfWork,
    project_id: ProjectId,
    checkout_binding_id: CheckoutBindingId,
    *,
    now: datetime,
) -> tuple[WorkspaceId, HostId]:
    """Verify ``checkout_binding_id`` belongs to ``project_id`` and return ``(workspace_id, host_id)``."""
    workspace_id = workspace.workspace_of_project(uow, project_id)
    workspace.get_checkout_binding(uow, checkout_binding_id, now=now)
    mapping = host_map_for_project(uow, project_id, now=now)
    host_id = mapping.get(checkout_binding_id)
    if host_id is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "checkout binding not found for project",
            details={"kind": "checkout_binding", "ref": str(checkout_binding_id)},
        )
    return workspace_id, host_id


def to_projection_summary_view(projection: Projection, *, host_id: HostId) -> ProjectionSummaryView:
    """Convert domain ``Projection`` to ``ProjectionSummaryView``."""
    return ProjectionSummaryView(
        projection_id=UUID(str(projection.id)),
        checkout_binding_id=UUID(str(projection.checkout_binding_id)),
        host_id=UUID(str(host_id)),
        target=cast("Any", projection.target.value),
        state=cast("Any", projection.state.value),
        desired_digest=projection.desired_digest,
        applied_desired_digest=projection.applied_desired_digest,
        applied_at=projection.applied_at,
        drift_checked_at=projection.drift_checked_at,
        row_version=projection.row_version,
    )


def to_applied_file_view(record: AppliedFileRecord) -> AppliedStateViewDefsAppliedFileRecord:
    """Convert domain ``AppliedFileRecord`` to ``AppliedStateViewDefsAppliedFileRecord``."""
    boundary = AppliedStateViewDefsManagedBoundary(
        ownership=cast("Any", record.boundary.ownership.value),
        block_ids=record.boundary.block_ids,
        owned_keys=tuple(
            AppliedStateViewDefsOwnedKeyPath(
                path=item.path,
                mode=item.mode,
            )
            for item in record.boundary.owned_keys
        ),
    )
    return AppliedStateViewDefsAppliedFileRecord(
        projection_id=UUID(str(record.projection_id)),
        relative_path=record.relative_path,
        surface=cast("Any", record.surface.value),
        boundary=boundary,
        applied_managed_digest=record.applied_managed_digest,
        applied_whole_digest=record.applied_whole_digest,
        pre_image_file_version_id=(
            None if record.pre_image_file_version_id is None else UUID(str(record.pre_image_file_version_id))
        ),
        renderer=record.renderer,
        applied_at=record.applied_at,
    )
