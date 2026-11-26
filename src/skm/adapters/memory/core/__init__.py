"""Memory adapters of the core repository ports (adapters §2.1).

``REPOSITORIES`` maps each core port to its factory over the backend state; ``InMemoryBackend`` merges it
with the tables of the module adapters. ``ConfigStore`` is not here: ``adapters/memory/config_store.py``
owns it.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.audit import MemoryAuditLog, MemoryConsumerReceipts
from skm.adapters.memory.core.events import MemoryEventReader
from skm.adapters.memory.core.idempotency import MemoryIdempotencyStore
from skm.adapters.memory.core.outbox import MemoryOutboxStore
from skm.adapters.memory.core.scopes import MemoryScopeRegistry, MemoryScopeTree
from skm.adapters.memory.core.state import MemoryBackendState
from skm.application_bus.ports import AuditLog, ConsumerReceipts, EventReader, IdempotencyStore, OutboxStore
from skm.kernel.scopes import ScopeRegistry
from skm.platform.config.store import ScopeTree

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        AuditLog: MemoryAuditLog,
        ConsumerReceipts: MemoryConsumerReceipts,
        EventReader: MemoryEventReader,
        IdempotencyStore: MemoryIdempotencyStore,
        OutboxStore: MemoryOutboxStore,
        ScopeRegistry: MemoryScopeRegistry,
        ScopeTree: MemoryScopeTree,
    }
)
