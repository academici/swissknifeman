"""Config on PostgreSQL: the settings repositories, ``ConfigStore`` and the real loader (settings §A.6, §A.11,
§B.10, §B.13).

The same scenarios run on memory and PostgreSQL (``side``): repositories keep every JSON value with its type,
a rollback leaves nothing, a write committed through one unit-of-work factory and its ``ConfigLoader`` is seen
by a second, independent loader (on PostgreSQL over its own pool on the same database; the cross-process CLI
scenario is tested separately), a failed command changes no generation, history or entry, and one import is
one generation with all its changes or none. PostgreSQL-only cases (``pg_side``) use real concurrency: two
commands writing keys bound by one section validator serialize on the generation row, so the second one is
checked against the first one's commit; concurrent saves of one entry conflict on the version; and
``pending_writes`` follows the transaction (writer mark, generation ``xmin``, savepoints, read-only).
"""

import itertools
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast, override
from uuid import UUID

import psycopg
import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.settings import REPOSITORIES as MEMORY_SETTINGS
from skm.adapters.memory.settings.repositories import settings_state
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.postgres.config_store import PostgresConfigStore, PostgresScopeTree
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.postgres.uow import PostgresUnitOfWork, PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.settings.domain.entry import (
    ConfigEntryId,
    EntryOp,
    change_entry,
    new_entry,
    same_value,
)
from skm.modules.settings.domain.history import ChangeKind, history_record
from skm.modules.settings.generated import commands
from skm.modules.settings.module import MODULE
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter, ConfigHistoryRepository
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, PackConfigSource, ScopeTree
from support import pg
from support.backend import LockedIds
from support.fault_injection import FaultPlan, FaultPoint, InjectedFault, faulty_uow_factory
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401 - fixtures by name
from support.registries import schemas, settings_registry
from support.seed import SEED

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = (ROOT / "tests/fixtures/corpus/examples/config/project-import.toml").read_text(encoding="utf-8")

INSTANCE = SEED.instance_id
WORKSPACE = ScopeId(SEED.workspace_id)
PROJECT = ScopeId(UUID("01900000-0000-7000-8000-0000000000c1"))
PLAN = ScopeId(UUID("01900000-0000-7000-8000-0000000000d1"))
KINDS = {
    INSTANCE: ScopeKind.INSTANCE,
    WORKSPACE: ScopeKind.WORKSPACE,
    PROJECT: ScopeKind.PROJECT,
    PLAN: ScopeKind.PLAN,
}
ACTOR = Actor(SEED.principal_id, PrincipalKind.HUMAN, "tester")
PRINCIPAL = PrincipalId(SEED.principal_id)
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
EVERYTHING = frozenset(CATALOG)

ROUNDS = "execution.review.max_rounds"
RUN_USD = "budgets.run.max_usd"
TASK_USD = "budgets.task.max_usd"
CONFIG_CHANGED = "urn:skm:settings:event:config-changed:v1"


@cache
def bus_registry() -> BusRegistry:
    return BusRegistry.build(
        (MODULE,), schemas=schemas(), permission_catalog=EVERYTHING, disabled_modules=frozenset()
    )


# ---------------------------------------------------------------------------------------------------------
# one backend with a bus, its loader and committed-state observations


