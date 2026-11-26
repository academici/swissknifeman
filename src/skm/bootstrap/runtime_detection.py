"""Compose the operator's runtime inventory probe with the current project caller."""

from collections.abc import Callable, Mapping
from typing import cast
from uuid import UUID

from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap.host_services import build_host_storage, read_recorded_host_id
from skm.bootstrap.runtimes import WorkerRuntimeSettings, runtime_environment
from skm.bootstrap.worker_runtimes import HostPlugins, WorkerRuntimes, runtime_auth, worker_redactor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.runtimes.host.detect_runtimes import detect_runtimes
from skm.modules.runtimes.public import DetectRuntimesReport, RuntimeRegistry
from skm.modules.settings.public import (
    ExplainConfig,
    ExplainConfigResult,
    GetHostConfigResultPlugins,
    worker_identifiers,
)
from skm.modules.workspace.public import GetHost, HostView
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.machine import MachineStore

__all__ = ["build_runtime_detection_host", "run_runtime_detection"]

_KEYS = ("runtimes.allowed", "plugins.allowed", "plugins.required")


def _project_limits(client: SkmClient) -> JsonObject:
    report = client.ask(
        ExplainConfig.from_json({"scope": {"level": "instance"}, "keys": list(_KEYS), "detail": "value"})
    )
    if not isinstance(report, ExplainConfigResult):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Project did not return runtime restrictions")
    limits: JsonObject = {}
    for entry in cast("list[JsonObject]", report.to_json()["keys"]):
        key = entry.get("key")
        if isinstance(key, str) and key in _KEYS and entry.get("valid") is not False:
            limits[key] = entry.get("value")
    if limits.keys() != set(_KEYS):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Project runtime restrictions are incomplete")
    return limits


def build_runtime_detection_host(
    bootstrap: BootstrapConfig,
    client: SkmClient,
    environ: Mapping[str, str],
    machine_store: MachineStore | None,
    on_secret: Callable[[str], None],
) -> HostServices:
    """Authorize the registered host and read its machine-approved runtime inputs."""
    if machine_store is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Runtime detection requires machine storage")
    host = (
        HostId(bootstrap.host_id)
        if isinstance(bootstrap.host_id, UUID)
        else read_recorded_host_id(bootstrap.state_dir)
    )
    if host is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Runtime detection requires a registered local host")
    host_view = client.ask(GetHost(host_id=host))
    if not isinstance(host_view, HostView) or host_view.host_id != host:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Project did not confirm the registered host")
    local = WorkerRuntimeSettings.read(machine_store)
    limits = _project_limits(client)
    plugin_limits = GetHostConfigResultPlugins(
        worker_identifiers(limits["plugins.allowed"], key="plugins.allowed"),
        worker_identifiers(limits["plugins.required"], key="plugins.required"),
    )
    redactor, _register = worker_redactor(bootstrap, environ, on_secret)
    gateway = WorkerRuntimes(
        HostPlugins(lambda: local, lambda: plugin_limits),
        lambda: local,
        lambda: limits["runtimes.allowed"],
        bootstrap.state_dir,
        build_host_storage(bootstrap.state_dir),
        runtime_environment(environ, redactor),
        lambda refs: runtime_auth(refs, bootstrap, environ, redactor, on_secret),
    )
    return HostServices(
        host, Surface.CLI, GatewayTable({RuntimeRegistry: gateway}, "host_gateway"), lambda: local, {}
    )


def run_runtime_detection(ctx: HostContext, redact: Callable[[str], str]) -> DetectRuntimesReport:
    """Publish the installation inventory without paths, environment or adapter internals."""
    return detect_runtimes(ctx, publish_local_details=False, redact=redact)
