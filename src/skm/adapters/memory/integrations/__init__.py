"""Memory adapters of the ``integrations`` repository ports (integrations §6, §11).

``REPOSITORIES`` maps each port to its factory over ``MemoryBackendState``; ``bootstrap.adapters`` merges it
with the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.integrations.repositories import MemoryProjectionRepository
from skm.modules.integrations.ports import ProjectionRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        ProjectionRepository: MemoryProjectionRepository,
    }
)