@dataclass
class Side:
    kind: str
    uow_factory: UnitOfWorkFactory
    clock: FrozenClock
    ids: LockedIds
    # committed state, seen from outside every unit of work
    generation: Callable[[], int]
    history: Callable[[], list[tuple[str, str, int]]]  # (key, change_kind, generation), oldest first
    entries: Callable[[], dict[tuple[UUID, str], tuple[str, JsonValue, bool, int]]]
    config_events: Callable[[], list[int]]  # generation of every committed ConfigChanged
    # an independent loader: memory over the same state, PostgreSQL over its own pool
    independent: Callable[[], tuple[UnitOfWorkFactory, ConfigLoader]]
    loader: ConfigLoader = field(init=False)
    bus: Bus = field(init=False)
    closers: list[Callable[[], None]] = field(default_factory=list[Callable[[], None]])
    dsn: str = ""  # PostgreSQL only: the session database
    _requests: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def __post_init__(self) -> None:
        self.loader = ConfigLoader(settings_registry(), EmptyPackConfigSource())
        self.bus = self.make_bus()

    def make_bus(self, uow_factory: UnitOfWorkFactory | None = None) -> Bus:
        return Bus(
            registry=bus_registry(),
            schemas=schemas(),
            uow_factory=uow_factory or self.uow_factory,
            authorizer=AUTHORIZER,
            scopes=FakeScopeChain(),
            config=self.loader,
            clock=self.clock,
            ids=self.ids,
            entropy=DeterministicEntropy(),
            gateways=GatewayTable({}, "control_plane_gateway"),
            retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=timedelta(hours=1),
        )

    def meta(self) -> RequestMeta:
        return RequestMeta(f"req_{next(self._requests):0>26}", Surface.TEST, None, self.clock.now())

    def run(self, dto: object, *, bus: Bus | None = None) -> Any:
        return (bus or self.bus).dispatch(dto, actor=ACTOR, meta=self.meta())

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        return self.uow_factory(self.meta(), readonly=readonly)

    def snapshot(self) -> tuple[object, ...]:
        return (self.generation(), self.history(), self.entries(), self.config_events())

    def close(self) -> None:
        for closer in reversed(self.closers):
            closer()


AUTHORIZER = FakeAuthorizer(None)


def _ports() -> dict[type, Callable[[Any], object]]:
    return {
        PackConfigSource: lambda _conn: EmptyPackConfigSource(),
        Authorizer: lambda _conn: AUTHORIZER,
    }


def _create_scopes(uow_factory: UnitOfWorkFactory, meta: RequestMeta, *, with_root: bool) -> None:
    with uow_factory(meta) as uow:
        scopes = uow.repo(ScopeRegistry)
        ws = WorkspaceId(WORKSPACE)
        if with_root:
            scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
            scopes.create(WORKSPACE, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=ws)
        scopes.create(PROJECT, ScopeKind.PROJECT, parent=WORKSPACE, workspace_id=ws)
        scopes.create(PLAN, ScopeKind.PLAN, parent=PROJECT, workspace_id=ws)
        uow.commit()


def memory_side() -> Side:
    clock, ids = FrozenClock(), LockedIds()
    backend = InMemoryBackend(
        factories={**MEMORY_CORE, **MEMORY_SETTINGS, ConfigStore: MemoryConfigStore, **_ports()},
        schemas=schemas(),
        subscriptions=bus_registry().subscription_index(),
        ids=ids,
        clock=clock,
    )
    factory = backend.uow_factory()

    def history() -> list[tuple[str, str, int]]:
        records = settings_state(backend.committed).history
        return [(item.key, item.change_kind.value, item.generation) for item in records]

    def entries() -> dict[tuple[UUID, str], tuple[str, JsonValue, bool, int]]:
        tables = settings_state(backend.committed).entries
        return {
            (scope_id, key): (item.op.value, item.value, item.locked, item.row_version)
            for scope_id, rows in tables.items()
            for key, item in rows.items()
        }

    def events() -> list[int]:
        found = backend.committed.core.events
        return [cast("int", item.payload["generation"]) for item in found if item.type == CONFIG_CHANGED]

    side = Side(
        "memory",
        factory,
        clock,
        ids,
        generation=lambda: backend.committed.core.config_generation,
        history=history,
        entries=entries,
        config_events=events,
        independent=lambda: (factory, ConfigLoader(settings_registry(), EmptyPackConfigSource())),
    )
    _create_scopes(factory, side.meta(), with_root=True)
    return side


type _PgFactories = Mapping[type, Callable[[psycopg.Connection], object]]


