"""Transactional delivery of one claimed outbox row and its dead notification.

``deliver`` (kernel-platform §4.5) hands one claimed outbox row to its in-process subscriber or to the SSE
feed; ``OutboxRelayPass`` is one bounded pass of the relay over the due destinations. Delivery is
at-least-once and the subscriber is idempotent through ``ConsumerReceipts``: the relay checks and adds the
receipt in the subscriber's own unit of work, with the subscriber's effects and the ``delivered`` mark, so a
redelivery never runs an effect twice. The ``delivered`` mark is a compare-and-set on the claimant taken
before the handler runs: it locks the row for the transaction, and a relay whose claim was taken over rolls
back instead of committing a second effect. A failure rolls the delivery back and records ``failed`` (with
the exponential backoff of ``events.delivery.*``) or, after ``max_attempts``, ``dead`` in a new short unit of
work.

External consumers (``<prefix>:<id>``, kernel-platform §4.5) deliver in three steps so that no transaction or
lock is held across the external call: a read-only unit of work reads the receipt, the envelope and the
consumer's ``prepare`` plan; ``send`` runs outside every transaction; a new unit of work marks the row (a
compare-and-set on the claimant) and adds the receipt. A crash between ``send`` and the mark repeats the
delivery (at-least-once). ``RetryAt`` fails with the consumer's own time, ``GiveUp`` is ``dead`` at once. A
row that became ``dead`` is announced by a separate bounded pass: ``claim_dead_notifications`` takes it in a
short unit of work, ``spec.on_dead`` builds the internal command, the bus dispatches it as the system actor
with the key ``dead:<id>:<delivery_generation>:<attempts>`` and ``mark_dead_notified`` (a compare-and-set on
relay, generation and ``claimed_at``) closes it. ``retry_dead`` raises the generation, so a new death never
meets the old idempotency receipt and a late notifier of the old one changes nothing. A failing ``on_dead``
defers the notification by ``events.delivery.backoff_max_seconds``, keeping the delivery error.
``SubscriberContext.config_for`` reads the work chain of any scope of the event workspace in the delivery
unit of work; a scope of another workspace is ``NotFound``.
"""

import math
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, Protocol, cast

from skm.application_bus.client import new_request_id
from skm.application_bus.context import ExternalConsumerContext, SubscriberContext
from skm.application_bus.ports import (
    ConsumerReceipts,
    DeliveryPlan,
    EventReader,
    ExternalConsumer,
    GiveUp,
    OutboxItem,
    OutboxState,
    OutboxStore,
    RetryAt,
    Sent,
)
from skm.application_bus.registry import (
    SSE_DESTINATION,
    BusRegistry,
    ExternalConsumerSpec,
    SubscriberSpec,
)
from skm.kernel.actor import Actor
from skm.kernel.cancel import CancelSource, CancelToken
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError
from skm.kernel.events import EventEnvelope
from skm.kernel.gateways import Gateways
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import Isolation, RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.logging.logger import StructLogger

_CLIENT: Final = "outbox-relay"
_JITTER: Final = 0.1  # backoff ± 10 % (adapters §1.4)
_UNROUTED: Final = "destination_unrouted"
_NOTIFY_FAILED: Final = " | on_dead_failed: "  # a failed notification is appended to the delivery error
_DEAD_PAGE: Final = 100


class DeliveryOutcome(StrEnum):
    DELIVERED = "delivered"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED = "failed"
    DEAD = "dead"
    STALE = "stale"  # the claim was taken over by another relay; nothing of this delivery was committed
    DEAD_NOTIFIED = "dead_notified"  # ``spec.on_dead`` was dispatched and the row closed
    DEAD_NOTIFICATION_DEFERRED = "dead_notification_deferred"  # ``on_dead`` failed; the row waits


@dataclass(frozen=True, slots=True)
class DeliverySettings:
    """The ``events.delivery.*`` slice (instance, live); the relay reads it again on every pass."""

    max_attempts: int = 10
    backoff_seconds: int = 2
    backoff_max_seconds: int = 3600
    timeout_seconds: int = 30
    visibility_timeout_seconds: int = 300

    @classmethod
    def from_config(cls, config: EffectiveConfig) -> "DeliverySettings":
        defaults = cls()  # slots: the class attributes are descriptors, not the defaults

        def number(key: str) -> int:
            value = config.get(f"events.delivery.{key}")
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            default: int = getattr(defaults, key)
            return default

        return cls(
            max_attempts=number("max_attempts"),
            backoff_seconds=number("backoff_seconds"),
            backoff_max_seconds=number("backoff_max_seconds"),
            timeout_seconds=number("timeout_seconds"),
            visibility_timeout_seconds=number("visibility_timeout_seconds"),
        )

    def attempts_of(self, spec: SubscriberSpec) -> int:
        """``SubscriberSpec.max_attempts`` only narrows ``events.delivery.max_attempts``, never widens it."""
        return self.max_attempts if spec.max_attempts is None else min(spec.max_attempts, self.max_attempts)


