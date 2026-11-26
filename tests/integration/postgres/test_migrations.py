"""Transactional migration runner, schema version gate and the runner bootstrap file (adapters §1.10).

Fixture migration chains are written into ``tmp_path``; no product migration is needed. Each PostgreSQL
test runs in its own scratch database created from ``SKM_TEST_DATABASE_URL``.
"""

import hashlib
import os
import signal
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from typing import cast, override
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import skm
from skm.adapters.postgres.core.schema_version import SchemaCompatibility, SchemaVersionReader
from skm.adapters.postgres.migrations.runner import (
    MigrationFile,
    MigrationRunner,
    MigrationSession,
    MigrationState,
    check_migration_sql,
    directory_loader,
    discover_migrations,
    known_version,
)
from skm.kernel.errors import (
    BackendUnavailable,
    InternalError,
    PreconditionFailed,
    SkmError,
    ValidationFailed,
)
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.outcomes import Severity
from skm.platform.system_clock import SystemClock

# sha256 of examples/sql/runner_bootstrap.sql: the packaged copy must stay byte-for-byte identical.
_BOOTSTRAP_SHA256 = "c96d007c8eff73bd3eefef92f5757f5d8cb589e71448d8fff380d55138fd200b"

BASE = (
    "CREATE TABLE skm_core.fx_base (id int PRIMARY KEY, note text);\n"
    "INSERT INTO skm_core.fx_base VALUES (1, 'COMMIT; -- inside a string');\n"
    "-- COMMIT is fine inside a comment\n"
)
CONFIG = "CREATE SCHEMA skm_config;\nCREATE TABLE skm_config.fx_cfg (k text PRIMARY KEY);\n"
SEED = "INSERT INTO skm_config.fx_cfg VALUES ('seed');\n"
CHAIN = {
    "0001_core_base.sql": BASE,
    "0002_settings_cfg.sql": CONFIG,
    "0003_planning_seed.data.sql": SEED,
}


class _Clock:
    def now(self) -> datetime:
        return SystemClock().now()


def _write(root: Path, sources: Mapping[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in sources.items():
        (root / name).write_bytes(text.encode("utf-8"))
    return root


def _runner(
    dsn: str, root: Path, *, runner_class: type[MigrationRunner] = MigrationRunner
) -> MigrationRunner:
    return runner_class(
        dsn,
        discover_migrations(root),
        directory_loader(root),
        _Clock(),
        "skm-test",
        use_packaged_baseline=False,
    )


# --- no database needed --------------------------------------------------------------------------------


def test_bootstrap_file_is_packaged_byte_for_byte() -> None:
    text = (
        resources.files("skm.adapters.postgres.migrations")
        .joinpath("sql", "runner_bootstrap.sql")
        .read_bytes()
    )
    assert hashlib.sha256(text).hexdigest() == _BOOTSTRAP_SHA256
    assert all(item.filename != "runner_bootstrap.sql" for item in discover_migrations())


def test_discovery_numbers_kinds_and_checksums(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        {
            "0001_core_base.sql": "SELECT 1;\r\nSELECT 2;\r\n",
            "0002_planning_seed.data.sql": "SELECT 3;",
            "0003_exports_code.py": "def apply(session):\n    pass\n",
            "runner_bootstrap.sql": "ignored",
            "README.md": "ignored",
        },
    )
    files = discover_migrations(root)
    assert [(item.version, item.module, item.slug, item.kind) for item in files] == [
        (1, "core", "base", "sql"),
        (2, "planning", "seed", "data_sql"),
        (3, "exports", "code", "py"),
    ]
    assert all(item.transactional is True for item in files)
    assert (
        files[0].checksum == "sha256:" + hashlib.sha256(b"SELECT 1;\nSELECT 2;\n").hexdigest()
    )  # CRLF folded
    assert [item.filename for item in files] == [
        "0001_core_base.sql",
        "0002_planning_seed.data.sql",
        "0003_exports_code.py",
    ]
    assert known_version(files) == 3
    assert known_version(()) == 0


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["0001_core_a.sql", "0003_core_b.sql"], "gap_in_numbering"),
        (["0002_core_a.sql"], "gap_in_numbering"),
        (["0001_core_a.sql", "0001_core_b.sql"], "duplicate_version"),
        (["0001_nomodule_a.sql"], "unknown_module"),
        (["0001_core_a.data.py"], "bad_file_name"),
        (["0001_Core_a.sql"], "bad_file_name"),
        (["001_core_a.sql"], "bad_file_name"),
    ],
)
def test_broken_chains_are_build_errors(tmp_path: Path, names: list[str], reason: str) -> None:
    root = _write(tmp_path, dict.fromkeys(names, "SELECT 1;"))
    with pytest.raises(InternalError) as caught:
        discover_migrations(root)
    assert caught.value.details["reason"] == reason
    assert "file" in caught.value.details