def _pg_factories() -> dict[type, Callable[[psycopg.Connection], object]]:
    return {
        **cast("_PgFactories", postgres_repository_table(("settings",))),
        ConfigStore: PostgresConfigStore,
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        **_ports(),
    }


def _pool(database: pg.TestDatabase) -> PoolHandle:
    return create_pool(
        PgSettings(
            dsn=database.dsn,
            application_name="skm-test",
            pool_min_size=1,
            pool_max_size=6,
            pool_timeout_seconds=5,
        )
    )


def postgres_side(database: pg.TestDatabase) -> Side:
    clock, ids = FrozenClock(), LockedIds()
    writer = PostgresEventWriter(
        schemas=schemas(), subscriptions=bus_registry().subscription_index(), ids=ids
    )
    closers: list[Callable[[], None]] = []
    pool = _pool(database)
    closers.append(pool.close)
    observer = psycopg.connect(database.dsn, autocommit=True, connect_timeout=5)
    closers.append(observer.close)
    factory = PostgresUowFactory(pool, _pg_factories(), writer, clock)

    def generation() -> int:
        row = observer.execute("SELECT value FROM skm_config.generation WHERE id = 1").fetchone()
        assert row is not None
        return cast("int", row[0])

    def history() -> list[tuple[str, str, int]]:
        rows = observer.execute(
            "SELECT key, change_kind, generation FROM skm_config.entry_history ORDER BY generation, key, id"
        ).fetchall()
        return [cast("tuple[str, str, int]", tuple(row)) for row in rows]

    def entries() -> dict[tuple[UUID, str], tuple[str, JsonValue, bool, int]]:
        rows = observer.execute(
            "SELECT scope_id, key, op, value, locked, row_version FROM skm_config.entries"
        ).fetchall()
        return {(row[0], row[1]): (row[2], row[3], row[4], row[5]) for row in rows}

    def events() -> list[int]:
        rows = observer.execute(
            "SELECT (payload->>'generation')::bigint FROM skm_core.domain_events "
            "WHERE event_type = %s ORDER BY id",
            (CONFIG_CHANGED,),
        ).fetchall()
        return [cast("int", row[0]) for row in rows]

    def independent() -> tuple[UnitOfWorkFactory, ConfigLoader]:
        other = _pool(database)  # another pool on the same database: nothing is shared with the writer
        closers.append(other.close)
        other_writer = PostgresEventWriter(
            schemas=schemas(), subscriptions=bus_registry().subscription_index(), ids=LockedIds()
        )
        return (
            PostgresUowFactory(other, _pg_factories(), other_writer, FrozenClock()),
            ConfigLoader(settings_registry(), EmptyPackConfigSource()),
        )

    side = Side(
        "postgres",
        factory,
        clock,
        ids,
        generation=generation,
        history=history,
        entries=entries,
        config_events=events,
        independent=independent,
        closers=closers,
        dsn=database.dsn,
    )
    _create_scopes(factory, side.meta(), with_root=False)  # clean_database seeded instance and workspaces
    return side


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def side(request: pytest.FixtureRequest) -> Iterator[Side]:
    made = (
        memory_side()
        if request.param == "memory"
        else postgres_side(request.getfixturevalue("clean_test_database"))
    )
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def pg_side(request: pytest.FixtureRequest) -> Iterator[Side]:
    """The PostgreSQL side alone; its tests carry the ``pg`` marker themselves."""
    made = postgres_side(request.getfixturevalue("clean_test_database"))
    try:
        yield made
    finally:
        made.close()


# ---------------------------------------------------------------------------------------------------------
# helpers


def entry(
    scope_id: ScopeId, key: str = ROUNDS, value: Any = 1, *, n: int = 1, op: EntryOp = EntryOp.SET
) -> Any:
    return new_entry(
        entry_id=ConfigEntryId(UUID(int=n)),
        scope=ScopeRef(KINDS[scope_id], scope_id),
        key=key,
        op=op,
        value=value,
        locked=False,
        reason="",
        actor=PRINCIPAL,
        now=NOW,
    )


