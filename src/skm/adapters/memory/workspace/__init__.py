"""Memory adapters of the workspace repository ports and ``access.WorkerHostLookup`` (workspace §3, §6, §11).

``REPOSITORIES`` maps each port to its factory over the backend state. ``WorkerHostLookup`` is a port of the
``access`` module that the workspace adapters implement (access §6), so the access authorizer sees the hosts
of the non-retired workers of a principal.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.workspace.repositories import (
    MemoryCheckoutBindingRepository,
    MemoryHostRepository,
    MemoryMountRepository,
    MemoryProjectRepository,
    MemoryRepositoryRepository,
    MemoryWorkerHostLookup,
    MemoryWorkerRepository,
    MemoryWorkspaceRepository,
)
from skm.modules.access.ports import WorkerHostLookup
from skm.modules.workspace.ports import (
    CheckoutBindingRepository,
    HostRepository,
    MountRepository,
    ProjectRepository,
    RepositoryRepository,
    WorkerRepository,
    WorkspaceRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        WorkspaceRepository: MemoryWorkspaceRepository,
        ProjectRepository: MemoryProjectRepository,
        RepositoryRepository: MemoryRepositoryRepository,
        MountRepository: MemoryMountRepository,
        HostRepository: MemoryHostRepository,
        CheckoutBindingRepository: MemoryCheckoutBindingRepository,
        WorkerRepository: MemoryWorkerRepository,
        WorkerHostLookup: MemoryWorkerHostLookup,
    }
)
