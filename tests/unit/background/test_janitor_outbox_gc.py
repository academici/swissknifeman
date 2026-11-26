"""``outbox_gc`` (kernel-platform §6): delivered rows and unguarded receipts past the retention.

Cases run over the ``backend`` fixture (memory ∥ postgres, ``pg`` marker; ``SKM_REQUIRE_PG=1`` makes a
missing server a failure). Rows are made for instance events with explicit ``hook:*`` destinations and moved
into their states through the store, so ``delivered_at`` and the receipt times are what a case says.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.app import FakeConfigLoader
from fakes.demo_module import Noted
from skm.application_bus.outbox_gc import OutboxGc
from skm.application_bus.ports import ConsumerReceipts, OutboxState, OutboxStore
from skm.kernel.ids import EventId
from skm.kernel.ports_uow import RequestMeta, UnitOfWork, UnitOfWorkFactory
from support import backend as backend_support
from support import pg as pg_support
from support.backend import PostgresTestBackend, TestBackend

# Fixtures by name: pytest finds them through the names this module holds.
backend = backend_support.backend
pg_backend = backend_support.pg_backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

NOTE_STREAM = UUID("01900000-0000-7000-8000-0000000000c3")
RETENTION_KEY = "events.outbox.delivered_retention_hours"
HOUR = timedelta(hours=1)


class CountingFactory:
    """A unit-of-work factory that counts the writable units of work (one per batch)."""

    def __init__(self, inner: UnitOfWorkFactory) -> None:
        self._inner = inner
        self.writable = 0

    @contextmanager
    def __call__(self, meta: RequestMeta, **options: Any) -> Iterator[UnitOfWork]:
        if not options.get("readonly", False):
            self.writable += 1
        with self._inner(meta, **options) as uow:
            yield uow


def start(backend: TestBackend) -> datetime:
    """On PostgreSQL the test clock starts at the database clock (the adapter never lets time go back)."""
    if backend.kind == "postgres":
        (row,) = cast("PostgresTestBackend", backend).execute("SELECT clock_timestamp()")
        backend.clock.set(cast("datetime", row[0]))
    return backend.clock.now()


def make_row(backend: TestBackend, name: str) -> tuple[UUID, EventId]:
    """A pending ``hook:<name>`` row claimed by ``relay-1``: (the outbox id, the event id)."""
    with backend.uow() as uow:
        uow.record(Noted(stream=NOTE_STREAM, text=name))
        uow.commit()
    event_id = backend.envelopes()[-1].id
    with backend.uow() as uow:
        uow.outbox.enqueue(event_id, f"hook:{name}")
        uow.commit()
    with backend.uow() as uow:
        (item,) = uow.repo(OutboxStore).claim(
            destination=f"hook:{name}", relay_id="relay-1", now=backend.clock.now(), limit=1
        )
        uow.commit()
    return item.id, event_id


def add_receipt(backend: TestBackend, name: str, event_id: EventId, at: datetime) -> None:
    with backend.uow() as uow:
        uow.repo(ConsumerReceipts).add(f"hook:{name}", event_id, at)
        uow.commit()


def gc(
    backend: TestBackend, values: dict[str, Any] | None = None, *, batch: int = 1000, factory: Any = None
) -> OutboxGc:
    return OutboxGc(
        uow_factory=factory or backend.uow_factory,
        config=cast("Any", FakeConfigLoader(values or {})),
        clock=backend.clock,
        ids=backend.ids,
        batch_size=batch,
    )


def remaining(backend: TestBackend) -> dict[str, str]:
    return {row.destination: row.state for row in backend.outbox_rows()}


def receipts_left(backend: TestBackend) -> int:
    return backend.table_counts("skm_core")["consumer_receipts"]


def test_only_delivered_rows_older_than_the_retention_go_and_unguarded_receipts_with_them(
    backend: TestBackend,
) -> None:
    t0 = start(backend)
    ids = {name: make_row(backend, name) for name in "abcdeg"}
    with backend.uow() as uow:
        store = uow.repo(OutboxStore)
        assert store.mark_delivered(ids["a"][0], at=t0, relay_id="relay-1")  # delivered long ago
        assert store.mark_delivered(ids["b"][0], at=t0 + 150 * HOUR, relay_id="relay-1")  # delivered recently
        assert store.mark_failed(
            ids["d"][0], relay_id="relay-1", error="x", next_at=t0 + 900 * HOUR, dead=False
        )
        assert store.mark_failed(
            ids["e"][0], relay_id="relay-1", error="x", next_at=t0 + 900 * HOUR, dead=True
        )
        uow.commit()
    # c and g stay pending (claimed, never marked): g has no receipt at all.
    for name in "abcde":  # every row has an old receipt, except that b's is recent
        add_receipt(backend, name, ids[name][1], t0 + (150 * HOUR if name == "b" else timedelta()))
    orphan = backend.envelopes()[-1].id  # a receipt of a pair without any outbox row
    add_receipt(backend, "orphan", orphan, t0)
    events_before = backend.table_counts("skm_core")["domain_events"]
    assert receipts_left(backend) == 6

    backend.clock.set(t0 + 200 * HOUR)  # cutoff: t0 + 32 h with the default 168 h
    assert gc(backend).run() == 1 + 2  # the delivered row a; the receipts of a and of the orphan pair
    assert remaining(backend) == {
        "hook:b": "delivered",
        "hook:c": "pending",
        "hook:d": "failed",
        "hook:e": "dead",
        "hook:g": "pending",
    }
    assert receipts_left(backend) == 4  # b (recent), c, d, e (their rows still guard them)
    assert backend.table_counts("skm_core")["domain_events"] == events_before
    assert gc(backend).run() == 0  # a second run finds nothing


def test_a_pair_with_an_undelivered_row_keeps_its_old_receipt_until_the_row_is_delivered_and_old(
    backend: TestBackend,
) -> None:
    t0 = start(backend)
    row, event_id = make_row(backend, "late")
    add_receipt(backend, "late", event_id, t0)
    backend.clock.set(t0 + 400 * HOUR)
    assert gc(backend).run() == 0  # pending: the receipt still guards against a redelivery
    with backend.uow() as uow:
        assert uow.repo(OutboxStore).mark_delivered(row, at=backend.clock.now(), relay_id="relay-1")
        uow.commit()
    gc(backend).run()  # delivered just now: the row is within the retention and stays
    assert remaining(backend) == {"hook:late": "delivered"}
    backend.clock.advance(169 * HOUR)
    gc(backend).run()
    assert remaining(backend) == {}
    assert receipts_left(backend) == 0
    assert gc(backend).run() == 0


@pytest.mark.parametrize(
    ("value", "purged"),
    [(24, True), (200, False), (True, False), (0, False), (9000, False), ("1", False), (None, False)],
)
def test_the_retention_comes_from_the_instance_config_and_invalid_values_keep_168_hours(
    backend: TestBackend, value: object, purged: bool
) -> None:
    t0 = start(backend)
    row, _ = make_row(backend, "cfg")
    with backend.uow() as uow:
        assert uow.repo(OutboxStore).mark_delivered(row, at=t0, relay_id="relay-1")
        uow.commit()
    backend.clock.set(t0 + 30 * HOUR)  # older than 24 h, younger than 168 h
    values = {} if value is None else {RETENTION_KEY: value}
    assert gc(backend, values).run() == (1 if purged else 0)
    assert (remaining(backend) == {}) is purged


def test_a_large_backlog_is_removed_in_batches_of_short_units_of_work(backend: TestBackend) -> None:
    t0 = start(backend)
    rows = [make_row(backend, f"n{n}") for n in range(5)]
    with backend.uow() as uow:
        for row, _ in rows:
            assert uow.repo(OutboxStore).mark_delivered(row, at=t0, relay_id="relay-1")
        uow.commit()
    backend.clock.set(t0 + 200 * HOUR)
    factory = CountingFactory(backend.uow_factory)
    assert gc(backend, batch=2, factory=factory).run() == 5
    assert 3 <= factory.writable <= 4  # 2 + 2 + 1 rows, plus optional empty receipts batch
    assert backend.outbox_rows() == []


def test_a_dead_row_is_never_purged_however_old(backend: TestBackend) -> None:
    t0 = start(backend)
    row, event_id = make_row(backend, "dead")
    with backend.uow() as uow:
        assert uow.repo(OutboxStore).mark_failed(row, relay_id="relay-1", error="x", next_at=t0, dead=True)
        uow.commit()
    add_receipt(backend, "dead", event_id, t0)
    backend.clock.set(t0 + 24 * 365 * HOUR)
    assert gc(backend, {RETENTION_KEY: 1}).run() == 0
    assert remaining(backend) == {"hook:dead": OutboxState.DEAD.value}
    assert receipts_left(backend) == 1
