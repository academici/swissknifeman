"""``deliver``, ``OutboxRelayPass`` and the relay service over the memory backend (kernel-platform §4.5).

The outbox store contract on both backends is ``tests/contracts/core/test_outbox.py``; here are the rules of
the delivery algorithm itself: the settings slice and backoff, the causal context of a subscriber, the event
scope its config comes from, the compare-and-set on the claimant, the routing and the bounded pass.
"""

import inspect
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast, override

import pytest

from fakes.app import FakeConfig, FakeConfigLoader, FakeGateways
from fakes.demo_module import ON_ECHOED, PERMISSIONS, Echo, Echoed, manifest
from skm.application_bus.context import SubscriberContext
from skm.application_bus.ports import ConsumerReceipts, OutboxItem, OutboxStore
from skm.application_bus.registry import BusRegistry
from skm.application_bus.subscribers import (
    DeliveryOutcome,
    DeliverySettings,
    OutboxRelayPass,
    backoff,
    deliver,
)
from skm.background.outbox_relay import OutboxRelayService
from skm.kernel.errors import Conflict
from skm.kernel.events import EventEnvelope
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.platform.logging.logger import get_logger
from support.backend import MemoryTestBackend

CONSUMER = ON_ECHOED.consumer_id
SETTINGS = DeliverySettings(max_attempts=3, backoff_seconds=60, backoff_max_seconds=600)


@pytest.fixture
def backend() -> Iterator[MemoryTestBackend]:
    made = MemoryTestBackend()
    try:
        yield made
    finally:
        made.close()


def registry_with(backend: MemoryTestBackend, handler: Callable[..., None], **changes: Any) -> BusRegistry:
    spec: Any = replace(ON_ECHOED, handler=handler, **changes)
    return BusRegistry.build(
        (manifest(subscribers=(spec,)),),
        schemas=backend.schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )


def echo(backend: MemoryTestBackend, text: str = "sub") -> EventEnvelope:
    backend.app().dispatch(Echo(workspace_id=backend.seed.workspace_id, text=text))
    return backend.envelopes(workspace_id=backend.seed.workspace_id)[-1]


def claim(backend: MemoryTestBackend, relay_id: str = "relay-1", destination: str = CONSUMER) -> OutboxItem:
    with backend.uow() as uow:
        (item,) = uow.repo(OutboxStore).claim(
            destination=destination, relay_id=relay_id, now=backend.clock.now(), limit=1
        )
        uow.commit()
    return item


def run(
    backend: MemoryTestBackend,
    item: OutboxItem,
    handler: Callable[..., None],
    *,
    config: Any = None,
    settings: DeliverySettings = SETTINGS,
    relay_id: str = "relay-1",
    **changes: Any,
) -> DeliveryOutcome:
    return deliver(
        item,
        registry=registry_with(backend, handler, **changes),
        uow_factory=backend.uow_factory,
        config=config or cast("Any", FakeConfigLoader()),
        delivery=settings,
        clock=backend.clock,
        ids=backend.ids,
        gateways=cast("Any", FakeGateways()),
        log=get_logger("tests.subscribers"),
        relay_id=relay_id,
        jitter=lambda: 0.5,  # no jitter: the back-off below is exact
    )


def state(backend: MemoryTestBackend, destination: str = CONSUMER) -> list[tuple[str, int, str | None]]:
    rows = backend.memory.committed.core.outbox.values()
    return [(row.state.value, row.attempts, row.last_error) for row in rows if row.destination == destination]


