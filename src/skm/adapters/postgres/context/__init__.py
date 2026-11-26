"""PostgreSQL adapters of the context repository ports (context §§6, 11; DDL ``0019``)."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.context.repositories import PostgresContextRepository, PostgresTextStore
from skm.adapters.postgres.context.research import PostgresResearchRepository
from skm.modules.context.ports import ContextRepository, ResearchRepository, TextStore

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        ContextRepository: PostgresContextRepository,
        ResearchRepository: PostgresResearchRepository,
        TextStore: PostgresTextStore,
    }
)