GOOD_SQL = [
    "CREATE TABLE a (id int);\n-- COMMIT;\nINSERT INTO a VALUES (1); /* ROLLBACK; */",
    "INSERT INTO t VALUES ('COMMIT;'), ('it''s; COMMIT');",
    "DO $$ BEGIN PERFORM 1; END $$;",
    "DO $tag$ BEGIN PERFORM 'a'; END $tag$;",
    "SELECT E'a\\'; COMMIT;';",
    'CREATE TABLE "commit" ("end" int);',
    "CREATE TABLE commit_log (end_at int, begin_at int);",
    "CREATE FUNCTION f() RETURNS int LANGUAGE sql BEGIN ATOMIC SELECT 1; SELECT 2; END; SELECT 3;",
    "/* nested /* COMMIT; */ still a comment */ SELECT 1;",
    "COMMENT ON TABLE t IS 'COMMIT; and -- skm:no-transaction';",
    "SELECT $1, $2;",
    "CREATE FUNCTION f() RETURNS void LANGUAGE sql BEGIN ATOMIC END; SELECT 1;",
    "SELECT 1 AS a$b$, 2 AS begin_atomic; SELECT 2;",
    "SELECT 1 AS x$$$ ; SELECT 2;",
    "-- one\r-- two\r\nSELECT 1;",
    "DO $a$ x $a$$b$ y $b$;",
]
BAD_SQL = [
    "COMMIT;",
    "SELECT 1; commit",
    "BEGIN; SELECT 1;",
    "begin work;",
    "END;",
    "ROLLBACK TO SAVEPOINT x;",
    "ABORT;",
    "START TRANSACTION;",
    "PREPARE TRANSACTION 'x';",
    "COMMIT PREPARED 'x';",
    "-- skm:no-transaction\nCREATE INDEX CONCURRENTLY i ON t (a);",
    "/* Skm:No-Transaction */ SELECT 1;",
    "SELECT 1;\n\\set AUTOCOMMIT off\n",
    "CREATE FUNCTION f() RETURNS int LANGUAGE sql BEGIN ATOMIC SELECT 1; END; COMMIT;",
    # a line comment ends at a bare CR, so the COMMIT after it is code
    "SELECT 1; -- note\rCOMMIT;",
    "-- note\rCOMMIT;",
    "SELECT 1;\r-- note\r\rROLLBACK;",
    # "begin atomic" words that are not the body of a CREATE FUNCTION / PROCEDURE
    "SELECT 1 AS begin, atomic; COMMIT; END;",
    "SELECT begin atomic FROM t; COMMIT; END;",
    "CREATE TABLE t (begin atomic int); COMMIT; END;",
    "CREATE FUNCTION f(begin atomic int) RETURNS int LANGUAGE sql RETURN 1; COMMIT; END;",
    "CREATE FUNCTION f() RETURNS void LANGUAGE sql BEGIN ATOMIC END; COMMIT;",
    "CREATE PROCEDURE p() LANGUAGE sql BEGIN ATOMIC SELECT 1; COMMIT; END;",
    "CREATE FUNCTION f() RETURNS int LANGUAGE sql BEGIN ATOMIC SELECT 1; END COMMIT; COMMIT;",
    # a "$" inside an identifier does not open a dollar quote that would hide the COMMIT
    "SELECT 1 AS x$$$; COMMIT; SELECT $$a$$;",
    "SELECT 1 AS a$$tag$; COMMIT; SELECT $tag$x$tag$;",
    "SELECT a$$b$$ FROM t; COMMIT; SELECT 'x';",
    "SELECT é$$$ FROM t; COMMIT; SELECT $$x$$;",
]


@pytest.mark.parametrize("text", GOOD_SQL)
def test_commit_words_in_literals_and_comments_are_allowed(text: str) -> None:
    check_migration_sql(text, file="0001_core_a.sql")


@pytest.mark.parametrize("text", BAD_SQL)
def test_transaction_control_and_marker_are_rejected(text: str) -> None:
    with pytest.raises(InternalError) as caught:
        check_migration_sql(text, file="0001_core_a.sql")
    assert dict(caught.value.details) == {"reason": "non_transactional_migration", "file": "0001_core_a.sql"}


