"""Idempotency, receipt race, denied audit and bounded retry of the bus on both backends (memory ∥ postgres).

Every test runs the real ``Bus`` over the memory backend and over ``PostgresUnitOfWork`` on the session test
database of ``support.pg``, cleaned before the test (``pg`` marker, ``SKM_REQUIRE_PG=1`` makes a missing
server a failure). What differs between the backends is isolated in ``Rig``: how the persisted rows are
counted, how receipts age and how a concurrent winner commits. The PostgreSQL-only mechanics (row-lock waits,
fresh database time, driver-level errors) are in ``tests/integration/postgres/test_idempotency.py``.
"""

import threading
from collections.abc import Callable, Generator, Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any, override
from uuid import UUID

import psycopg
import pytest

from fakes.app import (
    FakeConfigLoader,
    FakeConfigStore,
    FakeGateways,
    FakeScopeChain,
    Harness,
    build_harness,
    request_id,
)
from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.demo_module import (
    ECHO,
    ECHO_SECRET,
    PERMISSIONS,
    SCHEMA_ROOT,
    Echo,
    EchoResult,
    EchoSecret,
    handle_echo,
    manifest,
)
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.core.idempotency import MemoryIdempotencyStore
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core import REPOSITORIES
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.middleware import request_digest
from skm.application_bus.ports import AuditLog, IdempotencyReceipt, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, SkmError
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWorkFactory
from skm.platform.config.store import ConfigStore
from skm.platform.schema.registry import SchemaRegistry
from support.pg import TestDatabase
from support.seed import SEED

SECRET = "hunter2-quartz-lantern"
OTHER_SECRET = "mauve-falcon-9000"
TTL = timedelta(hours=24)
ATTEMPTS = 3


# ------------------------------------------------------------------------------------------ test doubles


