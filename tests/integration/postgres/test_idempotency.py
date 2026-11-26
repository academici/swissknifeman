"""PostgreSQL receipts, audit and the receipt race on a live server (adapters §1.5, kernel-platform §4.4).

Every test gets a scratch database with the whole migration chain, an instance scope and two workspaces.
Observation goes through a separate autocommit connection. Lock waits are provoked with real sessions: a
holder keeps a row lock, a unit of work blocks on it and the test inspects ``pg_stat_activity`` before it lets
go. The backend-neutral behaviour (memory ∥ postgres) is in ``tests/contracts/core/test_idempotency.py``.
"""

import os
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, override
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fakes.app import FakeConfigLoader, FakeConfigStore, FakeGateways, FakeScopeChain, request_id
from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.demo_module import (
    ECHO,
    PERMISSIONS,
    SCHEMA_ROOT,
    Echo,
    EchoResult,
    handle_echo,
    manifest,
)
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core import REPOSITORIES
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import ExplicitOutboxRow, PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, AuditRecord, IdempotencyReceipt, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, ValidationFailed
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.config.store import ConfigStore
from skm.platform.schema.registry import SchemaRegistry
from support.seed import SEED, seed_backend

pytestmark = pytest.mark.pg

ATTEMPTS = 3
TTL = timedelta(hours=72)
_WAIT_SECONDS = 15.0
PRINCIPAL = SEED.principal_id
WS = SEED.workspace_id


