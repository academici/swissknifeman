"""``PostgresUnitOfWork`` on a live server (adapters §1.3-1.4, kernel-platform §2.9/§2.11).

Every test gets a scratch database built from ``SKM_TEST_DATABASE_URL`` with the whole migration chain, an
instance scope and two workspaces. State, events and outbox rows are observed through a separate autocommit
connection, so "nothing persisted" means nothing any other session can see.
"""

import importlib
import os
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import ClassVar, LiteralString, cast, override
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
from skm.adapters.postgres.core.events_store import PostgresEventReader, PostgresEventWriter
from skm.adapters.postgres.core.scopes import PostgresScopeRegistry
from skm.adapters.postgres.jsonb import to_jsonb
from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.postgres.uow import PostgresUnitOfWork, PostgresUowFactory
from skm.application_bus.ports import EventReader
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, InternalError, ValidationFailed
from skm.kernel.events import DomainEvent
from skm.kernel.ids import EventId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Isolation, RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.platform.config.store import ScopeTree
from skm.platform.schema.registry import SchemaRegistry

pg = pytest.mark.pg

ECHOED = Echoed.event_type
NOTED = Noted.event_type
SUBSCRIPTIONS = MappingProxyType({ECHOED: ("demo.on_echoed",)})
FACTORIES = REPOSITORIES


