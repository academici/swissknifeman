"""Commit-order event allocation under concurrency (ADR 0017, adapters §1.4, kernel §8 "Instance feed").

Feed positions are allocated under counter row locks held until COMMIT, so a cursor reader never skips an
event that commits later with a smaller number. ``_GatedWriter`` pauses a unit of work after allocation and
before COMMIT; other sessions are then observed while it holds its counter locks. Lock-order tests hold one
counter row from a third session and probe the next row with ``FOR UPDATE NOWAIT``: the probe succeeds only if
no writer took that row before the held one. Each such test fails for a writer that allocates without the lock
or in another order.
"""

import os
import random
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, LiteralString, override
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fakes.app import request_id
from fakes.clock import FrozenClock
from fakes.demo_module import SCHEMA_ROOT, Echoed, Noted
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core import REPOSITORIES
from skm.adapters.postgres.core.events_store import ExplicitOutboxRow, PostgresEventWriter
from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.ports import EventReader
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.schema.registry import SchemaRegistry

pytestmark = pytest.mark.pg

FACTORIES = REPOSITORIES
_WAIT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class StreamEchoed(DomainEvent):
    """A workspace event on a chosen (project) stream."""

    event_type: ClassVar[str] = Echoed.event_type
    stream_kind: ClassVar[str] = "project"

    workspace_id: WorkspaceId
    stream: UUID
    text: str

    @override
    def stream_id(self) -> UUID:
        return self.stream

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.text}


class _Ids:
    def new_id(self) -> UUID:
        return uuid4()


class _RunnerClock:
    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 - migration runner clock of the scratch database, not product code


class _GatedWriter(PostgresEventWriter):
    """Signals ``allocated`` after writing and waits for ``release`` before the unit of work may COMMIT."""

    def __init__(self, *, fail_after: bool = False) -> None:
        super().__init__(schemas=SchemaRegistry.load(SCHEMA_ROOT), subscriptions={}, ids=_Ids())
        self.allocated = threading.Event()
        self.release = threading.Event()
        self._fail_after = fail_after

    @override
    def write(
        self,
        conn: psycopg.Connection,
        events: Sequence[DomainEvent],
        meta: RequestMeta,
        *,
        occurred_at: datetime,
        explicit: Sequence[ExplicitOutboxRow] = (),
    ) -> tuple[EventEnvelope, ...]:
        written = super().write(conn, events, meta, occurred_at=occurred_at, explicit=explicit)
        self.allocated.set()
        if not self.release.wait(_WAIT_SECONDS):
            raise TimeoutError("gate was never released")
        if self._fail_after:
            raise RuntimeError("fail after allocation")
        return written


def _checked_admin(dsn: str) -> None:
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("ordering tests create databases only on a local server through an '*_test' database")


@dataclass
class World:
    dsn: str
    observer: psycopg.Connection
    pool: PoolHandle
    clock: FrozenClock
    plain: PostgresUowFactory
    instance: UUID
    ws_low: WorkspaceId
    ws_high: WorkspaceId

    def gated(self, writer: _GatedWriter) -> PostgresUowFactory:
        return PostgresUowFactory(self.pool, FACTORIES, writer, self.clock)

    def meta(self, n: int) -> RequestMeta:
        return RequestMeta(request_id(n), Surface.TEST, None, self.clock.now())

    def commit(self, factory: PostgresUowFactory, n: int, *events: DomainEvent) -> None:
        with factory(self.meta(n)) as uow:
            for event in events:
                uow.record(event)
            uow.commit()

    def workspace_feed(self, workspace: WorkspaceId, after: int = 0) -> tuple[EventEnvelope, ...]:
        with self.plain(self.meta(900), readonly=True) as uow:
            return uow.repo(EventReader).after_workspace_seq(workspace, after, types=None, limit=500)

    def instance_feed(self, after: int = 0) -> tuple[EventEnvelope, ...]:
        with self.plain(self.meta(901), readonly=True) as uow:
            return uow.repo(EventReader).after_global_position(after, limit=500)

    def wait_for_lock_waiters(self, expected: int) -> None:
        deadline = time.monotonic() + _WAIT_SECONDS
        while time.monotonic() < deadline:
            row = self.observer.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            ).fetchone()
            if row is not None and row[0] >= expected:
                return
            time.sleep(0.02)
        pytest.fail(f"expected {expected} sessions waiting on a lock")


