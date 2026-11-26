"""Packaged 0.1.0 baselines, migration history and project grants on PostgreSQL."""

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from io import StringIO
from typing import Any, LiteralString, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.migrations.runner import (
    MigrationFile,
    MigrationRunner,
    MigrationState,
    discover_migrations,
    known_version,
    package_loader,
    packaged_baseline,
)
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.errors import PreconditionFailed
from skm.kernel.generated.error_codes import ErrorCode
from skm.platform.logging import setup


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 - migration runner clock of the scratch database, not product code


def test_packaged_baselines_start_independent_migration_chains() -> None:
    assert discover_migrations()[0].filename == "0001_core_baseline.sql"
    assert discover_migrations(database="machine")[0].filename == "0001_host_baseline.sql"
    project = packaged_baseline()
    machine = packaged_baseline(database="machine")
    assert project[0] == "0.1.0"
    assert machine[0] == "0.1.0-host"
    assert project[1] != machine[1]


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only against a loopback or socket test server (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail(
            "migration chain tests create databases only on a local server through an '*_test' database",
            pytrace=False,
        )


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_chain_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield make_conninfo(pg_dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def isolated_logging() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", setup._state.settings)  # main() reconfigures logging
        yield


def _runner(dsn: str) -> MigrationRunner:
    return MigrationRunner(dsn, discover_migrations(), package_loader(), _Clock(), "skm-test")


def _history(dsn: str) -> list[tuple[object, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return conn.execute(
            "SELECT version, name, checksum FROM skm_core.schema_migrations ORDER BY version"
        ).fetchall()


def _cli(*argv: str) -> tuple[int, str, str]:
    def never_a_backend(options: object, environ: object) -> Backend:
        raise AssertionError("skm db is local: it must not build a backend")

    out, err = StringIO(), StringIO()
    code = main(list(argv), environ={}, stdout=out, stderr=err, backend=never_a_backend)
    return code, out.getvalue(), err.getvalue()


def _rows(files: Sequence[MigrationFile]) -> list[tuple[object, ...]]:
    return [(item.version, item.filename, item.checksum) for item in files]


@pytest.mark.pg
def test_fresh_database_gets_the_whole_chain_once(scratch: str, isolated_logging: None) -> None:
    runner = _runner(scratch)
    versions = tuple(item.version for item in runner.files)
    assert versions == tuple(range(1, known_version(runner.files) + 1))
    assert runner.migrate() == versions
    assert _history(scratch) == _rows(runner.files)
    assert runner.migrate() == ()  # repeat: nothing pending
    assert _runner(scratch).migrate() == ()  # a new runner reads the history again
    assert _history(scratch) == _rows(runner.files)
    assert {state for _, _, state in runner.status()} == {MigrationState.APPLIED}
    assert runner.verify() == ()

    code, out, err = _cli("--json", "db", "verify", "--database-url", scratch)
    document = cast("Mapping[str, Any]", json.loads(out))
    assert (code, err, document["ok"]) == (0, "", True), out
    assert document["result"] == {"ok": True, "known_version": versions[-1], "pending": []}
    assert not document.get("diagnostics"), document


@pytest.mark.pg
def test_intake_tables_and_visas_are_append_only_for_skm_app(scratch: str) -> None:
    _runner(scratch).migrate()
    with psycopg.connect(scratch, autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'skm_app'").fetchone() is None:
            pytest.skip("test database user cannot create the skm_app role")
        assert conn.execute(
            """
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conrelid = 'skm_execution.revision_visas'::regclass
              AND contype = 'f' AND confrelid = 'skm_execution.readiness_reports'::regclass
            """
        ).fetchone() == (
            "FOREIGN KEY (workspace_id, plan_id, revision_id, readiness_report_id) "
            "REFERENCES skm_execution.readiness_reports(workspace_id, plan_id, revision_id, id) "
            "ON DELETE RESTRICT",
        )
        for table in (
            "skm_planning.plan_design_briefs",
            "skm_planning.plan_design_brief_rag_bindings",
            "skm_planning.plan_design_brief_research_references",
            "skm_execution.revision_visas",
        ):
            row = conn.execute(
                """SELECT has_table_privilege('skm_app', %(table)s, 'SELECT'),
                          has_table_privilege('skm_app', %(table)s, 'INSERT'),
                          has_table_privilege('skm_app', %(table)s, 'UPDATE'),
                          has_table_privilege('skm_app', %(table)s, 'DELETE'),
                          has_table_privilege('skm_app', %(table)s, 'TRUNCATE')""",
                {"table": table},
            ).fetchone()
            assert row == (True, True, False, False, False), table


@pytest.mark.pg
def test_old_database_is_refused_without_writing_bookkeeping(scratch: str) -> None:
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("CREATE TABLE public.old_catalog (id integer PRIMARY KEY)")
        conn.execute("INSERT INTO public.old_catalog VALUES (42)")
    runner = _runner(scratch)
    for dry_run in (True, False):
        with pytest.raises(PreconditionFailed) as caught:
            runner.migrate(dry_run=dry_run)
        assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
        assert caught.value.details["reason"] == "schema_baseline_missing"
    with psycopg.connect(scratch) as conn:
        assert conn.execute("SELECT to_regnamespace('skm_core')").fetchone() == (None,)
        assert conn.execute("SELECT id FROM public.old_catalog").fetchall() == [(42,)]


@pytest.mark.pg
@pytest.mark.parametrize(
    ("create", "probe"),
    [
        (
            'CREATE COLLATION public.old_sort FROM pg_catalog."C"',
            "SELECT count(*) FROM pg_collation WHERE oid = to_regcollation('public.old_sort')",
        ),
        (
            "CREATE TEXT SEARCH DICTIONARY public.old_search (TEMPLATE = pg_catalog.simple)",
            "SELECT count(*) FROM pg_ts_dict WHERE oid = 'public.old_search'::regdictionary",
        ),
        (
            "CREATE PUBLICATION old_publication FOR ALL TABLES",
            "SELECT count(*) FROM pg_publication WHERE pubname = 'old_publication'",
        ),
        (
            "CREATE CAST (name AS timestamp) WITH INOUT",
            "SELECT count(*) FROM pg_cast WHERE castsource = 'name'::regtype "
            "AND casttarget = 'timestamp'::regtype AND castmethod = 'i'",
        ),
    ],
    ids=["public-collation", "public-dictionary", "publication", "cast"],
)
def test_non_table_objects_prevent_initialization(
    scratch: str, create: LiteralString, probe: LiteralString
) -> None:
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute(create)
    runner = _runner(scratch)
    for dry_run in (True, False):
        with pytest.raises(PreconditionFailed) as caught:
            runner.migrate(dry_run=dry_run)
        assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
        assert caught.value.details["reason"] == "schema_baseline_missing"
        with psycopg.connect(scratch) as conn:
            assert conn.execute("SELECT to_regnamespace('skm_core')").fetchone() == (None,)
            assert conn.execute(probe).fetchone() == (1,)
