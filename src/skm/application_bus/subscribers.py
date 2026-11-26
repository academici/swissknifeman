"""Bounded outbox relay passes and the control-plane event sink contract."""

import random
from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import NoReturn, Protocol, override

from skm.application_bus.context import ExternalConsumerContext
from skm.application_bus.ports import OutboxItem, OutboxStore
from skm.application_bus.registry import BusRegistry, ExternalConsumerSpec
from skm.kernel.actor import Actor
from skm.kernel.cancel import CancelSource, CancelToken
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.events import EventEnvelope
from skm.kernel.gateways import Gateways, control_plane_gateway
from skm.kernel.id_generator import IdGenerator
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import Isolation, UnitOfWorkFactory
from skm.platform.config.secrets import SecretResolver
from skm.platform.logging.logger import StructLogger

from ._outbox_delivery import (
    CommandDispatcher,
    DeliveryContext,
    DeliveryOutcome,
    DeliverySettings,
    EventConfigLoader,
    ExternalConsumers,
    backoff,
    deliver,
    delivery_meta,
    error_text,
    notify_dead,
    route_delivery,
)

__all__ = [
    "CommandDispatcher",
    "DeliveryOutcome",
    "DeliverySettings",
    "EventConfigLoader",
    "EventSink",
    "EventSinkRegistry",
    "ExternalConsumers",
    "OutboxRelayPass",
    "SinkDeliveryResult",
    "backoff",
    "deliver",
]


