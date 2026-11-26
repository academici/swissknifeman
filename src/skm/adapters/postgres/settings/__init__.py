"""PostgreSQL adapters of the settings repository ports (settings §A.3, §A.11).

``REPOSITORIES`` maps each settings port to its factory over the unit-of-work connection; it is merged with
the core table by ``bootstrap.adapters.postgres_repository_table``. ``ConfigStore`` is not here (as in the
memory adapters): the composition binds ``PostgresConfigStore`` of ``adapters/postgres/config_store.py``;
``ScopeTree`` comes with the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.settings.repositories import (
    PostgresConfigEntryRepository,
    PostgresConfigGenerationCounter,
    PostgresConfigHistoryRepository,
)
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter, ConfigHistoryRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        ConfigEntryRepository: PostgresConfigEntryRepository,
        ConfigHistoryRepository: PostgresConfigHistoryRepository,
        ConfigGenerationCounter: PostgresConfigGenerationCounter,
    }
)