def set_value(level: str, scope_id: UUID, key: str, value: JsonValue, **fields: Any) -> commands.SetValue:
    scope = commands.SetValueDefsScopeRef(level=cast("Any", level), scope_id=scope_id)
    return commands.SetValue(scope=scope, key=key, value=value, **fields)


def import_config(document: Any, **fields: Any) -> commands.ImportConfig:
    fields.setdefault("format", "toml" if isinstance(document, str) else "json")
    scope = commands.ImportConfigDefsScopeRef(level="project", scope_id=PROJECT)
    return commands.ImportConfig(scope=scope, document=document, **fields)


def effective(uow_factory: UnitOfWorkFactory, loader: ConfigLoader, meta: RequestMeta) -> Any:
    with uow_factory(meta, readonly=True) as uow:
        return loader.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PROJECT, PROJECT)
        )


def strict_equal(left: JsonValue, right: JsonValue) -> bool:
    """Equal JSON values of equal types (a float is not the integer it equals)."""
    return same_value(left, right)


# ---------------------------------------------------------------------------------------------------------
# repositories and ConfigStore (memory ∥ postgres)

VALUES: Mapping[str, JsonValue] = {
    "values.float_exponent": 1e16,
    "values.float_small": 1e-7,
    "values.float_plain": 15.0,
    "values.wide_integer": 10**1500 + 7,
    "values.negative": -42,
    "values.text": 'tab\tquote" ünï ✓',
    "values.nested": {"b": [True, None, 1.5, {"$unset": True}], "a": {"z": -0.25}},
    "values.empty": [],
}


def test_every_json_value_reads_back_with_its_type(side: Side) -> None:
    with side.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        for n, (key, value) in enumerate(VALUES.items(), start=1):
            repo.add(entry(PROJECT, key, value, n=n))
        repo.add(entry(PROJECT, "values.unset", None, n=99, op=EntryOp.UNSET))
        uow.commit()
    with side.uow(readonly=True) as uow:
        found = uow.repo(ConfigEntryRepository).entries_of_scope(PROJECT)
        stored = uow.repo(ConfigStore).entries_for([PROJECT, PROJECT, PLAN])
        assert set(stored) == {PROJECT}
        for key, value in VALUES.items():
            assert strict_equal(found[key].value, value), key
            assert strict_equal(stored[PROJECT][key].value, value), key
        assert (found["values.unset"].op, found["values.unset"].value) == (EntryOp.UNSET, None)
        assert stored[PROJECT]["values.unset"].value is None
        assert found["values.float_exponent"] == entry(PROJECT, "values.float_exponent", 1e16, n=1)


def test_a_rolled_back_write_leaves_nothing_and_is_pending_inside(side: Side) -> None:
    with side.uow(readonly=True) as uow:
        assert uow.repo(ConfigStore).pending_writes() is False
    created = entry(PROJECT)
    with side.uow() as uow:
        store = uow.repo(ConfigStore)
        assert store.pending_writes() is False
        uow.repo(ConfigEntryRepository).add(created)
        generation = uow.repo(ConfigGenerationCounter).increment()
        uow.repo(ConfigHistoryRepository).append(
            history_record(
                record_id=UUID(int=500),
                before=None,
                after=created,
                kind=ChangeKind.CREATED,
                actor=PRINCIPAL,
                request_id=None,
                reason="",
                generation=generation,
                now=NOW,
            )
        )
        assert store.pending_writes() is True
        assert store.generation() == 1
        assert ROUNDS in store.entries_for([PROJECT])[PROJECT]
    assert side.snapshot() == (0, [], {}, [])
    with side.uow() as uow:
        assert uow.repo(ConfigStore).pending_writes() is False