# Migrated template database per admin DSN, cloned by every test.
_TEMPLATES: dict[str, str] = {}


def _template(admin: psycopg.Connection, pg_dsn: str) -> str:
    name = _TEMPLATES.get(pg_dsn)
    if name is None:
        name = f"skm_t_order_tpl_{os.getpid()}_{uuid4().hex[:8]}"
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        _TEMPLATES[pg_dsn] = name  # dropped at module end even if the migration fails
        dsn = make_conninfo(pg_dsn, dbname=name)
        MigrationRunner(dsn, discover_migrations(), package_loader(), _RunnerClock(), "skm-test").migrate()
    return name


@pytest.fixture(scope="module", autouse=True)
def _drop_templates() -> Iterator[None]:
    yield
    for pg_dsn, name in _TEMPLATES.items():
        with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
    _TEMPLATES.clear()


@pytest.fixture
def world(pg_dsn: str) -> Iterator[World]:
    _checked_admin(pg_dsn)
    name = f"skm_t_order_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        template = _template(admin, pg_dsn)
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template))
        )
        try:
            yield from _world(make_conninfo(pg_dsn, dbname=name))
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _world(dsn: str) -> Iterator[World]:
    with psycopg.connect(dsn, autocommit=True) as observer:
        instance = uuid4()
        low, high = sorted((uuid4(), uuid4()))
        insert = "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)"
        observer.execute(insert, (instance, "instance", None, None))
        for ws in (low, high):
            observer.execute(insert, (ws, "workspace", instance, ws))
        pool = create_pool(
            PgSettings(
                dsn=dsn, application_name="skm-test", pool_min_size=1, pool_max_size=8, pool_timeout_seconds=5
            )
        )
        clock = FrozenClock()
        writer = PostgresEventWriter(schemas=SchemaRegistry.load(SCHEMA_ROOT), subscriptions={}, ids=_Ids())
        try:
            yield World(
                dsn=dsn,
                observer=observer,
                pool=pool,
                clock=clock,
                plain=PostgresUowFactory(pool, FACTORIES, writer, clock),
                instance=instance,
                ws_low=WorkspaceId(low),
                ws_high=WorkspaceId(high),
            )
        finally:
            pool.close()


class _Thread:
    """Runs ``target`` and keeps its exception for the test thread."""

    def __init__(self, target: Callable[[], None]) -> None:
        self.error: BaseException | None = None
        self.done = threading.Event()

        def run() -> None:
            try:
                target()
            except BaseException as exc:  # noqa: BLE001 - reported to the test thread
                self.error = exc
            finally:
                self.done.set()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def join(self) -> None:
        self._thread.join(_WAIT_SECONDS)
        assert self.done.is_set(), "worker thread did not finish"
        if self.error is not None:
            raise self.error


@dataclass
class _Holder:
    """A third session holding one counter row lock (``SELECT … FOR UPDATE``) until ``release``."""

    conn: psycopg.Connection

    def release(self) -> None:
        self.conn.rollback()
        self.conn.close()


def _hold(w: World, statement: LiteralString, params: tuple[object, ...]) -> _Holder:
    conn = psycopg.connect(w.dsn)
    assert conn.execute(statement + " FOR UPDATE", params).fetchone() is not None
    return _Holder(conn)


def _free(w: World, statement: LiteralString, params: tuple[object, ...]) -> bool:
    """``True`` when no other session holds the row: ``FOR UPDATE NOWAIT`` succeeds."""
    with psycopg.connect(w.dsn) as probe:
        try:
            probe.execute(statement + " FOR UPDATE NOWAIT", params).fetchone()
        except psycopg.errors.LockNotAvailable:
            return False
        finally:
            probe.rollback()
    return True


_WS_COUNTER: LiteralString = "SELECT 1 FROM skm_core.workspace_event_counters WHERE workspace_id = %s"
_STREAM_COUNTER: LiteralString = (
    "SELECT 1 FROM skm_core.event_streams WHERE stream_kind = %s AND stream_id = %s"
)