def test_python_marker_is_rejected_at_discovery(tmp_path: Path) -> None:
    root = _write(tmp_path, {"0001_core_a.py": "# skm:no-transaction\ndef apply(session):\n    pass\n"})
    with pytest.raises(InternalError) as caught:
        discover_migrations(root)
    assert caught.value.details["reason"] == "non_transactional_migration"


def _unreachable_dsn() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"postgresql://migrator:hunter2-secret@127.0.0.1:{port}/nodb?connect_timeout=2"


def test_non_transactional_files_are_rejected_before_any_connection(tmp_path: Path) -> None:
    dsn = _unreachable_dsn()
    root = _write(
        tmp_path,
        {"0001_core_a.sql": "SELECT 1;", "0002_core_b.sql": "CREATE INDEX CONCURRENTLY i ON t (a);\nCOMMIT;"},
    )
    with pytest.raises(InternalError) as caught:  # not BackendUnavailable: the database is never contacted
        _runner(dsn, root).migrate()
    assert caught.value.details["reason"] == "non_transactional_migration"
    assert caught.value.details["file"] == "0002_core_b.sql"
    with pytest.raises(InternalError):
        _runner(dsn, root).verify()
    with pytest.raises(InternalError):
        _runner(dsn, root).migrate(dry_run=True)


def test_transactional_false_is_rejected_by_the_runner(tmp_path: Path) -> None:
    root = _write(tmp_path, {"0001_core_a.sql": "SELECT 1;"})
    (item,) = discover_migrations(root)
    forbidden = replace(item, transactional=False)
    with pytest.raises(InternalError) as caught:
        MigrationRunner(_unreachable_dsn(), [forbidden], directory_loader(root), _Clock(), "x")
    assert caught.value.details["reason"] == "non_transactional_migration"


def test_file_changed_after_discovery_is_refused(tmp_path: Path) -> None:
    root = _write(tmp_path, {"0001_core_a.sql": "SELECT 1;"})
    runner = _runner(_unreachable_dsn(), root)
    (root / "0001_core_a.sql").write_text("SELECT 2;")
    with pytest.raises(PreconditionFailed) as caught:
        runner.migrate()
    assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
    assert caught.value.details["reason"] == "source_changed"


def test_python_edit_between_discovery_and_load_never_runs(tmp_path: Path) -> None:
    sentinel = tmp_path / "ran"
    root = _write(tmp_path / "chain", {"0001_core_a.py": "def apply(session):\n    pass\n"})
    runner = _runner(_unreachable_dsn(), root)  # discovery recorded the checksum of the original bytes
    edited = (
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('edited')\n"
        "def apply(session):\n    pass\n"
    )
    (root / "0001_core_a.py").write_text(edited)
    with pytest.raises(PreconditionFailed) as caught:  # not BackendUnavailable: refused before any connection
        runner.migrate()
    assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
    assert caught.value.details["reason"] == "source_changed"
    assert caught.value.details["file"] == "0001_core_a.py"
    assert not sentinel.exists()
    for call in (runner.verify, lambda: runner.migrate(dry_run=True)):
        with pytest.raises(PreconditionFailed):
            call()
    assert not sentinel.exists()


class _Entry:
    """A file whose content changes after the first read: a loader that reads twice would run different
    bytes."""

    def __init__(self, first: bytes, later: bytes) -> None:
        self.reads = 0
        self._contents = (first, later)
        self.name = "0001_core_a.py"

    def joinpath(self, *_names: str) -> "_Entry":
        return self

    def read_bytes(self) -> bytes:
        self.reads += 1
        return self._contents[min(self.reads - 1, 1)]

    @override
    def __str__(self) -> str:
        return self.name


def test_python_loader_executes_the_bytes_it_checksummed() -> None:
    original = b"MARK = 'original'\ndef apply(session):\n    session.mark = MARK\n"
    later = b"MARK = 'edited'\ndef apply(session):\n    session.mark = MARK\n"
    item = MigrationFile(1, "core", "a", "py", "sha256:" + hashlib.sha256(original).hexdigest(), True)
    entry = _Entry(original, later)
    apply = directory_loader(entry)(item)  # pyright: ignore[reportArgumentType]
    assert entry.reads == 1
    marked = SimpleNamespace()
    apply(marked)  # pyright: ignore[reportArgumentType, reportCallIssue]
    assert marked.mark == "original"
    with pytest.raises(
        PreconditionFailed
    ) as caught:  # the second read is the edited file, not the checksummed one
        directory_loader(entry)(item)  # pyright: ignore[reportArgumentType]
    assert caught.value.details["reason"] == "source_changed"