def test_cas_duplicates_and_listings(side: Side) -> None:
    first = entry(PROJECT)
    with side.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        repo.add(first)
        for n, (scope_id, key) in enumerate(
            [
                (INSTANCE, ROUNDS),
                (WORKSPACE, ROUNDS),
                (PLAN, ROUNDS),
                (PROJECT, "aa.b_c"),
                (PROJECT, "aa.b.c"),
            ],
            start=2,
        ):
            repo.add(entry(scope_id, key, n=n))
        with pytest.raises(Conflict) as caught:
            repo.add(entry(PROJECT, n=50))
        assert caught.value.code is ErrorCode.ALREADY_EXISTS
        assert caught.value.details["key"] == ROUNDS
        with pytest.raises(Conflict) as caught:
            repo.add(entry(PLAN, "aa.b_c", n=1))  # the id of ``first``
        assert caught.value.details == {"kind": "config_entry", "ref": str(UUID(int=1))}
        uow.commit()  # the refused inserts did not break the transaction
    changed = change_entry(first, op=EntryOp.SET, value=2, reason="", actor=PRINCIPAL, now=NOW)
    with side.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        with pytest.raises(Conflict) as caught:
            repo.save(changed, expected_version=2)
        assert caught.value.details == {"expected": 2, "actual": 1}
        repo.save(changed, expected_version=1)
        with pytest.raises(Conflict) as caught:
            repo.remove(first.id, expected_version=1)
        assert caught.value.details == {"expected": 1, "actual": 2}
        uow.commit()
    with side.uow(readonly=True) as uow:
        repo = uow.repo(ConfigEntryRepository)
        assert repo.get(first.id) == changed
        assert list(repo.entries_of_scope(PROJECT)) == ["aa.b.c", "aa.b_c", ROUNDS]  # byte order of keys
        pages, after = [], None
        while True:
            page = repo.list(scope_id=None, level=None, key_prefix=None, after=after, limit=2)
            pages.append([(item.key, str(item.scope.id)) for item in page.items])
            after = page.next
            if after is None:
                break
        flat = [item for page in pages for item in page]
        assert flat == sorted(flat)
        assert [len(page) for page in pages] == [2, 2, 2]
        prefixed = repo.list(scope_id=None, level=None, key_prefix="aa.b_", after=None, limit=10)
        assert [item.key for item in prefixed.items] == ["aa.b_c"]  # ``_`` is no wildcard
        by_level = repo.list(scope_id=None, level=ScopeKind.PLAN, key_prefix=None, after=None, limit=10)
        assert [item.scope.id for item in by_level.items] == [PLAN]
        assert repo.count_shadowed_below(INSTANCE, ROUNDS) == 3
        assert repo.count_shadowed_below(WORKSPACE, ROUNDS) == 2
        assert repo.count_shadowed_below(PLAN, ROUNDS) == 0
        with pytest.raises(SkmError) as bad:
            repo.list(scope_id=None, level=None, key_prefix=None, after="bm90IGEgY3Vyc29y", limit=2)
        assert bad.value.code is ErrorCode.SCHEMA_INVALID


def test_history_pages_newest_first(side: Side) -> None:
    with side.uow() as uow:
        counter = uow.repo(ConfigGenerationCounter)
        history = uow.repo(ConfigHistoryRepository)
        assert [counter.increment() for _ in range(3)] == [1, 2, 3]
        for n in range(1, 4):
            history.append(
                history_record(
                    record_id=UUID(int=n),
                    before=None,
                    after=entry(PROJECT if n < 3 else WORKSPACE, value=0.5, n=n),
                    kind=ChangeKind.CREATED,
                    actor=PRINCIPAL,
                    request_id=f"req_{n}",
                    reason="",
                    generation=n,
                    now=NOW + timedelta(seconds=n % 2),
                )
            )
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(ConfigGenerationCounter).current() == 3
        history = uow.repo(ConfigHistoryRepository)
        first = history.list(scope_id=None, key=None, after=None, limit=2)
        rest = history.list(scope_id=None, key=None, after=first.next, limit=2)
        assert [record.id.int for record in (*first.items, *rest.items)] == [3, 1, 2]
        assert rest.next is None
        assert strict_equal(first.items[0].new_value, 0.5)
        project = history.list(scope_id=PROJECT, key=None, after=None, limit=10)
        assert [record.id.int for record in project.items] == [1, 2]
        with pytest.raises(SkmError) as bad:
            history.list(scope_id=None, key=None, after="bm90IGEgY3Vyc29y", limit=2)
        assert bad.value.code is ErrorCode.SCHEMA_INVALID


