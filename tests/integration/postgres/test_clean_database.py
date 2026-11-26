"""Session test database and cleanup of ``tests/support/pg.py`` (testing spec §5, adapters §1.11).

After cleanup the database is the freshly migrated one plus the instance seed: every truncatable table is
empty, ``skm_config.generation`` is ``(1, 0)`` and ``skm_artifacts.storage_backends`` holds the rows of the
fresh database. Rows a test COMMITs never reach the next test. Destructive SQL accepts only a local
``*_test`` admin database and the exact database this session created; a dev/live DSN, a remote host or a
name that only shares the ``skm_t_`` prefix is refused before any connection or mutation.
"""

import os

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from fakes.demo_module import Echo
from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.kernel.ids import WorkspaceId
from support import backend as backend_support
from support import pg as pg_support
from support.backend import PostgresTestBackend
from support.pg import (
    MIGRATION_HISTORY,
    SEEDED_TABLES,
    PgSession,
    TestDatabase,
    UnsafeDatabaseError,
    check_admin_dsn,
    clean_database,
    require_session_database,
    seeded_rows,
    worker_database_name,
)
from support.seed import SEED

# Fixtures by name: pytest finds them through the names this module holds.
pg_backend = backend_support.pg_backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

pg = pytest.mark.pg

DEV_DSN = "postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev"  # the Makefile's SKM_DATABASE_URL
CLOSED = "postgresql://skm@127.0.0.1:1/{name}"  # nothing listens: a connection attempt would fail loudly
SCOPE_ROWS = "SELECT count(*) FROM skm_core.scopes WHERE id = %s"
HISTORY_ROWS = "SELECT count(*) FROM skm_core.schema_migrations"