def test_connection_failure_does_not_leak_the_dsn(tmp_path: Path) -> None:
    dsn = _unreachable_dsn()
    root = _write(tmp_path, {"0001_core_a.sql": "SELECT 1;"})
    runner = _runner(dsn, root)
    assert "hunter2-secret" not in repr(runner)
    for call in (runner.migrate, runner.status, runner.verify):
        with pytest.raises(BackendUnavailable) as caught:
            call()
        assert dict(caught.value.details) == {"phase": "connect"}
        assert "hunter2-secret" not in str(caught.value) + repr(caught.value.to_problem())


def test_session_exposes_only_checked_value_operations() -> None:
    public = {name for name in dir(MigrationSession) if not name.startswith("_")}
    assert public == {"execute", "executemany", "fetchall"}


# --- live PostgreSQL -----------------------------------------------------------------------------------


def _checked_admin(dsn: str) -> dict[str, str]:
    """Destructive SQL (CREATE/DROP DATABASE) only against a loopback or socket test server (testing spec
    1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail(
            "migration tests create databases only on a local server through an '*_test' database",
            pytrace=False,
        )
    return info


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_mig_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(pg_dsn, dbname=name)
            with psycopg.connect(dsn, autocommit=True) as probe:
                row = probe.execute("SELECT current_database()").fetchone()
            assert row == (name,)
            yield dsn
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _query(dsn: str, statement: str, params: tuple[object, ...] | None = None) -> list[tuple[object, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        cursor = conn.execute(statement, params)  # pyright: ignore[reportArgumentType]
        return cursor.fetchall() if cursor.description is not None else []


def _versions(dsn: str) -> list[int]:
    return [
        int(cast("int", row[0]))
        for row in _query(dsn, "SELECT version FROM skm_core.schema_migrations ORDER BY version")
    ]


def _exists(dsn: str, name: str) -> bool:
    return bool(_query(dsn, "SELECT to_regclass(%s) IS NOT NULL", (name,))[0][0])


@pytest.mark.pg
def test_fresh_database_applies_the_chain_and_repeat_is_a_noop(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    runner = _runner(scratch, root)
    assert runner.migrate() == (1, 2, 3)
    assert _versions(scratch) == [1, 2, 3]
    rows = _query(
        scratch, "SELECT version, name, checksum, applied_by FROM skm_core.schema_migrations ORDER BY 1"
    )
    assert rows == [(item.version, item.filename, item.checksum, "skm-test") for item in runner.files]
    assert _query(scratch, "SELECT k FROM skm_config.fx_cfg") == [("seed",)]
    assert _query(scratch, "SELECT note FROM skm_core.fx_base") == [("COMMIT; -- inside a string",)]
    assert runner.migrate() == ()
    assert _runner(scratch, root).migrate() == ()  # a new process reads the history again
    assert [state for _, _, state in runner.status()] == [MigrationState.APPLIED] * 3
    assert runner.verify() == ()


class _StepClock:
    """Every reading is 250 ms after the previous one."""

    def __init__(self) -> None:
        self.ticks = 0

    def now(self) -> datetime:
        self.ticks += 1
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(milliseconds=250 * self.ticks)


@pytest.mark.pg
def test_duration_ms_is_recorded_in_the_history_row(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    runner = MigrationRunner(
        scratch,
        discover_migrations(root),
        directory_loader(root),
        _StepClock(),
        "skm-test",
        use_packaged_baseline=False,
    )
    assert runner.migrate() == (1, 2, 3)
    assert _query(scratch, "SELECT version, duration_ms FROM skm_core.schema_migrations ORDER BY 1") == [
        (1, 250),
        (2, 250),
        (3, 250),
    ]
    column = _query(
        scratch,
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'skm_core' AND table_name = 'schema_migrations' "
        "AND column_name = 'duration_ms'",
    )
    assert column == [("integer", "NO")]


@pytest.mark.pg
def test_duration_ms_is_written_inside_the_migration_transaction(scratch: str, tmp_path: Path) -> None:
    seen: list[int] = []

    class Failing(MigrationRunner):
        @override
        def _record_applied(self, conn: psycopg.Connection, item: MigrationFile, duration_ms: int) -> None:
            super()._record_applied(conn, item, duration_ms)  # the history row is inserted ...
            seen.append(duration_ms)
            raise RuntimeError("history written, then the migration fails")

    root = _write(tmp_path, CHAIN)
    with pytest.raises(InternalError):
        _runner(scratch, root, runner_class=Failing).migrate()
    assert len(seen) == 1
    assert not _exists(scratch, "skm_core.schema_migrations")
    assert not _exists(scratch, "skm_core.schema_baseline")
    assert not _exists(scratch, "skm_core.fx_base")


@pytest.mark.pg
def test_bootstrap_table_matches_the_registry_constraints(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, {})
    assert _runner(scratch, root).migrate() == ()  # empty chain: bootstrap only
    assert _runner(scratch, root).migrate() == ()  # and idempotent
    with psycopg.connect(scratch, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO skm_core.schema_migrations (version, name, checksum, duration_ms) "
                "VALUES (0, 'x', 'sha256:' || repeat('0', 64), 0)"
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO skm_core.schema_migrations (version, name, checksum, duration_ms) "
                "VALUES (1, 'x', 'md5:abc', 0)"
            )


@pytest.mark.pg
def test_edited_applied_file_is_refused_and_nothing_new_runs(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    _runner(scratch, root).migrate()
    _write(
        root,
        {
            "0002_settings_cfg.sql": CONFIG + "-- edited\n",
            "0004_core_more.sql": "CREATE TABLE skm_core.fx_more (a int);",
        },
    )
    runner = _runner(scratch, root)
    with pytest.raises(PreconditionFailed) as caught:
        runner.migrate()
    assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
    assert caught.value.details["version"] == 2
    assert caught.value.details["file"] == "0002_settings_cfg.sql"
    assert _versions(scratch) == [1, 2, 3]
    assert not _exists(scratch, "skm_core.fx_more")
    states = {version: state for _, version, state in runner.status()}
    assert states == {
        1: MigrationState.APPLIED,
        2: MigrationState.MODIFIED,
        3: MigrationState.APPLIED,
        4: MigrationState.PENDING,
    }
    diagnostics = {(d.code, d.severity, d.target) for d in runner.verify()}
    assert diagnostics == {
        ("MIGRATION_CHECKSUM_MISMATCH", Severity.ERROR, "0002_settings_cfg.sql"),
        ("SCHEMA_NOT_MIGRATED", Severity.WARNING, "0004_core_more.sql"),
    }


@pytest.mark.pg
def test_pending_number_below_the_applied_maximum_is_refused(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    runner = _runner(scratch, root)
    runner.migrate()
    _query(scratch, "DELETE FROM skm_core.schema_migrations WHERE version = 2")
    _query(scratch, "DROP SCHEMA skm_config CASCADE")
    with pytest.raises(PreconditionFailed) as caught:
        runner.migrate()
    assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
    assert caught.value.details["reason"] == "out_of_order"
    assert caught.value.details["version"] == 2
    assert _versions(scratch) == [1, 3]  # nothing applied, history untouched
    assert not _exists(scratch, "skm_config.fx_cfg")
    assert any(d.details.get("reason") == "out_of_order" for d in runner.verify())


@pytest.mark.pg
def test_database_newer_than_the_code_is_schema_too_new(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    _runner(scratch, root).migrate()
    older = _write(
        tmp_path / "older", {name: text for name, text in CHAIN.items() if not name.startswith("0003")}
    )
    runner = _runner(scratch, older)
    with pytest.raises(PreconditionFailed) as caught:
        runner.migrate()
    assert caught.value.code is ErrorCode.SCHEMA_TOO_NEW
    assert caught.value.details["version"] == 3
    assert [item.code for item in runner.verify()] == ["SCHEMA_TOO_NEW"]
    assert [state for _, _, state in runner.status()] == [MigrationState.APPLIED] * 2 + [
        MigrationState.UNKNOWN
    ]


@pytest.mark.pg
def test_dry_run_and_target(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    runner = _runner(scratch, root)
    assert runner.migrate(dry_run=True) == (1, 2, 3)
    assert not _exists(scratch, "skm_core.schema_migrations")  # no bootstrap, no DDL
    assert runner.migrate(dry_run=True, target=2) == (1, 2)
    assert runner.migrate(target=2) == (1, 2)
    assert _versions(scratch) == [1, 2]
    assert runner.migrate(dry_run=True) == (3,)
    for bad in (0, 4, True):
        with pytest.raises(ValidationFailed) as caught:
            runner.migrate(target=bad)
        assert caught.value.details["field"] == "target"
    assert runner.migrate() == (3,)


@pytest.mark.pg
def test_concurrent_runners_serialize(scratch: str, tmp_path: Path) -> None:
    slow = dict(CHAIN)
    slow["0001_core_base.sql"] = "SELECT pg_sleep(0.6);\n" + BASE
    root = _write(tmp_path, slow)
    outcomes: dict[int, tuple[int, ...] | BaseException] = {}
    start = threading.Barrier(4)

    def work(index: int) -> None:
        runner = _runner(scratch, root)
        start.wait(timeout=10)
        try:
            outcomes[index] = runner.migrate()
        except BaseException as exc:  # noqa: BLE001 - recorded and asserted below
            outcomes[index] = exc

    threads = [threading.Thread(target=work, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(isinstance(result, BaseException) for result in outcomes.values()), outcomes
    results = sorted(result for result in outcomes.values() if not isinstance(result, BaseException))
    assert results == [(), (), (), (1, 2, 3)]  # one runner applied the chain, the others found it applied
    assert _versions(scratch) == [1, 2, 3]
    assert _query(scratch, "SELECT count(*) FROM skm_core.fx_base") == [(1,)]


@pytest.mark.pg
@pytest.mark.parametrize(
    "bad_sql",
    [
        "-- skm:no-transaction\nCREATE TABLE skm_core.fx_bad (a int);",
        "CREATE TABLE skm_core.fx_bad (a int);\nCOMMIT;",
        "BEGIN;\nCREATE TABLE skm_core.fx_bad (a int);",
        "CREATE TABLE skm_core.fx_bad (a int);\nROLLBACK;",
        "CREATE TABLE skm_core.fx_bad (a int);\nEND;",
    ],
)
def test_non_transactional_sql_leaves_no_ddl_and_no_bootstrap(
    scratch: str, tmp_path: Path, bad_sql: str
) -> None:
    root = _write(tmp_path, {"0001_core_base.sql": BASE, "0002_core_bad.sql": bad_sql})
    runner = _runner(scratch, root)
    with pytest.raises(InternalError) as caught:
        runner.migrate()
    assert caught.value.details["reason"] == "non_transactional_migration"
    assert caught.value.details["file"] == "0002_core_bad.sql"
    assert not _exists(scratch, "skm_core.schema_migrations")  # rejected before the bootstrap
    assert not _exists(scratch, "skm_core.fx_base")
    assert not _exists(scratch, "skm_core.fx_bad")


@pytest.mark.pg
@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ('session.execute("COMMIT")', "non_transactional_migration"),
        ('session.execute("ROLLBACK")', "non_transactional_migration"),
        ('session.executemany("BEGIN", [()])', "non_transactional_migration"),
        ('session.fetchall("COMMIT")', "non_transactional_migration"),
        ("session.commit()", "apply_failed"),
        ("session.connection.commit()", "apply_failed"),
        ("session.autocommit = True", "apply_failed"),
    ],
)
def test_python_apply_cannot_commit(scratch: str, tmp_path: Path, body: str, reason: str) -> None:
    source = f"def apply(session):\n    session.execute('CREATE TABLE skm_core.fx_py (a int)')\n    {body}\n"
    root = _write(tmp_path, {"0001_core_base.sql": BASE, "0002_core_py.py": source})
    with pytest.raises(InternalError) as caught:
        _runner(scratch, root).migrate()
    assert caught.value.details["reason"] == reason
    assert _versions(scratch) == [1]  # the earlier migration committed on its own, this one left nothing
    assert not _exists(scratch, "skm_core.fx_py")


@pytest.mark.pg
def test_python_migration_runs_in_the_same_transaction(scratch: str, tmp_path: Path) -> None:
    source = (
        "def apply(session):\n"
        "    session.execute('CREATE TABLE skm_core.fx_py (a int, b text)')\n"
        "    session.executemany('INSERT INTO skm_core.fx_py VALUES (%s, %s)', [(1, 'x'), (2, 'y')])\n"
        "    rows = session.fetchall('SELECT a, b FROM skm_core.fx_py ORDER BY a')\n"
        "    assert rows == ({'a': 1, 'b': 'x'}, {'a': 2, 'b': 'y'}), rows\n"
        "    assert session.fetchall('CREATE TABLE skm_core.fx_py2 (a int)') == ()\n"
        "    session.execute(\"INSERT INTO skm_core.fx_py VALUES (3, 'COMMIT')\")\n"
    )
    root = _write(tmp_path, {"0001_core_py.py": source})
    assert _runner(scratch, root).migrate() == (1,)
    assert _query(scratch, "SELECT a, b FROM skm_core.fx_py ORDER BY a") == [
        (1, "x"),
        (2, "y"),
        (3, "COMMIT"),
    ]
    assert _runner(scratch, root).migrate() == ()


@pytest.mark.pg
def test_statement_postgres_refuses_in_a_transaction_has_no_fallback(scratch: str, tmp_path: Path) -> None:
    bad = "CREATE TABLE skm_core.fx_x (a int);\nCREATE INDEX CONCURRENTLY ix_fx_x ON skm_core.fx_x (a);\n"
    root = _write(tmp_path, {"0001_core_base.sql": BASE, "0002_core_index.sql": bad})
    with pytest.raises(InternalError) as caught:
        _runner(scratch, root).migrate()
    assert caught.value.details["sqlstate"] == "25001"  # active_sql_transaction
    assert caught.value.details["version"] == 2
    assert caught.value.details["file"] == "0002_core_index.sql"
    assert _versions(scratch) == [1]
    assert not _exists(scratch, "skm_core.fx_x")


@pytest.mark.pg
def test_failed_migration_rolls_back_and_stops_the_chain(scratch: str, tmp_path: Path) -> None:
    bad = "CREATE TABLE skm_core.fx_half (a int);\nSELEC 1;\n"
    root = _write(
        tmp_path,
        {
            "0001_core_base.sql": BASE,
            "0002_core_bad.sql": bad,
            "0003_core_next.sql": "CREATE TABLE skm_core.fx_next (a int);",
        },
    )
    with pytest.raises(SkmError) as caught:
        _runner(scratch, root).migrate()
    assert caught.value.details["version"] == 2
    assert caught.value.details["file"] == "0002_core_bad.sql"
    assert isinstance(caught.value.details["statement_position"], int)
    assert _versions(scratch) == [1]
    assert not _exists(scratch, "skm_core.fx_half")
    assert not _exists(scratch, "skm_core.fx_next")
    _write(
        root, {"0002_core_bad.sql": "CREATE TABLE skm_core.fx_half (a int);\n"}
    )  # a fixed file is a new pending file
    assert _runner(scratch, root).migrate() == (2, 3)


# -- killed runners: the process dies, the server rolls the open transaction back --

_KILLER = """
import os, signal, sys
from datetime import UTC, datetime
from pathlib import Path
from skm.adapters.postgres.migrations.runner import MigrationRunner, directory_loader, discover_migrations

