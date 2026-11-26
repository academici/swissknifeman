"""Optional Markdown exports and vault delivery ledger."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import Surface

from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .domain.events import VaultNoteQueued, VaultNoteWritten
from .host.registry import operations
from .permissions import PERMISSIONS
from .ports import VaultFs, VaultNoteRepository

HOST_OPERATIONS = operations(Surface.CLI, Surface.WORKER)

MODULE = ModuleManifest(
    id="exports",
    depends_on=("access", "workspace", "planning", "execution"),
    optional=True,
    db_schema="skm_exports",
    settings_sections=("exports",),
    permissions=PERMISSIONS,
    repository_ports=(VaultNoteRepository,),
    gateway_ports=(VaultFs,),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=HOST_OPERATIONS,
    events=(VaultNoteQueued, VaultNoteWritten),
)