@pytest.fixture(autouse=True)
def _no_libpq_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guards also read libpq's environment fallbacks; the host's own values must not leak in."""
    for name in ("PGHOST", "PGHOSTADDR", "PGDATABASE", "PGSERVICE"):
        monkeypatch.delenv(name, raising=False)


def scalar(dsn: str, statement: str, params: tuple[object, ...] = ()) -> object:
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        row = conn.execute(statement, params).fetchone()  # type: ignore[arg-type]
    assert row is not None
    return row[0]


# ---------------------------------------------------------------------------------------- guards, no server


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://skm@127.0.0.1:54329/skm_test",
        "postgresql://skm@[::1]:5432/skm_test",
        "postgresql://skm@localhost/skm_test",
        "postgresql:///skm_test",
        "host=/var/run/postgresql dbname=skm_test",
        "host=127.0.0.1,localhost dbname=other_test",
        "host=localhost hostaddr=127.0.0.1 dbname=skm_test",
    ],
)
def test_a_local_test_admin_database_is_accepted(dsn: str) -> None:
    check_admin_dsn(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        DEV_DSN,
        "postgresql://skm@127.0.0.1/skm_live",
        "postgresql://skm@127.0.0.1/skm_test_copy",  # the suffix, not a substring
        "postgresql://skm@127.0.0.1/skm_t_main_123",  # a worker database is not an admin database
        "postgresql://skm@127.0.0.1/",
        "postgresql://skm@db.example.com/skm_test",
        "postgresql://skm@10.0.0.5/skm_test",
        "host=127.0.0.1,db.example.com dbname=skm_test",
        "host=localhost hostaddr=10.1.2.3 dbname=skm_test",
        "service=prod dbname=skm_test",
        "not a dsn ===",
    ],
)
def test_a_dev_live_remote_or_unverifiable_dsn_is_refused(dsn: str) -> None:
    with pytest.raises(UnsafeDatabaseError):
        check_admin_dsn(dsn)


@pytest.mark.parametrize(
    ("variable", "value"), [("PGHOST", "db.example.com"), ("PGHOSTADDR", "10.0.0.5"), ("PGSERVICE", "prod")]
)
def test_libpq_environment_cannot_redirect_a_dsn_without_a_host(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(UnsafeDatabaseError):
        check_admin_dsn("dbname=skm_test")


def test_worker_databases_are_named_by_worker_and_pid() -> None:
    assert worker_database_name("main", 123) == "skm_t_main_123"
    assert worker_database_name("gw0", 7) == "skm_t_gw0_7"
    for worker, pid in (
        ("gw-0", 1),
        ("", 1),
        ("MAIN", 1),
        ("a;drop", 1),
        ("main", 0),
        ("main", -1),
        ("main", True),
    ):
        with pytest.raises(UnsafeDatabaseError):
            worker_database_name(worker, pid)


@pytest.mark.parametrize("dsn", [CLOSED.format(name="skm_dev"), "postgresql://skm@db.example.com/skm_test"])
def test_a_session_refuses_before_it_connects(dsn: str) -> None:
    session = PgSession(worker="probe", pid=os.getpid())
    with pytest.raises(UnsafeDatabaseError):
        session.open(dsn)  # UnsafeDatabaseError, not a connection error: nothing was attempted
    session.close()  # created nothing, drops nothing


def test_cleanup_without_a_session_database_refuses_before_it_connects() -> None:
    with pytest.raises(UnsafeDatabaseError):
        clean_database(CLOSED.format(name="skm_t_main_1"), ())


# ------------------------------------------------------------------------------------ the session database


def assert_fresh(database: TestDatabase) -> None:
    """Truncatable tables empty but the instance seed; seeded tables exactly as after the migrations."""
    with psycopg.connect(database.dsn, autocommit=True, connect_timeout=5) as conn:
        for table in database.tables:
            query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(*table.split(".")))
            row = conn.execute(query).fetchone()
            assert row is not None
            assert row[0] == (3 if table == "skm_core.scopes" else 0), table  # the instance seed only
        assert conn.execute("SELECT id, value FROM skm_config.generation").fetchall() == [(1, 0)]
        for table in SEEDED_TABLES:
            assert seeded_rows(conn, table) == database.seed_rows[table], table
        backends = conn.execute("SELECT id, kind, config_ref FROM skm_artifacts.storage_backends").fetchall()
        assert backends == [("local-primary", "local", "paths.blobs_root")]
        sequences = conn.execute(
            "SELECT schemaname || '.' || sequencename, last_value FROM pg_sequences "
            "WHERE schemaname LIKE 'skm\\_%'"
        ).fetchall()
        assert all(last is None for _, last in sequences), sequences  # RESTART IDENTITY


def write_config_and_events(backend: PostgresTestBackend, text: str) -> None:
    """Commit what a later test must not see: a config entry, its history, a generation bump and events."""
    now = backend.clock.now()
    entry = backend.ids.new_id()
    backend.execute(
        "INSERT INTO skm_config.entries (id, scope_id, key, op, value, created_by, created_at, updated_by, "
        "updated_at) VALUES (%s, %s, 'storage.retry.max_attempts', 'set', '5', %s, %s, %s, %s)",
        (entry, SEED.instance_id, SEED.principal_id, now, SEED.principal_id, now),
    )
    backend.execute(
        "INSERT INTO skm_config.entry_history (id, entry_id, scope_id, key, change_kind, new_op, new_value, "
        "actor_id, generation, changed_at) "
        "VALUES (%s, %s, %s, 'storage.retry.max_attempts', 'created', 'set', '5', %s, 1, %s)",
        (backend.ids.new_id(), entry, SEED.instance_id, SEED.principal_id, now),
    )
    backend.execute("UPDATE skm_config.generation SET value = value + 1 WHERE id = 1")
    backend.app().dispatch(Echo(workspace_id=SEED.workspace_id, text=text), idempotency_key=f"key-{text}")


@pg
def test_the_session_database_is_this_workers_migrated_database(test_database: TestDatabase) -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    assert test_database.name == f"skm_t_{worker}_{os.getpid()}"
    assert scalar(test_database.dsn, "SELECT current_database()") == test_database.name
    assert scalar(test_database.dsn, HISTORY_ROWS) == len(discover_migrations())
    assert MIGRATION_HISTORY not in test_database.tables
    assert not set(SEEDED_TABLES) & set(test_database.tables)
    assert "skm_core.domain_events" in test_database.tables


@pg
def test_seeded_tables_are_exactly_the_tables_a_fresh_database_fills(test_database: TestDatabase) -> None:
    """A migration that seeds another table fails here until SEEDED_TABLES (and the SQL README) name it."""
    assert set(test_database.filled) == set(SEEDED_TABLES)
    assert test_database.seed_rows["skm_config.generation"] == ('{"id":1,"value":0}',)


@pg
@pytest.mark.parametrize("round_", [1, 2])
def test_every_pg_test_starts_fresh_and_its_committed_config_does_not_leak(
    pg_backend: PostgresTestBackend, round_: int
) -> None:
    """Both rounds commit config and events; whichever runs second sees none of the first one's rows."""
    assert_fresh(pg_backend.database)
    write_config_and_events(pg_backend, f"round-{round_}")
    assert pg_backend.execute("SELECT id, value FROM skm_config.generation") == [(1, 1)]
    counts = pg_backend.table_counts("skm_core")
    assert (counts["domain_events"], counts["idempotency_receipts"], counts["audit_records"]) == (1, 1, 1)
    assert pg_backend.table_counts("skm_config")["entries"] == 1