def backoff(attempts: int, settings: DeliverySettings, jitter: float = 0.5) -> timedelta:
    """``min(backoff_seconds · 2^(attempts-1), backoff_max_seconds)`` ± 10 %; ``jitter`` 0.5 is none."""
    exponent = max(attempts, 1) - 1
    base = settings.backoff_seconds * math.pow(2, min(exponent, 64))
    delay = min(base, float(settings.backoff_max_seconds))
    factor = 1 + _JITTER * (2 * min(max(jitter, 0.0), 1.0) - 1)
    return timedelta(seconds=max(delay * factor, 0.0))


class EventConfigLoader(Protocol):
    """What delivery needs of ``ConfigLoader``: the effective config of the event scope, delivery UoW."""

    def effective(self, store: ConfigStore, scopes: ScopeTree, scope: ScopeRef | None) -> EffectiveConfig: ...


class CommandDispatcher(Protocol):
    """What the relay needs of the bus to announce a dead row: ``Bus.dispatch``."""

    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> object: ...


class ExternalConsumers:
    """The consumers of the registry's ``ExternalConsumerSpec``s, each built once per relay process.

    A factory that fails is retried at the next delivery instead of stopping the relay: the row it served
    fails with backoff and the other destinations go on.
    """

    def __init__(self, context: ExternalConsumerContext) -> None:
        self._context = context
        self._built: dict[str, ExternalConsumer] = {}
        self._lock = threading.Lock()

    def get(self, spec: ExternalConsumerSpec) -> ExternalConsumer:
        with self._lock:
            consumer = self._built.get(spec.prefix)
            if consumer is None:
                consumer = spec.factory(self._context)
                self._built[spec.prefix] = consumer
            return consumer


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    """What every delivery of one relay shares."""

    registry: BusRegistry
    uow_factory: UnitOfWorkFactory
    config: EventConfigLoader
    clock: Clock
    ids: IdGenerator
    gateways: Gateways
    log: StructLogger
    relay_id: str
    jitter: Callable[[], float]
    externals: ExternalConsumers | None = None
    cancel: CancelToken = field(default_factory=lambda: CancelSource().token)


def delivery_meta(
    shared: DeliveryContext, envelope: EventEnvelope | None, *, key: str | None = None
) -> RequestMeta:
    """Own request id; causality comes from the committed envelope, never from client-supplied ids."""
    return RequestMeta(
        new_request_id(shared.ids),
        Surface.BACKGROUND,
        key,
        shared.clock.now(),
        client=_CLIENT,
        correlation_id=None if envelope is None else envelope.correlation_id,
        causation_id=None if envelope is None else str(envelope.id),
    )


def _event_scope(envelope: EventEnvelope) -> ScopeRef | None:
    if envelope.workspace_id is None:
        return None
    return ScopeRef(kind=ScopeKind.WORKSPACE, id=ScopeId(envelope.workspace_id))


def _config_for(
    shared: DeliveryContext, uow: UnitOfWork, envelope: EventEnvelope
) -> Callable[[ScopeRef], EffectiveConfig]:
    """``SubscriberContext.config_for``: the work chain of a scope of the event workspace, in this UoW.

    The instance scope is allowed (every chain starts there); a scope of another workspace, an unknown scope
    and a kind that does not match the record are ``NotFound``. A host scope is refused by the loader.
    """

    def config_for(scope: ScopeRef) -> EffectiveConfig:
        record = uow.repo(ScopeRegistry).get(ScopeId(scope.id))
        foreign = record.workspace_id is not None and record.workspace_id != envelope.workspace_id
        if foreign or record.kind != scope.kind:
            raise NotFound(ErrorCode.NOT_FOUND, "scope not found", details={"kind": "scope"})
        return shared.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope)

    return config_for


def _context(
    shared: DeliveryContext, item: OutboxItem, consumer_id: str, uow: UnitOfWork, envelope: EventEnvelope
) -> SubscriberContext:
    return SubscriberContext(
        consumer_id=consumer_id,
        attempt=item.attempts,
        clock=shared.clock,
        ids=shared.ids,
        log=shared.log,
        config=shared.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), _event_scope(envelope)),
        gateways=shared.gateways,
        config_for=_config_for(shared, uow, envelope),
    )


