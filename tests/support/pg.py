"""PostgreSQL test database of a session and the cleanup between tests (testing spec §5, adapters §1.11).

Destructive SQL runs only on a local server (a loopback address or a Unix socket) reached through a test
admin database whose name ends with ``_test``. The session creates exactly one database
``skm_t_<worker>_<pid>`` by cloning a template keyed by migration checksums. Template creation and cloning
share an advisory lock; migrations run only when that template is first created. The worker keeps its clone
in private state:
``clean_database`` and the final DROP act on it alone, after comparing the stored session DSN and
``current_database()``. A dev or live DSN, a remote host, another worker's database or a name that merely
shares the ``skm_t_`` prefix is refused before any CREATE, DROP or cleanup.

Tests whose units of work really COMMIT cannot be isolated by an outer rollback, so cleanup is one
server-side pass deleting populated ``skm_*`` tables except the migration history, its baseline and
``SEEDED_TABLES``, followed by sequence resets, seeded-row resets and ``seed_instance``, in one transaction.
Every test still starts with fresh committed state; sharing a migrated clone never shares test rows.

Re-export ``pg_session``, ``test_database`` and ``clean_test_database`` in a suite's conftest. Mark its
PostgreSQL cases with ``pytest.mark.pg`` and request ``clean_test_database: TestDatabase``; use its ``dsn``
for a connection or backend. ``pg_dsn`` captures only ``SKM_TEST_DATABASE_URL`` before environment scrubbing.

``SKM_KEEP_TEST_DB`` cannot be honoured here yet: the root ``conftest`` removes every ``SKM_*`` variable at
configure time and its ``RunnerControls`` does not carry the flag, so the session database is always dropped.
"""

import hashlib
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from types import MappingProxyType
from typing import ClassVar, Final, LiteralString, cast

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fakes.clock import FrozenClock
from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from support.seed import SEED

__all__ = [
    "MIGRATION_HISTORY",
    "SEEDED_TABLES",
    "PgSession",
    "TestDatabase",
    "UnsafeDatabaseError",
    "check_admin_dsn",
    "clean_database",
    "clean_test_database",
    "pg_session",
    "require_session_database",
    "seed_instance",
    "seeded_rows",
    "table_counts",
    "test_database",
    "worker_database_name",
]

# Rows the migrations insert (``examples/sql/README.md``, "Строки, засеянные миграциями"): table -> the
# statement that restores the migrated value, or None when tests never change the row and TRUNCATE skips it.
SEEDED_TABLES: Final[Mapping[str, LiteralString | None]] = MappingProxyType(
    {
        "skm_artifacts.storage_backends": None,  # 0010: ('local-primary', 'local', 'paths.blobs_root')
        "skm_config.generation": "UPDATE skm_config.generation SET value = 0 WHERE id = 1",  # 0005: (1, 0)
    }
)
MIGRATION_HISTORY: Final = "skm_core.schema_migrations"
_MIGRATION_METADATA: Final = frozenset({MIGRATION_HISTORY, "skm_core.schema_baseline"})

_WORKER = re.compile(r"[a-z0-9]{1,20}")
_SCHEMA = re.compile(r"skm_[a-z]+")
_SERVER: Final = "SELECT current_database()"
_TABLES: Final = (
    "SELECT table_schema || '.' || table_name FROM information_schema.tables "
    "WHERE table_type = 'BASE TABLE' AND table_schema LIKE 'skm\\_%' ORDER BY 1"
)
_SEED_SCOPE: Final = "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)"
# libpq reads these when the DSN leaves the parameter out; the checks below see what libpq would use.
_ENVIRONMENT: Final = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "dbname": "PGDATABASE",
    "service": "PGSERVICE",
}


class _Active:
    """The session of this process; ``clean_database`` acts only on its database.

    Every conftest or module that binds ``pg_session`` gets its own session-scoped fixture definition, so the
    fixtures share this one ``PgSession`` and the last one to finish drops the database.
    """

    session: "PgSession | None" = None
    users: int = 0


class UnsafeDatabaseError(RuntimeError):
    """A DSN, a server or a database that destructive test SQL must not touch."""


@dataclass(frozen=True, slots=True)
class TestDatabase:
    """The migrated database of this session: its DSN, the cleanup list and what the fresh database held.

    ``filled`` names every table (but the history) that had rows right after the migrations, so a test can
    prove ``SEEDED_TABLES`` is complete; ``seed_rows`` are those rows of the seeded tables.
    """

    __test__: ClassVar[bool] = False

    name: str
    dsn: str
    tables: tuple[str, ...]
    seed_rows: Mapping[str, tuple[str, ...]]
    filled: tuple[str, ...]


