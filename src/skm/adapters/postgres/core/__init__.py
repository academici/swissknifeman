"""PostgreSQL adapters of the core repository ports (adapters §1.1).

``REPOSITORIES`` maps each core port to its factory over the unit-of-work connection. The idempotency and
audit adapters are not in this table: ``bootstrap.composition`` binds them with their own dependencies.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.core.consumer_receipts import PostgresConsumerReceipts
from skm.adapters.postgres.core.events_store import PostgresEventReader
from skm.adapters.postgres.core.outbox import PostgresOutboxStore
from skm.adapters.postgres.core.scopes import PostgresScopeRegistry, PostgresScopeTree
from skm.application_bus.ports import ConsumerReceipts, EventReader, OutboxStore
from skm.kernel.scopes import ScopeRegistry
from skm.platform.config.store import ScopeTree

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        ConsumerReceipts: PostgresConsumerReceipts,
        EventReader: PostgresEventReader,
        OutboxStore: PostgresOutboxStore,
        ScopeRegistry: PostgresScopeRegistry,
        ScopeTree: PostgresScopeTree,
    }
)