def error_text(exc: BaseException) -> str:
    """A safe ``last_error``: the error type and, for an ``SkmError``, its code; never the message."""
    if isinstance(exc, SkmError):
        return f"{type(exc).__name__}: {exc.code.value}"
    return type(exc).__name__


def _load(shared: DeliveryContext, item: OutboxItem) -> EventEnvelope:
    """The committed envelope, read first: the delivery UoW takes its causal context from it."""
    with shared.uow_factory(delivery_meta(shared, None), readonly=True) as uow:
        found = uow.repo(EventReader).by_ids([item.event_id])
    if not found:
        raise LookupError("the event of the outbox row is missing")
    return found[0]


def _record_failure(
    shared: DeliveryContext, item: OutboxItem, error: str, *, next_at: datetime, dead: bool
) -> DeliveryOutcome:
    """The delivery was rolled back; record ``failed`` or ``dead`` in a new short unit of work.

    A dead row of an external consumer is due for its notification at once, so the caller passes ``now``.
    """
    with shared.uow_factory(delivery_meta(shared, None), isolation=Isolation.READ_COMMITTED) as uow:
        marked = uow.repo(OutboxStore).mark_failed(
            item.id, relay_id=shared.relay_id, error=error, next_at=next_at, dead=dead
        )
        if not marked:
            return DeliveryOutcome.STALE
        uow.commit()
    event = "relay.delivery.dead" if dead else "relay.delivery.failed"
    log = shared.log.warning if dead else shared.log.info
    log(
        event,
        destination=item.destination,
        event_id=str(item.event_id),
        attempt=item.attempts,
        error_type=error,
    )
    return DeliveryOutcome.DEAD if dead else DeliveryOutcome.FAILED


def _give_up(shared: DeliveryContext, item: OutboxItem, error: str) -> DeliveryOutcome:
    """``dead`` at once, due for its notification now."""
    return _record_failure(shared, item, error, next_at=shared.clock.now(), dead=True)


def _fail(
    shared: DeliveryContext,
    item: OutboxItem,
    exc: BaseException,
    *,
    max_attempts: int,
    settings: DeliverySettings,
    external: bool = False,
) -> DeliveryOutcome:
    dead = item.attempts >= max_attempts
    now = shared.clock.now()
    next_at = now if dead and external else now + backoff(item.attempts, settings, shared.jitter())
    return _record_failure(shared, item, error_text(exc), next_at=next_at, dead=dead)


def _deliver_sse(shared: DeliveryContext, item: OutboxItem) -> DeliveryOutcome:
    """No receipt: mark delivered (the adapter sends ``NOTIFY skm_events``), visible only after commit."""
    with shared.uow_factory(delivery_meta(shared, None), isolation=Isolation.READ_COMMITTED) as uow:
        if not uow.repo(OutboxStore).mark_delivered(item.id, at=shared.clock.now(), relay_id=shared.relay_id):
            return DeliveryOutcome.STALE
        uow.commit()
    return DeliveryOutcome.DELIVERED


def _deliver_subscriber(
    shared: DeliveryContext, item: OutboxItem, spec: SubscriberSpec, settings: DeliverySettings
) -> DeliveryOutcome:
    try:
        envelope = _load(shared, item)  # an event is immutable once committed
        with shared.uow_factory(delivery_meta(shared, envelope), isolation=spec.isolation) as uow:
            outbox, receipts = uow.repo(OutboxStore), uow.repo(ConsumerReceipts)
            # The CAS first: it locks the row, so no other relay claims it while this transaction is open.
            if not outbox.mark_delivered(item.id, at=shared.clock.now(), relay_id=shared.relay_id):
                return DeliveryOutcome.STALE
            if receipts.seen(item.destination, item.event_id):
                uow.commit()
                return DeliveryOutcome.SKIPPED_DUPLICATE
            spec.handler(envelope, _context(shared, item, spec.consumer_id, uow, envelope), uow)
            receipts.add(item.destination, item.event_id, shared.clock.now())
            uow.commit()
    except Exception as exc:  # noqa: BLE001 - any subscriber failure is retried with backoff (kernel §4.5 step 7)
        return _fail(shared, item, exc, max_attempts=settings.attempts_of(spec), settings=settings)
    return DeliveryOutcome.DELIVERED