# ---------------------------------------------------------------------------------------------- guards


def _params(dsn: str) -> dict[str, str]:
    try:
        given = {key: str(value) for key, value in conninfo_to_dict(dsn).items() if value is not None}
    except psycopg.Error as exc:
        raise UnsafeDatabaseError("the test database DSN cannot be parsed") from exc
    for key, variable in _ENVIRONMENT.items():
        if not given.get(key) and os.environ.get(variable):
            given[key] = os.environ[variable]
    return given


def _local_host(host: str) -> bool:
    if host in {"", "localhost"} or host.startswith(("/", "@")):  # default or explicit Unix socket
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _require_local(params: Mapping[str, str]) -> None:
    if params.get("service"):
        raise UnsafeDatabaseError("a pg_service entry can name any server; give host and dbname instead")
    hosts = params.get("host", "").split(",")
    addresses = [item for item in params.get("hostaddr", "").split(",") if item]
    if not all(_local_host(host.strip()) for host in hosts) or not all(
        _local_host(address.strip()) and not address.startswith("/") for address in addresses
    ):
        raise UnsafeDatabaseError("test databases are created only on a loopback or Unix-socket server")


def check_admin_dsn(dsn: str) -> None:
    """Refuse anything but a local server's ``*_test`` admin database; no connection is opened."""
    params = _params(dsn)
    _require_local(params)
    if not params.get("dbname", "").endswith("_test"):
        raise UnsafeDatabaseError("the test admin database must be named '*_test' (SKM_TEST_DATABASE_URL)")


def worker_database_name(worker: str, pid: int) -> str:
    """``skm_t_<worker>_<pid>``; ``worker`` is ``PYTEST_XDIST_WORKER`` (``gw0`` …) or ``main``."""
    if not _WORKER.fullmatch(worker) or type(pid) is not int or pid <= 0:
        raise UnsafeDatabaseError("worker database names are skm_t_<[a-z0-9]+>_<pid>")
    return f"skm_t_{worker}_{pid}"


def _local_endpoint(host: str, hostaddr: str) -> bool:
    """Whether libpq reached the server through a Unix socket or a loopback address.

    ``host`` is the socket directory of a Unix-socket connection; otherwise ``hostaddr`` is the address the
    client really connected to (``localhost`` resolved). The server's own ``inet_server_addr()`` cannot
    decide this: behind a published container port (``127.0.0.1:54329:5432``) it is the bridge address.
    """
    if host.startswith(("/", "@")):
        return True
    try:
        return ip_address(hostaddr).is_loopback
    except ValueError:
        return False


def _server(conn: psycopg.Connection) -> str:
    """``current_database()`` after checking that the connection itself went to a local endpoint."""
    try:
        hostaddr = conn.info.hostaddr
    except psycopg.NotSupportedError:  # libpq < 12 cannot name the address it connected to
        hostaddr = ""
    if not _local_endpoint(conn.info.host, hostaddr):
        raise UnsafeDatabaseError("the server is not reached through loopback or a Unix socket")
    row = conn.execute(_SERVER).fetchone()
    if row is None:
        raise UnsafeDatabaseError("the server did not describe the connection")
    return cast("str", row[0])


def require_session_database(conn: psycopg.Connection, name: str) -> None:
    """The connection must be to ``name`` exactly, and ``name`` must be the database of this session."""
    session = _Active.session
    if session is None or session.database is None or session.database.name != name:
        raise UnsafeDatabaseError("only the database created by this pytest session may be cleaned")
    if _server(conn) != name:
        raise UnsafeDatabaseError("current_database() is not the database of this session")


# ---------------------------------------------------------------------------------------------- session


