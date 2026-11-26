"""``skm db migrate|status|verify|snapshot`` over a fixture chain on PostgreSQL (adapters §1.10, K21).

The product chain is not needed: fixture migration files are written into ``tmp_path`` and the runner's
package root is pointed at them, so the commands run the same code on a chain this test controls. Each live
test gets its own scratch database created from ``SKM_TEST_DATABASE_URL`` (loopback and ``*_test`` only). The
snapshot tests need a ``pg_dump`` whose major version is at least the server's (or the compose service).
"""

import importlib.resources
import json
import os
import socket
from collections.abc import Iterator, Mapping
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.migrations import runner as runner_module
from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.adapters.postgres.migrations.snapshot import normalize_dump
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands import db as db_module
from skm.entrypoints.cli.main import Backend, main
from skm.platform.logging import setup

BASE = (
    "CREATE TABLE skm_core.fx_base (id int PRIMARY KEY, note text);\n"
    "INSERT INTO skm_core.fx_base VALUES (1, 'COMMIT; -- inside a string');\n"
)
CONFIG = "CREATE SCHEMA skm_config;\nCREATE TABLE skm_config.fx_cfg (k text PRIMARY KEY);\n"
SEED = "INSERT INTO skm_config.fx_cfg VALUES ('seed');\n"
CHAIN = {"0001_core_base.sql": BASE, "0002_settings_cfg.sql": CONFIG, "0003_planning_seed.data.sql": SEED}


@pytest.fixture(autouse=True)
def isolated_logging() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", setup._state.settings)  # main() reconfigures logging
        yield


def never_a_backend(options: object, environ: object) -> Backend:
    raise AssertionError("skm db is local: it must not build a backend")