class LockedIds(SequentialIds):
    """Thread-safe deterministic ids; the concurrent tests share one generator."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    @override
    def new_id(self) -> UUID:
        with self._lock:
            return super().new_id()


@dataclass
class Faults:
    """Retryable failures scheduled for the first attempts; ``code`` is the SQLSTATE the driver reports."""

    in_handler: int = 0  # attempts that fail after the first domain write, before the receipt
    at_commit: int = 0  # attempts that fail in place of COMMIT, after receipt, audit and events were buffered
    code: str = "40001"
    attempts: int = 0
    commits: int = 0
    attempt_ids: list[UUID] = field(default_factory=list[UUID])
    external_calls: list[str] = field(default_factory=list[str])

    def error(self) -> SkmError:
        driver = psycopg.errors.lookup(self.code)()
        return translate_pg_error(driver)


class FaultyUow:
    """Delegates to a real unit of work and fails ``commit`` as scheduled; the real one then rolls back."""

    def __init__(self, inner: Any, faults: Faults) -> None:
        self._inner = inner
        self._faults = faults

    def __enter__(self) -> "FaultyUow":
        self._inner.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._inner.__exit__(*exc)

    def commit(self) -> None:
        self._faults.commits += 1
        if self._faults.commits <= self._faults.at_commit:
            raise self._faults.error()
        self._inner.commit()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class FaultyFactory:
    def __init__(self, inner: UnitOfWorkFactory, faults: Faults) -> None:
        self._inner = inner
        self._faults = faults

    def __call__(self, meta: RequestMeta, **kwargs: Any) -> Any:
        return FaultyUow(self._inner(meta, **kwargs), self._faults)


# ------------------------------------------------------------------------------------------ the rig


@dataclass
class Counts:
    events: int
    outbox: int
    receipts: int
    allowed: int
    denied: int


class Rig:
    """One bus over one backend and what the tests need to look behind it."""

    def __init__(
        self,
        kind: str,
        *,
        bus: Bus,
        clock: FrozenClock,
        authorizer: FakeAuthorizer,
        config: FakeConfigLoader,
        ids: SequentialIds,
        uow_factory: UnitOfWorkFactory,
        age: Callable[[], None],
        counts: Callable[[], Counts],
        dump: Callable[[], str],
        commit_receipt: Callable[[IdempotencyReceipt], None],
    ) -> None:
        self.kind = kind
        self.bus = bus
        self.clock = clock
        self.authorizer = authorizer
        self.config = config
        self.ids = ids
        self.uow_factory = uow_factory
        self.age_receipts = age
        self.counts = counts
        self.dump = dump
        self.commit_receipt = commit_receipt
        self.workspace_id = SEED.workspace_id
        self.actor = SEED.actor()

    def echo(self, text: str = "hello") -> Echo:
        return Echo(workspace_id=self.workspace_id, text=text)

    def meta(self, key: str | None = None, n: int = 1) -> RequestMeta:
        return RequestMeta(request_id(n), Surface.TEST, key, self.clock.now())

    def dispatch(
        self, cmd: object, key: str | None = None, *, actor: Actor | None = None, n: int = 1
    ) -> object:
        return self.bus.dispatch(cmd, actor=actor or self.actor, meta=self.meta(key, n))


def _bus(
    registry: BusRegistry,
    schemas: SchemaRegistry,
    uow_factory: UnitOfWorkFactory,
    authorizer: FakeAuthorizer,
    config: FakeConfigLoader,
    clock: FrozenClock,
    ids: SequentialIds,
) -> Bus:
    return Bus(
        registry=registry,
        schemas=schemas,
        uow_factory=uow_factory,
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=config,  # type: ignore[arg-type] - the fake implements the part of ConfigLoader the bus calls
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=FakeGateways(),  # type: ignore[arg-type]
        retry=RetryPolicy(max_attempts=ATTEMPTS, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=TTL,
    )


def _memory_rig(commands: Sequence[Any], faults: Faults | None) -> Rig:
    ids = LockedIds()
    h: Harness = build_harness(manifests=(manifest(commands=tuple(commands)),), ttl=TTL, ids=ids)
    factory: UnitOfWorkFactory = h.uow_factory
    if faults is not None:
        factory = FaultyFactory(h.uow_factory, faults)
    bus = _bus(h.registry, h.schemas, factory, h.authorizer, h.config, h.clock, ids)

    def counts() -> Counts:
        core = h.backend.committed.core
        return Counts(
            events=len(core.events),
            outbox=len(core.outbox),
            receipts=len(core.idempotency),
            allowed=sum(1 for row in core.audit if row.decision == "allowed"),
            denied=sum(1 for row in core.audit if row.decision == "denied"),
        )

    def age() -> None:
        h.clock.advance(TTL + timedelta(seconds=1))

    def dump() -> str:
        return repr(list(h.backend.committed.core.idempotency.values()))

    return Rig(
        "memory",
        bus=bus,
        clock=h.clock,
        authorizer=h.authorizer,
        config=h.config,
        ids=ids,
        uow_factory=factory,
        age=age,
        counts=counts,
        dump=dump,
        commit_receipt=MemoryIdempotencyStore(h.backend.committed).put,
    )


# ------------------------------------------------------------------------------------------ postgres rig


def _postgres_rig(dsn: str, commands: Sequence[Any], faults: Faults | None, pool_size: int) -> Generator[Rig]:
    ids = LockedIds()
    clock = FrozenClock()
    schemas = SchemaRegistry.load(SCHEMA_ROOT)
    registry = BusRegistry.build(
        (manifest(commands=tuple(commands)),),
        schemas=schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )
    pool: PoolHandle = create_pool(
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
    writer = PostgresEventWriter(schemas=schemas, subscriptions=registry.subscription_index(), ids=ids)
    plain = PostgresUowFactory(pool, factories, writer, clock)  # clean_database seeded the SEED scopes
    factory: UnitOfWorkFactory = plain if faults is None else FaultyFactory(plain, faults)
    authorizer = FakeAuthorizer(None)
    config = FakeConfigLoader()
    with psycopg.connect(dsn, autocommit=True) as observer:

        def count(table: str, where: str = "true") -> int:
            statement = f"SELECT count(*) FROM skm_core.{table} WHERE {where}"  # noqa: S608 - literals of this test
            row = observer.execute(statement).fetchone()  # type: ignore[arg-type]
            assert row is not None
            return int(row[0])

        def counts() -> Counts:
            return Counts(
                events=count("domain_events"),
                outbox=count("outbox"),
                receipts=count("idempotency_receipts"),
                allowed=count("audit_records", "decision = 'allowed'"),
                denied=count("audit_records", "decision = 'denied'"),
            )

        def age() -> None:
            observer.execute(
                "UPDATE skm_core.idempotency_receipts SET created_at = created_at - interval '2 days', "
                "expires_at = clock_timestamp() - interval '1 second'"
            )

        def dump() -> str:
            rows = observer.execute(
                "SELECT row_to_json(t)::text FROM skm_core.idempotency_receipts t"
            ).fetchall()
            return "\n".join(row[0] for row in rows)

        def commit_receipt(receipt: IdempotencyReceipt) -> None:
            with plain(RequestMeta(request_id(99), Surface.TEST, None, clock.now())) as uow:
                uow.repo(IdempotencyStore).put(receipt)
                uow.commit()

        try:
            yield Rig(
                "postgres",
                bus=_bus(registry, schemas, factory, authorizer, config, clock, ids),
                clock=clock,
                authorizer=authorizer,
                config=config,
                ids=ids,
                uow_factory=factory,
                age=age,
                counts=counts,
                dump=dump,
                commit_receipt=commit_receipt,
            )
        finally:
            pool.close()


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def make_rig(request: pytest.FixtureRequest) -> Iterator[Callable[..., Rig]]:
    """``make_rig(commands=..., faults=..., pool_size=...)``: the rig of the memory or postgres parameter."""
    generators: list[Generator[Rig]] = []

    def make(*, commands: Sequence[Any] = (ECHO,), faults: Faults | None = None, pool_size: int = 8) -> Rig:
        if request.param == "memory":
            return _memory_rig(commands, faults)
        database: TestDatabase = request.getfixturevalue("clean_test_database")
        generator = _postgres_rig(database.dsn, commands, faults, pool_size)
        generators.append(generator)
        return next(generator)

    yield make
    for generator in generators:
        generator.close()


def other_actor() -> Actor:
    return Actor(
        principal_id=PrincipalId(UUID("01900000-0000-7000-8000-0000000000b2")),
        kind=PrincipalKind.HUMAN,
        display_name="other",
    )


def run_concurrently(calls: Sequence[Callable[[], object]]) -> list[object]:
    """Start all calls together; each slot holds the result or the raised exception."""
    barrier = threading.Barrier(len(calls))
    slots: list[object] = [None] * len(calls)

    def worker(index: int) -> None:
        barrier.wait(timeout=10)
        try:
            slots[index] = calls[index]()
        except BaseException as exc:  # noqa: BLE001 - the test inspects every outcome
            slots[index] = exc

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a concurrent dispatch never finished"
    return slots


def faulty_echo(faults: Faults, spec: Any = ECHO) -> Any:
    """``demo.echo`` whose first ``faults.in_handler`` attempts fail after the domain write."""

    def handler(cmd: Any, ctx: Any, uow: Any) -> EchoResult:
        faults.attempts += 1
        faults.attempt_ids.append(ctx.ids.new_id())
        result = handle_echo(cmd, ctx, uow)  # the first domain write: an event for the demo stream
        if faults.attempts <= faults.in_handler:
            raise faults.error()
        return result

    return replace(spec, handler=handler)


# ------------------------------------------------------------------------------------------ idempotency


def test_same_key_and_body_return_the_stored_result_without_a_second_effect(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig()
    first = rig.dispatch(rig.echo(), "k1")
    again = rig.dispatch(rig.echo(), "k1", n=2)
    assert first == again == EchoResult(text="hello")
    assert rig.counts() == Counts(events=1, outbox=2, receipts=1, allowed=1, denied=0)


def test_same_key_with_another_body_is_key_reused(make_rig: Callable[..., Rig]) -> None:
    rig = make_rig()
    rig.dispatch(rig.echo("one"), "k1")
    with pytest.raises(Conflict) as caught:
        rig.dispatch(rig.echo("two"), "k1", n=2)
    assert caught.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert rig.counts() == Counts(events=1, outbox=2, receipts=1, allowed=1, denied=0)


def test_principals_and_workspaces_have_independent_keys(make_rig: Callable[..., Rig]) -> None:
    rig = make_rig()
    rig.dispatch(rig.echo("same"), "shared")
    rig.dispatch(rig.echo("same"), "shared", actor=other_actor(), n=2)
    other_workspace = Echo(workspace_id=SEED.other_workspace_id, text="same")
    rig.dispatch(other_workspace, "shared", n=3)
    assert rig.counts() == Counts(events=3, outbox=6, receipts=3, allowed=3, denied=0)


def test_an_expired_receipt_before_the_janitor_executes_the_command_again(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig()
    rig.dispatch(rig.echo(), "k1")
    rig.age_receipts()  # still stored: no purge has run
    assert rig.counts().receipts == 1
    assert rig.dispatch(rig.echo(), "k1", n=2) == EchoResult(text="hello")
    assert rig.counts() == Counts(events=2, outbox=4, receipts=1, allowed=2, denied=0)
    rig.dispatch(rig.echo(), "k1", n=3)  # the replacement is live again
    assert rig.counts().events == 2


def test_a_secret_change_under_one_key_is_key_reused_and_no_plaintext_is_stored(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(commands=(ECHO, ECHO_SECRET))
    body = EchoSecret(workspace_id=rig.workspace_id, text="hello", secret=SECRET)
    rig.dispatch(body, "k1")
    with pytest.raises(Conflict) as caught:
        rig.dispatch(replace(body, secret=OTHER_SECRET), "k1", n=2)
    assert caught.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert rig.dispatch(body, "k1", n=3) == EchoResult(text="hello")  # the same secret still replays
    stored = rig.dump()
    assert "sha256:" in stored
    assert SECRET not in stored
    assert OTHER_SECRET not in stored
    for secret in (SECRET, OTHER_SECRET):
        assert secret not in str(caught.value) + repr(caught.value.to_problem())
    assert rig.counts().events == 1


def test_a_failed_command_stores_no_receipt_and_the_key_runs_again(make_rig: Callable[..., Rig]) -> None:
    state = {"calls": 0}

    def flaky(cmd: Any, ctx: Any, uow: Any) -> EchoResult:
        state["calls"] += 1
        result = handle_echo(cmd, ctx, uow)
        if state["calls"] == 1:
            raise RuntimeError("handler defect")
        return result

    rig = make_rig(commands=(replace(ECHO, handler=flaky),))
    with pytest.raises(SkmError):
        rig.dispatch(rig.echo(), "k1")
    assert rig.counts() == Counts(events=0, outbox=0, receipts=0, allowed=0, denied=0)
    assert rig.dispatch(rig.echo(), "k1", n=2) == EchoResult(text="hello")
    assert rig.counts() == Counts(events=1, outbox=2, receipts=1, allowed=1, denied=0)


def test_concurrent_duplicates_commit_one_aggregate_one_receipt_and_one_result(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig()
    outcomes = run_concurrently([lambda n=n: rig.dispatch(rig.echo(), "dup", n=n) for n in range(1, 5)])
    assert outcomes == [EchoResult(text="hello")] * 4
    counts = rig.counts()
    assert (counts.events, counts.outbox, counts.receipts) == (1, 2, 1)
    assert counts.allowed == 1  # the losers' audit rows were rolled back with them


def test_a_lost_receipt_race_replays_the_winner_after_a_new_authorization(
    make_rig: Callable[..., Rig],
) -> None:
    state = {"raced": False}

    def racing(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        result = handle_echo(cmd, ctx, uow)
        if not state["raced"]:
            state["raced"] = True
            now = rig.clock.now()
            # The concurrent duplicate commits first, on another connection (adapters §2.2: the memory backend
            # holds one unit of work, so its winner is written straight into the committed state).
            rig.commit_receipt(
                IdempotencyReceipt(
                    workspace_id=rig.workspace_id,
                    principal_id=rig.actor.principal_id,
                    operation="demo.echo",
                    key="race",
                    request_digest=request_digest(ECHO, cmd),
                    result={"text": "winner"},
                    created_at=now,
                    expires_at=now + TTL,
                )
            )
            if rig.kind == "memory":  # postgres: the loser's own receipt INSERT meets the committed row
                raise Conflict(ErrorCode.ALREADY_EXISTS, "lost the receipt race")
        return result

    rig = make_rig(commands=(replace(ECHO, handler=racing),))
    assert rig.dispatch(rig.echo(), "race") == EchoResult(text="winner")
    assert [call.readonly for call in rig.authorizer.calls] == [False, True]
    assert rig.counts().events == 0  # the loser's attempt rolled back with its audit row
    assert rig.counts().allowed == 0
    assert rig.counts().receipts == 1


def test_the_replay_of_a_lost_race_is_authorized_again_and_a_denial_leaks_no_result(
    make_rig: Callable[..., Rig],
) -> None:
    def racing(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        rig.authorizer.deny_all()  # the right is withdrawn while the duplicate is in flight
        raise Conflict(ErrorCode.ALREADY_EXISTS, "lost the receipt race")

    rig = make_rig(commands=(replace(ECHO, handler=racing),))
    now = rig.clock.now()
    rig.commit_receipt(
        IdempotencyReceipt(
            workspace_id=rig.workspace_id,
            principal_id=rig.actor.principal_id,
            operation="demo.echo",
            key="race",
            request_digest=request_digest(ECHO, rig.echo()),
            result={"text": "winner"},
            created_at=now,
            expires_at=now + TTL,
        )
    )
    rig.authorizer.allowed = None
    # the receipt exists, so the first lookup would replay it: age it out of the lookup, keep the row
    rig.age_receipts()
    with pytest.raises(Forbidden) as caught:
        rig.dispatch(rig.echo(), "race")
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert "winner" not in repr(caught.value.to_problem())
    assert rig.counts().denied == 1


def test_a_conflict_without_a_receipt_stays_the_original_conflict(make_rig: Callable[..., Rig]) -> None:
    def conflicting(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)
        raise Conflict(ErrorCode.ALREADY_EXISTS, "entity exists")

    rig = make_rig(commands=(replace(ECHO, handler=conflicting),))
    with pytest.raises(Conflict) as caught:
        rig.dispatch(rig.echo(), "k1")
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert rig.counts() == Counts(events=0, outbox=0, receipts=0, allowed=0, denied=0)


# ------------------------------------------------------------------------------------------ denied audit


def test_a_denied_command_leaves_a_denied_audit_row_and_nothing_else(make_rig: Callable[..., Rig]) -> None:
    rig = make_rig(
        pool_size=1
    )  # one connection: the denial can be written only after the command's UoW is left
    rig.authorizer.deny_all()
    with pytest.raises(Forbidden) as caught:
        rig.dispatch(rig.echo(), "k1")
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert rig.counts() == Counts(events=0, outbox=0, receipts=0, allowed=0, denied=1)


def test_a_denial_found_by_the_handler_rolls_its_writes_back_and_keeps_the_denied_audit(
    make_rig: Callable[..., Rig],
) -> None:
    def refusing(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)  # state is written first
        raise Forbidden(ErrorCode.FORBIDDEN, "not yours", details={"reason_code": "ROLE_LACKS_PERMISSION"})

    rig = make_rig(commands=(replace(ECHO, handler=refusing),), pool_size=1)
    with pytest.raises(Forbidden):
        rig.dispatch(rig.echo(), "k1")
    assert rig.counts() == Counts(events=0, outbox=0, receipts=0, allowed=0, denied=1)


# ------------------------------------------------------------------------------------------ bounded retry


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_a_retryable_failure_after_the_first_write_repeats_the_whole_command(
    make_rig: Callable[..., Rig], code: str
) -> None:
    faults = Faults(in_handler=1, code=code)
    rig = make_rig(commands=(faulty_echo(faults),), faults=faults)
    assert rig.dispatch(rig.echo(), "k1") == EchoResult(text="hello")
    assert faults.attempts == 2
    assert rig.counts() == Counts(events=1, outbox=2, receipts=1, allowed=1, denied=0)
    # a new unit of work repeats scope, authorization and config: nothing is carried over from the rollback
    assert [call.readonly for call in rig.authorizer.calls] == [False, False]
    assert rig.config.calls == 2
    assert rig.dispatch(rig.echo(), "k1", n=2) == EchoResult(
        text="hello"
    )  # the stored receipt serves a repeat
    assert faults.attempts == 2


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_a_retryable_failure_in_place_of_commit_repeats_the_whole_command(
    make_rig: Callable[..., Rig], code: str
) -> None:
    faults = Faults(at_commit=2, code=code)
    rig = make_rig(commands=(faulty_echo(faults),), faults=faults)
    assert rig.dispatch(rig.echo(), "k1") == EchoResult(text="hello")
    assert faults.attempts == 3  # two rolled-back attempts, the third commits
    assert rig.counts() == Counts(events=1, outbox=2, receipts=1, allowed=1, denied=0)
    assert len(rig.authorizer.calls) == 3
    assert rig.config.calls == 3


def test_ids_of_rolled_back_attempts_are_not_visible_and_nothing_external_is_called(
    make_rig: Callable[..., Rig],
) -> None:
    faults = Faults(in_handler=2)
    rig = make_rig(commands=(faulty_echo(faults),), faults=faults)
    result = rig.dispatch(rig.echo(), "k1")
    assert result == EchoResult(text="hello")
    assert len(set(faults.attempt_ids)) == 3  # every attempt drew fresh ids from the shared generator
    visible = rig.dump() + repr(result)
    for attempt_id in faults.attempt_ids:  # none of them reached the result or the stored receipt
        assert str(attempt_id) not in visible
    assert (
        faults.external_calls == []
    )  # the bus has no external effect of its own; the outbox only holds rows
    counts = rig.counts()
    assert (counts.events, counts.outbox, counts.receipts, counts.allowed) == (1, 2, 1, 1)


@pytest.mark.parametrize("code", ["40001", "40P01"])
def test_retry_exhaustion_keeps_the_canonical_error_and_commits_nothing(
    make_rig: Callable[..., Rig], code: str
) -> None:
    faults = Faults(in_handler=99, code=code)
    rig = make_rig(commands=(faulty_echo(faults),), faults=faults)
    with pytest.raises(Conflict) as caught:
        rig.dispatch(rig.echo(), "k1")
    assert caught.value.code is ErrorCode.SERIALIZATION_FAILURE
    assert caught.value.retryable is True
    assert faults.attempts == ATTEMPTS  # bounded: max_attempts, not one more
    assert rig.counts() == Counts(events=0, outbox=0, receipts=0, allowed=0, denied=0)
    assert len(rig.authorizer.calls) == ATTEMPTS


def test_a_keyless_command_is_retried_too_and_stores_no_receipt(make_rig: Callable[..., Rig]) -> None:
    faults = Faults(in_handler=1)
    rig = make_rig(commands=(faulty_echo(faults),), faults=faults)
    assert rig.dispatch(rig.echo()) == EchoResult(text="hello")
    assert faults.attempts == 2
    assert rig.counts() == Counts(events=1, outbox=2, receipts=0, allowed=1, denied=0)
