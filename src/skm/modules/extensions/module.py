"""Manifest of the extensions module (extensions §3)."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest

from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .domain import events
from .host.registry import HOST_OPERATIONS
from .permissions import PERMISSIONS
from .ports import (
    BuiltinPacks,
    PackReader,
    PackRepository,
    QuarantineRepository,
    ResourceRepository,
    RuntimeCatalogSeeder,
    UpstreamFetcher,
)

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="extensions",
    depends_on=("access", "workspace", "policy"),
    optional=False,
    db_schema="skm_extensions",
    settings_sections=("extensions",),
    permissions=PERMISSIONS,
    repository_ports=(
        PackRepository,
        ResourceRepository,
        QuarantineRepository,
    ),
    gateway_ports=(
        PackReader,
        BuiltinPacks,
        RuntimeCatalogSeeder,
        UpstreamFetcher,
    ),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=HOST_OPERATIONS,
    events=(
        events.PackInstalled,
        events.PackVersionUninstalled,
        events.ResourceVersionAdded,
        events.ResourceQuarantined,
        events.ResourceReleased,
    ),
)
