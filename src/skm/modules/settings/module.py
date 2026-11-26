"""Manifest of the settings module (settings §A.3)."""

from skm.kernel.module_manifest import ModuleManifest

from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .domain.events import ConfigChanged, ConfigLocked, ConfigUnlocked
from .permissions import PERMISSIONS
from .ports import ConfigEntryRepository, ConfigGenerationCounter, ConfigHistoryRepository

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="settings",
    depends_on=(),
    optional=False,
    db_schema="skm_config",
    settings_sections=(),
    permissions=PERMISSIONS,
    repository_ports=(ConfigEntryRepository, ConfigHistoryRepository, ConfigGenerationCounter),
    gateway_ports=(),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(),
    events=(ConfigChanged, ConfigLocked, ConfigUnlocked),
)
