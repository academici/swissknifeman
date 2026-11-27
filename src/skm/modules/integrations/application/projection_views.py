"""Shared scope, ownership validation, and view assembly for ``integrations`` handlers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.hook_subscriptions import HookSubscription, parse_subscriptions
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.presets import (
    CLAUDE_SETTINGS,
    preset_of_renderer,
    preset_subscription_config,
)
from skm.modules.integrations.domain.projection import Projection
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.settings import IntegrationsSettings
from skm.modules.integrations.generated.views import (
    AppliedStateViewDefsAppliedFileRecord,
    AppliedStateViewDefsManagedBoundary,
    AppliedStateViewDefsOwnedKeyPath,
    DesiredProjectionViewDefsJsonValue,
    ProjectionSummaryView,
)
from skm.modules.workspace import public as workspace
from skm.modules.workspace.public import CheckoutBindingId
from skm.platform.jsonc.digest import is_tagged_digest

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.integrations.ports import ProjectionRepository
    from skm.platform.config import EffectiveConfig

__all__ = [
    "PacksConfigView",
    "applied_preset_subscriptions",
    "assemble_mcp_servers",
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


def applied_preset_subscriptions(
    repo: ProjectionRepository, project: ProjectId, target: TargetId
) -> tuple[tuple[HookSubscription, ...], int]:
    config: dict[str, JsonValue] = {}
    version = 0
    after = None
    while True:
        page = repo.list_for_project(project, after=after, limit=_SCOPE_PAGE_SIZE)
        version = max(version, max((item.row_version for item in page.items), default=0))
        for projection in page.items:
            if projection.target is not target or projection.state == "removed":
                continue
            preset = preset_of_renderer(projection.renderer_version)
            if preset is not None and any(
                file.relative_path == CLAUDE_SETTINGS and preset_of_renderer(file.renderer) == preset
                for file in repo.files(projection.id)
            ):
                config.update(preset_subscription_config(preset, target))
        after = page.next
        if after is None:
            break
    subscriptions, violations = parse_subscriptions(config, dict.fromkeys(config, "project"))
    if violations:
        raise ValueError("invalid built-in preset subscription")
    return subscriptions, version


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


class PacksConfigView:
    __slots__ = ("_base", "_enabled", "_extra_pins")

    def __init__(
        self,
        base: EffectiveConfig,
        enabled: Sequence[str] | None = None,
        extra_pins: Mapping[str, str] | None = None,
    ) -> None:
        self._base = base
        self._enabled = None if enabled is None else list(enabled)
        self._extra_pins = dict(extra_pins or {})

    def get(self, key: str) -> Any:
        if key == "extensions.packs.enabled" and self._enabled is not None:
            return list(self._enabled)
        if key == "extensions.resources.pinned" and self._extra_pins:
            return {**self._extra_pins, **cast("Mapping[str, str]", self._base.get(key))}
        return self._base.get(key)


def assemble_mcp_servers(
    settings: IntegrationsSettings,
) -> Mapping[str, Mapping[str, DesiredProjectionViewDefsJsonValue]]:
    servers: dict[str, Mapping[str, DesiredProjectionViewDefsJsonValue]] = {}
    if settings.mcp.include_skm:
        servers["skm"] = {"command": "skm", "args": ("mcp", "serve"), "type": "stdio", "enabled": True}
    for name, entry in sorted(settings.mcp.servers.items()):
        if entry.enabled is False:
            servers.pop(name, None)
            continue
        spec: dict[str, DesiredProjectionViewDefsJsonValue] = {"enabled": True}
        for attr in ("type", "command", "args", "url", "tool_count"):
            if (val := getattr(entry, attr)) is not None:
                spec[attr] = val
        if entry.env_refs is not None:
            spec["env_refs"] = {k: str(v) for k, v in sorted(entry.env_refs.items())}
        servers[name] = spec
    return servers
