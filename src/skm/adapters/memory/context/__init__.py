"""Memory adapters of the context repository ports (context §§6, 11)."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.context.repositories import MemoryContextRepository, MemoryTextStore
from skm.adapters.memory.context.research import MemoryResearchRepository
from skm.adapters.memory.core.state import MemoryBackendState
from skm.modules.context.ports import ContextRepository, ResearchRepository, TextStore

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        ContextRepository: MemoryContextRepository,
        ResearchRepository: MemoryResearchRepository,
        TextStore: MemoryTextStore,
    }
)
