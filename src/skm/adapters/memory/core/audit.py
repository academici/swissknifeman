"""``AuditLog`` and ``ConsumerReceipts`` over the memory state."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime

from skm.adapters.memory.core.state import MemoryBackendState
from skm.application_bus.ports import AuditRecord, OutboxState
from skm.kernel.ids import EventId

__all__ = ["MemoryAuditLog", "MemoryConsumerReceipts"]


class MemoryAuditLog:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core

    def append(self, record: AuditRecord) -> None:
        self._core.require_writable()
        self._core.audit.append(replace(record, target=deepcopy(record.target)))


class MemoryConsumerReceipts:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core

    def seen(self, consumer_id: str, event_id: EventId) -> bool:
        return (consumer_id, event_id) in self._core.consumer_receipts

    def add(self, consumer_id: str, event_id: EventId, at: datetime) -> None:
        """A second receipt of the same pair keeps the first (``ON CONFLICT DO NOTHING``)."""
        self._core.require_writable()
        self._core.consumer_receipts.setdefault((consumer_id, event_id), at)

    def purge(self, *, before: datetime, limit: int) -> int:
        self._core.require_writable()
        # A receipt guards against a redelivery: keep it while its outbox row is still undelivered.
        undelivered = {
            (row.destination, row.event_id)
            for row in self._core.outbox.values()
            if row.state is not OutboxState.DELIVERED
        }
        old = [
            pair
            for pair, at in self._core.consumer_receipts.items()
            if at < before and pair not in undelivered
        ]
        removed = old[: max(limit, 0)]
        for pair in removed:
            del self._core.consumer_receipts[pair]
        return len(removed)
