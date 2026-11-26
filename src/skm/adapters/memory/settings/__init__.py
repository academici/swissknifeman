"""Memory adapters of the settings repository ports (settings §A.3, §A.11).

``REPOSITORIES`` maps each settings port to its factory over the backend state; ``InMemoryBackend`` merges it
with the core table and the config store (``adapters/memory/config_store.py``).
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.settings.repositories import (
    MemoryConfigEntryRepository,
    MemoryConfigGenerationCounter,
    MemoryConfigHistoryRepository,
)
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter, ConfigHistoryRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        ConfigEntryRepository: MemoryConfigEntryRepository,
        ConfigHistoryRepository: MemoryConfigHistoryRepository,
        ConfigGenerationCounter: MemoryConfigGenerationCounter,
    }
)