# ---------------------------------------------------------------------------------------------------------
# bus, loader and an independent loader (memory ∥ postgres)


def test_a_committed_write_is_seen_by_an_independent_loader(side: Side) -> None:
    factory, loader = side.independent()
    before = effective(factory, loader, side.meta())
    assert (before.generation, before.resolution(ROUNDS).value) == (0, 2)
    assert effective(factory, loader, side.meta()) is before  # cached by generation

    result = side.run(set_value("project", PROJECT, ROUNDS, 1, reason="tighter"))
    assert (result.changed, result.generation) == (True, 1)

    after = effective(factory, loader, side.meta())
    assert after is not before
    assert after.generation == 1
    resolution = after.resolution(ROUNDS)
    assert resolution.value == 1
    assert resolution.winner is not None
    assert resolution.winner.entry_id == result.entry.entry_id
    assert side.history() == [(ROUNDS, "created", 1)]
    assert side.config_events() == [1]
    assert effective(side.uow_factory, side.loader, side.meta()).resolution(ROUNDS).value == 1


def test_a_failed_command_changes_no_generation_history_or_entry(side: Side) -> None:
    side.run(set_value("project", PROJECT, RUN_USD, 10))
    before = side.snapshot()
    with pytest.raises(SkmError) as caught:  # R14: budgets.task_le_run on the candidate
        side.run(set_value("project", PROJECT, TASK_USD, 15))
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert side.snapshot() == before
    with pytest.raises(SkmError) as caught:  # CAS: the entry is at version 1
        side.run(set_value("project", PROJECT, RUN_USD, 9, expected_row_version=2))
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    assert side.snapshot() == before

    # Everything is written, then the unit of work fails before COMMIT: the whole transaction vanishes.
    failing = side.make_bus(
        faulty_uow_factory(side.uow_factory, FaultPlan({FaultPoint.UOW_BEFORE_COMMIT: 1}))
    )
    with pytest.raises((InjectedFault, SkmError)):
        side.run(set_value("project", PROJECT, TASK_USD, 5), bus=failing)
    assert side.snapshot() == before
    factory, loader = side.independent()
    assert effective(factory, loader, side.meta()).generation == 1

    done = side.run(set_value("project", PROJECT, TASK_USD, 5))
    assert done.generation == 2  # no generation was lost to the failures
    assert side.history() == [(RUN_USD, "created", 1), (TASK_USD, "created", 2)]


def test_an_import_is_one_generation_with_all_changes_or_none(side: Side) -> None:
    refused = {
        "budgets": {"run": {"max_usd": 10}, "task": {"max_usd": 15}},
        "execution": {"review": {"max_rounds": 1}},
    }
    with pytest.raises(SkmError) as caught:
        side.run(import_config(refused))
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert side.snapshot() == (0, [], {}, [])

    applied = side.run(import_config(EXAMPLE, confirmed=True))
    assert (applied.applied, applied.generation) == (True, 1)
    keys = sorted(item.key for item in applied.changes)
    assert len(keys) > 5
    assert side.generation() == 1
    history = side.history()
    assert sorted(key for key, _kind, _generation in history) == keys
    assert {generation for _key, _kind, generation in history} == {1}
    assert side.config_events() == [1]
    stored = side.entries()
    assert {key for _scope, key in stored} == set(keys)
    assert strict_equal(stored[(PROJECT, RUN_USD)][1], 15.0)

    factory, loader = side.independent()
    seen = effective(factory, loader, side.meta())
    assert seen.generation == 1
    assert strict_equal(cast("JsonValue", seen.resolution(RUN_USD).value), 15.0)
    for item in applied.effective_diff:
        assert seen.resolution(item.key).value == item.after, item.key

    again = side.run(import_config(EXAMPLE, confirmed=True))  # the same document: nothing to write
    assert (again.applied, again.generation) == (True, 1)
    assert side.generation() == 1