class PgSession:
    """Private state of one pytest session: its admin DSN and the single database it created."""

    __test__: ClassVar[bool] = False

    def __init__(self, *, worker: str, pid: int) -> None:
        self._name = worker_database_name(worker, pid)
        self._admin: str | None = None
        self._database: TestDatabase | None = None
        self._created = False
        self._failed: BaseException | None = None
        self._conn: psycopg.Connection | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def database(self) -> TestDatabase | None:
        return self._database

    def open(self, admin_dsn: str) -> TestDatabase:
        """Create and migrate the database on first use; later calls return the same one."""
        if self._database is not None:
            if admin_dsn != self._admin:
                raise UnsafeDatabaseError("the session database belongs to another admin DSN")
            return self._database
        if self._failed is not None:
            raise RuntimeError("the session test database could not be prepared") from self._failed
        check_admin_dsn(admin_dsn)
        try:
            self._database = self._create(admin_dsn)
        except BaseException as exc:
            self._failed = exc
            raise
        return self._database

    @staticmethod
    def _ensure_template(admin: psycopg.Connection, admin_dsn: str) -> str:
        """Create and migrate a reusable PG template database keyed by migration checksums."""
        migrations = discover_migrations()
        digest = hashlib.sha256(
            "|".join(f"{m.module}:{m.version}:{m.slug}:{m.kind}:{m.checksum}" for m in migrations).encode(
                "utf-8"
            )
        ).hexdigest()[:12]
        tpl_name = f"skm_t_tpl_{digest}"
        if admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (tpl_name,)).fetchone() is None:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(tpl_name)))
            try:
                tpl_dsn = make_conninfo(admin_dsn, dbname=tpl_name)
                MigrationRunner(tpl_dsn, migrations, package_loader(), FrozenClock(), "skm-test").migrate()
            except BaseException:
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(tpl_name)))
                raise
        return tpl_name

    def _create(self, admin_dsn: str) -> TestDatabase:
        with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5) as admin:
            if not _server(admin).endswith("_test"):
                raise UnsafeDatabaseError("the admin connection is not to a '*_test' database")
            admin.execute("SELECT pg_advisory_lock(hashtext('skm_test_template_lock'))")
            try:
                tpl_name = self._ensure_template(admin, admin_dsn)
                try:
                    admin.execute(
                        sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                            sql.Identifier(self._name),
                            sql.Identifier(tpl_name),
                        )
                    )
                except psycopg.errors.DuplicateDatabase as exc:
                    # never adopt (or later drop) a foreign database
                    raise UnsafeDatabaseError(
                        f"{self._name} already exists; drop the leftover database by hand"
                    ) from exc
            finally:
                admin.execute("SELECT pg_advisory_unlock(hashtext('skm_test_template_lock'))")
            self._admin = admin_dsn
            self._created = True
        dsn = make_conninfo(admin_dsn, dbname=self._name)
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            if _server(conn) != self._name:
                raise UnsafeDatabaseError("the migrated database is not the one this session created")
            found = tuple(cast("str", row[0]) for row in conn.execute(_TABLES).fetchall())
            missing = sorted(set(SEEDED_TABLES) - set(found))
            if missing:
                raise UnsafeDatabaseError(f"SEEDED_TABLES names tables the migrations lack: {missing}")
            tables = tuple(
                name for name in found if name not in _MIGRATION_METADATA and name not in SEEDED_TABLES
            )
            seed_rows = MappingProxyType({table: seeded_rows(conn, table) for table in SEEDED_TABLES})
            filled = tuple(
                name for name in found if name not in _MIGRATION_METADATA and _has_rows(conn, name)
            )
        return TestDatabase(name=self._name, dsn=dsn, tables=tables, seed_rows=seed_rows, filled=filled)

    def connection(self, dsn: str) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(dsn, connect_timeout=5)
        return self._conn

    def close(self) -> None:
        """Drop the database this session created, and nothing else."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None
        if not self._created or self._admin is None:
            return
        check_admin_dsn(self._admin)
        with psycopg.connect(self._admin, autocommit=True, connect_timeout=5) as admin:
            if not _server(admin).endswith("_test"):
                raise UnsafeDatabaseError("the admin connection is not to a '*_test' database")
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(self._name))
            )
        self._created = False
        self._database = None


def _has_rows(conn: psycopg.Connection, table: str) -> bool:
    query = sql.SQL("SELECT EXISTS (SELECT FROM {})").format(sql.Identifier(*table.split(".")))
    row = conn.execute(query).fetchone()
    return bool(row and row[0])


def seeded_rows(conn: psycopg.Connection, table: str) -> tuple[str, ...]:
    """Rows of a seeded table as canonical JSON text, in a stable order."""
    if table not in SEEDED_TABLES:
        raise ValueError(f"{table} is not a seeded table")
    query = sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
        sql.Identifier(*table.split("."))
    )
    return tuple(cast("str", row[0]) for row in conn.execute(query).fetchall())


def seed_instance(conn: psycopg.Connection) -> None:
    """The instance scope and the two workspace scopes of ``support.seed.SEED``, as the memory seed has them.

    No principals are seeded: the bus test apps authorize through ``fakes.authorizer.FakeAuthorizer``.
    """
    conn.execute(_SEED_SCOPE, (SEED.instance_id, "instance", None, None))
    for workspace_id in (SEED.workspace_id, SEED.other_workspace_id):
        conn.execute(_SEED_SCOPE, (workspace_id, "workspace", SEED.instance_id, workspace_id))


_SEQ_RESET = """
SELECT setval(
    format('%I.%I', schemaname, sequencename)::regclass,
    start_value,
    false
)
FROM pg_sequences
WHERE schemaname LIKE 'skm%' AND last_value IS NOT NULL
"""


_CLEAN_FN = """
CREATE OR REPLACE FUNCTION pg_temp.skm_clean_tables(tbls text[]) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    tbl text;
    has_rows boolean;
