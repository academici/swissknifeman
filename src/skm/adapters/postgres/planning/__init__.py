"""PostgreSQL adapters of the planning repository ports (planning §3, §6, §11; DDL ``0008``..``0029``).

``REPOSITORIES`` maps each implemented port to its factory over the unit-of-work connection; it is
merged with the core table by ``bootstrap.adapters.postgres_repository_table``.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.planning.counters import PostgresPlanCounters
from skm.adapters.postgres.planning.drafts import PostgresDraftRepository
from skm.adapters.postgres.planning.plans import PostgresPlanRepository
from skm.adapters.postgres.planning.queries import PostgresPlanningQueries
from skm.adapters.postgres.planning.revisions import PostgresRevisionRepository
from skm.modules.planning.ports import (
    DraftRepository,
    PlanCounters,
    PlanningQueries,
    PlanRepository,
    RevisionRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        PlanRepository: PostgresPlanRepository,
        PlanCounters: PostgresPlanCounters,
        DraftRepository: PostgresDraftRepository,
        RevisionRepository: PostgresRevisionRepository,
        PlanningQueries: PostgresPlanningQueries,
    }
)