# ---------------------------------------------------------------------------------------------------------
# PostgreSQL: concurrency, locks and pending writes


class _HoldCommit:
    """A unit of work that stops before COMMIT until ``release`` is set."""

    def __init__(self, inner: UnitOfWork, reached: threading.Event, release: threading.Event) -> None:
        self._inner, self._reached, self._release = inner, reached, release

    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._inner.__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        self._reached.set()
        assert self._release.wait(10), "the held commit was never released"
        self._inner.commit()

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class _Run(threading.Thread):
    def __init__(self, call: Callable[[], object]) -> None:
        super().__init__(daemon=True)
        self._call = call
        self.result: object = None
        self.error: BaseException | None = None

    @override
    def run(self) -> None:
        try:
            self.result = self._call()
        except BaseException as exc:  # noqa: BLE001 - handed to the test thread
            self.error = exc


def _wait_for_lock_waiter(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = conn.execute(
                "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                "WHERE NOT l.granted AND a.datname = current_database()"
            ).fetchone()
            if row is not None and cast("int", row[0]) > 0:
                return
            time.sleep(0.02)
    raise AssertionError("the second writer never waited for a lock")


@pytest.mark.pg
def test_writers_of_keys_bound_by_one_validator_serialize(pg_side: Side) -> None:
    pg_side.run(set_value("project", PROJECT, RUN_USD, 20))
    pg_side.run(set_value("project", PROJECT, TASK_USD, 5))
    reached, release = threading.Event(), threading.Event()

    def holding(meta: RequestMeta, **options: Any) -> UnitOfWork:
        return cast("UnitOfWork", _HoldCommit(pg_side.uow_factory(meta, **options), reached, release))

    holder = pg_side.make_bus(cast("UnitOfWorkFactory", holding))
    # Each write alone keeps budgets.task_le_run (task 5 ≤ run 8; task 15 ≤ run 20), together they break it.
    first = _Run(lambda: pg_side.run(set_value("project", PROJECT, RUN_USD, 8), bus=holder))
    first.start()
    assert reached.wait(10), first.error
    second = _Run(lambda: pg_side.run(set_value("project", PROJECT, TASK_USD, 15)))
    second.start()
    try:
        _wait_for_lock_waiter(pg_side.dsn)
    finally:
        release.set()
        first.join(10)
        second.join(10)
    assert first.error is None, first.error
    assert isinstance(second.error, SkmError), second.error
    assert second.error.code is ErrorCode.CONFIG_INVALID  # checked against the first writer's commit
    stored = pg_side.entries()
    assert (stored[(PROJECT, RUN_USD)][1], stored[(PROJECT, TASK_USD)][1]) == (8, 5)
    assert pg_side.generation() == 3
    assert [generation for _key, _kind, generation in pg_side.history()] == [1, 2, 3]


@pytest.mark.pg
def test_concurrent_saves_of_one_entry_conflict_on_the_version(pg_side: Side) -> None:
    first = entry(PROJECT)
    with pg_side.uow() as uow:
        uow.repo(ConfigEntryRepository).add(first)
        uow.commit()
    one = change_entry(first, op=EntryOp.SET, value=2, reason="", actor=PRINCIPAL, now=NOW)
    other = change_entry(first, op=EntryOp.SET, value=3, reason="", actor=PRINCIPAL, now=NOW)
    saved = threading.Event()
    release = threading.Event()

    def writer() -> None:
        with pg_side.uow() as uow:
            uow.repo(ConfigEntryRepository).save(one, expected_version=1)
            saved.set()
            assert release.wait(10)
            uow.commit()

    def racer() -> None:
        with pg_side.uow() as uow:
            uow.repo(ConfigEntryRepository).save(other, expected_version=1)
            uow.commit()

    holder = _Run(writer)
    holder.start()
    assert saved.wait(10), holder.error
    late = _Run(racer)
    late.start()
    try:
        _wait_for_lock_waiter(pg_side.dsn)
    finally:
        release.set()
        holder.join(10)
        late.join(10)
    assert holder.error is None, holder.error
    assert isinstance(late.error, Conflict), late.error
    assert late.error.details == {"expected": 1, "actual": 2}
    assert pg_side.entries()[(PROJECT, ROUNDS)] == ("set", 2, False, 2)


@pytest.mark.pg
def test_pending_writes_follows_the_transaction(pg_side: Side) -> None:
    with pg_side.uow() as uow:
        store = uow.repo(ConfigStore)
        conn = cast("PostgresUnitOfWork", uow).connection
        with conn.transaction(force_rollback=True):  # a savepoint, rolled back at its end
            uow.repo(ConfigGenerationCounter).increment()
            assert store.pending_writes() is True  # the mark: xmin is the savepoint's own id here
        assert store.pending_writes() is False
        assert store.generation() == 0
    with pg_side.uow() as uow:
        # A writer that bypasses the repositories still moves the generation row: its xmin is ours.
        cast("PostgresUnitOfWork", uow).connection.execute(
            "UPDATE skm_config.generation SET value = value + 1 WHERE id = 1"
        )
        assert uow.repo(ConfigStore).pending_writes() is True
        uow.commit()
    with pg_side.uow() as uow:
        assert uow.repo(ConfigStore).pending_writes() is False  # a committed write does not carry over
        assert uow.repo(ConfigStore).generation() == 1
        uow.repo(ConfigEntryRepository).add(entry(PROJECT))
        assert uow.repo(ConfigStore).pending_writes() is True  # the writer mark, without the generation


@pytest.mark.pg
def test_the_loader_never_caches_uncommitted_configuration(pg_side: Side) -> None:
    factory, loader = pg_side.independent()
    committed = effective(factory, loader, pg_side.meta())
    with factory(pg_side.meta()) as uow:
        uow.repo(ConfigEntryRepository).add(entry(PROJECT, value=1))
        uow.repo(ConfigGenerationCounter).increment()
        own = loader.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PROJECT, PROJECT)
        )
        assert (own.generation, own.resolution(ROUNDS).value) == (1, 1)  # its own uncommitted write
    again = effective(factory, loader, pg_side.meta())
    assert again is committed  # the rolled-back snapshot never entered the cache
    assert again.resolution(ROUNDS).value == 2


@pytest.mark.pg
def test_history_is_append_only_and_the_generation_row_stays(pg_side: Side) -> None:
    pg_side.run(set_value("project", PROJECT, ROUNDS, 1))
    with psycopg.connect(pg_side.dsn, autocommit=True, connect_timeout=5) as conn:
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute("UPDATE skm_config.entry_history SET reason = 'rewritten'")
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute("DELETE FROM skm_config.entry_history")
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute("DELETE FROM skm_config.generation")
    assert pg_side.history() == [(ROUNDS, "created", 1)]
    assert pg_side.generation() == 1


def test_the_settings_ports_and_the_scope_tree_are_bound_for_postgres() -> None:
    table = postgres_repository_table(("settings",))
    assert table[ScopeTree] is PostgresScopeTree  # config_store's scope tree is the bound core one
    assert {ConfigEntryRepository, ConfigHistoryRepository, ConfigGenerationCounter} <= set(table)
    assert ConfigStore not in table  # bound by the composition, as for memory