def _settle(
    shared: DeliveryContext, item: OutboxItem, envelope: EventEnvelope, *, receipt: bool
) -> DeliveryOutcome:
    """A short unit of work: the CAS on the claimant first (a stale claim adds no receipt), then the receipt.

    ``receipt=False`` is the duplicate path, whose receipt exists already.
    """
    with shared.uow_factory(delivery_meta(shared, envelope), isolation=Isolation.READ_COMMITTED) as uow:
        if not uow.repo(OutboxStore).mark_delivered(item.id, at=shared.clock.now(), relay_id=shared.relay_id):
            return DeliveryOutcome.STALE
        if receipt:
            uow.repo(ConsumerReceipts).add(item.destination, item.event_id, shared.clock.now())
        uow.commit()
    return DeliveryOutcome.DELIVERED if receipt else DeliveryOutcome.SKIPPED_DUPLICATE


def _external_attempts(
    spec: ExternalConsumerSpec, plan: DeliveryPlan | None, settings: DeliverySettings
) -> int:
    """``plan.max_attempts`` (a hook's own retry policy), else the spec's, else ``events.delivery.*``."""
    if plan is not None and plan.max_attempts is not None:
        return plan.max_attempts
    return (
        settings.max_attempts if spec.max_attempts is None else min(spec.max_attempts, settings.max_attempts)
    )


def _prepare(
    shared: DeliveryContext, item: OutboxItem, envelope: EventEnvelope, consumer: ExternalConsumer
) -> tuple[bool, DeliveryPlan | None]:
    """The read-only unit of work: ``(seen, plan)``; the connection is back in the pool when this returns."""
    with shared.uow_factory(delivery_meta(shared, envelope), readonly=True) as uow:
        if uow.repo(ConsumerReceipts).seen(item.destination, item.event_id):
            return True, None
        ctx = _context(shared, item, item.destination, uow, envelope)
        return False, consumer.prepare(item, envelope, ctx, uow)


def _deliver_external(
    shared: DeliveryContext, item: OutboxItem, spec: ExternalConsumerSpec, settings: DeliverySettings
) -> DeliveryOutcome:
    attempts = _external_attempts(spec, None, settings)
    try:
        if shared.externals is None:
            raise LookupError("the relay has no external consumers")
        consumer = shared.externals.get(spec)
        envelope = _load(shared, item)
        seen, plan = _prepare(shared, item, envelope, consumer)
        if seen:
            return _settle(shared, item, envelope, receipt=False)
        if plan is None:  # nothing to deliver: the receipt and the mark close the row
            return _settle(shared, item, envelope, receipt=True)
        attempts = _external_attempts(spec, plan, settings)
        timeout = settings.timeout_seconds if plan.timeout_seconds is None else plan.timeout_seconds
        # Outside every transaction and lock: a crash from here to the mark below repeats the delivery.
        result = consumer.send(plan, attempt=item.attempts, timeout_seconds=timeout, cancel=shared.cancel)
        match result:
            case Sent():
                return _settle(shared, item, envelope, receipt=True)
            case RetryAt(next_at=next_at, error=error):
                if item.attempts >= attempts:
                    return _give_up(shared, item, error)
                return _record_failure(shared, item, error, next_at=next_at, dead=False)
            case GiveUp(error=error):
                return _give_up(shared, item, error)
            case _:
                raise TypeError("ExternalConsumer.send returned an unknown result")
    except Exception as exc:  # noqa: BLE001 - prepare/send failures are retried with backoff (kernel §4.5)
        return _fail(shared, item, exc, max_attempts=attempts, settings=settings, external=True)


def route_delivery(shared: DeliveryContext, item: OutboxItem, settings: DeliverySettings) -> DeliveryOutcome:
    """``sse``, an in-process subscriber, an external consumer; a destination that routes nowhere is dead."""
    if item.destination == SSE_DESTINATION:
        return _deliver_sse(shared, item)
    target = shared.registry.route(item.destination)
    if isinstance(target, SubscriberSpec):
        return _deliver_subscriber(shared, item, target, settings)
    if isinstance(target, ExternalConsumerSpec):
        return _deliver_external(shared, item, target, settings)
    return _give_up(shared, item, _UNROUTED)


def deliver(  # noqa: PLR0913 - the relay passes every collaborator explicitly
    item: OutboxItem,
    *,
    registry: BusRegistry,
    uow_factory: UnitOfWorkFactory,
    config: EventConfigLoader,
    delivery: DeliverySettings,
    clock: Clock,
    ids: IdGenerator,
    gateways: Gateways,
    log: StructLogger,
    relay_id: str,
    jitter: Callable[[], float] = random.random,
    externals: ExternalConsumers | None = None,
    cancel: CancelToken | None = None,
) -> DeliveryOutcome:
    """Deliver one row ``relay_id`` claimed: ``sse``, an in-process subscriber or an external consumer.

    A destination that routes nowhere is ``dead`` with ``destination_unrouted`` (kernel-platform §4.5).
    """
    shared = DeliveryContext(
        registry,
        uow_factory,
        config,
        clock,
        ids,
        gateways,
        log,
        relay_id,
        jitter,
        externals,
        CancelSource().token if cancel is None else cancel,
    )
    return route_delivery(shared, item, delivery)


