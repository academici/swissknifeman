"""Manifest of the ``runtimes`` module (runtimes §3)."""

from __future__ import annotations

from skm.kernel.module_manifest import HostOperationSpec, ModuleManifest
from skm.kernel.ports_uow import Surface

from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .domain.events import CapabilityVerified, HostRuntimesRecorded
from .generated.host import DetectRuntimesReport, DetectRuntimesRequest
from .host.detect_runtimes import detect_runtimes
from .permissions import PERMISSIONS
from .ports import (
    AgentRuntime,
    CapabilityCatalog,
    CapabilityVerificationRepository,
    HostModelAvailabilityRepository,
    HostRuntimeRepository,
    ModelCatalogRepository,
    RuntimeRegistry,
    WorkerModelOfferPolicy,
)

__all__ = ["DETECT_RUNTIMES_SPEC", "MODULE"]

DETECT_RUNTIMES_SPEC = HostOperationSpec(
    name="runtimes.host.detect_runtimes",
    run=detect_runtimes,
    request=DetectRuntimesRequest,
    result=DetectRuntimesReport,
    surfaces=frozenset({Surface.CLI, Surface.WORKER}),
)

MODULE = ModuleManifest(
    id="runtimes",
    depends_on=("access", "workspace", "extensions"),
    optional=False,
    db_schema="skm_runtimes",
    settings_sections=("runtimes",),
    permissions=PERMISSIONS,
    repository_ports=(
        HostRuntimeRepository,
        CapabilityVerificationRepository,
        ModelCatalogRepository,
        HostModelAvailabilityRepository,
    ),
    gateway_ports=(
        AgentRuntime,
        RuntimeRegistry,
        WorkerModelOfferPolicy,
        CapabilityCatalog,
    ),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(DETECT_RUNTIMES_SPEC,),
    events=(
        HostRuntimesRecorded,
        CapabilityVerified,
    ),
)