def _echo(workspace: WorkspaceId, text: str) -> Echoed:
    return Echoed(workspace_id=workspace, text=text)


# --- commit order -------------------------------------------------------------------------------------------


def test_a_late_commit_cannot_be_skipped_by_a_cursor_reader(world: World) -> None:
    w = world
    gate = _GatedWriter()
    first = _Thread(lambda: w.commit(w.gated(gate), 1, _echo(w.ws_low, "first")))
    assert gate.allocated.wait(_WAIT_SECONDS)  # first holds workspace_seq 1, not committed
    second = _Thread(lambda: w.commit(w.plain, 2, _echo(w.ws_low, "second")))
    w.wait_for_lock_waiters(1)  # second waits for the feed counter instead of taking number 2 now
    assert not second.done.is_set()
    assert w.workspace_feed(w.ws_low) == ()  # nothing a reader could advance its cursor past
    gate.release.set()
    first.join()
    second.join()
    feed = w.workspace_feed(w.ws_low)
    assert [(e.workspace_seq, e.payload["text"]) for e in feed] == [(1, "first"), (2, "second")]
    assert feed[0].recorded_at <= feed[1].recorded_at


def test_instance_feed_positions_follow_commit_order(world: World) -> None:
    w = world
    gate = _GatedWriter()
    first = _Thread(lambda: w.commit(w.gated(gate), 1, Noted(stream=uuid4(), text="first")))
    assert gate.allocated.wait(_WAIT_SECONDS)
    second = _Thread(lambda: w.commit(w.plain, 2, Noted(stream=uuid4(), text="second")))
    w.wait_for_lock_waiters(1)
    assert w.instance_feed() == ()
    gate.release.set()
    first.join()
    second.join()
    feed = w.instance_feed()
    assert [(e.global_position, e.workspace_seq, e.payload["text"]) for e in feed] == [
        (1, None, "first"),
        (2, None, "second"),
    ]
    assert w.observer.execute(
        "SELECT last_seq FROM skm_core.event_streams WHERE stream_kind = 'instance_feed' AND stream_id = %s",
        (w.instance,),
    ).fetchone() == (2,)


def test_a_rolled_back_allocation_leaves_no_gap_for_the_next_writer(world: World) -> None:
    w = world
    gate = _GatedWriter(fail_after=True)
    failed = _Thread(lambda: w.commit(w.gated(gate), 1, _echo(w.ws_low, "lost")))
    assert gate.allocated.wait(_WAIT_SECONDS)
    second = _Thread(lambda: w.commit(w.plain, 2, _echo(w.ws_low, "kept")))
    w.wait_for_lock_waiters(1)
    gate.release.set()
    with pytest.raises(RuntimeError, match="fail after allocation"):
        failed.join()
    second.join()
    assert [(e.workspace_seq, e.payload["text"]) for e in w.workspace_feed(w.ws_low)] == [(1, "kept")]
    assert w.observer.execute("SELECT count(*) FROM skm_core.outbox").fetchone() == (
        1,
    )  # the sse row of "kept"


def test_concurrent_writers_never_leave_a_gap_behind_a_cursor(world: World) -> None:
    w = world
    writers, commits = 4, 12
    stop = threading.Event()
    polls: list[tuple[int, list[int]]] = []

    def write(worker: int) -> None:
        rng = random.Random(worker)
        for i in range(commits):
            events = [_echo(w.ws_low, f"w{worker}-{i}-{k}") for k in range(rng.randint(1, 3))]
            w.commit(w.plain, worker * 1000 + i + 1, *events)

    def read() -> None:
        cursor = 0
        while not stop.is_set():
            seqs = [e.workspace_seq or 0 for e in w.workspace_feed(w.ws_low, cursor)]
            polls.append((cursor, seqs))
            cursor = max(seqs, default=cursor)

    reader = _Thread(read)
    workers = [_Thread(lambda worker=worker: write(worker)) for worker in range(writers)]
    for thread in workers:
        thread.join()
    stop.set()
    reader.join()
    total = len(w.workspace_feed(w.ws_low))
    seen: list[int] = []
    for cursor, seqs in polls:  # every poll continues exactly where the cursor stood: no skipped number
        assert seqs == list(range(cursor + 1, cursor + 1 + len(seqs)))
        seen.extend(seqs)
    remainder = [e.workspace_seq or 0 for e in w.workspace_feed(w.ws_low, max(seen, default=0))]
    assert seen + remainder == list(range(1, total + 1))
    assert total >= writers * commits


