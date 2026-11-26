"""``build_app(backend="postgres")`` on a live server (kernel-platform §5.3 steps 6a-8, mechanisms/06 §1, §4).

Every test gets a scratch database cloned from one migrated template (the pattern of ``test_uow``), so a
database without migrations, with a newer history or with the whole chain is one fixture away. Applications
are the test composition: ``FakeAuthorizer`` and ``FakeScopeChain`` come through ``CompositionOverrides``
instead of the production authorizer and actor. Connections of one application are told apart from every other
session by a unique ``application_name``.
"""

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import psycopg_pool
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from integration.postgres.test_machine_store import Databases
from integration.postgres.test_machine_store import databases as databases
from skm.adapters.postgres.core.schema_version import SchemaCompatibility, SchemaVersionReader
from skm.adapters.postgres.machine import PostgresMachineStore
from skm.adapters.postgres.migrations.runner import (
    MigrationRunner,
    baseline_chain_sha256,
    discover_migrations,
    package_loader,
    packaged_baseline,
)
from skm.bootstrap import composition
from skm.bootstrap.composition import KNOWN_SCHEMA_VERSION, App, CompositionOverrides, build_app
from skm.bootstrap.lifecycle import local_migrate
from skm.bootstrap.platform_module import local_migration_runner
from skm.entrypoints.cli.main import main
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.access.generated.results import BootstrapLocalOwnerResult
from skm.modules.access.public import SYSTEM_ACTOR
from skm.modules.settings.generated import commands, queries
from skm.modules.workspace.public import RegisterHost, RegisterHostResult
from skm.platform.config.bootstrap import BootstrapConfig, load_bootstrap
from skm.platform.config.secrets import SecretRef
from skm.platform.logging.redaction import Redactor
from skm.platform.machine import MachineProfile
from skm.platform.system_clock import SystemClock

pg = pytest.mark.pg

ROUNDS = "execution.review.max_rounds"
INSTANCE = UUID("01900000-0000-7000-8000-000000000001")
WORKSPACE = UUID("01900000-0000-7000-8000-000000000002")
HOST = UUID("01900000-0000-7000-8000-000000000003")
OWNER = Actor(PrincipalId(UUID("01900000-0000-7000-8000-0000000000b1")), PrincipalKind.HUMAN, "fixture-owner")
SCOPE = commands.SetValueDefsScopeRef(level="workspace", scope_id=WORKSPACE)
LOOKUP = queries.GetValueDefsScopeRef(level="workspace", scope_id=WORKSPACE)


class _RunnerClock:
    def now(self):
        return SystemClock().now()


# ---------------------------------------------------------------------------------------------- databases


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only against a loopback server through an '*_test' database."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("composition tests create databases only on a local '*_test' server", pytrace=False)


_TEMPLATES: dict[str, str] = {}


def _template(admin: psycopg.Connection, pg_dsn: str) -> str:
    name = _TEMPLATES.get(pg_dsn)
    if name is None:
        name = f"skm_t_comp_tpl_{os.getpid()}_{uuid4().hex[:8]}"
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        _TEMPLATES[pg_dsn] = name  # dropped at module end even if the migration fails
        runner = MigrationRunner(
            make_conninfo(pg_dsn, dbname=name),
            discover_migrations(),
            package_loader(),
            _RunnerClock(),
            "skm-test",
        )
        runner.migrate()
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
    name = f"skm_t_comp_{os.getpid()}_{uuid4().hex[:8]}"
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
def empty(pg_dsn: str) -> Iterator[str]:
    """DSN of a database without a single migration."""
    yield from _database(pg_dsn, migrated=False)


@pytest.fixture
def migrated(pg_dsn: str) -> Iterator[str]:
    """DSN of a database with the whole chain and the instance scope (``skm init`` comes later)."""
    for dsn in _database(pg_dsn, migrated=True):
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            conn.execute(
                "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) "
                "VALUES (%s, 'instance', NULL, NULL)",
                (INSTANCE,),
            )
        yield dsn


