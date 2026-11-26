"""Memory adapters of the planning repository ports (planning §3, §6, §11).

``REPOSITORIES`` maps each implemented port to its factory over the backend state.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.planning.queries import MemoryPlanningQueries
from skm.adapters.memory.planning.repositories import (
    MemoryDraftRepository,
    MemoryPlanCounters,
    MemoryPlanRepository,
    MemoryRevisionRepository,
)
from skm.modules.planning.ports import (
    DraftRepository,
    PlanCounters,
    PlanningQueries,
    PlanRepository,
    RevisionRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        PlanRepository: MemoryPlanRepository,
        PlanCounters: MemoryPlanCounters,
        DraftRepository: MemoryDraftRepository,
        RevisionRepository: MemoryRevisionRepository,
        PlanningQueries: MemoryPlanningQueries,
    }
)
