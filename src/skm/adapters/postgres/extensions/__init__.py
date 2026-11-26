"""PostgreSQL adapters of the extensions repository ports (extensions §6, §11; DDL ``0018``).

``REPOSITORIES`` maps each port to its factory over the unit-of-work connection; it is merged with the core
table by ``bootstrap.adapters.postgres_repository_table``.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.extensions.repositories import (
    PostgresPackRepository,
    PostgresQuarantineRepository,
    PostgresResourceRepository,
)
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        PackRepository: PostgresPackRepository,
        ResourceRepository: PostgresResourceRepository,
        QuarantineRepository: PostgresQuarantineRepository,
    }
)
