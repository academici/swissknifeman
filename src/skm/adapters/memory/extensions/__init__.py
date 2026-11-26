"""Memory adapters of the extensions repository ports (extensions §6, §11).

``REPOSITORIES`` maps each port to its factory over the backend state; ``bootstrap.adapters`` merges it with
the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.extensions.repositories import (
    MemoryPackRepository,
    MemoryQuarantineRepository,
    MemoryResourceRepository,
)
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        PackRepository: MemoryPackRepository,
        ResourceRepository: MemoryResourceRepository,
        QuarantineRepository: MemoryQuarantineRepository,
    }
)
