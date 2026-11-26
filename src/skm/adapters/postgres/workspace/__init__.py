"""PostgreSQL adapters of the workspace ports and ``access.WorkerHostLookup`` (workspace §3, §6, §11).

``REPOSITORIES`` maps each port to its factory over the unit-of-work connection; it is merged with the core
table by ``bootstrap.adapters.postgres_repository_table``. ``WorkerHostLookup`` is a port of the ``access``
module that the workspace adapters implement (access §6), so the access authorizer sees the hosts of the
non-retired workers of a principal. Every factory takes the connection and an optional ``clock`` (the system
clock by default) for ``updated_at`` and the ``added_at`` of remotes.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.workspace.bindings import PostgresCheckoutBindingRepository
from skm.adapters.postgres.workspace.hosts import PostgresHostRepository
from skm.adapters.postgres.workspace.mounts import PostgresMountRepository
from skm.adapters.postgres.workspace.projects import PostgresProjectRepository
from skm.adapters.postgres.workspace.repositories import PostgresRepositoryRepository
from skm.adapters.postgres.workspace.worker_hosts import PostgresWorkerHostLookup
from skm.adapters.postgres.workspace.workers import PostgresWorkerRepository
from skm.adapters.postgres.workspace.workspaces import PostgresWorkspaceRepository
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

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        WorkspaceRepository: PostgresWorkspaceRepository,
        ProjectRepository: PostgresProjectRepository,
        RepositoryRepository: PostgresRepositoryRepository,
        MountRepository: PostgresMountRepository,
        HostRepository: PostgresHostRepository,
        CheckoutBindingRepository: PostgresCheckoutBindingRepository,
        WorkerRepository: PostgresWorkerRepository,
        WorkerHostLookup: PostgresWorkerHostLookup,
    }
)