def nothing(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    pass


# ------------------------------------------------------------------------------------- settings and backoff


def test_backoff_doubles_from_the_base_up_to_the_maximum_within_ten_percent() -> None:
    settings = DeliverySettings(backoff_seconds=2, backoff_max_seconds=30)
    assert [backoff(n, settings).total_seconds() for n in (1, 2, 3, 4, 5, 6)] == [2, 4, 8, 16, 30, 30]
    assert backoff(1, settings, 0.0).total_seconds() == pytest.approx(1.8)
    assert backoff(1, settings, 1.0).total_seconds() == pytest.approx(2.2)
    assert backoff(10_000, settings, 2.0) == timedelta(seconds=33)  # jitter is clamped, no overflow
    assert backoff(0, settings) == timedelta(seconds=2)


def test_settings_come_from_events_delivery_and_keep_defaults_for_invalid_values() -> None:
    config = FakeConfig({"events.delivery.max_attempts": 4, "events.delivery.backoff_seconds": True})
    settings = DeliverySettings.from_config(cast("Any", config))
    assert settings == DeliverySettings(max_attempts=4)


# -------------------------------------------------------------------------------------------------- deliver


def test_a_subscriber_runs_in_the_event_scope_with_the_events_causal_context(
    backend: MemoryTestBackend,
) -> None:
    parent = echo(backend)
    item = claim(backend)
    scopes: list[ScopeRef | None] = []
    seen: list[SubscriberContext] = []

    class Loader(FakeConfigLoader):
        @override
        def effective(self, store: Any, scopes_: Any, scope: Any, kind: str = "work", **_: Any) -> FakeConfig:
            scopes.append(scope)
            return super().effective(store, scopes_, scope, kind)

    def follow_up(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        seen.append(ctx)
        uow.record(Echoed(workspace_id=backend.seed.workspace_id, text="follow-up"))
        assert isinstance(ctx.config_for(workspace), FakeConfig)

    workspace = ScopeRef(kind=ScopeKind.WORKSPACE, id=cast("Any", backend.seed.workspace_id))
    assert run(backend, item, follow_up, config=Loader()) is DeliveryOutcome.DELIVERED
    assert scopes == [workspace, workspace]  # the context config, then the subscriber's config_for
    (ctx,) = seen
    assert (ctx.consumer_id, ctx.attempt) == (CONSUMER, 1)
    child = backend.envelopes(workspace_id=backend.seed.workspace_id)[-1]
    assert child.correlation_id == parent.correlation_id
    assert child.parent_causation_id == str(parent.id)  # the verified committed parent, not a client id
    assert child.causation_id is not None
    assert child.causation_id.startswith("req_")
    assert child.causation_id != parent.causation_id


def test_the_receipt_the_effect_and_the_mark_commit_together(backend: MemoryTestBackend) -> None:
    parent = echo(backend)
    item = claim(backend)
    assert run(backend, item, nothing) is DeliveryOutcome.DELIVERED
    assert state(backend) == [("delivered", 1, None)]
    assert (CONSUMER, parent.id) in backend.memory.committed.core.consumer_receipts


def test_a_failure_rolls_back_and_records_failed_with_a_safe_error(backend: MemoryTestBackend) -> None:
    echo(backend)
    item = claim(backend)

    def failing(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        uow.repo(ConsumerReceipts).add("demo.other", envelope.id, ctx.clock.now())
        raise Conflict(cast("Any", "ALREADY_EXISTS"), "token=hunter2")

    assert run(backend, item, failing) is DeliveryOutcome.FAILED
    ((status, attempts, error),) = state(backend)
    assert (status, attempts) == ("failed", 1)
    assert error == "Conflict: ALREADY_EXISTS"
    assert "hunter2" not in error
    assert backend.memory.committed.core.consumer_receipts == {}  # the subscriber's write rolled back
    row = next(iter(backend.memory.committed.core.outbox.values()))
    assert row.available_at == backend.clock.now() + backoff(1, SETTINGS)
    assert row.claimed_by is None


@pytest.mark.parametrize("relay", [deliver, OutboxRelayPass.__init__])
def test_the_relay_jitters_its_back_off_by_default(relay: Callable[..., object]) -> None:
    # kernel-platform §4.5: the retry delay is the doubled back-off ±10 % jitter, so relays desynchronise
    draw = inspect.signature(relay).parameters["jitter"].default
    draws = {draw() for _ in range(32)}
    assert len(draws) > 1
    assert all(0.0 <= value <= 1.0 for value in draws)
    lowest, highest = backoff(3, SETTINGS, 0.0), backoff(3, SETTINGS, 1.0)
    assert lowest < backoff(3, SETTINGS) < highest


def test_the_spec_max_attempts_narrows_the_dead_threshold(backend: MemoryTestBackend) -> None:
    echo(backend)
    item = claim(backend)

    def failing(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        raise RuntimeError("boom")

    assert run(backend, item, failing, max_attempts=1) is DeliveryOutcome.DEAD
    assert state(backend) == [("dead", 1, "RuntimeError")]


def test_a_taken_over_claim_commits_nothing(backend: MemoryTestBackend) -> None:
    echo(backend)
    stale = claim(backend, "relay-1")
    backend.clock.advance(timedelta(seconds=61))
    claim(backend, "relay-2")
    calls: list[object] = []
    assert run(backend, stale, lambda *args: calls.append(args)) is DeliveryOutcome.STALE
    assert calls == []
    assert state(backend) == [("pending", 2, None)]


def test_a_missing_event_is_a_delivery_failure(backend: MemoryTestBackend) -> None:
    echo(backend)
    item = replace(claim(backend), event_id=cast("Any", backend.ids.new_id()))
    assert run(backend, item, nothing) is DeliveryOutcome.FAILED
    assert state(backend) == [("failed", 1, "LookupError")]


def test_sse_needs_no_receipt_and_an_unrouted_destination_is_a_dead_letter(
    backend: MemoryTestBackend,
) -> None:
    echo(backend)
    sse = claim(backend, destination="sse")
    assert run(backend, sse, nothing) is DeliveryOutcome.DELIVERED
    assert state(backend, "sse") == [("delivered", 1, None)]
    assert backend.memory.committed.core.consumer_receipts == {}
    item = claim(backend, destination=CONSUMER)
    unrouted = replace(item, destination="demo.unknown")
    assert run(backend, unrouted, nothing) is DeliveryOutcome.DEAD
    assert state(backend) == [("dead", 1, "destination_unrouted")]


# --------------------------------------------------------------------------------- the pass and the service


def test_the_pass_rereads_settings_and_rotates_destinations(backend: MemoryTestBackend) -> None:
    for n in range(3):
        echo(backend, f"rotate-{n}")
    reads: list[int] = []

    def settings() -> DeliverySettings:
        reads.append(1)
        return SETTINGS

    worker = OutboxRelayPass(
        registry=registry_with(backend, nothing),
        uow_factory=backend.uow_factory,
        config=cast("Any", FakeConfigLoader()),
        settings=settings,
        clock=backend.clock,
        ids=backend.ids,
        gateways=cast("Any", FakeGateways()),
        log=get_logger("tests.subscribers"),
        relay_id="relay-1",
        batch_size=2,
    )
    assert worker.run_once() == {DeliveryOutcome.DELIVERED: 2}  # one row of each destination
    assert worker.run_once() == {DeliveryOutcome.DELIVERED: 2}  # wrapped around to the start
    assert worker.run_once() == {DeliveryOutcome.DELIVERED: 2}
    assert worker.run_once() == {}
    assert len(reads) == 4
    with pytest.raises(ValueError, match="batch_size"):
        OutboxRelayPass(
            registry=registry_with(backend, nothing),
            uow_factory=backend.uow_factory,
            config=cast("Any", FakeConfigLoader()),
            settings=settings,
            clock=backend.clock,
            ids=backend.ids,
            gateways=cast("Any", FakeGateways()),
            log=get_logger("tests.subscribers"),
            relay_id="relay-1",
            batch_size=0,
        )


def test_the_service_ticks_one_pass_and_waits_when_idle() -> None:
    passes = iter([{DeliveryOutcome.DELIVERED: 2, DeliveryOutcome.FAILED: 1}, {}])

    class Pass:
        def run_once(self) -> dict[DeliveryOutcome, int]:
            return next(passes)

    service = OutboxRelayService(Pass())
    assert service.name == "outbox_relay"
    busy = service.tick()
    assert (busy.processed, busy.next_delay_seconds) == (3, 0.0)
    idle = service.tick()
    assert (idle.processed, idle.next_delay_seconds) == (0, None)