class _Ids(SequentialIds):
    """Thread-safe deterministic ids."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    @override
    def new_id(self) -> UUID:
        with self._lock:
            return super().new_id()


class _RunnerClock:
    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 - migration runner clock of the scratch database, not product code


class _ScriptedWriter(PostgresEventWriter):
    """Event writer whose ``write`` runs a script after the real write and before the unit of work may COMMIT.

    ``before_commit(call)`` receives the 1-based number of the call; it may block (a gate) or raise (a failure
    such as a driver error). The events, sequence numbers and outbox rows are already written when it runs.
    """

    def __init__(self, schemas: SchemaRegistry, subscriptions: Any, ids: _Ids) -> None:
        super().__init__(schemas=schemas, subscriptions=subscriptions, ids=ids)
        self.calls = 0
        self.before_commit: Callable[[int], None] = lambda call: None
        self._lock = threading.Lock()

    def write(  # type: ignore[override]
        self,
        conn: psycopg.Connection,
        events: Sequence[DomainEvent],
        meta: RequestMeta,
        *,
        occurred_at: datetime,
        explicit: Sequence[ExplicitOutboxRow] = (),
    ) -> tuple[EventEnvelope, ...]:
        written = super().write(conn, events, meta, occurred_at=occurred_at, explicit=explicit)
        with self._lock:
            self.calls += 1
            call = self.calls
        self.before_commit(call)
        return written


def _checked_admin(dsn: str) -> None:
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("idempotency tests create databases only on a local '*_test' server", pytrace=False)


_TEMPLATES: dict[str, str] = {}


@pytest.fixture(scope="module", autouse=True)
def _drop_templates() -> Iterator[None]:
    yield
    for dsn, name in _TEMPLATES.items():
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
    _TEMPLATES.clear()


def _template(admin: psycopg.Connection, dsn: str) -> str:
    name = _TEMPLATES.get(dsn)
    if name is None:
        name = f"skm_t_idem_i_tpl_{os.getpid()}_{uuid4().hex[:8]}"
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        _TEMPLATES[dsn] = name
        runner = MigrationRunner(
            make_conninfo(dsn, dbname=name),
            discover_migrations(),
            package_loader(),
            _RunnerClock(),
            "skm-test",
        )
        runner.migrate(target=None)
    return name


@pytest.fixture
def migrated(pg_dsn: str) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_idem_i_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        template = _template(admin, pg_dsn)
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template))
        )
        try:
            yield make_conninfo(pg_dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@dataclass
class World:
    dsn: str
    observer: psycopg.Connection
    pool: PoolHandle
    uows: PostgresUowFactory
    writer: _ScriptedWriter
    clock: FrozenClock
    ids: _Ids
    authorizer: FakeAuthorizer
    config: FakeConfigLoader
    bus: Callable[..., Bus]

    def meta(self, n: int = 1, key: str | None = None) -> RequestMeta:
        return RequestMeta(request_id(n), Surface.TEST, key, self.clock.now())

    def scalar(self, statement: str, params: tuple[object, ...] = ()) -> Any:
        row = self.observer.execute(statement, params or None).fetchone()  # type: ignore[call-overload]
        assert row is not None
        return row[0]

    def count(self, table: str, where: str = "true") -> int:
        return int(self.scalar(f"SELECT count(*) FROM skm_core.{table} WHERE {where}"))  # noqa: S608 - test literals

    def receipt(
        self,
        *,
        key: str = "k1",
        workspace_id: WorkspaceId | None = WS,
        principal_id: PrincipalId = PRINCIPAL,
        operation: str = "demo.echo",
        digest: str | None = None,
        created_at: datetime | None = None,
        ttl: timedelta = TTL,
    ) -> IdempotencyReceipt:
        created = created_at or self.clock.now()
        return IdempotencyReceipt(
            workspace_id=workspace_id,
            principal_id=principal_id,
            operation=operation,
            key=key,
            request_digest=digest or "sha256:" + "a" * 64,
            result={"text": "stored"},
            created_at=created,
            expires_at=created + ttl,
        )

    def put(self, receipt: IdempotencyReceipt) -> None:
        with self.uows(self.meta()) as uow:
            uow.repo(IdempotencyStore).put(receipt)
            uow.commit()

    def expire(self, key: str = "k1", *, ago: str = "1 second") -> None:
        self.observer.execute(
            "UPDATE skm_core.idempotency_receipts SET created_at = created_at - interval '2 days', "
            "expires_at = clock_timestamp() - %s::interval WHERE key = %s",
            (ago, key),
        )

    def wait_for_lock_wait(self, *, count: int = 1) -> None:
        """Until ``count`` pool sessions wait for a lock, i.e. a unit of work is blocked behind another."""
        deadline = time.monotonic() + _WAIT_SECONDS
        while time.monotonic() < deadline:
            waiting = self.scalar(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND application_name = 'skm-test' AND wait_event_type = 'Lock'"
            )
            if waiting >= count:
                return
            time.sleep(0.02)
        pytest.fail("no session ever waited for a lock")


def _world(dsn: str, *, pool_size: int = 6, commands: Sequence[Any] = (ECHO,)) -> Iterator[World]:
    ids = _Ids()
    clock = FrozenClock()
    schemas = SchemaRegistry.load(SCHEMA_ROOT)
    registry = BusRegistry.build(
        (manifest(commands=tuple(commands)),),
        schemas=schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )
    pool = create_pool(
        PgSettings(
            dsn=dsn,
            application_name="skm-test",
            pool_min_size=1,
            pool_max_size=pool_size,
            pool_timeout_seconds=3,
        )
    )
    factories: dict[type, Any] = {
        **REPOSITORIES,
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        ConfigStore: lambda conn: FakeConfigStore(),
    }
    writer = _ScriptedWriter(schemas, registry.subscription_index(), ids)
    uows = PostgresUowFactory(pool, factories, writer, clock)
    seed_backend(uows)
    writer.calls = 0  # the seed commit is not part of the test
    authorizer = FakeAuthorizer(None)
    config = FakeConfigLoader()

    def bus(*, max_attempts: int = ATTEMPTS) -> Bus:
        return Bus(
            registry=registry,
            schemas=schemas,
            uow_factory=uows,
            authorizer=authorizer,
            scopes=FakeScopeChain(),
            config=config,  # type: ignore[arg-type] - the fake implements the part of ConfigLoader the bus calls
            clock=clock,
            ids=ids,
            entropy=DeterministicEntropy(),
            gateways=FakeGateways(),  # type: ignore[arg-type]
            retry=RetryPolicy(max_attempts=max_attempts, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=TTL,
        )

    with psycopg.connect(dsn, autocommit=True) as observer:
        try:
            yield World(dsn, observer, pool, uows, writer, clock, ids, authorizer, config, bus)
        finally:
            pool.close()


@pytest.fixture
def world(migrated: str) -> Iterator[World]:
    yield from _world(migrated)


@pytest.fixture
def single(migrated: str) -> Iterator[World]:
    """One pooled connection: a second connection held by a request would time the pool out."""
    yield from _world(migrated, pool_size=1)


def actor() -> Actor:
    return SEED.actor()


def echo(text: str = "hello") -> Echo:
    return Echo(workspace_id=WS, text=text)


def in_thread(call: Callable[[], object]) -> "Outcome":
    outcome = Outcome()

    def run() -> None:
        try:
            outcome.value = call()
        except BaseException as exc:  # noqa: BLE001 - the test inspects the outcome
            outcome.error = exc
        finally:
            outcome.done.set()

    threading.Thread(target=run, daemon=True).start()
    return outcome


class Outcome:
    def __init__(self) -> None:
        self.value: object = None
        self.error: BaseException | None = None
        self.done = threading.Event()

    def result(self) -> object:
        assert self.done.wait(_WAIT_SECONDS), "the concurrent call never finished"
        if self.error is not None:
            raise self.error
        return self.value


# ------------------------------------------------------------------------------------------ adapter


def test_a_receipt_round_trips_with_the_database_clock_and_the_derived_result_type(world: World) -> None:
    receipt = world.receipt(key="k.1:a-b_c", operation="workspace.create_project")
    world.put(receipt)
    with world.uows(world.meta(), readonly=True) as uow:
        found = uow.repo(IdempotencyStore).get(WS, PRINCIPAL, "workspace.create_project", "k.1:a-b_c")
    assert found is not None
    assert (found.request_digest, found.result, found.workspace_id) == (
        receipt.request_digest,
        {"text": "stored"},
        WS,
    )
    assert (
        found.expires_at - found.created_at == TTL
    )  # ttl is the receipt's length, the times are the database's
    assert abs(found.created_at - datetime.now(UTC)) < timedelta(minutes=5)  # noqa: TID251 - compares with real time
    assert found.created_at != receipt.created_at  # FrozenClock is 2026-01-01
    row = world.observer.execute(
        "SELECT result_type, scope_key FROM skm_core.idempotency_receipts"
    ).fetchone()
    assert row == ("urn:skm:workspace:result:create-project:v1", WS)


def test_instance_level_receipts_use_the_nil_scope_key_and_do_not_meet_workspace_ones(world: World) -> None:
    world.put(world.receipt(workspace_id=None))
    world.put(world.receipt(workspace_id=WS))
    world.put(world.receipt(workspace_id=SEED.other_workspace_id))
    with world.uows(world.meta(), readonly=True) as uow:
        store = uow.repo(IdempotencyStore)
        assert store.get(None, PRINCIPAL, "demo.echo", "k1") is not None
        assert store.get(WS, PRINCIPAL, "demo.echo", "k1") is not None
    scope_keys = {
        row[0] for row in world.observer.execute("SELECT scope_key FROM skm_core.idempotency_receipts")
    }
    assert scope_keys == {UUID(int=0), WS, SEED.other_workspace_id}


def test_a_live_receipt_is_a_conflict_and_stays_untouched(world: World) -> None:
    world.put(world.receipt(digest="sha256:" + "1" * 64))
    with pytest.raises(Conflict) as caught:
        world.put(world.receipt(digest="sha256:" + "2" * 64))
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert world.scalar("SELECT request_digest FROM skm_core.idempotency_receipts") == "sha256:" + "1" * 64


def test_two_puts_of_one_key_in_one_transaction_conflict(world: World) -> None:
    with world.uows(world.meta()) as uow:
        store = uow.repo(IdempotencyStore)
        store.put(world.receipt())
        with pytest.raises(Conflict):
            store.put(world.receipt())


def test_an_expired_unpurged_receipt_is_invisible_and_is_replaced(world: World) -> None:
    world.put(world.receipt(digest="sha256:" + "1" * 64))
    world.expire()
    assert world.count("idempotency_receipts") == 1  # no janitor has run
    with world.uows(world.meta(), readonly=True) as uow:
        assert uow.repo(IdempotencyStore).get(WS, PRINCIPAL, "demo.echo", "k1") is None
    world.put(world.receipt(digest="sha256:" + "2" * 64))
    assert world.count("idempotency_receipts") == 1
    assert world.scalar("SELECT request_digest FROM skm_core.idempotency_receipts") == "sha256:" + "2" * 64
    assert world.scalar(
        "SELECT expires_at > clock_timestamp() + interval '71 hours' FROM skm_core.idempotency_receipts"
    )


def test_a_receipt_that_does_not_outlive_its_creation_is_a_program_error(world: World) -> None:
    with pytest.raises(InternalError):
        world.put(world.receipt(ttl=timedelta(0)))
    assert world.count("idempotency_receipts") == 0


def test_a_malformed_key_is_rejected_by_the_database_check(world: World) -> None:
    with pytest.raises(ValidationFailed) as caught:
        world.put(world.receipt(key="not a valid key"))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_purge_removes_only_expired_rows_up_to_the_limit_and_skips_locked_ones(world: World) -> None:
    for n in range(4):
        world.put(world.receipt(key=f"old{n}"))
        world.expire(f"old{n}")
    world.put(world.receipt(key="live"))
    now = datetime.now(UTC)  # noqa: TID251 - database rows expire in real time
    with world.uows(world.meta()) as uow:
        store = uow.repo(IdempotencyStore)
        assert store.purge_expired(now, limit=0) == 0
        assert store.purge_expired(now, limit=-3) == 0
        assert store.purge_expired(now, limit=3) == 3
        uow.commit()
    assert world.count("idempotency_receipts", "key LIKE 'old%'") == 1
    assert world.count("idempotency_receipts", "key = 'live'") == 1
    with psycopg.connect(world.dsn) as holder:  # a concurrent writer holds the last expired row
        holder.execute("SELECT 1 FROM skm_core.idempotency_receipts WHERE key LIKE 'old%' FOR UPDATE")
        with world.uows(world.meta()) as uow:
            assert uow.repo(IdempotencyStore).purge_expired(now, limit=10) == 0  # skipped, not waited for
            uow.commit()
    with world.uows(world.meta()) as uow:
        assert uow.repo(IdempotencyStore).purge_expired(now, limit=10) == 1
        uow.commit()
    assert world.count("idempotency_receipts") == 1


# ----------------------------------------------------------------------------------- fresh time (ench6)


def test_a_replacement_after_a_row_lock_wait_uses_the_database_clock_of_that_moment(world: World) -> None:
    """The transaction starts with a live receipt, waits for a row lock, and the receipt expires meanwhile.

    A predicate or TTL taken from ``now()`` (the start of the transaction) or from ``EXCLUDED`` would see a
    live row and raise a Conflict, or would give the replacement a TTL that began before the wait.
    """
    world.observer.execute(
        "INSERT INTO skm_core.idempotency_receipts (id, workspace_id, principal_id, operation, key, "
        "request_digest, result_type, result, created_at, expires_at) "
        "VALUES (%s, %s, %s, 'demo.echo', 'k1', %s, "
        "'urn:skm:demo:result:echo:v1', '{\"text\": \"old\"}', clock_timestamp() - interval '1 hour', "
        "clock_timestamp() + interval '2 seconds')",
        (uuid4(), WS, PRINCIPAL, "sha256:" + "0" * 64),
    )
    old_id = world.scalar("SELECT id FROM skm_core.idempotency_receipts")
    transaction_started = threading.Event()
    seen: dict[str, datetime] = {}

    def replace_receipt() -> None:
        with world.uows(world.meta()) as uow:
            seen["now"] = uow.connection.execute("SELECT now()").fetchone()[0]  # type: ignore[index]
            transaction_started.set()
            uow.repo(IdempotencyStore).put(
                world.receipt(digest="sha256:" + "9" * 64, ttl=timedelta(minutes=10))
            )
            uow.commit()

    with psycopg.connect(world.dsn) as holder:
        holder.execute("SELECT 1 FROM skm_core.idempotency_receipts WHERE key = 'k1' FOR UPDATE")
        outcome = in_thread(replace_receipt)
        assert transaction_started.wait(_WAIT_SECONDS)
        world.wait_for_lock_wait()  # the upsert is blocked behind the holder
        assert world.scalar(
            "SELECT expires_at > clock_timestamp() FROM skm_core.idempotency_receipts"
        )  # still live
        while not world.scalar("SELECT expires_at <= clock_timestamp() FROM skm_core.idempotency_receipts"):
            time.sleep(0.05)  # the receipt expires while the transaction waits
        holder.commit()  # release the lock after the expiry
    outcome.result()  # no Conflict: the expiry was judged after the wait
    row = world.observer.execute(
        "SELECT id, request_digest, created_at, expires_at FROM skm_core.idempotency_receipts"
    ).fetchone()
    assert row is not None
    new_id, digest, created_at, expires_at = row
    assert (new_id != old_id, digest) == (True, "sha256:" + "9" * 64)
    waited = created_at - seen["now"]
    assert waited >= timedelta(seconds=1), "created_at must come from the moment of replacement, not now()"
    assert timedelta(minutes=10) <= expires_at - created_at < timedelta(minutes=10, seconds=1)
    assert expires_at > seen["now"] + timedelta(minutes=10) + waited / 2  # not shortened by the wait


# ------------------------------------------------------------------------------------------ audit


def test_allowed_audit_rolls_back_with_its_unit_of_work_and_denied_audit_commits_alone(world: World) -> None:
    record = AuditRecord(
        id=uuid4(),
        workspace_id=WS,
        actor_id=PRINCIPAL,
        action="demo.echo",
        target={"scope": {"kind": "workspace", "id": str(WS)}, "permission": "demo.echo"},
        decision="allowed",
        reason_code=None,
        request_id=request_id(),
        recorded_at=world.clock.now(),
    )
    with world.uows(world.meta()) as uow:
        uow.repo(AuditLog).append(record)  # no commit: the row vanishes with the transaction
    assert world.count("audit_records") == 0
    denied = replace(record, id=uuid4(), decision="denied", reason_code="ROLE_LACKS_PERMISSION")
    with world.uows(world.meta()) as uow:
        uow.repo(AuditLog).append(denied)
        uow.commit()
    row = world.observer.execute(
        "SELECT decision, reason_code, target, recorded_at <= clock_timestamp() FROM skm_core.audit_records"
    ).fetchone()
    assert row == ("denied", "ROLE_LACKS_PERMISSION", record.target, True)


def test_the_audit_adapter_translates_the_database_checks(world: World) -> None:
    broken = AuditRecord(
        uuid4(), WS, PRINCIPAL, "demo.echo", {}, "denied", None, request_id(), world.clock.now()
    )
    with pytest.raises(ValidationFailed) as caught, world.uows(world.meta()) as uow:
        uow.repo(AuditLog).append(broken)  # a denied row needs a reason (ck_audit_records__reason)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["constraint"] == "ck_audit_records__reason"


# ----------------------------------------------------------------------------------- receipt race on the bus


def _dispatch(w: World, cmd: Echo, key: str, n: int, bus: Bus | None = None) -> Callable[[], object]:
    return lambda: (bus or w.bus()).dispatch(cmd, actor=actor(), meta=w.meta(n, key))


def test_a_duplicate_blocked_on_the_winners_receipt_row_replays_the_winners_result(world: World) -> None:
    gate_reached, release = threading.Event(), threading.Event()

    def gate(call: int) -> None:
        if call == 1:
            gate_reached.set()
            assert release.wait(_WAIT_SECONDS)

    world.writer.before_commit = gate
    winner = in_thread(_dispatch(world, echo(), "dup", 1))
    assert gate_reached.wait(_WAIT_SECONDS)  # the winner holds its receipt row, uncommitted
    loser = in_thread(_dispatch(world, echo(), "dup", 2))
    world.wait_for_lock_wait()  # the loser's receipt INSERT waits for the winner
    assert world.count("domain_events") == 0
    release.set()
    assert winner.result() == loser.result() == EchoResult(text="hello")
    assert (world.count("domain_events"), world.count("idempotency_receipts")) == (1, 1)
    assert world.count("outbox") == 2  # one 'sse' row and one subscriber row of the single event
    assert (
        world.count("audit_records", "decision = 'allowed'") == 1
    )  # the loser's audit row rolled back with it
    assert world.scalar("SELECT last_seq FROM skm_core.workspace_event_counters") == 1
    assert [call.readonly for call in world.authorizer.calls].count(
        True
    ) == 1  # the loser authorized the replay


def test_a_duplicate_with_another_body_blocked_on_the_winner_is_key_reused(world: World) -> None:
    gate_reached, release = threading.Event(), threading.Event()

    def gate(call: int) -> None:
        if call == 1:
            gate_reached.set()
            assert release.wait(_WAIT_SECONDS)

    world.writer.before_commit = gate
    winner = in_thread(_dispatch(world, echo("one"), "dup", 1))
    assert gate_reached.wait(_WAIT_SECONDS)
    loser = in_thread(_dispatch(world, echo("two"), "dup", 2))
    world.wait_for_lock_wait()
    release.set()
    assert winner.result() == EchoResult(text="one")
    with pytest.raises(Conflict) as caught:
        loser.result()
    assert caught.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert (world.count("domain_events"), world.count("idempotency_receipts")) == (1, 1)


def test_a_waiting_duplicate_proceeds_when_the_winner_rolls_back(world: World) -> None:
    gate_reached, release = threading.Event(), threading.Event()

    def gate(call: int) -> None:
        if call == 1:
            gate_reached.set()
            assert release.wait(_WAIT_SECONDS)
            raise RuntimeError("winner fails before COMMIT")

    world.writer.before_commit = gate
    winner = in_thread(_dispatch(world, echo(), "dup", 1))
    assert gate_reached.wait(_WAIT_SECONDS)
    loser = in_thread(_dispatch(world, echo(), "dup", 2))
    world.wait_for_lock_wait()
    release.set()
    with pytest.raises(InternalError):
        winner.result()
    assert loser.result() == EchoResult(text="hello")  # no receipt survived: the loser's attempt is the one
    assert (world.count("domain_events"), world.count("idempotency_receipts")) == (1, 1)
    assert world.scalar("SELECT last_seq FROM skm_core.workspace_event_counters") == 1  # no number was lost


def test_many_concurrent_duplicates_leave_one_effect(world: World) -> None:
    barrier = threading.Barrier(5)

    def call(n: int) -> object:
        barrier.wait(timeout=_WAIT_SECONDS)
        return _dispatch(world, echo(), "storm", n)()

    outcomes = [in_thread(lambda n=n: call(n)) for n in range(1, 6)]
    assert [outcome.result() for outcome in outcomes] == [EchoResult(text="hello")] * 5
    assert (world.count("domain_events"), world.count("idempotency_receipts"), world.count("outbox")) == (
        1,
        1,
        2,
    )


# ----------------------------------------------------------------------------------- retry with driver errors


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_a_driver_serialization_error_before_commit_is_retried_without_losing_a_sequence_number(
    single: World, code: str
) -> None:
    def fail_once(call: int) -> None:
        if call == 1:  # events, outbox rows and counters were written; the receipt and audit row too
            raise psycopg.errors.lookup(code)()

    single.writer.before_commit = fail_once
    assert single.bus().dispatch(echo(), actor=actor(), meta=single.meta(1, "k1")) == EchoResult(text="hello")
    assert single.writer.calls == 2
    assert (single.count("domain_events"), single.count("outbox"), single.count("idempotency_receipts")) == (
        1,
        2,
        1,
    )
    assert single.count("audit_records", "decision = 'allowed'") == 1
    assert (
        single.scalar("SELECT workspace_seq FROM skm_core.domain_events") == 1
    )  # the rollback consumed none
    assert single.scalar("SELECT last_seq FROM skm_core.workspace_event_counters") == 1
    assert len(single.authorizer.calls) == 2  # scope, authz and config ran again
    assert single.config.calls == 2


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_retry_exhaustion_is_the_canonical_retryable_conflict_and_leaves_no_trace(
    single: World, code: str
) -> None:
    def always(call: int) -> None:
        raise psycopg.errors.lookup(code)()

    single.writer.before_commit = always
    with pytest.raises(Conflict) as caught:
        single.bus(max_attempts=2).dispatch(echo(), actor=actor(), meta=single.meta(1, "k1"))
    assert caught.value.code is ErrorCode.SERIALIZATION_FAILURE
    assert caught.value.retryable is True
    assert single.writer.calls == 2  # bounded by max_attempts
    for table in (
        "domain_events",
        "outbox",
        "idempotency_receipts",
        "audit_records",
        "workspace_event_counters",
    ):
        assert single.count(table) == 0, table
    # the one connection is back in the pool and the key is still free
    single.writer.before_commit = lambda call: None
    assert single.bus().dispatch(echo(), actor=actor(), meta=single.meta(2, "k1")) == EchoResult(text="hello")


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_a_server_raised_error_after_the_first_domain_write_repeats_scope_authz_and_config(
    migrated: str, code: str
) -> None:
    calls = {"n": 0}

    def flaky(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        calls["n"] += 1
        result = handle_echo(cmd, ctx, uow)  # the first domain write: a buffered event
        if calls["n"] == 1:
            try:  # a repository's statement that the server aborts with the SQLSTATE
                uow.connection.execute(
                    f"DO $$ BEGIN RAISE EXCEPTION 'abort' USING ERRCODE = '{code}'; END $$"
                )
            except psycopg.Error as exc:
                raise translate_pg_error(exc) from exc
        return result

    with contextmanager(_world)(migrated, pool_size=1, commands=(replace(ECHO, handler=flaky),)) as world:
        assert world.bus().dispatch(echo(), actor=actor(), meta=world.meta(1, "k1")) == EchoResult(
            text="hello"
        )
        assert calls["n"] == 2
        assert (world.count("domain_events"), world.count("outbox"), world.count("idempotency_receipts")) == (
            1,
            2,
            1,
        )
        assert world.count("audit_records", "decision = 'allowed'") == 1
        assert [call.readonly for call in world.authorizer.calls] == [False, False]
        assert world.config.calls == 2
