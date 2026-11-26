"""Memory adapters of the ``runtimes`` repository ports (runtimes §6, §11).

``REPOSITORIES`` maps each port to its factory over ``MemoryBackendState``; ``bootstrap.adapters`` merges it
with the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.runtimes.repositories import (
    MemoryCapabilityVerificationRepository,
    MemoryHostModelAvailabilityRepository,
    MemoryHostRuntimeRepository,
    MemoryModelCatalogRepository,
)
from skm.modules.runtimes.ports import (
    CapabilityVerificationRepository,
    HostModelAvailabilityRepository,
    HostRuntimeRepository,
    ModelCatalogRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        HostRuntimeRepository: MemoryHostRuntimeRepository,
        CapabilityVerificationRepository: MemoryCapabilityVerificationRepository,
        ModelCatalogRepository: MemoryModelCatalogRepository,
        HostModelAvailabilityRepository: MemoryHostModelAvailabilityRepository,
    }
)
