"""Outbox store, consumer receipts, the relay pass and the platform outbox operations (memory ∥ postgres).

Every case runs over the ``backend`` fixture: the memory backend and ``PostgresUnitOfWork`` on the cleaned
session test database (``pg`` marker; ``SKM_REQUIRE_PG=1`` makes a missing server a failure). Events come from
the real ``demo.echo`` command, so each one has a ``demo.on_echoed`` row and an ``sse`` row. Time is the
backend's ``FrozenClock``; on PostgreSQL it starts at the database's clock, and the adapter takes the later of
the caller's time and ``clock_timestamp()``, so advancing the clock moves both backends past a boundary. The
PostgreSQL-only cases (``pg_backend``) prove what memory does not model: the fresh database time of a claim
made late in an old transaction, ``NOTIFY`` only after commit and two relays running at the same time.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from functools import cache
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.app import FakeConfigLoader, FakeGateways, FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from fakes.demo_module import ON_ECHOED, PERMISSIONS, Echo, Echoed, manifest
from fakes.entropy import DeterministicEntropy
from skm.adapters.postgres.core.outbox import PostgresOutboxStore
from skm.adapters.postgres.uow import PostgresUnitOfWork
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.context import SubscriberContext
from skm.application_bus.ports import ConsumerReceipts, OutboxItem, OutboxState, OutboxStore
from skm.application_bus.registry import BusRegistry
from skm.application_bus.subscribers import DeliveryOutcome, DeliverySettings, OutboxRelayPass
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import EventId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.platform.generated.commands import RetryOutbox
from skm.platform.generated.queries import ListDeadOutbox
from skm.platform.generated.results import ListDeadOutboxResult, RetryOutboxResult
from skm.platform.logging.logger import get_logger
from skm.platform.schema.registry import SchemaRegistry
from support import backend as backend_support
from support import pg as pg_support
from support.backend import PostgresTestBackend, TestBackend

# Fixtures by name: pytest finds them through the names this module holds.
backend = backend_support.backend
pg_backend = backend_support.pg_backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

CONSUMER = ON_ECHOED.consumer_id
EXPIRED = timedelta(seconds=301)  # past the claim expiry of both adapters (memory 60 s, PostgreSQL 300 s)
# Backoff long enough that a row is never due again by accident while a test runs.
SETTINGS = DeliverySettings(max_attempts=3, backoff_seconds=60, backoff_max_seconds=600)
DUE_AGAIN = timedelta(seconds=SETTINGS.backoff_max_seconds * 1.2)


# -------------------------------------------------------------------------------------------------- helpers


def start(backend: TestBackend) -> None:
    """On PostgreSQL the test clock starts at the database clock (the adapter never lets time go back)."""
    if backend.kind == "postgres":
        (row,) = cast("PostgresTestBackend", backend).execute("SELECT clock_timestamp()")
        backend.clock.set(cast("datetime", row[0]))


def echo(backend: TestBackend, text: str = "outbox") -> EventId:
    backend.app().dispatch(Echo(workspace_id=backend.seed.workspace_id, text=text))
    return backend.envelopes(workspace_id=backend.seed.workspace_id)[-1].id


def rows(backend: TestBackend, destination: str = CONSUMER) -> list[tuple[str, int]]:
    return [(row.state, row.attempts) for row in backend.outbox_rows() if row.destination == destination]


def effects(backend: TestBackend) -> int:
    """The subscriber effect is a project scope; the seed has only the instance and two workspaces."""
    return backend.table_counts("skm_core")["scopes"] - 3


def project_effect(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    workspace = envelope.workspace_id
    assert workspace is not None
    uow.repo(ScopeRegistry).create(
        ScopeId(ctx.ids.new_id()), ScopeKind.PROJECT, parent=ScopeId(workspace), workspace_id=workspace
    )


def failing(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    project_effect(envelope, ctx, uow)  # written, then rolled back with the failure
    raise RuntimeError("subscriber failed: secret-token-1234")


def registry_with(backend: TestBackend, handler: Callable[..., None]) -> BusRegistry:
    spec: Any = replace(ON_ECHOED, handler=handler)
    return BusRegistry.build(
        (manifest(subscribers=(spec,)),),
        schemas=backend.schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )


def relay(
    backend: TestBackend,
    handler: Callable[..., None] = project_effect,
    *,
    relay_id: str = "relay-1",
    batch: int = 100,
    settings: DeliverySettings = SETTINGS,
) -> OutboxRelayPass:
    return OutboxRelayPass(
        registry=registry_with(backend, handler),
        uow_factory=backend.uow_factory,
        config=cast("Any", FakeConfigLoader()),
        settings=lambda: settings,
        clock=backend.clock,
        ids=backend.ids,
        gateways=cast("Any", FakeGateways()),
        log=get_logger("tests.outbox_relay"),
        relay_id=relay_id,
        batch_size=batch,
    )


@cache
def _platform_schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def platform_bus(backend: TestBackend, *, allowed: frozenset[str] | None = None) -> Bus:
    schemas = _platform_schemas()
    registry = BusRegistry.build(
        (PLATFORM_MANIFEST,),
        schemas=schemas,
        permission_catalog=PLATFORM_MANIFEST.permissions,
        disabled_modules=frozenset(),
    )
    return Bus(
        registry=registry,
        schemas=schemas,
        uow_factory=backend.uow_factory,
        authorizer=FakeAuthorizer(allowed),
        scopes=FakeScopeChain(),
        config=cast("Any", FakeConfigLoader()),
        clock=backend.clock,
        ids=backend.ids,
        entropy=DeterministicEntropy(),
        gateways=cast("Any", FakeGateways()),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=24),
    )


def claim(backend: TestBackend, relay_id: str, destination: str = CONSUMER) -> tuple[OutboxItem, ...]:
    with backend.uow() as uow:
        items = uow.repo(OutboxStore).claim(
            destination=destination, relay_id=relay_id, now=backend.clock.now(), limit=10
        )
        uow.commit()
    return items


def kill(backend: TestBackend, item: OutboxItem, relay_id: str = "relay-1") -> None:
    """The row of ``item`` (claimed by ``relay_id``) becomes dead."""
    with backend.uow() as uow:
        assert uow.repo(OutboxStore).mark_failed(
            item.id, relay_id=relay_id, error="GiveUp", next_at=backend.clock.now(), dead=True
        )
        uow.commit()


# ------------------------------------------------------------------------------------------------ the store


def test_a_claimed_row_is_hidden_from_another_relay_until_the_claim_expires(backend: TestBackend) -> None:
    start(backend)
    echo(backend)
    (first,) = claim(backend, "relay-1")
    assert first.attempts == 1
    assert claim(backend, "relay-2") == ()  # live claim: no second claimant
    backend.clock.advance(timedelta(seconds=30))
    assert claim(backend, "relay-2") == ()
    backend.clock.advance(EXPIRED)  # relay-1 crashed after its claim: the row is claimed again
    (again,) = claim(backend, "relay-2")
    assert (again.id, again.attempts) == (first.id, 2)
    assert again.claimed_at >= first.claimed_at + EXPIRED


def test_a_stale_claimant_marks_nothing(backend: TestBackend) -> None:
    start(backend)
    echo(backend)
    (stale,) = claim(backend, "relay-1")
    backend.clock.advance(EXPIRED)
    (fresh,) = claim(backend, "relay-2")
    with backend.uow() as uow:
        store = uow.repo(OutboxStore)
        now = backend.clock.now()
        assert not store.mark_delivered(stale.id, at=now, relay_id="relay-1")
        assert not store.mark_failed(stale.id, relay_id="relay-1", error="late", next_at=now, dead=True)
        assert store.mark_delivered(fresh.id, at=now, relay_id="relay-2")
        assert not store.mark_delivered(fresh.id, at=now, relay_id="relay-2")  # already delivered
        uow.commit()
    assert rows(backend) == [("delivered", 2)]


def test_marking_an_unknown_row_is_not_found(backend: TestBackend) -> None:
    with backend.uow() as uow, pytest.raises(NotFound):
        uow.repo(OutboxStore).mark_failed(
            UUID(int=7), relay_id="relay-1", error="x", next_at=backend.clock.now(), dead=False
        )


def test_due_destinations_keyset_routes_only_registered_selectors(backend: TestBackend) -> None:
    start(backend)
    echo(backend)
    with backend.uow(readonly=True) as uow:
        store = uow.repo(OutboxStore)
        now = backend.clock.now()

        def due(consumers: frozenset[str], *, sse: bool, after: str | None = None) -> tuple[str, ...]:
            return store.due_destinations(
                consumer_ids=consumers, prefixes=frozenset(), include_sse=sse, now=now, after=after, limit=10
            )

        assert due(frozenset({CONSUMER}), sse=True) == (CONSUMER, "sse")
        assert due(frozenset({CONSUMER}), sse=True, after=CONSUMER) == ("sse",)
        assert due(frozenset(), sse=False) == ()  # unregistered consumers are never claimed
        assert due(frozenset({"demo.other"}), sse=False) == ()


def test_retry_dead_requeues_only_dead_rows_with_a_new_generation(backend: TestBackend) -> None:
    start(backend)
    echo(backend, "one")
    echo(backend, "two")
    first, second = claim(backend, "relay-1")
    kill(backend, first)
    with backend.uow() as uow:
        store = uow.repo(OutboxStore)
        with pytest.raises(ValueError, match="filter"):
            store.retry_dead(outbox_id=None, event_id=None, destination=None, now=backend.clock.now())
        assert (
            store.retry_dead(outbox_id=second.id, event_id=None, destination=None, now=backend.clock.now())
            == 0
        )
        assert (
            store.retry_dead(outbox_id=None, event_id=None, destination=CONSUMER, now=backend.clock.now())
            == 1
        )
        uow.commit()
    assert sorted(rows(backend)) == [("pending", 0), ("pending", 1)]  # the claimed live row keeps its claim
    backend.clock.advance(EXPIRED)
    again = {item.id: item for item in claim(backend, "relay-2")}
    assert again[first.id].delivery_generation == first.delivery_generation + 1
    assert again[second.id].delivery_generation == second.delivery_generation


def test_list_dead_pages_operator_entries_by_cursor(backend: TestBackend) -> None:
    start(backend)
    for text in ("a", "b", "c"):
        echo(backend, text)
    claimed = claim(backend, "relay-1")
    for item in claimed:
        kill(backend, item)
    with backend.uow(readonly=True) as uow:
        store = uow.repo(OutboxStore)
        first = store.list_dead(after=None, limit=2)
        assert len(first.items) == 2
        assert first.next is not None
        rest = store.list_dead(after=first.next, limit=2)
        assert len(rest.items) == 1
        assert rest.next is None
        everything = store.list(
            destination_prefix="demo.", state=None, workspace_id=None, after=None, limit=10
        )
        other = store.list(
            destination_prefix="",
            state=None,
            workspace_id=backend.seed.other_workspace_id,
            after=None,
            limit=10,
        )
    entries = (*first.items, *rest.items)
    assert sorted(entry.id for entry in entries) == sorted(item.id for item in claimed)
    assert all(entry.state is OutboxState.DEAD and entry.last_error == "GiveUp" for entry in entries)
    assert all(entry.destination == CONSUMER and entry.attempts == 1 for entry in entries)
    assert len(everything.items) == 3
    assert other.items == ()


def test_dead_notification_claims_are_compare_and_set_on_relay_generation_and_time(
    backend: TestBackend,
) -> None:
    start(backend)
    event_id = echo(backend)
    with backend.uow() as uow:
        uow.outbox.enqueue(event_id, "hook:sub1")
        uow.commit()
    (item,) = claim(backend, "relay-1", "hook:sub1")
    kill(backend, item)
    with backend.uow() as uow:
        store = uow.repo(OutboxStore)
        now = backend.clock.now()
        assert store.claim_dead_notifications(prefixes=frozenset(), relay_id="n1", now=now, limit=5) == ()
        (notice,) = store.claim_dead_notifications(
            prefixes=frozenset({"hook"}), relay_id="n1", now=now, limit=5
        )
        assert (
            store.claim_dead_notifications(prefixes=frozenset({"hook"}), relay_id="n2", now=now, limit=5)
            == ()
        )
        generation, claimed_at = notice.delivery_generation, notice.claimed_at
        assert not store.mark_delivered(
            notice.id, at=now, relay_id="n1"
        )  # a notification claim delivers nothing
        assert not store.mark_dead_notified(
            notice.id, relay_id="n1", generation=generation + 1, claimed_at=claimed_at, at=now
        )
        assert not store.mark_dead_notified(
            notice.id, relay_id="n2", generation=generation, claimed_at=claimed_at, at=now
        )
        assert store.defer_dead_notification(
            notice.id, relay_id="n1", generation=generation, claimed_at=claimed_at, next_at=now, error="busy"
        )
        uow.commit()
    with backend.uow() as uow:
        store = uow.repo(OutboxStore)
        (notice,) = store.claim_dead_notifications(
            prefixes=frozenset({"hook"}), relay_id="n2", now=backend.clock.now(), limit=5
        )
        assert store.mark_dead_notified(
            notice.id,
            relay_id="n2",
            generation=notice.delivery_generation,
            claimed_at=notice.claimed_at,
            at=backend.clock.now(),
        )
        assert (
            store.claim_dead_notifications(
                prefixes=frozenset({"hook"}), relay_id="n3", now=backend.clock.now() + EXPIRED, limit=5
            )
            == ()
        )
        uow.commit()


def test_receipts_are_idempotent_and_purge_keeps_those_of_undelivered_rows(backend: TestBackend) -> None:
    start(backend)
    pending = echo(backend, "pending")
    with backend.uow() as uow:
        receipts = uow.repo(ConsumerReceipts)
        now = backend.clock.now()
        receipts.add(CONSUMER, pending, now)
        receipts.add(CONSUMER, pending, now + timedelta(hours=1))  # the first receipt stays
        assert receipts.seen(CONSUMER, pending)
        assert not receipts.seen("demo.other", pending)
        uow.commit()
    with backend.uow() as uow:
        later = backend.clock.now() + timedelta(days=2)
        assert uow.repo(ConsumerReceipts).purge(before=later, limit=10) == 0  # its row is not delivered yet
        uow.commit()
    relay(backend).run_once()  # the row is delivered as a duplicate (the receipt exists)
    with backend.uow() as uow:
        assert uow.repo(ConsumerReceipts).purge(before=backend.clock.now() + timedelta(days=2), limit=10) == 1
        uow.commit()
    assert backend.table_counts("skm_core")["consumer_receipts"] == 0


# ------------------------------------------------------------------------------------------------ the relay


def test_a_row_is_delivered_after_commit_and_never_before(backend: TestBackend) -> None:
    start(backend)
    worker = relay(backend)
    with backend.uow() as uow:
        uow.record(Echoed(workspace_id=backend.seed.workspace_id, text="rolled back"))
        listed = uow.repo(OutboxStore).list(
            destination_prefix="", state=None, workspace_id=None, after=None, limit=10
        )
        assert listed.items == ()  # the rows are written by the commit, with the event
        if backend.kind == "postgres":  # memory admits one open unit of work at a time
            assert worker.run_once() == {}  # an uncommitted event is invisible to the relay
    assert worker.run_once() == {}  # rolled back: nothing to deliver
    echo(backend)
    assert worker.run_once() == {DeliveryOutcome.DELIVERED: 2}  # demo.on_echoed and sse
    assert rows(backend) == [("delivered", 1)]
    assert rows(backend, "sse") == [("delivered", 1)]
    assert effects(backend) == 1
    assert backend.table_counts("skm_core")["consumer_receipts"] == 1  # sse rows take no receipt
    assert worker.run_once() == {}


def test_a_failing_subscriber_retries_with_backoff_then_dies_after_max_attempts(backend: TestBackend) -> None:
    start(backend)
    echo(backend)
    worker = relay(backend, failing)
    assert worker.run_once() == {DeliveryOutcome.FAILED: 1, DeliveryOutcome.DELIVERED: 1}
    assert rows(backend) == [("failed", 1)]
    assert effects(backend) == 0  # the effect rolled back
    assert worker.run_once() == {}  # backoff: not due yet
    backend.clock.advance(DUE_AGAIN)
    assert worker.run_once() == {DeliveryOutcome.FAILED: 1}
    backend.clock.advance(DUE_AGAIN)
    assert worker.run_once() == {DeliveryOutcome.DEAD: 1}
    assert rows(backend) == [("dead", 3)]
    backend.clock.advance(DUE_AGAIN)
    assert worker.run_once() == {}  # dead rows are never claimed again
    assert effects(backend) == 0


def test_the_subscriber_max_attempts_only_narrows_the_setting() -> None:
    narrow = replace(ON_ECHOED, max_attempts=2)
    wide = replace(ON_ECHOED, max_attempts=50)
    assert SETTINGS.attempts_of(narrow) == 2
    assert SETTINGS.attempts_of(wide) == SETTINGS.max_attempts
    assert SETTINGS.attempts_of(ON_ECHOED) == SETTINGS.max_attempts


def test_a_duplicate_with_a_receipt_runs_no_effect(backend: TestBackend) -> None:
    start(backend)
    event_id = echo(backend)
    with backend.uow() as uow:
        uow.repo(ConsumerReceipts).add(
            CONSUMER, event_id, backend.clock.now()
        )  # an earlier delivery's receipt
        uow.commit()
    calls: list[EventId] = []

    def counting(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        calls.append(envelope.id)

    outcomes = relay(backend, counting).run_once()
    assert outcomes == {DeliveryOutcome.SKIPPED_DUPLICATE: 1, DeliveryOutcome.DELIVERED: 1}
    assert calls == []
    assert rows(backend) == [("delivered", 1)]


def test_a_poison_backlog_does_not_starve_a_healthy_destination(backend: TestBackend) -> None:
    start(backend)
    for n in range(12):
        echo(backend, f"poison-{n}")
    worker = relay(backend, failing, batch=4)  # 2 due destinations: 2 claims each per pass
    for _ in range(6):
        worker.run_once()
    assert [state for state, _ in rows(backend, "sse")] == ["delivered"] * 12
    assert all(state == "failed" for state, _ in rows(backend))
    assert effects(backend) == 0


# -------------------------------------------------------------------------------------- platform operations


def test_operators_list_and_requeue_dead_rows_through_the_bus(backend: TestBackend) -> None:
    start(backend)
    echo(backend)
    worker = relay(backend, failing, settings=replace(SETTINGS, max_attempts=1))
    assert worker.run_once() == {DeliveryOutcome.DEAD: 1, DeliveryOutcome.DELIVERED: 1}
    bus = platform_bus(backend)
    actor = backend.seed.actor()
    listed = bus.ask(ListDeadOutbox(limit=10), actor=actor, meta=backend.meta())
    assert isinstance(listed, ListDeadOutboxResult)
    assert listed.next is None
    (entry,) = listed.items
    assert (entry.destination, entry.attempts) == (CONSUMER, 1)
    assert entry.last_error == "RuntimeError"  # the type only: the message may hold secrets
    assert ListDeadOutboxResult.from_json(listed.to_json()) == listed

    result = bus.dispatch(RetryOutbox(outbox_id=entry.outbox_id), actor=actor, meta=backend.meta("retry-1"))
    assert result == RetryOutboxResult(requeued=1)
    assert rows(backend) == [("pending", 0)]
    again = bus.dispatch(RetryOutbox(outbox_id=entry.outbox_id), actor=actor, meta=backend.meta("retry-1"))
    assert again == RetryOutboxResult(requeued=1)  # the idempotency key replays the stored result
    assert bus.dispatch(RetryOutbox(event_id=entry.event_id), actor=actor, meta=backend.meta()) == (
        RetryOutboxResult(requeued=0)  # nothing dead is left
    )
    assert relay(backend).run_once() == {DeliveryOutcome.DELIVERED: 1}
    assert rows(backend) == [("delivered", 1)]
    assert effects(backend) == 1


def test_platform_outbox_operations_need_admin_events_and_a_selector(backend: TestBackend) -> None:
    actor = backend.seed.actor()
    denied = platform_bus(backend, allowed=frozenset({"config.read", "admin.storage"}))
    with pytest.raises(Forbidden):
        denied.ask(ListDeadOutbox(), actor=actor, meta=backend.meta())
    with pytest.raises(Forbidden):
        denied.dispatch(RetryOutbox(destination=CONSUMER), actor=actor, meta=backend.meta())
    with pytest.raises(ValidationFailed) as caught:
        platform_bus(backend).dispatch(RetryOutbox(), actor=actor, meta=backend.meta())
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(ValidationFailed):
        platform_bus(backend).ask(ListDeadOutbox(limit=201), actor=actor, meta=backend.meta())


# ------------------------------------------------------------------------------------------ PostgreSQL only


@pytest.mark.pg
def test_a_claim_late_in_an_old_transaction_uses_fresh_database_time(pg_backend: PostgresTestBackend) -> None:
    start(pg_backend)
    echo(pg_backend)
    pg_backend.execute(
        "UPDATE skm_core.outbox SET available_at = clock_timestamp() + interval '400 milliseconds' "
        "WHERE destination = %s",
        (CONSUMER,),
    )
    stale = pg_backend.clock.now()
    with pg_backend.uow() as uow:
        store = uow.repo(OutboxStore)
        assert store.claim(destination=CONSUMER, relay_id="relay-1", now=stale, limit=5) == ()
        time.sleep(0.6)  # the transaction is older than the boundary; its now() is not
        (item,) = store.claim(destination=CONSUMER, relay_id="relay-1", now=stale, limit=5)
        assert item.claimed_at > stale
        uow.commit()


@pytest.mark.pg
def test_a_claim_expires_by_database_time_not_by_the_callers_stale_sample(
    pg_backend: PostgresTestBackend,
) -> None:
    start(pg_backend)
    echo(pg_backend)
    stale = pg_backend.clock.now()
    with pg_backend.uow() as uow:
        store = PostgresOutboxStore(
            cast("PostgresUnitOfWork", uow).connection, visibility=timedelta(milliseconds=300)
        )
        (first,) = store.claim(destination=CONSUMER, relay_id="relay-1", now=stale, limit=5)
        assert store.claim(destination=CONSUMER, relay_id="relay-2", now=stale, limit=5) == ()
        time.sleep(0.5)
        (second,) = store.claim(destination=CONSUMER, relay_id="relay-2", now=stale, limit=5)
        assert second.id == first.id
        assert second.claimed_at > first.claimed_at
        uow.commit()


@pytest.mark.pg
def test_sse_notify_is_visible_only_after_the_delivery_commits(pg_backend: PostgresTestBackend) -> None:
    start(pg_backend)
    echo(pg_backend)
    (envelope,) = pg_backend.envelopes(workspace_id=pg_backend.seed.workspace_id)
    listener = pg_backend.observer
    listener.execute("LISTEN skm_events")
    (item,) = claim(pg_backend, "relay-1", "sse")
    with pg_backend.uow() as uow:
        assert uow.repo(OutboxStore).mark_delivered(item.id, at=pg_backend.clock.now(), relay_id="relay-1")
        assert list(listener.notifies(timeout=0.3, stop_after=1)) == []  # not before commit
        uow.commit()
    (notice,) = list(listener.notifies(timeout=2.0, stop_after=1))
    assert (notice.channel, notice.payload) == (
        "skm_events",
        f"{envelope.workspace_id}:{envelope.workspace_seq}",
    )


@pytest.mark.pg
def test_two_relays_in_parallel_never_run_one_effect_twice(pg_backend: PostgresTestBackend) -> None:
    start(pg_backend)
    total = 8
    for n in range(total):
        echo(pg_backend, f"parallel-{n}")
    barrier = threading.Barrier(2, timeout=10)
    seen: list[EventId] = []
    lock = threading.Lock()

    def slow_effect(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        with lock:
            seen.append(envelope.id)
        project_effect(envelope, ctx, uow)
        time.sleep(0.02)

    workers = [relay(pg_backend, slow_effect, relay_id=f"relay-{n}", batch=3) for n in (1, 2)]
    errors: list[BaseException] = []

    def run(worker: OutboxRelayPass) -> None:
        try:
            barrier.wait()
            for _ in range(10):
                worker.run_once()
        except BaseException as exc:  # noqa: BLE001 - reported by the main thread
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    assert sorted(seen) == sorted(set(seen))
    assert len(seen) == total
    assert effects(pg_backend) == total
    assert pg_backend.table_counts("skm_core")["consumer_receipts"] == total
    assert all(state == "delivered" for state, _ in rows(pg_backend))