@dataclass(frozen=True, slots=True)
class ProjectEchoed(DomainEvent):
    """A workspace event on its own (project) stream, validated by the demo ``echoed`` schema."""

    event_type: ClassVar[str] = ECHOED
    stream_kind: ClassVar[str] = "project"

    workspace_id: WorkspaceId
    project: UUID
    text: str

    @override
    def stream_id(self) -> UUID:
        return self.project

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


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only against a loopback or socket test server (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail(
            "UoW tests create databases only on a local server through an '*_test' database", pytrace=False
        )


def _migrate(dsn: str) -> None:
    MigrationRunner(dsn, discover_migrations(), package_loader(), _RunnerClock(), "skm-test").migrate()


# Migrated template database per admin DSN, cloned by every test that needs the whole chain.
_TEMPLATES: dict[str, str] = {}


def _template(admin: psycopg.Connection, pg_dsn: str) -> str:
    name = _TEMPLATES.get(pg_dsn)
    if name is None:
        name = f"skm_t_uow_tpl_{os.getpid()}_{uuid4().hex[:8]}"
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        _TEMPLATES[pg_dsn] = name  # dropped at module end even if the migration fails
        _migrate(make_conninfo(pg_dsn, dbname=name))
    return name


@pytest.fixture(scope="module", autouse=True)
def _drop_templates() -> Iterator[None]:
    yield
    for pg_dsn, name in _TEMPLATES.items():
        with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
    _TEMPLATES.clear()


def _database(pg_dsn: str, *, migrated: bool) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_uow_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        create = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
        if migrated:
            create = sql.SQL("{} TEMPLATE {}").format(create, sql.Identifier(_template(admin, pg_dsn)))
        admin.execute(create)
        try:
            yield make_conninfo(pg_dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    """DSN of an empty scratch database; the test migrates it itself."""
    yield from _database(pg_dsn, migrated=False)


@pytest.fixture
def migrated(pg_dsn: str) -> Iterator[str]:
    """DSN of a scratch database with the whole migration chain."""
    yield from _database(pg_dsn, migrated=True)


@dataclass
class World:
    observer: psycopg.Connection
    pool: PoolHandle
    writer: PostgresEventWriter
    uows: PostgresUowFactory
    clock: FrozenClock
    instance: UUID
    ws_a: WorkspaceId
    ws_b: WorkspaceId

    def meta(
        self, n: int = 1, *, correlation_id: str | None = None, causation_id: str | None = None
    ) -> RequestMeta:
        return RequestMeta(
            request_id(n),
            Surface.TEST,
            None,
            self.clock.now(),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def count(self, statement: LiteralString, params: tuple[object, ...] = ()) -> int:
        row = self.observer.execute(statement, params).fetchone()
        assert row is not None
        return int(row[0])

    def events(self) -> list[tuple[object, ...]]:
        return self.observer.execute(
            "SELECT id, workspace_id, stream_kind, stream_id, stream_seq, workspace_seq, global_position, "
            "request_id, correlation_id, causation_id, parent_causation_id FROM skm_core.domain_events "
            "ORDER BY recorded_at, coalesce(workspace_seq, global_position)"
        ).fetchall()

    def counters(self) -> dict[object, int]:
        rows = self.observer.execute("SELECT workspace_id, last_seq FROM skm_core.workspace_event_counters")
        streams = self.observer.execute("SELECT stream_kind, stream_id, last_seq FROM skm_core.event_streams")
        return {**{row[0]: row[1] for row in rows}, **{(row[0], row[1]): row[2] for row in streams}}


def _world(dsn: str, *, pool_max_size: int = 4) -> Iterator[World]:
    with psycopg.connect(dsn, autocommit=True) as observer:
        instance, ws_a, ws_b = uuid4(), uuid4(), uuid4()
        insert = "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)"
        observer.execute(insert, (instance, "instance", None, None))
        observer.execute(insert, (ws_a, "workspace", instance, ws_a))
        observer.execute(insert, (ws_b, "workspace", instance, ws_b))
        settings = PgSettings(
            dsn=dsn,
            application_name="skm-test",
            pool_min_size=1,
            pool_max_size=pool_max_size,
            pool_timeout_seconds=5,
        )
        pool = create_pool(settings)
        clock = FrozenClock()
        writer = PostgresEventWriter(
            schemas=SchemaRegistry.load(SCHEMA_ROOT), subscriptions=SUBSCRIPTIONS, ids=_Ids()
        )
        try:
            yield World(
                observer=observer,
                pool=pool,
                writer=writer,
                uows=PostgresUowFactory(pool, FACTORIES, writer, clock),
                clock=clock,
                instance=instance,
                ws_a=WorkspaceId(ws_a),
                ws_b=WorkspaceId(ws_b),
            )
        finally:
            pool.close()


@pytest.fixture
def world(migrated: str) -> Iterator[World]:
    yield from _world(migrated)


@pytest.fixture
def single(migrated: str) -> Iterator[World]:
    """One pooled connection: every unit of work reuses the same server session."""
    yield from _world(migrated, pool_max_size=1)


def _echo(w: World, text: str = "hello", workspace: WorkspaceId | None = None) -> Echoed:
    return Echoed(workspace_id=workspace or w.ws_a, text=text)


def _commit(
    w: World,
    *events: DomainEvent,
    n: int = 1,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    with w.uows(w.meta(n, correlation_id=correlation_id, causation_id=causation_id)) as uow:
        for event in events:
            uow.record(event)
        uow.commit()


def _backend_pid(uow: PostgresUnitOfWork) -> int:
    row = uow.connection.execute("SELECT pg_backend_pid()").fetchone()
    assert row is not None
    return int(row[0])


def _assert_nothing_written(w: World) -> None:
    assert w.events() == []
    assert w.count("SELECT count(*) FROM skm_core.outbox") == 0
    assert w.counters() == {}


# --- no database needed -------------------------------------------------------------------------------------


def test_factory_and_unit_of_work_satisfy_the_kernel_protocols() -> None:
    assert isinstance(PostgresUowFactory, type)
    assert isinstance(PostgresUnitOfWork, type)
    factory: UnitOfWorkFactory = PostgresUowFactory(
        None,  # type: ignore[arg-type] - never entered here
        FACTORIES,
        PostgresEventWriter(schemas=SchemaRegistry.load(SCHEMA_ROOT), subscriptions={}, ids=_Ids()),
        FrozenClock(),
    )
    uow: UnitOfWork = factory(
        RequestMeta(request_id(), Surface.TEST, None, FrozenClock().now()), readonly=True
    )
    assert uow.readonly
    with pytest.raises(RuntimeError):  # not entered: no connection, no repositories
        uow.repo(ScopeRegistry)


def test_postgres_repository_table_merges_core_and_module_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    table = postgres_repository_table(("workspace", "access"))
    assert table[ScopeRegistry] is PostgresScopeRegistry
    assert ScopeTree in table
    assert REPOSITORIES[EventReader] is PostgresEventReader
    assert table[EventReader] is PostgresEventReader
    with pytest.raises(TypeError):
        table[ScopeRegistry] = PostgresScopeRegistry  # type: ignore[index] - the table is read-only
    module = importlib.import_module("skm.adapters.postgres.workspace")
    monkeypatch.setattr(module, "REPOSITORIES", {ScopeRegistry: PostgresScopeRegistry}, raising=False)
    with pytest.raises(ValueError, match="bound twice"):
        postgres_repository_table(("workspace",))


# --- lifecycle ----------------------------------------------------------------------------------------------


@pg
def test_commit_binds_state_events_and_outbox_in_one_transaction(world: World) -> None:
    w = world
    project = ScopeId(uuid4())
    with w.uows(w.meta()) as uow:
        uow.repo(ScopeRegistry).create(
            project, ScopeKind.PROJECT, parent=ScopeId(w.ws_a), workspace_id=w.ws_a
        )
        uow.record(_echo(w))
        uow.connection.execute("SELECT 1")
        assert w.count("SELECT count(*) FROM skm_core.scopes WHERE id = %s", (project,)) == 0
        uow.commit()
        assert w.count("SELECT count(*) FROM skm_core.scopes WHERE id = %s", (project,)) == 1
    [event] = w.events()
    assert event[1:7] == (w.ws_a, "workspace", w.ws_a, 1, 1, None)
    destinations = w.observer.execute(
        "SELECT destination, state, attempts FROM skm_core.outbox WHERE event_id = %s ORDER BY destination",
        (event[0],),
    ).fetchall()
    assert destinations == [("demo.on_echoed", "pending", 0), ("sse", "pending", 0)]
    assert w.counters() == {w.ws_a: 1, ("workspace", w.ws_a): 1}


@pg
def test_exit_without_commit_rolls_back_state_and_consumes_no_number(world: World) -> None:
    w = world
    project = ScopeId(uuid4())
    with w.uows(w.meta()) as uow:
        uow.repo(ScopeRegistry).create(
            project, ScopeKind.PROJECT, parent=ScopeId(w.ws_a), workspace_id=w.ws_a
        )
        uow.record(_echo(w, "dropped"))
    assert w.count("SELECT count(*) FROM skm_core.scopes WHERE id = %s", (project,)) == 0
    _assert_nothing_written(w)
    _commit(w, _echo(w, "kept"))
    assert [row[5] for row in w.events()] == [1]


@pg
def test_exception_in_the_body_rolls_back_and_propagates(world: World) -> None:
    w = world

    def body() -> None:
        with w.uows(w.meta()) as uow:
            uow.record(_echo(w))
            uow.repo(ScopeRegistry).create(
                ScopeId(uuid4()), ScopeKind.PROJECT, parent=ScopeId(w.ws_a), workspace_id=w.ws_a
            )
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        body()
    _assert_nothing_written(w)
    assert w.count("SELECT count(*) FROM skm_core.scopes WHERE kind = 'project'") == 0


@pg
def test_failed_commit_leaves_no_sequence_event_or_outbox_row(world: World) -> None:
    w = world
    with w.uows(w.meta()) as uow:
        uow.record(_echo(w))
        uow.record(Noted(stream=uuid4(), text="instance"))
        uow.outbox.enqueue(EventId(uuid4()), "hook:one")  # no such event: fails after numbers were allocated
        with pytest.raises(InternalError) as caught:
            uow.commit()
        assert dict(caught.value.details) == {"destination": "hook:one"}
        with pytest.raises(RuntimeError):  # the failed commit ended the unit of work
            uow.commit()
        with pytest.raises(RuntimeError):
            uow.repo(ScopeRegistry)
    _assert_nothing_written(w)
    _commit(w, _echo(w), Noted(stream=uuid4(), text="instance"))
    assert {(row[5], row[6]) for row in w.events()} == {(None, 1), (1, None)}  # numbers start at 1 again


@pg
def test_second_commit_reentry_and_commit_after_rollback_are_runtime_errors(world: World) -> None:
    w = world
    uow = w.uows(w.meta())
    with uow:
        uow.commit()
        with pytest.raises(RuntimeError):
            uow.commit()
    with pytest.raises(RuntimeError), uow:
        pass
    with w.uows(w.meta()) as other:
        other.record(_echo(w))
        other.rollback()
        other.rollback()  # idempotent
        with pytest.raises(RuntimeError):
            other.commit()
        with pytest.raises(RuntimeError):
            other.record(_echo(w))
    _assert_nothing_written(w)


@pg
def test_repositories_are_cached_per_unit_of_work_and_unknown_ports_fail(world: World) -> None:
    w = world
    with w.uows(w.meta()) as first:
        registry = first.repo(ScopeRegistry)
        assert first.repo(ScopeRegistry) is registry
        assert first.repo(EventReader) is not registry
        with pytest.raises(InternalError) as caught:
            first.repo(UnitOfWork)
        assert caught.value.code is ErrorCode.INTERNAL_ERROR
        assert dict(caught.value.details) == {"port": "UnitOfWork"}
    with w.uows(w.meta()) as second:
        assert second.repo(ScopeRegistry) is not registry


@pg
def test_isolation_and_readonly_reach_the_server_and_are_reset_on_release(single: World) -> None:
    w = single
    query = "SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')"
    with w.uows(w.meta(), readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
        assert uow.connection.execute(query).fetchone() == ("repeatable read", "on")
        assert uow.isolation is Isolation.REPEATABLE_READ
    with w.uows(w.meta(), isolation=Isolation.SERIALIZABLE) as uow:
        assert uow.connection.execute(query).fetchone() == ("serializable", "off")
    with w.pool.connection() as conn:  # a plain pool user gets the server defaults back
        assert conn.execute(query).fetchone() == ("read committed", "off")


# --- readonly -----------------------------------------------------------------------------------------------


@pg
def test_readonly_unit_of_work_refuses_record_enqueue_and_sql_writes(single: World) -> None:
    w = single
    with w.uows(w.meta(), readonly=True) as uow:
        assert uow.readonly
        with pytest.raises(RuntimeError, match="readonly"):
            uow.record(_echo(w))
        with pytest.raises(RuntimeError, match="readonly"):
            uow.outbox.enqueue(EventId(uuid4()), "hook:one")
        with pytest.raises(InternalError) as caught:  # the server refuses a write that bypasses record()
            uow.repo(ScopeRegistry).create(
                ScopeId(uuid4()), ScopeKind.PROJECT, parent=ScopeId(w.ws_a), workspace_id=w.ws_a
            )
        assert caught.value.details.get("sqlstate") == "25006"
    _assert_nothing_written(w)
    assert w.count("SELECT count(*) FROM skm_core.scopes WHERE kind = 'project'") == 0
    _commit(w, _echo(w))  # the same server session writes again: read_only was not left on it
    assert len(w.events()) == 1


@pg
def test_readonly_commit_reads_a_consistent_snapshot(world: World) -> None:
    w = world
    _commit(w, _echo(w, "one"))
    with w.uows(w.meta(), readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
        reader = uow.repo(EventReader)
        assert reader.head_workspace_seq(w.ws_a) == 1
        _commit(w, _echo(w, "two"), n=2)
        assert reader.head_workspace_seq(w.ws_a) == 1  # REPEATABLE READ snapshot
        uow.commit()
    with w.uows(w.meta(), readonly=True) as uow:
        assert uow.repo(EventReader).head_workspace_seq(w.ws_a) == 2


# --- errors keep their cause; a retry never continues the old transaction ----------------------------------


@pg
def test_commit_time_error_is_translated_with_its_cause_and_the_retry_is_fresh(single: World) -> None:
    w = single
    with w.uows(w.meta()) as uow:
        pid = _backend_pid(uow)
        uow.connection.execute(
            "CREATE TEMP TABLE uow_probe "
            "(x int, CONSTRAINT uq_uow_probe UNIQUE (x) DEFERRABLE INITIALLY DEFERRED) ON COMMIT DROP"
        )
        uow.connection.execute("INSERT INTO uow_probe VALUES (1), (1)")  # checked only at COMMIT
        uow.record(_echo(w))
        with pytest.raises(Conflict) as caught:
            uow.commit()
    error = caught.value
    assert error.code is ErrorCode.ALREADY_EXISTS
    assert dict(error.details) == {"constraint": "uq_uow_probe"}
    assert isinstance(error.__cause__, psycopg.errors.UniqueViolation)
    _assert_nothing_written(w)
    with w.uows(w.meta(2)) as retry:
        assert _backend_pid(retry) == pid  # the same server session ...
        assert retry.connection.execute("SELECT to_regclass('pg_temp.uow_probe')").fetchone() == (None,)
        retry.record(_echo(w))
        retry.commit()  # ... in a new transaction
    assert [(row[5], row[7]) for row in w.events()] == [(1, request_id(2))]


@pg
def test_statement_error_during_commit_is_translated_and_the_connection_is_reusable(single: World) -> None:
    w = single
    unknown = WorkspaceId(uuid4())  # no scope row: the feed counter's foreign key refuses it
    with w.uows(w.meta()) as uow:
        uow.record(_echo(w, workspace=unknown))
        with pytest.raises(ValidationFailed) as caught:
            uow.commit()
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    assert isinstance(caught.value.__cause__, psycopg.errors.ForeignKeyViolation)
    _assert_nothing_written(w)
    _commit(w, _echo(w), n=2)  # an aborted transaction would refuse every statement here
    assert len(w.events()) == 1


@pg
def test_rollback_failure_is_a_note_on_the_active_error_not_a_replacement(single: World) -> None:
    w = single

    def body() -> None:
        with w.uows(w.meta()) as uow:
            uow.record(_echo(w))
            uow.connection.close()  # the server session is gone: the rollback on exit fails too
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom") as caught:
        body()
    assert any("rollback" in note for note in caught.value.__notes__)
    uow = w.uows(w.meta(2))
    # without an active error the rollback failure itself is raised
    with pytest.raises(BackendUnavailable) as failed, uow:
        uow.connection.close()
    assert isinstance(failed.value.__cause__, psycopg.OperationalError)
    _commit(w, _echo(w), n=3)  # the pool replaced the broken connection
    assert len(w.events()) == 1


# --- events and outbox --------------------------------------------------------------------------------------


@pg
def test_invalid_event_is_an_internal_error_at_record(world: World) -> None:
    w = world
    with w.uows(w.meta()) as uow:
        with pytest.raises(InternalError) as caught:
            uow.record(_echo(w, text=""))  # minLength 1
        assert dict(caught.value.details) == {"event": "Echoed"}
        uow.commit()
    _assert_nothing_written(w)


@pg
def test_exactly_one_sse_row_per_workspace_event_and_none_per_instance_event(world: World) -> None:
    w = world
    project = uuid4()
    _commit(
        w,
        _echo(w, "a1"),
        ProjectEchoed(w.ws_a, project, "a2"),
        Noted(stream=uuid4(), text="instance 1"),
        _echo(w, "b1", w.ws_b),
        Noted(stream=uuid4(), text="instance 2"),
    )
    rows = w.observer.execute(
        "SELECT e.workspace_id IS NULL, e.event_type, "
        "count(*) FILTER (WHERE o.destination = 'sse'), count(*) FILTER (WHERE o.destination <> 'sse') "
        "FROM skm_core.domain_events e LEFT JOIN skm_core.outbox o ON o.event_id = e.id "
        "GROUP BY e.id ORDER BY 1, 2"
    ).fetchall()
    assert rows == [
        (False, ECHOED, 1, 1),
        (False, ECHOED, 1, 1),
        (False, ECHOED, 1, 1),
        (True, NOTED, 0, 0),
        (True, NOTED, 0, 0),
    ]
    numbers = Counter((row[1] is None, row[2], row[4], row[5], row[6]) for row in w.events())
    assert numbers == Counter(
        [
            (False, "workspace", 1, 1, None),
            (False, "project", 1, 2, None),
            (False, "workspace", 1, 1, None),  # ws_b has its own feed
            (True, "config", 1, None, 1),
            (True, "config", 1, None, 2),
        ]
    )


@pg
def test_explicit_outbox_rows_target_own_or_committed_events_once(world: World) -> None:
    w = world
    _commit(w, _echo(w, "earlier"))
    [(stored, *_)] = w.events()
    earlier = EventId(cast("UUID", stored))
    later = w.clock.now() + timedelta(hours=1)
    with w.uows(w.meta(2)) as uow:
        uow.record(_echo(w, "now"))
        uow.outbox.enqueue(earlier, "hook:audit", available_at=later)
        uow.outbox.enqueue(earlier, "hook:audit")  # duplicate (event_id, destination): no-op
        with pytest.raises(ValueError, match="external prefix"):
            uow.outbox.enqueue(earlier, "sse")
        uow.commit()
    rows = w.observer.execute(
        "SELECT destination, available_at FROM skm_core.outbox WHERE event_id = %s ORDER BY destination",
        (earlier,),
    ).fetchall()
    assert [row[0] for row in rows] == ["demo.on_echoed", "hook:audit", "sse"]
    assert rows[1][1] == later


# --- causality (kernel-platform §2.9) -----------------------------------------------------------------------


@pg
def test_command_events_keep_request_correlation_and_parent(world: World) -> None:
    w = world
    _commit(w, _echo(w, "root"), n=1)
    _commit(w, _echo(w, "child"), n=2, correlation_id="corr-root", causation_id=request_id(9))
    root, child = w.events()
    assert root[7:] == (
        request_id(1),
        request_id(1),
        request_id(1),
        None,
    )  # no correlation given: own request
    assert child[7:] == (request_id(2), "corr-root", request_id(2), request_id(9))


@pg
def test_subscriber_chain_keeps_its_parent_without_logs_or_audit(world: World) -> None:
    """``E -> consumer command C -> F``: the link lives in the rows, not in logs or audit records."""
    w = world
    _commit(w, _echo(w, "E"), n=1)
    with w.uows(w.meta(50), readonly=True) as uow:
        [e] = uow.repo(EventReader).after_workspace_seq(w.ws_a, 0, types=None, limit=10)
    # the subscriber builds the meta of its command C in code from the verified event (kernel §2.9)
    _commit(
        w, ProjectEchoed(w.ws_a, uuid4(), "F"), n=2, correlation_id=e.correlation_id, causation_id=str(e.id)
    )
    assert (
        w.count("SELECT count(*) FROM skm_core.audit_records") == 0
    )  # audit=False: nothing else holds the link
    with w.uows(w.meta(51), readonly=True) as uow:
        [_, f] = uow.repo(EventReader).after_workspace_seq(w.ws_a, 0, types=None, limit=10)
    assert (f.request_id, f.causation_id, f.parent_causation_id, f.correlation_id) == (
        request_id(2),
        request_id(2),
        str(e.id),
        request_id(1),
    )


@pg
def test_events_written_without_a_parent_read_with_an_unknown_parent(scratch: str) -> None:
    _migrate(scratch)
    old = uuid4()
    with psycopg.connect(scratch, autocommit=True) as conn:
        ws = uuid4()
        instance = uuid4()
        insert = "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)"
        conn.execute(insert, (instance, "instance", None, None))
        conn.execute(insert, (ws, "workspace", instance, ws))
        conn.execute(
            "INSERT INTO skm_core.domain_events "
            "(id, workspace_id, stream_kind, stream_id, stream_seq, workspace_seq, event_type, actor_id, "
            "request_id, correlation_id, causation_id, payload, occurred_at) "
            "VALUES (%s, %s, 'workspace', %s, 1, 1, %s, NULL, 'req-old', 'req-old', 'req-old', %s, now())",
            (old, ws, ws, ECHOED, to_jsonb({"workspace_id": str(ws), "text": "old"})),
        )
    with psycopg.connect(scratch, autocommit=True) as conn:
        assert conn.execute(
            "SELECT parent_causation_id FROM skm_core.domain_events WHERE id = %s", (old,)
        ).fetchone() == (None,)
        [envelope] = PostgresEventReader(conn).by_ids([EventId(old)])
    assert envelope.parent_causation_id is None
    assert envelope.to_json()["parent_causation_id"] is None


@pg
def test_client_supplied_ids_are_stored_verbatim_and_never_become_authority(world: World) -> None:
    w = world
    _commit(w, _echo(w, "foreign", w.ws_b), n=1)
    [foreign] = w.events()
    # A caller claims the event of another workspace as its cause and invents a correlation.
    _commit(w, _echo(w, "claimed"), n=2, correlation_id="forged-corr", causation_id=str(foreign[0]))
    _commit(w, _echo(w, "garbage"), n=3, causation_id="not-an-event")
    _, claimed, garbage = w.events()
    assert claimed[8:] == ("forged-corr", request_id(2), str(foreign[0]))  # stored as text, nothing inherited
    assert claimed[8] != foreign[8]
    assert garbage[10] == "not-an-event"  # never resolved against stored events
    assert (
        w.count("SELECT count(*) FROM skm_core.outbox WHERE event_id = %s", (foreign[0],)) == 2
    )  # its own rows
    assert w.count("SELECT count(*) FROM skm_core.consumer_receipts") == 0
    with w.uows(w.meta(60), readonly=True) as uow:
        seen = uow.repo(EventReader).after_workspace_seq(w.ws_a, 0, types=None, limit=10)
    assert foreign[0] not in {envelope.id for envelope in seen}  # the claim opens nothing of workspace B
    with w.uows(w.meta(4, causation_id="x" * 65)) as uow:  # oversized ids are a defect, nothing is written
        uow.record(_echo(w, "too long"))
        with pytest.raises(InternalError):
            uow.commit()
    assert len(w.events()) == 3