class OutboxRelayPass:
    """One relay process: bounded passes over the due destinations (kernel-platform §4.5, "Progress").

    Each pass asks for the due destinations after a rotating cursor (wrapping at the end), gives every one
    an equal share of ``batch_size`` claims and advances the cursor after each destination, so a poison
    backlog of one destination never starves another. Claims commit in their own short unit of work before
    delivery. The destinations are the subscribers' consumer ids, ``sse`` and the prefixes of the registry's
    external consumers. After the normal delivery a separate pass of at most ``dead_batch_size`` announces the
    due dead rows of the prefixes that declare ``on_dead``; it needs ``dispatcher`` and ``actor``.
    """

    def __init__(  # noqa: PLR0913 - the composition root passes every collaborator explicitly
        self,
        *,
        registry: BusRegistry,
        uow_factory: UnitOfWorkFactory,
        config: EventConfigLoader,
        settings: Callable[[], DeliverySettings],
        clock: Clock,
        ids: IdGenerator,
        gateways: Gateways,
        log: StructLogger,
        relay_id: str,
        batch_size: int,
        jitter: Callable[[], float] = random.random,
        secrets: SecretResolver | None = None,
        dispatcher: CommandDispatcher | None = None,
        actor: Actor | None = None,
        cancel: CancelToken | None = None,
        dead_batch_size: int | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if dead_batch_size is not None and dead_batch_size < 1:
            raise ValueError("dead_batch_size must be positive")
        external = registry.external_consumers()
        if external and secrets is None:
            raise ValueError("external consumers need a SecretResolver")
        announcing = frozenset(prefix for prefix, spec in external.items() if spec.on_dead is not None)
        if announcing and (dispatcher is None or actor is None):
            raise ValueError("on_dead notifications need a dispatcher and an actor")
        token = CancelSource().token if cancel is None else cancel
        consumers = (
            None
            if secrets is None or not external
            else ExternalConsumers(ExternalConsumerContext(log, clock, secrets, gateways))
        )
        self._shared = DeliveryContext(
            registry, uow_factory, config, clock, ids, gateways, log, relay_id, jitter, consumers, token
        )
        self._settings = settings
        self._batch = batch_size
        self._dead_batch = batch_size if dead_batch_size is None else dead_batch_size
        self._consumers = frozenset(spec.consumer_id for spec in registry.subscribers())
        self._prefixes = frozenset(external)
        self._announcing = announcing
        self._dispatcher = dispatcher
        self._actor = actor
        self._cursor: str | None = None

    def _due(self) -> tuple[str, ...]:
        shared = self._shared
        with shared.uow_factory(delivery_meta(shared, None), readonly=True) as uow:
            store = uow.repo(OutboxStore)
            found = store.due_destinations(
                consumer_ids=self._consumers,
                prefixes=self._prefixes,
                include_sse=True,
                now=shared.clock.now(),
                after=self._cursor,
                limit=self._batch,
            )
            if not found and self._cursor is not None:  # the end of the ring: wrap around
                self._cursor = None
                found = store.due_destinations(
                    consumer_ids=self._consumers,
                    prefixes=self._prefixes,
                    include_sse=True,
                    now=shared.clock.now(),
                    after=None,
                    limit=self._batch,
                )
        return found

    def _claim(self, destination: str, limit: int) -> tuple[OutboxItem, ...]:
        shared = self._shared
        with shared.uow_factory(delivery_meta(shared, None), isolation=Isolation.READ_COMMITTED) as uow:
            items = uow.repo(OutboxStore).claim(
                destination=destination, relay_id=shared.relay_id, now=shared.clock.now(), limit=limit
            )
            uow.commit()
        return items

    def _claim_dead(self) -> tuple[OutboxItem, ...]:
        shared = self._shared
        with shared.uow_factory(delivery_meta(shared, None), isolation=Isolation.READ_COMMITTED) as uow:
            items = uow.repo(OutboxStore).claim_dead_notifications(
                prefixes=self._announcing,
                relay_id=shared.relay_id,
                now=shared.clock.now(),
                limit=self._dead_batch,
            )
            uow.commit()
        return items

    def _announce(self, settings: DeliverySettings, counts: dict[DeliveryOutcome, int]) -> None:
        """The bounded dead-notification pass; one failing row never stops the others."""
        shared, dispatcher, actor = self._shared, self._dispatcher, self._actor
        if not self._announcing or dispatcher is None or actor is None:
            return
        for item in self._claim_dead():
            spec = shared.registry.route(item.destination)
            if not isinstance(spec, ExternalConsumerSpec) or spec.on_dead is None:
                continue
            try:
                outcome = notify_dead(shared, item, spec, settings, dispatcher, actor)
            except Exception as exc:  # noqa: BLE001 - the claim expires and the row is announced again
                shared.log.warning(
                    "relay.dead_notification.error", destination=item.destination, error_type=error_text(exc)
                )
                continue
            counts[outcome] = counts.get(outcome, 0) + 1

    def run_once(self) -> dict[DeliveryOutcome, int]:
        """One pass; the outcome counts of the rows it handled (empty when nothing was due)."""
        settings = self._settings()
        destinations = self._due()
        counts: dict[DeliveryOutcome, int] = {}
        shared = self._shared
        if destinations:
            share = max(1, self._batch // len(destinations))
            for destination in destinations:
                for item in self._claim(destination, share):
                    outcome = route_delivery(shared, item, settings)
                    counts[outcome] = counts.get(outcome, 0) + 1
                self._cursor = destination
        self._announce(settings, counts)
        return counts


class SinkDeliveryResult(Protocol):
    """Outcome of one ``EventSink.deliver``; integrations §6.3 ``DeliveryResult`` has these fields."""

    @property
    def ok(self) -> bool: ...

    @property
    def retryable(self) -> bool: ...

    @property
    def reason(self) -> str | None: ...

    @property
    def status(self) -> int | None: ...

    @property
    def retry_after_ms(self) -> int | None: ...

    @property
    def response_excerpt(self) -> str | None:  # <= 2048 characters, no headers
        ...


class EventSink(Protocol):
    """Delivers one envelope to an external system; idempotent by ``envelope.id`` (the receiver dedupes)."""

    sink_id: str

    def deliver(self, envelope: EventEnvelope, config: Mapping[str, JsonValue]) -> SinkDeliveryResult:
        """Called outside any transaction; ``config`` holds resolved secret values, never logged."""
        ...

    def config_schema(self) -> str:
        """URN of the schema of ``target.config`` of this sink."""
        ...


@control_plane_gateway
class EventSinkRegistry:
    """``sink_id`` -> ``EventSink``; immutable after construction."""

    __slots__ = ("_sinks",)

    _sinks: Mapping[str, EventSink]

    def __init__(self, sinks: Iterable[EventSink]) -> None:
        found: dict[str, EventSink] = {}
        problems: list[str] = []
        for sink in sinks:
            sink_id: object = getattr(sink, "sink_id", None)
            if not isinstance(sink_id, str) or not sink_id:
                problems.append(f"{type(sink).__name__}: sink_id must be a non-empty string")
            elif sink_id in found:
                problems.append(f"duplicate sink_id {sink_id!r}")
            else:
                found[sink_id] = sink
        if problems:
            raise ValueError("event sink registry is invalid:\n- " + "\n- ".join(problems))
        object.__setattr__(self, "_sinks", MappingProxyType(found))

    @override
    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"EventSinkRegistry is immutable: cannot set {name!r}")

    @override
    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError(f"EventSinkRegistry is immutable: cannot delete {name!r}")

    def get(self, sink_id: str) -> EventSink:
        """A missing sink (plugin disabled or not loaded) is ``CAPABILITY_UNAVAILABLE``."""
        sink = self._sinks.get(sink_id)
        if sink is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"event sink {sink_id!r} is not available",
                details={"capability": "event_sink", "sink_id": sink_id, "reason_code": "not_registered"},
            )
        return sink

    def has(self, sink_id: str) -> bool:
        return sink_id in self._sinks

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._sinks))