# ---------------------------------------------------------------------------------------------- helpers


class Sessions:
    """Server sessions of one application name, seen through an autocommit observer."""

    def __init__(self, dsn: str, name: str) -> None:
        self.name = name
        self._observer = psycopg.connect(dsn, autocommit=True, connect_timeout=5)

    def count(self) -> int:
        row = self._observer.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s AND pid <> pg_backend_pid()",
            (self.name,),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def settle(self, expected: int, timeout: float = 5.0) -> int:
        """The count once it equals ``expected`` (a closed client leaves the server a moment later)."""
        deadline = time.monotonic() + timeout
        while (found := self.count()) != expected and time.monotonic() < deadline:
            time.sleep(0.05)
        return found

    def close(self) -> None:
        self._observer.close()


@pytest.fixture
def sessions(request: pytest.FixtureRequest) -> Iterator[Callable[[str], Sessions]]:
    opened: list[Sessions] = []

    def observe(dsn: str) -> Sessions:
        found = Sessions(dsn, f"skm-comp-{uuid4().hex[:12]}")
        opened.append(found)
        return found

    yield observe
    for found in opened:
        found.close()


def _bootstrap(tmp_path: Path, dsn: str, application_name: str, **changes: object) -> BootstrapConfig:
    loaded = load_bootstrap(None, {"SKM_DATABASE_URL": dsn}, tmp_path)
    return replace(
        loaded, database_application_name=application_name, database_pool_timeout_seconds=2, **changes
    )


def _overrides(**changes: object) -> CompositionOverrides:
    return CompositionOverrides(authorizer=FakeAuthorizer(), scopes=FakeScopeChain(), **changes)  # type: ignore[arg-type]


def _build(bootstrap: BootstrapConfig, *, surface: Surface = Surface.CLI, **changes: object) -> App:
    return build_app(
        bootstrap,
        surface=surface,
        environ=changes.pop("environ", {}),  # type: ignore[arg-type]
        invocation={},
        backend="postgres",
        overrides=_overrides(**changes),
    )


def _meta() -> RequestMeta:
    return RequestMeta("req_" + "0" * 26, Surface.CLI, None, SystemClock().now())


def _create_workspace(app: App) -> None:
    with app.uow_factory(_meta()) as uow:
        uow.repo(ScopeRegistry).create(
            ScopeId(WORKSPACE),
            ScopeKind.WORKSPACE,
            parent=ScopeId(INSTANCE),
            workspace_id=WorkspaceId(WORKSPACE),
        )
        uow.commit()


def _set(app: App, value: int) -> None:
    app.client(actor=OWNER, surface=Surface.CLI).dispatch(
        commands.SetValue(scope=SCOPE, key=ROUNDS, value=value, reason="composition test")
    )


def _get(app: App) -> object:
    return app.client(actor=OWNER, surface=Surface.CLI).ask(queries.GetValue(scope=LOOKUP, key=ROUNDS)).value  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------- shared config