def run(*argv: str, environ: Mapping[str, str] | None = None) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    code = main(list(argv), environ=dict(environ or {}), stdout=out, stderr=err, backend=never_a_backend)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fixture chain in place of ``migrations/sql``: discovery and loading both follow it."""
    root = tmp_path / "chain"
    root.mkdir()
    for name, text in CHAIN.items():
        (root / name).write_bytes(text.encode("utf-8"))
    monkeypatch.setattr(runner_module, "_package_root", lambda _database="project": root)
    return root


# --- no database ----------------------------------------------------------------------------------


def test_the_group_is_local_and_discovered() -> None:
    group = next(item for item in GROUPS if item.name == "db")
    assert group is db_module.GROUP
    assert group.requires_backend is False  # K21: outside the bus, usable on a database that is not migrated
    assert group.module is None


def test_the_migration_directory_is_a_package_with_the_bootstrap_file() -> None:
    package = importlib.resources.files("skm.adapters.postgres.migrations.sql")
    assert package.joinpath("__init__.py").is_file()  # shipped and importable, like every package directory
    assert package.joinpath("runner_bootstrap.sql").is_file()
    discover_migrations()  # whatever numbered files exist form a valid chain


def test_there_is_no_apply_route_on_the_bus() -> None:
    from skm.bootstrap.platform_module import PLATFORM_MANIFEST

    assert all(
        getattr(spec, "name", "") != "platform.apply_migrations" for spec in PLATFORM_MANIFEST.commands
    )
    assert all(getattr(spec, "name", "") != "platform.apply_migrations" for spec in PLATFORM_MANIFEST.queries)


def test_a_bare_group_and_an_unknown_verb_are_usage_errors() -> None:
    assert run("db")[0] == 2
    assert run("db", "apply")[0] == 2


def test_without_a_bootstrap_the_hint_names_database_url(tmp_path: Path) -> None:
    for verb in ("migrate", "status", "verify", "snapshot"):
        code, out, err = run("--json", "db", verb, environ={"HOME": str(tmp_path)})
        error = json.loads(out)["error"]
        assert (code, err, error["code"]) == (6, "", "BOOTSTRAP_MISSING"), verb
        assert "--database-url" in error["details"]["hint"]


def test_an_unreachable_database_fails_without_the_password(chain: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    dsn = f"postgresql://skm_migrator:hunter2-secret@127.0.0.1:{port}/nodb?connect_timeout=2"
    for verb in ("migrate", "status", "verify", "snapshot"):
        code, out, err = run("db", verb, "--database-url", dsn)
        assert code != 0, verb
        assert "hunter2-secret" not in out + err
    code, out, err = run("--json", "db", "status", "--database-url", dsn)
    assert code != 0
    assert "hunter2-secret" not in out + err
    assert json.loads(out)["ok"] is False


def test_a_non_transactional_file_is_refused_before_any_connection(tmp_path: Path, chain: Path) -> None:
    (chain / "0004_core_bad.sql").write_text(
        "CREATE TABLE skm_core.fx_bad (a int);\nCOMMIT;\n", encoding="utf-8"
    )
    dsn = (
        "postgresql://skm:pw-not-used@127.0.0.1:1/never"  # a connection attempt would be BACKEND_UNAVAILABLE
    )
    for verb in ("migrate", "verify"):
        code, out, err = run("--json", "db", verb, "--database-url", dsn)
        assert code == 70, (
            verb,
            out,
            err,
        )  # INTERNAL_ERROR: the chain is refused, the database never contacted
        assert json.loads(out)["error"]["code"] == "INTERNAL_ERROR"


# --- live PostgreSQL ------------------------------------------------------------------------------


def _checked_admin(dsn: str) -> None:
    """Destructive SQL (CREATE/DROP DATABASE) only on a loopback or socket test server (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail(
            "CLI migration tests create databases only on a local server through '*_test'", pytrace=False
        )


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_cli_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(pg_dsn, dbname=name)
            with psycopg.connect(dsn, autocommit=True) as probe:
                assert probe.execute("SELECT current_database()").fetchone() == (name,)
            yield dsn
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _query(dsn: str, statement: str) -> list[tuple[object, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        cursor = conn.execute(cast("Any", statement))
        return cursor.fetchall() if cursor.description is not None else []


def _versions(dsn: str) -> list[int]:
    rows = _query(dsn, "SELECT version FROM skm_core.schema_migrations ORDER BY version")
    return [int(row[0]) for row in rows]  # pyright: ignore[reportArgumentType]


def _exists(dsn: str, name: str) -> bool:
    return bool(_query(dsn, f"SELECT to_regclass('{name}') IS NOT NULL")[0][0])


def _applied_logs(err: str) -> int:
    """The runner logs each applied migration on stderr (one JSON record each); nothing else may be there."""
    records = [json.loads(line) for line in err.splitlines()]
    assert all(record["event"] == "db.migration.applied" for record in records), err
    return len(records)


def _result(out: str) -> dict[str, Any]:
    document = json.loads(out)
    assert document["ok"] is True, document
    return document["result"]


@pytest.mark.pg
def test_status_before_migrate_lists_the_whole_chain_as_pending(scratch: str, chain: Path) -> None:
    code, out, err = run("--json", "db", "status", "--database-url", scratch)
    assert (code, err) == (0, "")
    result = _result(out)
    assert (result["known_version"], result["db_version"], result["state"]) == (3, 0, "not_migrated")
    assert [(m["version"], m["state"]) for m in result["migrations"]] == [
        (1, "pending"),
        (2, "pending"),
        (3, "pending"),
    ]
    assert not _exists(scratch, "skm_core.schema_migrations")  # status never creates the bookkeeping table


@pytest.mark.pg
def test_migrate_applies_the_chain_once_and_status_and_verify_follow(scratch: str, chain: Path) -> None:
    code, out, err = run("db", "migrate", "--database-url", scratch)
    assert (code, out.strip(), _applied_logs(err)) == (
        0,
        "applied 3 (0001_core_base … 0003_planning_seed)",
        3,
    )
    assert _versions(scratch) == [1, 2, 3]
    assert _query(scratch, "SELECT k FROM skm_config.fx_cfg") == [("seed",)]

    code, out, err = run("db", "migrate", "--database-url", scratch)  # a second run is a no-op
    assert (code, out.strip(), err) == (0, "up to date (0003)", "")

    code, out, _ = run("--json", "db", "migrate", "--database-url", scratch)
    assert _result(out) == {"applied": [], "pending": [], "current": 3, "dry_run": False}

    code, out, _ = run("--json", "db", "status", "--database-url", scratch)
    result = _result(out)
    assert (result["known_version"], result["db_version"], result["state"]) == (3, 3, "ok")
    assert [m["state"] for m in result["migrations"]] == ["applied"] * 3

    code, out, err = run("db", "verify", "--database-url", scratch)
    assert (code, out.strip(), err) == (0, "migrations verified (0003)", "")


@pytest.mark.pg
def test_human_status_prints_a_table(scratch: str, chain: Path) -> None:
    run("db", "migrate", "--database-url", scratch, "--target", "1")
    code, out, _ = run("db", "status", "--database-url", scratch)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "schema  database 0001, code 0003 (not_migrated)"
    assert [line.split() for line in lines[2:]] == [
        ["0001", "0001_core_base.sql", "applied"],
        ["0002", "0002_settings_cfg.sql", "pending"],
        ["0003", "0003_planning_seed.data.sql", "pending"],
    ]


@pytest.mark.pg
def test_dry_run_changes_nothing_and_target_stops_early(scratch: str, chain: Path) -> None:
    code, out, _ = run("--json", "db", "migrate", "--database-url", scratch, "--dry-run")
    assert _result(out) == {"applied": [], "pending": [1, 2, 3], "current": 0, "dry_run": True}
    assert not _exists(scratch, "skm_core.schema_migrations")  # not even the bookkeeping table

    code, out, _ = run("--json", "db", "migrate", "--database-url", scratch, "--target", "2")
    assert _result(out) == {"applied": [1, 2], "pending": [3], "current": 2, "dry_run": False}
    assert _versions(scratch) == [1, 2]

    code, out, _ = run("--json", "db", "migrate", "--database-url", scratch, "--target", "9")
    assert code == 1  # not a migration number: SCHEMA_INVALID
    assert json.loads(out)["error"]["code"] == "SCHEMA_INVALID"
    assert _versions(scratch) == [1, 2]


@pytest.mark.pg
def test_verify_rejects_a_changed_applied_file_and_migrate_refuses_to_go_on(
    scratch: str, chain: Path
) -> None:
    assert run("db", "migrate", "--database-url", scratch)[0] == 0
    (chain / "0002_settings_cfg.sql").write_bytes(
        (CONFIG + "-- edited after it was applied\n").encode("utf-8")
    )

    code, out, _ = run("--json", "db", "verify", "--database-url", scratch)
    assert code == 6  # precondition: the history does not match the packaged migrations
    error = json.loads(out)["error"]
    assert error["code"] == "MIGRATION_CHECKSUM_MISMATCH"
    finding = error["details"]["findings"][0]
    assert finding["target"] == "0002_settings_cfg.sql"
    assert finding["details"]["version"] == 2

    code, out, _ = run(
        "--json", "db", "status", "--database-url", scratch
    )  # status still reports, and names it
    assert [m["state"] for m in _result(out)["migrations"]] == ["applied", "modified", "applied"]

    (chain / "0004_core_more.sql").write_text("CREATE TABLE skm_core.fx_more (a int);\n", encoding="utf-8")
    code, out, _ = run("--json", "db", "migrate", "--database-url", scratch)
    assert code == 6
    assert json.loads(out)["error"]["code"] == "MIGRATION_CHECKSUM_MISMATCH"
    assert _versions(scratch) == [1, 2, 3]
    assert not _exists(scratch, "skm_core.fx_more")  # nothing was applied behind a changed file


@pytest.mark.pg
def test_a_deleted_applied_file_and_a_newer_database_fail_verify(scratch: str, chain: Path) -> None:
    assert run("db", "migrate", "--database-url", scratch)[0] == 0
    (chain / "0003_planning_seed.data.sql").unlink()
    code, out, _ = run("--json", "db", "verify", "--database-url", scratch)
    assert code == 6
    assert (
        json.loads(out)["error"]["code"] == "SCHEMA_TOO_NEW"
    )  # the database has 0003, this code ends at 0002
    code, out, _ = run("--json", "db", "status", "--database-url", scratch)
    result = _result(out)
    assert (result["known_version"], result["db_version"], result["state"]) == (2, 3, "too_new")


@pytest.mark.pg
def test_a_broken_migration_is_not_accepted_and_leaves_no_trace(scratch: str, chain: Path) -> None:
    (chain / "0004_core_broken.sql").write_text(
        "CREATE TABLE skm_core.fx_half (a int);\nINSERT INTO skm_core.no_such_table VALUES (1);\n",
        encoding="utf-8",
    )
    code, out, _ = run("--json", "db", "migrate", "--database-url", scratch)
    assert code != 0
    assert json.loads(out)["ok"] is False
    assert _versions(scratch) == [1, 2, 3]  # the good prefix stays applied, the broken file is not recorded
    assert not _exists(scratch, "skm_core.fx_half")  # and its first statement was rolled back with the rest

    code, out, _ = run("--json", "db", "verify", "--database-url", scratch)
    assert code == 0  # the history is intact; the broken file is merely pending
    assert [d["code"] for d in json.loads(out)["diagnostics"]] == ["SCHEMA_NOT_MIGRATED"]


@pytest.mark.pg
def test_the_dsn_comes_from_the_bootstrap_migrator_url_before_database_url(
    scratch: str, chain: Path, tmp_path: Path
) -> None:
    bootstrap = tmp_path / "bootstrap.toml"
    bootstrap.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\ninstance_id = "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11"\n'
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/APP_DSN"\n'
        'migrator_url = "secret://env/MIGRATOR_DSN"\n',
        encoding="utf-8",
    )
    environ = {"APP_DSN": "postgresql://skm_app:wrong@127.0.0.1:1/none", "MIGRATOR_DSN": scratch}
    code, out, err = run("--bootstrap", str(bootstrap), "db", "migrate", environ=environ)
    assert (code, _applied_logs(err)) == (0, 3)
    assert out.startswith("applied 3")
    assert _versions(scratch) == [1, 2, 3]
    assert (
        run("--bootstrap", str(bootstrap), "db", "migrate", "--database-url", scratch, environ=environ)[0]
        == 0
    )


@pytest.mark.pg
def test_snapshot_prints_the_normalized_schema_and_changes_nothing(scratch: str, chain: Path) -> None:
    assert run("db", "migrate", "--database-url", scratch)[0] == 0
    before = _query(scratch, "SELECT version, checksum FROM skm_core.schema_migrations ORDER BY version")

    code, first, err = run("db", "snapshot", "--database-url", scratch)
    assert (code, err) == (0, "")
    assert "CREATE TABLE skm_core.fx_base" in first
    assert "CREATE TABLE skm_config.fx_cfg" in first
    assert first == normalize_dump(first)
    assert first.endswith("\n")
    assert not first.endswith("\n\n")
    assert not any(line.startswith(("--", "SET ", "\\restrict")) for line in first.splitlines())
    assert "OWNER TO" not in first
    assert "GRANT " not in first
    assert "INSERT INTO" not in first  # schema only: no fixture rows

    code, second, _ = run("db", "snapshot", "--database-url", scratch)
    assert second == first  # reproducible
    assert (
        _query(scratch, "SELECT version, checksum FROM skm_core.schema_migrations ORDER BY version") == before
    )
    assert _query(scratch, "SELECT count(*) FROM skm_core.fx_base") == [(1,)]

    code, out, _ = run("--json", "db", "snapshot", "--database-url", scratch)
    assert _result(out) == {"snapshot": first}


@pytest.mark.pg
def test_snapshot_output_writes_a_file_and_write_needs_a_fully_migrated_database(
    scratch: str, chain: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_copy = tmp_path / "package" / "schema.snapshot.sql"
    monkeypatch.setattr(db_module, "SNAPSHOT_FILE", package_copy)
    run("db", "migrate", "--database-url", scratch, "--target", "2")

    code, out, _ = run("--json", "db", "snapshot", "--database-url", scratch, "--write")
    assert code == 6  # pending migrations: the package copy is only ever taken from a complete chain
    assert json.loads(out)["error"]["code"] == "SCHEMA_NOT_MIGRATED"
    assert not package_copy.exists()

    target = tmp_path / "out" / "partial.sql"
    code, out, _ = run("db", "snapshot", "--database-url", scratch, "--output", str(target))
    assert (code, out.strip()) == (0, str(target))  # --output has no such guard: it is the operator's file
    assert "CREATE TABLE skm_config.fx_cfg" in target.read_text(encoding="utf-8")

    assert run("db", "migrate", "--database-url", scratch)[0] == 0
    code, out, _ = run("db", "snapshot", "--database-url", scratch, "--write")
    assert (code, out.strip()) == (0, str(package_copy))
    assert package_copy.read_text(encoding="utf-8") == run("db", "snapshot", "--database-url", scratch)[1]

    code, out, _ = run(
        "--json", "db", "snapshot", "--database-url", scratch, "--write", "--output", str(target)
    )
    assert code == 1  # mutually exclusive
    assert json.loads(out)["error"]["code"] == "SCHEMA_INVALID"