@pg
def test_cleanup_restores_the_fresh_database_after_commits(pg_backend: PostgresTestBackend) -> None:
    database = pg_backend.database
    write_config_and_events(pg_backend, "dirty")
    workspace = WorkspaceId(pg_backend.ids.new_id())
    pg_backend.ensure_workspace(workspace)  # a skm_workspace row too: TRUNCATE CASCADE reaches every module
    assert pg_backend.table_counts("skm_workspace")["workspaces"] == 1
    clean_database(database.dsn, database.tables)
    assert_fresh(database)
    assert scalar(database.dsn, HISTORY_ROWS) == len(discover_migrations())  # the history is kept
    clean_database(database.dsn, database.tables)  # cleaning a clean database is a no-op
    assert_fresh(database)


@pg
def test_the_backend_works_on_the_session_database_not_the_admin_one(
    pg_backend: PostgresTestBackend, pg_dsn: str
) -> None:
    assert pg_backend.execute("SELECT current_database()") == [(pg_backend.database.name,)]
    assert pg_backend.database.dsn != pg_dsn
    with pg_backend.uow(readonly=True) as uow:
        connection = uow.connection  # type: ignore[attr-defined] - the PostgreSQL unit of work
        row = connection.execute("SELECT current_database(), current_setting('application_name')").fetchone()
    assert row == (pg_backend.database.name, "skm-test")


@pg
def test_cleanup_refuses_every_dsn_but_the_session_database(test_database: TestDatabase, pg_dsn: str) -> None:
    marker = SEED.instance_id
    clean_database(test_database.dsn, test_database.tables)
    refused = [
        pg_dsn,  # the admin database
        DEV_DSN,
        make_conninfo(test_database.dsn, application_name="other"),  # same target, not the stored DSN
        make_conninfo(test_database.dsn, dbname=test_database.name + "0"),  # the prefix alone
        make_conninfo(test_database.dsn, dbname=f"skm_t_gw9_{os.getpid()}"),  # another worker
    ]
    for dsn in refused:
        with pytest.raises(UnsafeDatabaseError):
            clean_database(dsn, test_database.tables)
    for tables in (
        test_database.tables[:-1],
        (*test_database.tables, MIGRATION_HISTORY),
        (*test_database.tables, *SEEDED_TABLES),
    ):
        with pytest.raises(UnsafeDatabaseError):
            clean_database(test_database.dsn, tables)
    assert scalar(test_database.dsn, SCOPE_ROWS, (marker,)) == 1  # nothing was truncated


@pg
def test_cleanup_checks_current_database_on_its_connection(test_database: TestDatabase, pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn, connect_timeout=5) as admin, pytest.raises(UnsafeDatabaseError):
        require_session_database(admin, test_database.name)
    with psycopg.connect(test_database.dsn, connect_timeout=5) as conn:
        with pytest.raises(UnsafeDatabaseError):
            require_session_database(conn, "skm_t_main_1")
        require_session_database(conn, test_database.name)


@pg
def test_a_second_session_never_adopts_or_drops_an_existing_database(
    test_database: TestDatabase, pg_dsn: str
) -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    intruder = PgSession(worker=worker, pid=os.getpid())  # same name as the live session database
    with pytest.raises(UnsafeDatabaseError, match="already exists"):
        intruder.open(pg_dsn)
    intruder.close()
    assert scalar(test_database.dsn, "SELECT current_database()") == test_database.name