# --- lock order ---------------------------------------------------------------------------------------------


def test_feed_counter_is_locked_before_the_stream_counter(world: World) -> None:
    w = world
    stream = uuid4()
    w.commit(w.plain, 1, StreamEchoed(w.ws_low, stream, "creates the counter rows"))
    holder = _hold(w, _WS_COUNTER, (w.ws_low,))
    try:
        writer = _Thread(lambda: w.commit(w.plain, 2, StreamEchoed(w.ws_low, stream, "waits")))
        w.wait_for_lock_waiters(1)
        assert _free(w, _STREAM_COUNTER, ("project", stream))  # waiting on the feed, holding no stream row
    finally:
        holder.release()
    writer.join()
    assert [e.stream_seq for e in w.workspace_feed(w.ws_low)] == [1, 2]


def test_instance_feed_is_locked_before_workspace_feeds(world: World) -> None:
    w = world
    w.commit(w.plain, 1, _echo(w.ws_low, "seed"), Noted(stream=uuid4(), text="seed"))
    holder = _hold(w, _STREAM_COUNTER, ("instance_feed", w.instance))
    try:
        writer = _Thread(lambda: w.commit(w.plain, 2, _echo(w.ws_low, "ws"), Noted(stream=uuid4(), text="i")))
        w.wait_for_lock_waiters(1)
        assert _free(w, _WS_COUNTER, (w.ws_low,))
    finally:
        holder.release()
    writer.join()
    assert [e.global_position for e in w.instance_feed()] == [1, 2]


def test_multi_event_transactions_take_workspace_feeds_in_one_order(world: World) -> None:
    w = world
    w.commit(w.plain, 1, _echo(w.ws_low, "seed"), _echo(w.ws_high, "seed"))
    holder = _hold(w, _WS_COUNTER, (w.ws_low,))
    try:
        # recorded in opposite orders: locking in record order would deadlock these two
        a = _Thread(lambda: w.commit(w.plain, 2, _echo(w.ws_high, "a"), _echo(w.ws_low, "a")))
        b = _Thread(lambda: w.commit(w.plain, 3, _echo(w.ws_low, "b"), _echo(w.ws_high, "b")))
        w.wait_for_lock_waiters(2)
        assert _free(w, _WS_COUNTER, (w.ws_high,))  # neither took the higher feed before the lower one
    finally:
        holder.release()
    a.join()
    b.join()
    for ws in (w.ws_low, w.ws_high):
        assert [e.workspace_seq for e in w.workspace_feed(ws)] == [1, 2, 3]


def test_multi_event_transactions_take_stream_counters_in_one_order(world: World) -> None:
    w = world
    low, high = sorted((uuid4(), uuid4()))
    # instance events share the instance feed; their streams differ
    w.commit(w.plain, 1, Noted(stream=low, text="seed"), Noted(stream=high, text="seed"))
    holder = _hold(w, _STREAM_COUNTER, ("config", low))
    try:
        writer = _Thread(
            lambda: w.commit(w.plain, 2, Noted(stream=high, text="h"), Noted(stream=low, text="l"))
        )
        w.wait_for_lock_waiters(1)
        assert _free(w, _STREAM_COUNTER, ("config", high))
    finally:
        holder.release()
    writer.join()
    by_stream = {(e.stream_id, e.stream_seq) for e in w.instance_feed()}
    assert by_stream == {(low, 1), (high, 1), (low, 2), (high, 2)}
    # one transaction gets consecutive feed positions in record order
    assert [(e.stream_id, e.global_position) for e in w.instance_feed(2)] == [(high, 3), (low, 4)]