def _dead_reason(shared: DeliveryContext, item: OutboxItem) -> str:
    """The stored delivery error of a dead row, without the note of an earlier failed notification."""
    after: str | None = None
    with shared.uow_factory(delivery_meta(shared, None), readonly=True) as uow:
        store = uow.repo(OutboxStore)
        while True:
            page = store.list(
                destination_prefix=item.destination,
                state=OutboxState.DEAD,
                workspace_id=None,
                after=after,
                limit=_DEAD_PAGE,
            )
            for entry in page.items:
                if entry.id == item.id:
                    return (entry.last_error or "dead").split(_NOTIFY_FAILED, 1)[0]
            if page.next is None:
                return "dead"
            after = str(page.next)


def notify_dead(
    shared: DeliveryContext,
    item: OutboxItem,
    spec: ExternalConsumerSpec,
    settings: DeliverySettings,
    dispatcher: CommandDispatcher,
    actor: Actor,
) -> DeliveryOutcome:
    """One claimed dead row: dispatch ``on_dead`` once, then close it with the generation/claim CAS."""
    assert spec.on_dead is not None  # noqa: S101 - only prefixes with on_dead are claimed
    try:
        envelope = _load(shared, item)
        plan = _replan(shared, item, envelope, spec)
        reason = _dead_reason(shared, item)
        command = spec.on_dead(item, plan, reason)
        key = f"dead:{item.id}:{item.delivery_generation}:{item.attempts}"
        dispatcher.dispatch(command, actor=actor, meta=delivery_meta(shared, envelope, key=key))
    except Exception as exc:  # noqa: BLE001 - a failing on_dead never stops the other notifications
        return _defer_dead(shared, item, exc, settings)
    with shared.uow_factory(delivery_meta(shared, None), isolation=Isolation.READ_COMMITTED) as uow:
        closed = uow.repo(OutboxStore).mark_dead_notified(
            item.id,
            relay_id=shared.relay_id,
            generation=item.delivery_generation,
            claimed_at=item.claimed_at,
            at=shared.clock.now(),
        )
        if not closed:  # taken over, or retried and dead again in a newer generation
            return DeliveryOutcome.STALE
        uow.commit()
    shared.log.info("relay.dead_notified", destination=item.destination, event_id=str(item.event_id))
    return DeliveryOutcome.DEAD_NOTIFIED


def _replan(
    shared: DeliveryContext, item: OutboxItem, envelope: EventEnvelope, spec: ExternalConsumerSpec
) -> DeliveryPlan | None:
    """The plan the consumer would deliver now; ``None`` when it has none or cannot prepare one."""
    try:
        return _prepare(shared, item, envelope, cast("ExternalConsumers", shared.externals).get(spec))[1]
    except Exception as exc:  # noqa: BLE001 - the notification goes out without a plan
        shared.log.info(
            "relay.dead_notification.no_plan", destination=item.destination, error_type=error_text(exc)
        )
        return None


def _defer_dead(
    shared: DeliveryContext, item: OutboxItem, exc: BaseException, settings: DeliverySettings
) -> DeliveryOutcome:
    """Keep the delivery error, note the failure and wait ``backoff_max_seconds``; no send is repeated."""
    note = error_text(exc)
    try:
        reason = _dead_reason(shared, item)
    except Exception:  # noqa: BLE001 - the notification still waits; only the stored reason is generic
        reason = "dead"
    with shared.uow_factory(delivery_meta(shared, None), isolation=Isolation.READ_COMMITTED) as uow:
        now = shared.clock.now()
        deferred = uow.repo(OutboxStore).defer_dead_notification(
            item.id,
            relay_id=shared.relay_id,
            generation=item.delivery_generation,
            claimed_at=item.claimed_at,
            next_at=now + timedelta(seconds=max(1, settings.backoff_max_seconds)),
            error=f"{reason}{_NOTIFY_FAILED}{note}",
        )
        if not deferred:
            return DeliveryOutcome.STALE
        uow.commit()
    shared.log.warning("relay.dead_notification.failed", destination=item.destination, error_type=note)
    return DeliveryOutcome.DEAD_NOTIFICATION_DEFERRED
