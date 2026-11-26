"""outbox_relay service: ticks one bounded relay pass (kernel-platform §4.5, §6).

The delivery algorithm and its pass (``application_bus.subscribers.OutboxRelayPass``) are built by bootstrap
and handed in here, so this layer stays free of bus internals. The pass covers subscribers, ``sse``, external
consumers and the dead-row notifications of their ``on_dead``. A pass that handled rows asks for the next
tick at once; an idle pass waits for the configured interval.
"""

from collections.abc import Mapping
from typing import Any, Protocol

from .service_runner import BackgroundService, TickResult

__all__ = ["OutboxRelay", "OutboxRelayService", "RelayPass"]


class OutboxRelay(BackgroundService, Protocol):
    name: str = "outbox_relay"


class RelayPass(Protocol):
    def run_once(self) -> Mapping[Any, int]:
        """One bounded pass; the outcome counts of the rows it handled."""
        ...


class OutboxRelayService:
    name: str = "outbox_relay"

    def __init__(self, relay: RelayPass) -> None:
        self._relay = relay

    def tick(self) -> TickResult:
        processed = sum(self._relay.run_once().values())
        return TickResult(processed, 0.0 if processed else None)
