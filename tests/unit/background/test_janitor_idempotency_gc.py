"""``idempotency_gc`` and the janitor service that ticks it with ``outbox_gc`` (kernel-platform §6).

Cases run over the ``backend`` fixture (memory ∥ postgres, ``pg`` marker; ``SKM_REQUIRE_PG=1`` makes a
missing server a failure). The cutoff is the clock's now: a receipt is purged once its ``expires_at`` has
passed, a live one is kept, and a second run finds nothing. A PostgreSQL receipt gets its times from the
database clock (``put`` keeps only the TTL), so the cases age receipts by moving the janitor's clock.
"""

from datetime import datetime, timedelta
from typing import Any, cast

import pytest

from fakes.app import FakeConfigLoader
from skm.application_bus.outbox_gc import IdempotencyGc, OutboxGc
from skm.application_bus.ports import IdempotencyReceipt, IdempotencyStore
from skm.background.janitor import JanitorService
from skm.background.service_runner import TickResult
from skm.platform.logging.logger import get_logger
from support import backend as backend_support
from support import pg as pg_support
from support.backend import PostgresTestBackend, TestBackend

# Fixtures by name: pytest finds them through the names this module holds.
backend = backend_support.backend
pg_backend = backend_support.pg_backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

HOUR = timedelta(hours=1)


def start(backend: TestBackend) -> datetime:
    """On PostgreSQL the test clock starts at the database clock (the adapter never lets time go back)."""
    if backend.kind == "postgres":
        (row,) = cast("PostgresTestBackend", backend).execute("SELECT clock_timestamp()")
        backend.clock.set(cast("datetime", row[0]))
    return backend.clock.now()


def put(backend: TestBackend, key: str, *, ttl: timedelta) -> None:
    now = backend.clock.now()
    with backend.uow() as uow:
        uow.repo(IdempotencyStore).put(
            IdempotencyReceipt(
                workspace_id=backend.seed.workspace_id,
                principal_id=backend.seed.principal_id,
                operation="demo.echo",
                key=key,
                request_digest="sha256:" + "0" * 64,
                result={"text": key},
                created_at=now,
                expires_at=now + ttl,
            )
        )
        uow.commit()


def alive(backend: TestBackend) -> int:
    return backend.table_counts("skm_core")["idempotency_receipts"]


def gc(backend: TestBackend, *, batch: int = 1000) -> IdempotencyGc:
    return IdempotencyGc(
        uow_factory=backend.uow_factory, clock=backend.clock, ids=backend.ids, batch_size=batch
    )


def test_only_expired_receipts_are_purged_and_a_repeat_is_a_no_op(backend: TestBackend) -> None:
    start(backend)
    put(backend, "old-1", ttl=HOUR)
    put(backend, "old-2", ttl=2 * HOUR)
    put(backend, "live-1", ttl=5 * HOUR)
    put(backend, "live-2", ttl=48 * HOUR)
    assert alive(backend) == 4
    assert gc(backend).run() == 0  # nothing has expired yet
    backend.clock.advance(3 * HOUR)
    assert gc(backend).run() == 2
    assert alive(backend) == 2
    with backend.uow(readonly=True) as uow:
        store = uow.repo(IdempotencyStore)
        for key in ("live-1", "live-2"):
            found = store.get(backend.seed.workspace_id, backend.seed.principal_id, "demo.echo", key)
            assert found is not None
            assert found.result == {"text": key}  # the live receipts are intact
    assert gc(backend).run() == 0
    assert alive(backend) == 2
    backend.clock.advance(24 * HOUR)  # live-1 expires with the clock, live-2 does not
    assert gc(backend).run() == 1
    assert alive(backend) == 1


def test_nothing_happens_on_an_empty_store(backend: TestBackend) -> None:
    start(backend)
    assert gc(backend).run() == 0
    assert alive(backend) == 0


def test_a_large_backlog_is_purged_in_batches(backend: TestBackend) -> None:
    start(backend)
    for n in range(5):
        put(backend, f"old-{n}", ttl=HOUR)
    put(backend, "live", ttl=48 * HOUR)
    backend.clock.advance(2 * HOUR)
    assert gc(backend, batch=2).run() == 5
    assert alive(backend) == 1


def test_a_batch_size_must_be_positive(backend: TestBackend) -> None:
    with pytest.raises(ValueError, match="positive"):
        gc(backend, batch=0)


class Boom:
    name = "boom"

    def run(self) -> int:
        raise RuntimeError("secret-token-1234")


def test_the_janitor_ticks_both_tasks_and_a_failing_task_does_not_stop_the_others(
    backend: TestBackend,
) -> None:
    start(backend)
    put(backend, "old", ttl=HOUR)
    backend.clock.advance(2 * HOUR)
    janitor = JanitorService(
        [
            Boom(),
            gc(backend),
            OutboxGc(
                uow_factory=backend.uow_factory,
                config=cast("Any", FakeConfigLoader()),
                clock=backend.clock,
                ids=backend.ids,
            ),
        ],
        log=get_logger("tests.janitor"),
    )
    with pytest.raises(RuntimeError):  # the first failure is raised after every task ran
        janitor.tick()
    assert alive(backend) == 0  # idempotency_gc ran after the failing task
    healthy = JanitorService([gc(backend)], log=get_logger("tests.janitor"))
    put(backend, "old-again", ttl=HOUR)
    backend.clock.advance(2 * HOUR)
    assert healthy.tick() == TickResult(1)
    assert healthy.tick() == TickResult(0)
    assert janitor.name == "janitor"


def test_janitor_task_names_are_unique(backend: TestBackend) -> None:
    with pytest.raises(ValueError, match="unique"):
        JanitorService([gc(backend), gc(backend)], log=get_logger("tests.janitor"))