@pg
def test_two_independently_built_apps_share_the_committed_configuration(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    first = _build(_bootstrap(tmp_path, migrated, seen.name))
    second = _build(_bootstrap(tmp_path, migrated, seen.name))
    try:
        assert first.bus is not second.bus
        assert first.config is not second.config
        assert first.uow_factory is not second.uow_factory
        _create_workspace(first)
        _set(first, 3)
        assert _get(second) == 3  # committed by the first application, read by the second
        _set(second, 5)
        assert _get(first) == 5  # and the other way round: the first one's cache follows the generation
    finally:
        first.close()
        second.close()


@pg
def test_configuration_outlives_the_application_that_wrote_it(migrated: str, tmp_path: Path) -> None:
    writer = _build(_bootstrap(tmp_path, migrated, "skm-comp-writer"))
    try:
        _create_workspace(writer)
        _set(writer, 4)
    finally:
        writer.close()
    reader = _build(_bootstrap(tmp_path, migrated, "skm-comp-reader"))
    try:
        assert _get(reader) == 4
    finally:
        reader.close()


@pg
def test_process_config_is_captured_from_the_database_instance(migrated: str, tmp_path: Path) -> None:
    app = _build(_bootstrap(tmp_path, migrated, "skm-comp-process"))
    try:
        assert app.config.process is not None
        assert app.config.process.instance_scope_id == INSTANCE
        assert app.instance_id == INSTANCE
        assert app.host_id is None
    finally:
        app.close()


@pg
def test_a_bootstrap_naming_another_instance_is_refused(migrated: str, tmp_path: Path) -> None:
    bootstrap = replace(_bootstrap(tmp_path, migrated, "skm-comp-identity"), instance_id=uuid4())
    with pytest.raises(ValidationFailed) as caught:
        _build(bootstrap)
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert caught.value.details["reason"] == "process_identity_mismatch"


# ---------------------------------------------------------------------------------------------- schema gate


@pg
def test_an_unmigrated_database_refuses_an_ordinary_command_and_db_status_still_works(
    empty: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(empty)
    with pytest.raises(PreconditionFailed) as caught:
        _build(_bootstrap(tmp_path, empty, seen.name))
    assert caught.value.code is ErrorCode.SCHEMA_NOT_MIGRATED
    assert caught.value.details["code_version"] == KNOWN_SCHEMA_VERSION
    assert caught.value.details["hint"] == "skm db migrate"
    assert seen.settle(0) == 0  # the start-up connection is closed and no pool was opened
    status = local_migration_runner(empty).status()  # what `skm db status` reads: no App, no gate
    assert [state.value for _, _, state in status].count("pending") == KNOWN_SCHEMA_VERSION


@pg
def test_a_database_older_than_the_code_is_not_migrated(migrated: str, tmp_path: Path) -> None:
    with psycopg.connect(migrated, autocommit=True) as conn:
        conn.execute("DELETE FROM skm_core.schema_migrations WHERE version = %s", (KNOWN_SCHEMA_VERSION,))
    with pytest.raises(PreconditionFailed) as caught:
        _build(_bootstrap(tmp_path, migrated, "skm-comp-older"))
    assert caught.value.code is ErrorCode.SCHEMA_NOT_MIGRATED
    assert caught.value.details["database_version"] == (KNOWN_SCHEMA_VERSION - 1 or None)


@pg
@pytest.mark.parametrize(
    "surface", [Surface.CLI, Surface.BACKGROUND, Surface.MCP, Surface.TEST, Surface.WORKER, Surface.HOOK]
)
def test_a_database_newer_than_the_code_is_refused_on_non_api_surfaces(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions], surface: Surface
) -> None:
    seen = sessions(migrated)
    newer = KNOWN_SCHEMA_VERSION + 1
    with psycopg.connect(migrated, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO skm_core.schema_migrations "
            "(version, name, checksum, applied_at, applied_by, duration_ms) "
            "SELECT %s, 'future', checksum, applied_at, applied_by, duration_ms "
            "FROM skm_core.schema_migrations WHERE version = 1",
            (newer,),
        )
    with pytest.raises(PreconditionFailed) as caught:
        _build(replace(_bootstrap(tmp_path, migrated, seen.name), host_id=HOST), surface=surface)
    assert caught.value.code is ErrorCode.SCHEMA_TOO_NEW
    assert caught.value.details["database_version"] == newer
    assert seen.settle(0) == 0


@pg
@pytest.mark.parametrize(
    ("database", "state"),
    [("empty", "not_migrated"), ("migrated", "not_migrated"), ("migrated", "too_new")],
)
def test_api_starts_only_health_and_status_on_incompatible_schema(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    database: str,
    state: str,
) -> None:
    from typing import Any, cast

    from security.api.harness import BASE, TestClient
    from skm.entrypoints.api.app import create_app

    dsn = request.getfixturevalue(database)
    with psycopg.connect(dsn, autocommit=True) as conn:
        if database != "empty":
            if state == "not_migrated":
                conn.execute(
                    "DELETE FROM skm_core.schema_migrations WHERE version = %s", (KNOWN_SCHEMA_VERSION,)
                )
            else:
                conn.execute(
                    "INSERT INTO skm_core.schema_migrations "
                    "(version, name, checksum, applied_by, duration_ms) "
                    "VALUES (%s, 'future', %s, 'api-test', 0)",
                    (KNOWN_SCHEMA_VERSION + 1, "sha256:" + "a" * 64),
                )

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("restricted startup must not start plugins or artifact coordination")

    monkeypatch.setattr(composition.ProcessPlugins, "start", forbidden)
    monkeypatch.setattr(composition, "bind_postgres_artifacts", forbidden)
    before = local_migration_runner(dsn).status()
    app = _build(_bootstrap(tmp_path, dsn, "skm-api-status"), surface=Surface.API)
    try:
        # This service cannot be wired (no interval): attempting to start it fails immediately.
        service = type("ForbiddenService", (), {"name": "must_not_start"})()
        app = replace(app, services=(cast("Any", service),))
        with TestClient(create_app(app), base_url=BASE) as client:
            assert client.get("/health/live").json() == {"status": "live"}
            ready = client.get("/health/ready")
            assert ready.status_code == 503
            assert ready.json()["checks"]["schema"] == state
            assert client.get("/api/v1/admin/migrations").status_code == 401
            for path in ("/api/v1/me", "/api/v1/openapi.json", "/health/details", "/"):
                response = client.get(path)
                assert response.status_code == 409
                assert response.json()["code"] == (
                    "SCHEMA_TOO_NEW" if state == "too_new" else "SCHEMA_NOT_MIGRATED"
                )
        assert local_migration_runner(dsn).status() == before
        if database == "empty":
            with psycopg.connect(dsn) as conn:
                assert conn.execute("SELECT to_regclass('skm_core.scopes')").fetchone() == (None,)
    finally:
        app.close()


@pg
def test_fresh_database_records_the_packaged_project_baseline(migrated: str) -> None:
    with psycopg.connect(migrated) as conn:
        applied = conn.execute("SELECT version, name, checksum FROM skm_core.schema_migrations").fetchall()
        history = {version: (name, checksum) for version, name, checksum in applied}
        assert history == {item.version: (item.filename, item.checksum) for item in discover_migrations()}
        epoch, expected = packaged_baseline()
        assert baseline_chain_sha256(history) == expected
        assert conn.execute("SELECT epoch, chain_sha256 FROM skm_core.schema_baseline").fetchone() == (
            epoch,
            expected,
        )


@pg
def test_missing_baseline_is_rejected_by_migration_startup_and_health(migrated: str, tmp_path: Path) -> None:
    from security.api.harness import BASE, TestClient
    from skm.entrypoints.api.app import create_app

    with psycopg.connect(migrated, autocommit=True) as conn:
        history = conn.execute("SELECT version, name, checksum FROM skm_core.schema_migrations").fetchall()
        conn.execute("DROP TABLE skm_core.schema_baseline")
    config = _bootstrap(tmp_path, migrated, "skm-missing-baseline", database_migrate_on_start=True)
    runner = local_migration_runner(migrated)
    for migrate in (runner.migrate, lambda: local_migrate(config, {}, lambda _: None, startup=True)):
        with pytest.raises(PreconditionFailed) as caught:
            migrate()
        assert caught.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
        assert caught.value.details["reason"] == "schema_baseline_missing"
    with psycopg.connect(migrated) as conn:
        reader = SchemaVersionReader(KNOWN_SCHEMA_VERSION)
        assert reader.compatibility(conn) is SchemaCompatibility.INVALID
        with pytest.raises(PreconditionFailed, match="schema baseline"):
            reader.require(conn)
        assert conn.execute("SELECT to_regclass('skm_core.schema_baseline')").fetchone() == (None,)
        assert (
            conn.execute("SELECT version, name, checksum FROM skm_core.schema_migrations").fetchall()
            == history
        )
        assert conn.execute("SELECT id FROM skm_core.scopes").fetchall() == [(INSTANCE,)]
    with (
        closing(_build(config, surface=Surface.API)) as app,
        TestClient(create_app(app), base_url=BASE) as client,
    ):
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"]["schema"] == "invalid"


@pg
def test_tampered_baseline_marker_is_refused(migrated: str) -> None:
    with psycopg.connect(migrated, autocommit=True) as conn:
        original = conn.execute("SELECT epoch, chain_sha256 FROM skm_core.schema_baseline").fetchone()
        assert original == packaged_baseline()
        conn.execute("UPDATE skm_core.schema_baseline SET chain_sha256 = repeat('0', 64)")
        with pytest.raises(PreconditionFailed, match="schema baseline") as caught:
            local_migration_runner(migrated).migrate()
        assert caught.value.details["reason"] == "schema_baseline_mismatch"
        assert SchemaVersionReader(KNOWN_SCHEMA_VERSION).compatibility(conn) is SchemaCompatibility.INVALID
        assert conn.execute("SELECT chain_sha256 FROM skm_core.schema_baseline").fetchone() == ("0" * 64,)


@pg
def test_postgres_startup_sync_honors_host_setting_and_keeps_pack_versions(
    migrated: str, tmp_path: Path
) -> None:
    config = _bootstrap(tmp_path, migrated, "skm-pack-sync")
    with psycopg.connect(migrated) as conn:
        conn.execute(
            "INSERT INTO skm_access.principals (id, kind, display_name, created_at, updated_at) "
            "VALUES (%s, 'service', 'system', now(), now())",
            (SYSTEM_PRINCIPAL_ID,),
        )
    with (
        closing(_build(config, surface=Surface.API, environ={"SKM__EXTENSIONS__SYNC_ON_START": "false"})),
        psycopg.connect(migrated) as conn,
    ):
        assert conn.execute("SELECT slug FROM skm_extensions.packs").fetchall() == []

    def packs() -> list[tuple[object, ...]]:
        with psycopg.connect(migrated) as conn:
            return conn.execute(
                "SELECT p.slug, v.id, v.digest FROM skm_extensions.packs p "
                "JOIN skm_extensions.pack_versions v ON v.pack_id = p.id ORDER BY p.slug, v.id"
            ).fetchall()

    with closing(_build(config, surface=Surface.API)):
        first = packs()
        assert [row[0] for row in first].count("core") == 1
    with closing(_build(config, surface=Surface.API)):
        assert packs() == first


@pg
def test_the_known_version_is_the_applied_version_of_a_fully_migrated_database(migrated: str) -> None:
    with psycopg.connect(migrated) as conn:
        row = conn.execute("SELECT max(version) FROM skm_core.schema_migrations").fetchone()
    assert row is not None
    assert row[0] == KNOWN_SCHEMA_VERSION == len(discover_migrations())


@pg
def test_an_unreachable_database_is_backend_unavailable(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path, "postgresql://skm@127.0.0.1:1/none", "skm-comp-down")
    with pytest.raises(BackendUnavailable) as caught:
        _build(bootstrap)
    assert caught.value.details["phase"] == "connect"


# ---------------------------------------------------------------------------------------------- the pool


@pg
def test_pool_max_size_below_the_cli_minimum_is_config_invalid(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    bootstrap = _bootstrap(tmp_path, migrated, seen.name, database_pool_max_size=1)
    with pytest.raises(ValidationFailed) as caught:
        _build(bootstrap)
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert caught.value.details == {"field": "database.pool_max_size", "minimum": 2}
    assert seen.settle(0) == 0  # refused before any pool connection


@pg
def test_the_serve_minimum_comes_from_the_captured_threadpool_size(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    with psycopg.connect(migrated, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, 'host', %s, NULL)",
            (HOST, INSTANCE),
        )
    base = replace(_bootstrap(tmp_path, migrated, seen.name), host_id=HOST)
    with pytest.raises(ValidationFailed) as caught:
        _build(replace(base, database_pool_max_size=18), surface=Surface.API)
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    # api.threadpool.size (default 16) + no background service yet + 3
    assert caught.value.details == {"field": "database.pool_max_size", "minimum": 19}
    assert seen.settle(0) == 0
    app = _build(replace(base, database_pool_max_size=19), surface=Surface.API)
    try:
        assert app.host_id == HOST
        assert app.host is None  # serve never touches a checkout
        assert app.config.process is not None
        assert app.config.process.host_target is not None
    finally:
        app.close()


@pg
def test_the_pool_has_the_surface_default_when_the_bootstrap_sets_no_maximum(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    app = _build(_bootstrap(tmp_path, migrated, seen.name, database_pool_min_size=1))
    try:
        assert seen.settle(1) == 1  # the start-up connection is gone, the pool holds its minimum
        with app.uow_factory(_meta()) as first, app.uow_factory(_meta()) as second:
            assert first.repo(ScopeRegistry).instance().id == INSTANCE
            assert second.repo(ScopeRegistry).instance().id == INSTANCE
            assert seen.count() == 2
            with pytest.raises(BackendUnavailable) as caught, app.uow_factory(_meta()):
                pass  # a CLI process gets two connections: the third unit of work waits and times out
            assert caught.value.details["reason"] == "pool_timeout"
    finally:
        app.close()


@pg
def test_an_explicit_pool_maximum_is_honoured(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    app = _build(
        _bootstrap(tmp_path, migrated, seen.name, database_pool_min_size=3, database_pool_max_size=4)
    )
    try:
        assert seen.settle(3) == 3
        opened = [app.uow_factory(_meta()) for _ in range(4)]
        for unit in opened:
            unit.__enter__()
        try:
            assert seen.settle(4) == 4
            with pytest.raises(BackendUnavailable), app.uow_factory(_meta()):
                pass
        finally:
            for unit in reversed(opened):
                unit.__exit__(None, None, None)
    finally:
        app.close()


@pg
def test_closing_the_app_leaves_no_connection_and_close_is_idempotent(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    app = _build(
        _bootstrap(tmp_path, migrated, seen.name, database_pool_min_size=2, database_pool_max_size=3)
    )
    assert seen.settle(2) == 2
    app.close()
    assert seen.settle(0) == 0
    app.close()
    with pytest.raises(psycopg_pool.PoolClosed), app.uow_factory(_meta()):  # the pool is gone
        pass
    assert seen.settle(0) == 0


# ---------------------------------------------------------------------------------------------- other inputs


@pg
def test_the_dsn_may_be_a_secret_reference(migrated: str, tmp_path: Path) -> None:
    bootstrap = replace(
        _bootstrap(tmp_path, migrated, "skm-comp-secret"),
        database_url=SecretRef.parse("secret://env/SKM_TEST_DSN"),
    )
    app = _build(bootstrap, environ={"SKM_TEST_DSN": migrated})
    app.close()
    with pytest.raises(ValidationFailed) as caught:
        _build(bootstrap, environ={})
    assert caught.value.details["reason"] == "secret_unresolved"


@pg
def test_a_bootstrap_without_a_dsn_is_config_invalid(migrated: str, tmp_path: Path) -> None:
    with pytest.raises(ValidationFailed) as caught:
        _build(replace(_bootstrap(tmp_path, migrated, "skm-comp-nodsn"), database_url=None))
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert caught.value.details["field"] == "database.url"


@pg
def test_memory_repository_overrides_cannot_back_the_postgres_composition(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions]
) -> None:
    seen = sessions(migrated)
    with pytest.raises(ValidationFailed) as caught:
        _build(
            _bootstrap(tmp_path, migrated, seen.name), repositories={ScopeRegistry: lambda _state: object()}
        )
    assert caught.value.details["reason"] == "memory_repositories_override"
    assert seen.settle(0) == 0


@pg
def test_doctor_checks_are_refused_inside_an_open_unit_of_work_of_the_same_thread(
    migrated: str, tmp_path: Path
) -> None:
    app = _build(_bootstrap(tmp_path, migrated, "skm-comp-doctor"))
    try:
        assert app.doctor is not None
        app.doctor.collect(redactor=Redactor())  # outside every unit of work
        with app.uow_factory(_meta()), pytest.raises(RuntimeError, match="outside every unit of work"):
            app.doctor.collect(redactor=Redactor())
        app.doctor.collect(redactor=Redactor())  # the unit of work is over again
    finally:
        app.close()


@pg
def test_a_failed_build_after_the_pool_opened_closes_it(
    migrated: str, tmp_path: Path, sessions: Callable[[str], Sessions], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = sessions(migrated)

    def broken(**_options: object) -> object:
        raise RuntimeError("event writer failed")

    monkeypatch.setattr(composition, "PostgresEventWriter", broken)
    with pytest.raises(RuntimeError, match="event writer failed"):
        _build(_bootstrap(tmp_path, migrated, seen.name, database_pool_min_size=2, database_pool_max_size=2))
    assert seen.settle(0) == 0


def _install_project_plugin(
    dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, scenario: str
) -> tuple[str, Path]:
    plugin_id = "a01.projectonly"
    module = f"skm_a01_fixture_{scenario}"
    site = tmp_path / "site"
    dist = site / f"{module}-1.0.dist-info"
    dist.mkdir(parents=True)
    marker = tmp_path / "project-plugin-imported"
    (site / f"{module}.py").write_text(
        "from pathlib import Path\n"
        "from skm.plugin_api import API_VERSION, ComponentKind, ComponentSpec, PluginManifest, Side\n"
        f"marker = Path({str(marker)!r})\n"
        "marker.write_text('import')\n"
        "class Estimator:\n"
        "    estimator_id = 'a01-fixture'\n"
        "    def estimate(self, text): return len(text)\n"
        "def factory(ctx):\n"
        "    marker.write_text(marker.read_text() + ' factory')\n"
        "    return Estimator()\n"
        f"manifest = PluginManifest({plugin_id!r}, '1.0.0', API_VERSION, '>=0.1.0', 'Fixture', 'A01', (\n"
        "    ComponentSpec(ComponentKind.TOKEN_ESTIMATOR, 'a01-fixture', Side.HOST, factory),\n"
        "))\n",
        encoding="utf-8",
    )
    (dist / "METADATA").write_text(f"Name: {module}\nVersion: 1.0\n", encoding="utf-8")
    (dist / "entry_points.txt").write_text(
        f"[skm.plugins]\n{plugin_id} = {module}:manifest\n", encoding="utf-8"
    )
    (dist / "RECORD").write_text(f"{module}.py,,\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(site))
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO skm_config.entries "
            "(id, scope_id, key, op, value, created_by, created_at, updated_by, updated_at) "
            "VALUES (%s, %s, 'plugins.allowed', 'set', %s::jsonb, %s, now(), %s, now())",
            (uuid4(), INSTANCE, json.dumps([plugin_id]), OWNER.principal_id, OWNER.principal_id),
        )
    return plugin_id, marker


@pg
def test_production_worker_never_loads_project_only_plugin(
    migrated: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_id, marker = _install_project_plugin(migrated, tmp_path, monkeypatch, scenario="worker")
    with psycopg.connect(migrated) as connection:
        connection.execute(
            "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, 'host', %s, NULL)",
            (HOST, INSTANCE),
        )
    config = _bootstrap(
        tmp_path,
        migrated,
        "skm-prod-worker-plugin-gate",
        host_id=HOST,
        token_pepper=SecretRef.parse("secret://env/SKM_TEST_WORKER_PEPPER"),
    )
    env = {
        "SKM_TEST_WORKER_PEPPER": "synthetic-a01-test-token-pepper-32-bytes",
        "SKM__EXTENSIONS__SYNC_ON_START": "false",
    }
    with closing(build_app(config, surface=Surface.WORKER, environ=env, invocation={})) as worker:
        assert worker.config.process is not None
        assert worker.config.process.work.get("plugins.allowed") == [plugin_id]
        assert worker.plugins == ()
        assert not marker.exists()

    # A production CLI that uses the existing plugin configuration still finds the installed distribution.
    with closing(build_app(config, surface=Surface.CLI, environ=env, invocation={})) as cli:
        assert any(plugin.plugin_id == plugin_id for plugin in cli.plugins)
        assert marker.read_text() == "import factory"


@pg
def test_managed_runtime_commands_do_not_import_project_only_plugins(
    migrated: str, databases: Databases, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    MigrationRunner(
        databases.machine_migrator,
        discover_migrations(database="machine"),
        package_loader(database="machine"),
        SystemClock(),
        "skm-a01-plugin-machine",
        database="machine",
    ).migrate()
    installation = uuid4()
    machine = PostgresMachineStore(databases.machine)
    machine.initialize_installation(installation)
    machine.put_profile(MachineProfile(installation, "default", INSTANCE, f"embedded:{INSTANCE}", None))
    machine.set_operator_setting(installation, "plugins.allowed", [])
    bootstrap = tmp_path / "bootstrap.toml"
    bootstrap.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{INSTANCE}"\n'
        '[access]\nmode = "embedded"\n'
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n'
        '[secrets]\ntoken_pepper = "secret://env/SKM_FIXTURE_PEPPER"\n',
        encoding="utf-8",
    )
    environ = {
        "HOME": str(tmp_path),
        "SKM_DATABASE_URL": migrated,
        "SKM_MACHINE_DATABASE_URL": databases.machine,
        "SKM_INSTALLATION_ID": str(installation),
        "SKM_INSTANCE_ID": str(INSTANCE),
        "SKM_FIXTURE_PEPPER": "synthetic-a01-plugin-test-token-pepper",
        "SKM__EXTENSIONS__SYNC_ON_START": "false",
    }
    config = load_bootstrap(str(bootstrap), environ, tmp_path)
    with closing(build_app(config, surface=Surface.CLI, environ=environ, invocation={})) as app:
        system = app.client(actor=SYSTEM_ACTOR, surface=Surface.CLI)
        owner = cast(
            "BootstrapLocalOwnerResult", system.dispatch(BootstrapLocalOwner(display_name="Fixture owner"))
        )
        assert owner.token_secret is not None
        client = app.client(actor=app.authenticate(owner.token_secret), surface=Surface.CLI)
        host = cast(
            "RegisterHostResult",
            client.dispatch(
                RegisterHost.from_json({"name": "test-host", "platform": {"os": "linux", "arch": "x86_64"}})
            ),
        )
    token_secret = owner.token_secret
    environ["SKM_HOST_ID"] = str(host.host_id)
    _, marker = _install_project_plugin(migrated, tmp_path, monkeypatch, scenario="cli")

    def run(*command: str) -> tuple[int, str]:
        out, err = StringIO(), StringIO()
        status = main(
            ("--bootstrap", str(bootstrap), "--as-token", token_secret, "--json", *command),
            environ=environ,
            stdout=out,
            stderr=err,
        )
        return status, out.getvalue() + err.getvalue()

    status, output = run("runtime", "detect")
    assert status == 0, output
    assert not marker.exists()

    status, output = run("session", "start")
    assert status != 0, output
    assert "no project selected" in output, output
    assert not marker.exists()

    status, output = run("whoami")
    assert status == 0, output
    assert str(owner.principal_id) in output
    assert marker.read_text() == "import factory"
