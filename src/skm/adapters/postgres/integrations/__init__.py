"""PostgreSQL adapters of the ``integrations`` repository ports (integrations §6, §11; DDL ``0020``).

``REPOSITORIES`` maps each port to its factory over the unit-of-work connection; ``bootstrap.adapters`` merges
it with the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.integrations.repositories import PostgresProjectionRepository
from skm.modules.integrations.ports import ProjectionRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        ProjectionRepository: PostgresProjectionRepository,
    }
)
