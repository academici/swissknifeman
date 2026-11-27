"""Bind the local projection adapters for embedded and HTTP CLI sessions."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid5

from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed, error_for
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.integrations.generated.host import SyncProjectionsResult
from skm.modules.settings.public import ExplainConfig, ExplainConfigResult

if TYPE_CHECKING:
    from skm.bootstrap.machine_access import MachineCaller, MachineOperation
    from skm.modules.integrations.domain.projection import LocalPreImage, LocalPreImageKey
    from skm.modules.integrations.generated.queries import ListProjections
    from skm.modules.integrations.generated.views import ProjectionsView
    from skm.platform.config.bootstrap import BootstrapConfig
    from skm.platform.machine import MachinePrincipal, MachineStore

__all__ = [
    "bind_cli_projections",
    "bind_managed_projections",
    "list_host_projections",
    "offline_projection_doctor",
    "run_machine_projection_operation",
]
_PRE_IMAGE_MAX_BYTES = 64 * 1024 * 1024


def bind_cli_projections(
    host: HostServices | None,
    state_dir: Path,
    client: SkmClient,
    *,
    environ: Mapping[str, str] | None = None,
    instance_id: UUID | None = None,
) -> HostServices | None:
    if host is None:
        return None

    from skm.adapters.checkout_fs.local import LocalCheckoutFs
    from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
    from skm.adapters.git.excludes import GitInfoExcludes
    from skm.adapters.host_commands.subprocess_runner import SubprocessHostCommandRunner
    from skm.adapters.integrations.registry import default_target_registry
    from skm.modules.integrations.host.registry import HOST_OPERATIONS
    from skm.modules.integrations.ports import (
        CheckoutFs,
        CheckoutGitExcludes,
        HostCommandRunner,
        IntegrationTargetRegistry,
        ProjectionConfig,
        UserHomeReader,
    )

    def config(project_id: ProjectId) -> JsonObject:
        result = client.ask(
            ExplainConfig.from_json(
                {
                    "scope": {"level": "project", "scope_id": str(project_id)},
                    "keys": [
                        "integrations.targets",
                        "integrations.conflict_suffix",
                        "integrations.desired.max_bytes",
                    ],
                    "detail": "value",
                }
            )
        )
        assert isinstance(result, ExplainConfigResult)  # noqa: S101
        values: JsonObject = {}
        for entry in cast("list[JsonObject]", result.to_json()["keys"]):
            key = cast("str", entry["key"])
            if entry.get("valid") is False:
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Invalid projection configuration", details={"key": key}
                )
            values[key] = entry["value"]
        return values

    entries = {
        CheckoutFs: LocalCheckoutFs(state_dir, state_dir=state_dir),
        CheckoutGitExcludes: GitInfoExcludes(),
        IntegrationTargetRegistry: default_target_registry(),
        ProjectionConfig: config,
        UserHomeReader: LocalUserHomeReader(),
        HostCommandRunner: SubprocessHostCommandRunner.for_session(
            os.environ if environ is None else environ
        ),
        **host.gateways.entries,
    }
    operations = {
        **host.operations,
        **{spec.name: spec for spec in HOST_OPERATIONS if host.surface in spec.surfaces},
    }
    from skm.bootstrap.hook_subscriptions import with_subscription_gateways

    return cast(
        "HostServices",
        with_subscription_gateways(
            replace(
                host,
                gateways=GatewayTable(entries, "host_gateway"),
                operations=operations,
                instance_id=instance_id or host.instance_id,
            ),
            state_dir,
            os.environ if environ is None else environ,
        ),
    )


class _ManagedProjectionCheckouts:
    def __init__(
        self,
        store: MachineStore,
        scope: Callable[[], MachinePrincipal],
        context: HostContext,
        state_dir: Path,
    ) -> None:
        self.store = store
        self.scope = scope
        self.context = context
        self.state_dir = state_dir

    def resolve(self, project_id: ProjectId, mount: str) -> tuple[UUID, Path]:
        from skm.adapters.git.repo_inspect import GitRepositoryInspector
        from skm.bootstrap.checkout_operations import LocalCheckoutResolver
        from skm.kernel.ids import WorkspaceId
        from skm.modules.workspace.public import GetProject, GetWorkspace, ProjectView, WorkspaceView

        project = self.context.client.ask(GetProject(project_id))
        if not isinstance(project, ProjectView) or project.state != "active":
            raise error_for(ErrorCode.PROJECT_ARCHIVED, "Project must be active")
        workspace = self.context.client.ask(GetWorkspace(WorkspaceId(project.workspace_id)))
        if not isinstance(workspace, WorkspaceView) or workspace.state != "active":
            raise error_for(ErrorCode.PROJECT_ARCHIVED, "Workspace must be active")
        return LocalCheckoutResolver(
            self.scope(), self.context.host_id, self.store, self.context.client, GitRepositoryInspector()
        ).resolve(project_id, mount)

    def sync(self, project_id: ProjectId) -> SyncProjectionsResult:
        from skm.modules.integrations.host.sync_projections import sync

        return sync(self.context, {"scope": "project", "scope_id": str(project_id)})

    def require_apply(self, project_id: ProjectId) -> None:
        from skm.modules.access.public import WhoAmI, WhoAmIView

        identity = self.context.client.ask(WhoAmI(scope_id=project_id))
        if not isinstance(identity, WhoAmIView) or "integration.apply" not in identity.effective_permissions:
            raise Forbidden(ErrorCode.FORBIDDEN, "Current project permission integration.apply is required")

    def _pre_image_path(self, key: LocalPreImageKey) -> tuple[UUID, Path]:
        scope = self.scope()
        identifier = uuid5(key.binding_id, f"{key.project_id}:{key.target.value}:{key.relative_path}")
        folder = self.state_dir / "integrations" / "pre-images"
        for identity in (scope.installation_id, scope.instance_id, scope.principal_id, self.context.host_id):
            folder /= str(identity)
        return identifier, folder / str(identifier)

    def save_pre_image(self, key: LocalPreImageKey, contents: bytes | None, *, replace: bool) -> UUID:
        from os.path import lexists

        from skm.bootstrap.instance_secrets import ensure_private_dir
        from skm.platform.fs.atomic_write import atomic_write_nofollow

        if contents is not None and len(contents) > _PRE_IMAGE_MAX_BYTES:
            raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "Projection backup exceeds its limit")
        identifier, path = self._pre_image_path(key)
        ensure_private_dir(path.parent)
        if replace or not lexists(path):
            atomic_write_nofollow(str(path), b"\x02" if contents is None else b"\x01" + contents)
        else:
            self.read_pre_image(key)
        return identifier

    def read_pre_image(self, key: LocalPreImageKey) -> LocalPreImage | None:
        from os.path import lexists

        from skm.bootstrap.instance_secrets import check_private_dir, read_private
        from skm.modules.integrations.domain.projection import LocalPreImage

        _, path = self._pre_image_path(key)
        if not lexists(path):
            return None
        check_private_dir(path.parent)
        encoded = read_private(path, _PRE_IMAGE_MAX_BYTES + 2)
        if encoded in (b"\x00", b"\x02"):
            return LocalPreImage(None, verified_absence=encoded == b"\x02")
        if encoded[:1] == b"\x01" and len(encoded) <= _PRE_IMAGE_MAX_BYTES + 1:
            return LocalPreImage(encoded[1:])
        raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "Invalid local projection backup")


def bind_managed_projections(
    context: HostContext,
    store: MachineStore,
    scope: Callable[[], MachinePrincipal],
    state_dir: Path,
) -> HostContext:
    from skm.modules.integrations.ports import LocalCheckoutProjections

    entries = dict(cast("GatewayTable", context.gateways).entries)
    local = _ManagedProjectionCheckouts(store, scope, context, state_dir)
    entries[LocalCheckoutProjections] = local
    local.context = replace(context, gateways=GatewayTable(entries, "host_gateway"))
    return local.context


def list_host_projections(context: HostContext, query: ListProjections) -> ProjectionsView:
    from skm.modules.integrations.host.observe import list_local_projections

    return list_local_projections(context, query)


def offline_projection_doctor(
    config: BootstrapConfig, start: Path, project: str | None, targets: list[str] | None
) -> JsonObject:
    from skm.adapters.checkout_fs.local import LocalCheckoutFs
    from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
    from skm.adapters.git.repo_inspect import GitRepositoryInspector
    from skm.adapters.integrations.registry import default_target_registry
    from skm.bootstrap.checkout_operations import checkout_host_id
    from skm.modules.integrations.domain.target import TargetId

    inspector = GitRepositoryInspector()
    root = inspector.toplevel(start)
    marker = inspector.read_marker(root)
    if marker is None or config.instance_id is None or marker.instance_id != config.instance_id:
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_UNBOUND, "Current checkout has no marker for this profile"
        )
    if project is not None and project != str(marker.project_id):
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "Use the project UUID from the local checkout")
    selected = tuple(dict.fromkeys(targets or ["claude_code", "codex", "cursor", "grok"]))
    fs = LocalCheckoutFs(root, state_dir=config.state_dir)
    registry = default_target_registry()
    home = LocalUserHomeReader()
    checks: list[JsonValue] = []
    warnings, errors, passed = 0, 0, 0
    for name in selected:
        target = registry.get(TargetId(name))
        checks.append(
            {
                "check_id": "local.live_authority",
                "target": name,
                "level": "warning",
                "title": "Local observations only",
                "detail": "Live project authorization, policy and applied records were not checked.",
            }
        )
        warnings += 1
        for layer in target.client_layers(fs, home):
            valid = bool(layer.get("valid"))
            passed += int(valid)
            errors += int(not valid)
            checks.append(
                {
                    "check_id": f"local.layer.{layer['layer']}",
                    "target": name,
                    "level": "ok" if valid else "error",
                    "title": f"Native {layer['layer']} layer",
                    "detail": "Readable and valid" if valid else "Unreadable or invalid",
                }
            )
    return {
        "schema": "urn:skm:integrations:host:doctor-report:v1",
        "project_id": str(marker.project_id),
        "host_id": str(checkout_host_id(config)),
        "targets": list(selected),
        "status": "error" if errors else "warning",
        "counts": {"ok": passed, "warning": warnings, "error": errors},
        "checks": checks,
    }


def run_machine_projection_operation(
    operation: MachineOperation, caller: MachineCaller, payload: JsonObject
) -> JsonValue:
    from skm.modules.integrations.host import apply_projection, plan_projection, run_doctor, sync_projections
    from skm.platform.logging.logger import get_logger

    config = caller.project.config
    if config is None:
        raise error_for(ErrorCode.CONFIG_INVALID, "Machine project bootstrap is unavailable")
    host = bind_cli_projections(
        HostServices(caller.host_id, Surface.CLI, GatewayTable({}, "host_gateway"), lambda: {}, {}),
        config.state_dir,
        caller.client,
        environ=caller.project.environ,
        instance_id=caller.profile.instance_id,
    )
    assert host is not None  # noqa: S101 -- services supplied above
    context = bind_managed_projections(
        host.context(
            client=caller.client, cancel=CancelSource().token, log=get_logger("machine.projections")
        ),
        caller.store,
        lambda: caller.scope,
        config.state_dir,
    )
    if operation == "integrations.plan":
        return cast("JsonValue", plan_projection.run(context, payload))
    if operation == "integrations.list":
        from skm.modules.integrations.generated.queries import ListProjections

        return cast("JsonValue", list_host_projections(context, ListProjections.from_json(payload)).to_json())
    if operation == "integrations.apply":
        # Write paths and bytes must originate from a newly rendered local plan.
        request = dict(payload)
        expected = request.pop("plan_digests", None)
        restore = request.pop("restore_pre_image", False)
        if not isinstance(expected, list) or not all(isinstance(digest, str) for digest in expected):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "plan_digests must contain the confirmed digests"
            )
        if not isinstance(restore, bool):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "restore_pre_image must be boolean")
        plans = plan_projection.run(context, request)
        if [item["plan_digest"] for item in plans] != expected:
            raise error_for(ErrorCode.VERSION_CONFLICT, "Projection plan changed before apply")
        return cast(
            "JsonValue", apply_projection.run(context, {"plans": plans, "restore_pre_image": restore})
        )
    if operation == "integrations.doctor":
        return cast("JsonValue", run_doctor.run(context, payload))
    if operation == "workspace.sync-projections":
        return cast("JsonValue", sync_projections.sync(context, payload))
    raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "Machine projection operation is unavailable")