class Clock:
    def now(self):
        return datetime.now(UTC)

root, mode, at = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])

def die():
    os.kill(os.getpid(), signal.SIGKILL)

class Killer(MigrationRunner):
    def _record_applied(self, conn, item, duration_ms):
        if mode == "before_history" and item.version == at:
            die()
        super()._record_applied(conn, item, duration_ms)
        if mode == "after_history" and item.version == at:
            die()

    def _after_commit(self, item):
        if mode == "after_commit" and item.version == at:
            die()

Killer(
    os.environ["SKM_FIXTURE_DSN"], discover_migrations(root), directory_loader(root), Clock(), "killer",
    use_packaged_baseline=False,
).migrate()
"""

KILL_CHAIN = {
    "0001_core_base.sql": BASE,
    "0002_core_two.sql": "CREATE TABLE skm_core.fx_two (a int);\nINSERT INTO skm_core.fx_two VALUES (1);\n",
    "0003_core_three.sql": "CREATE TABLE skm_core.fx_three (a int);\n",
}


def _kill_runner(
    dsn: str, root: Path, mode: str, at: int, tmp_path: Path
) -> subprocess.CompletedProcess[bytes]:
    script = tmp_path / "killer.py"
    script.write_text(_KILLER, encoding="utf-8")
    src = str(Path(skm.__file__).resolve().parent.parent)
    inherited = [entry for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep) if entry]
    env = {**os.environ, "SKM_FIXTURE_DSN": dsn, "PYTHONPATH": os.pathsep.join([src, *inherited])}
    return subprocess.run(
        [sys.executable, str(script), str(root), mode, str(at)],
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )


@pytest.mark.pg
@pytest.mark.parametrize("mode", ["before_history", "after_history"])
def test_killed_runner_leaves_neither_ddl_nor_history(scratch: str, tmp_path: Path, mode: str) -> None:
    root = _write(tmp_path / "chain", KILL_CHAIN)
    done = _kill_runner(scratch, root, mode, 2, tmp_path)
    assert done.returncode == -signal.SIGKILL, done.stderr.decode()
    assert _versions(scratch) == [1]
    assert not _exists(scratch, "skm_core.fx_two")  # the DDL after which the runner died is gone
    assert not _exists(scratch, "skm_core.fx_three")
    assert _runner(scratch, root).migrate() == (2, 3)  # restart: the lock was released and 2 runs once
    assert _query(scratch, "SELECT count(*) FROM skm_core.fx_two") == [(1,)]


@pytest.mark.pg
def test_lost_response_after_commit_is_not_reexecuted(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path / "chain", KILL_CHAIN)
    done = _kill_runner(scratch, root, "after_commit", 2, tmp_path)
    assert done.returncode == -signal.SIGKILL, done.stderr.decode()
    assert _versions(scratch) == [1, 2]
    assert _query(scratch, "SELECT count(*) FROM skm_core.fx_two") == [(1,)]
    assert _runner(scratch, root).migrate() == (3,)  # 2 is applied: its CREATE TABLE is not run a second time
    assert _query(scratch, "SELECT count(*) FROM skm_core.fx_two") == [(1,)]


# -- schema compatibility gate --


@pytest.mark.pg
def test_schema_version_reader_gates_ordinary_operations(scratch: str, tmp_path: Path) -> None:
    root = _write(tmp_path, CHAIN)
    files = discover_migrations(root)
    with psycopg.connect(scratch) as conn:
        reader = SchemaVersionReader(3, files=files)
        assert reader.read(conn) is None  # no history table at all
        assert reader.compatibility(conn) is SchemaCompatibility.NOT_MIGRATED
        with pytest.raises(PreconditionFailed) as missing:
            reader.require(conn)
        assert missing.value.code is ErrorCode.SCHEMA_NOT_MIGRATED
        assert not _exists(scratch, "skm_core.schema_migrations")  # reading never creates anything
    _runner(scratch, root).migrate(target=2)
    with psycopg.connect(scratch) as conn:
        assert SchemaVersionReader(3, files=files).read(conn) == 2
        with pytest.raises(PreconditionFailed) as behind:
            SchemaVersionReader(3, files=files).require(conn)
        assert behind.value.code is ErrorCode.SCHEMA_NOT_MIGRATED
        assert behind.value.details["database_version"] == 2
    _runner(scratch, root).migrate()
    with psycopg.connect(scratch) as conn:
        assert SchemaVersionReader(3, files=files).require(conn) == 3
        assert SchemaVersionReader(3, files=files).compatibility(conn) is SchemaCompatibility.COMPATIBLE
        with pytest.raises(PreconditionFailed) as newer:
            SchemaVersionReader(2, files=files[:2]).require(conn)
        assert newer.value.code is ErrorCode.SCHEMA_TOO_NEW
        assert dict(newer.value.details) == {"database_version": 3, "code_version": 2}
        assert SchemaVersionReader(2, files=files[:2]).compatibility(conn) is SchemaCompatibility.TOO_NEW


@pytest.mark.pg
def test_schema_version_reader_on_an_empty_history(scratch: str, tmp_path: Path) -> None:
    _runner(scratch, _write(tmp_path, {})).migrate()
    with psycopg.connect(scratch) as conn:
        assert SchemaVersionReader(0).read(conn) is None
        assert SchemaVersionReader(0).classify(None) is SchemaCompatibility.NOT_MIGRATED


def test_reader_rejects_a_negative_known_version() -> None:
    with pytest.raises(ValueError, match="known_version"):
        SchemaVersionReader(-1)


def test_schema_snapshot_passes_only_the_dsn_connection_variables_to_pg_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skm.adapters.postgres.migrations import snapshot

    calls: list[tuple[list[str], Mapping[str, str] | None]] = []

    def fake_run(args: list[str], env: Mapping[str, str] | None = None) -> str:
        calls.append((args, env))
        return "pg_dump (PostgreSQL) 17.0" if args[1:] == ["--version"] else "CREATE SCHEMA skm_core;\n"

    monkeypatch.setenv("SKM_AMBIENT_SECRET", "leak")
    monkeypatch.setenv("PGSERVICE", "ambient")
    monkeypatch.setattr(snapshot, "_server_major", lambda dsn: 16)
    monkeypatch.setattr(snapshot.shutil, "which", lambda name: "/bin/pg_dump")
    monkeypatch.setattr(snapshot, "_run", fake_run)

    assert (
        snapshot.schema_snapshot("postgresql://u:pw@h:5433/db?sslmode=require") == "CREATE SCHEMA skm_core;\n"
    )
    env = calls[-1][1]
    assert env == {
        "PGHOST": "h",
        "PGPORT": "5433",
        "PGUSER": "u",
        "PGPASSWORD": "pw",
        "PGDATABASE": "db",
        "PGSSLMODE": "require",
    }
