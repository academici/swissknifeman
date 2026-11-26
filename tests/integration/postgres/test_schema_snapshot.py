"""The package ``schema.snapshot.sql`` is the schema of a database migrated from zero.

05 §14, adapters §1.10. The file is only ever written by ``make db-snapshot``; this test applies the
packaged chain to a fresh scratch database created from ``SKM_TEST_DATABASE_URL`` and compares its
normalized ``pg_dump --schema-only`` with the file, so every DDL change shows up as a snapshot diff in
review. Table totals are not hard-coded: the catalog of the migrated database is compared with the
snapshot text. The dump needs a ``pg_dump`` whose major version is at least the server's (or the
compose service).
"""

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib import resources
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from skm.adapters.postgres.migrations.snapshot import normalize_dump, schema_snapshot

_CREATE_TABLE = re.compile(r"^CREATE TABLE (skm_[a-z_]+)\.([a-z0-9_]+) \($", re.MULTILINE)
_SKM_SCHEMAS = r"skm\_%"
# Deferred FKs: the column comes with the earlier migration, the constraint with 0018/0019 (05 §14).
_DEFERRED_FKS = (
    "fk_runs__resource_versions",
    "fk_reviews__resource_versions",
    "fk_attempt_steps__context_manifests",
)


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 - migration runner clock of the scratch database, not product code


def _snapshot_file() -> str:
    package = resources.files("skm.adapters.postgres.migrations")
    return package.joinpath("schema.snapshot.sql").read_text("utf-8")


# --- no database needed -------------------------------------------------------------------------------------


def test_the_snapshot_file_is_normalized_schema_only_text() -> None:
    text = _snapshot_file()
    assert text == normalize_dump(text)
    lines = text.splitlines()
    assert not any(line.startswith(("--", "SET ", "\\restrict", "\\unrestrict")) for line in lines)
    # statements, not function bodies: grant_app() builds GRANT statements as text
    assert not any(line.startswith(("GRANT ", "REVOKE ", "INSERT INTO ", "COPY ")) for line in lines)
    assert not any(line.startswith("ALTER ") and " OWNER TO " in line for line in lines)  # --no-owner
    assert _CREATE_TABLE.search(text) is not None
    for name in _DEFERRED_FKS:
        assert f"ADD CONSTRAINT {name} FOREIGN KEY" in text, name


# --- live PostgreSQL ----------------------------------------------------------------------------------------


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only against a loopback or socket test server (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail(
            "schema snapshot tests create databases only on a local server through an '*_test' database",
            pytrace=False,
        )


@pytest.fixture
def migrated(pg_dsn: str) -> Iterator[str]:
    """A scratch database with the whole packaged chain applied from zero."""
    _checked_admin(pg_dsn)
    name = f"skm_t_snap_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(pg_dsn, dbname=name)
            files = discover_migrations()
            runner = MigrationRunner(dsn, files, package_loader(), _Clock(), "skm-test")
            assert runner.migrate() == tuple(item.version for item in files)
            assert runner.verify() == ()
            yield dsn
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.pg
def test_the_snapshot_of_a_fresh_database_matches_the_file(migrated: str) -> None:
    assert schema_snapshot(migrated) == _snapshot_file(), (
        "schema drift: run `make db-snapshot` and review the diff"
    )


@pytest.mark.pg
def test_ddl_outside_the_chain_is_a_snapshot_difference(migrated: str) -> None:
    with psycopg.connect(migrated, autocommit=True) as conn:
        conn.execute("ALTER TABLE skm_core.scopes ADD COLUMN fx_drift integer")
    drifted = schema_snapshot(migrated)
    assert drifted != _snapshot_file()
    assert "fx_drift integer" in drifted


@pytest.mark.pg
def test_the_snapshot_lists_every_table_and_no_constraint_is_left_unvalidated(migrated: str) -> None:
    with psycopg.connect(migrated, autocommit=True) as conn:
        tables = conn.execute(
            "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname LIKE %s ORDER BY 1, 2",
            (_SKM_SCHEMAS,),
        ).fetchall()
        unvalidated = conn.execute(
            "SELECT c.conname FROM pg_catalog.pg_constraint c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname LIKE %s AND NOT c.convalidated ORDER BY 1",
            (_SKM_SCHEMAS,),
        ).fetchall()
        deferred = conn.execute(
            "SELECT conname FROM pg_catalog.pg_constraint "
            "WHERE contype = 'f' AND conname = ANY(%s) ORDER BY 1",
            (list(_DEFERRED_FKS),),
        ).fetchall()
    assert sorted(_CREATE_TABLE.findall(_snapshot_file())) == [(schema, table) for schema, table in tables]
    assert unvalidated == []  # every deferred FK is added NOT VALID and validated in the same migration
    assert sorted(name for (name,) in deferred) == sorted(_DEFERRED_FKS)