BEGIN
    PERFORM set_config('session_replication_role', 'replica', true);
    FOREACH tbl IN ARRAY tbls LOOP
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s LIMIT 1)', tbl) INTO has_rows;
        IF has_rows THEN
            EXECUTE format('DELETE FROM %s', tbl);
        END IF;
    END LOOP;
    PERFORM set_config('session_replication_role', 'origin', true);
END;
$$;
"""


def _delete_populated_tables(conn: psycopg.Connection, tables: Sequence[str]) -> None:
    quoted = [
        f"{sql.Identifier(s).as_string(conn)}.{sql.Identifier(t).as_string(conn)}"
        for s, t in (tbl.split(".") for tbl in tables)
    ]
    conn.execute(_CLEAN_FN)
    conn.execute("SELECT pg_temp.skm_clean_tables(%s)", (quoted,))
    conn.execute(_SEQ_RESET)


def clean_database(dsn: str, tables: Sequence[str]) -> None:
    """DELETE populated non-seeded tables, reset used sequences and seed the instance.

    Accepts only the DSN and table list of the database this session created; anything else is refused
    before a connection is opened. The statements run in one transaction: a failure leaves no half-clean
    state.
    """
    session = _Active.session
    database = None if session is None else session.database
    if session is None or database is None or dsn != database.dsn:
        raise UnsafeDatabaseError("clean_database accepts only the DSN of the session database")
    if tuple(tables) != database.tables:
        raise UnsafeDatabaseError("clean_database accepts only the table list of the session database")
    conn = session.connection(dsn)
    with conn.transaction():
        require_session_database(conn, database.name)
        if tables:
            _delete_populated_tables(conn, tables)
        for reset in SEEDED_TABLES.values():
            if reset is not None:
                conn.execute(reset)
        seed_instance(conn)


def table_counts(conn: psycopg.Connection, schema: str) -> Mapping[str, int]:
    """Committed row count of every table of ``schema`` (without the migration history)."""
    if not _SCHEMA.fullmatch(schema):
        raise ValueError(f"not an skm schema: {schema!r}")
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY 1",
        (schema,),
    ).fetchall()
    counts: dict[str, int] = {}
    for (name,) in rows:
        if f"{schema}.{name}" in _MIGRATION_METADATA:
            continue
        query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, cast("str", name)))
        row = conn.execute(query).fetchone()
        counts[cast("str", name)] = 0 if row is None else cast("int", row[0])
    return MappingProxyType(counts)


# ---------------------------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def pg_session() -> Iterator[PgSession]:
    """One database per session and worker, created lazily by the first pg test that asks for it."""
    if _Active.session is None:
        _Active.session = PgSession(worker=os.environ.get("PYTEST_XDIST_WORKER", "main"), pid=os.getpid())
    session = _Active.session
    _Active.users += 1
    try:
        yield session
    finally:
        _Active.users -= 1
        if _Active.users == 0:
            _Active.session = None
            session.close()


@pytest.fixture
def test_database(pg_session: PgSession, pg_dsn: str) -> TestDatabase:
    """The migrated session database; ``pg_dsn`` keeps the pg-marker gate and never falls back to dev."""
    return pg_session.open(pg_dsn)


@pytest.fixture
def clean_test_database(test_database: TestDatabase) -> TestDatabase:
    """The session database, cleaned before the test (committed rows of earlier tests are gone)."""
    clean_database(test_database.dsn, test_database.tables)
    return test_database
