"""PostgreSQL adapters of the ``runtimes`` repository ports (runtimes §6, §11; DDL ``0017``).

``REPOSITORIES`` maps each port to its factory over the unit-of-work connection; ``bootstrap.adapters`` merges
it with the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.runtimes.repositories import (
    PostgresCapabilityVerificationRepository,
    PostgresHostModelAvailabilityRepository,
    PostgresHostRuntimeRepository,
    PostgresModelCatalogRepository,
)
from skm.modules.runtimes.ports import (
    CapabilityVerificationRepository,
    HostModelAvailabilityRepository,
    HostRuntimeRepository,
    ModelCatalogRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        HostRuntimeRepository: PostgresHostRuntimeRepository,
        CapabilityVerificationRepository: PostgresCapabilityVerificationRepository,
        ModelCatalogRepository: PostgresModelCatalogRepository,
        HostModelAvailabilityRepository: PostgresHostModelAvailabilityRepository,
    }
)
