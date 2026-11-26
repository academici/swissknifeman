"""Exercise the machine and project baselines through separate database roles and connections."""

from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Final
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.errors import InsufficientPrivilege

from skm.adapters.postgres.machine import PostgresMachineStore
from skm.adapters.postgres.migrations.runner import (
    MigrationDatabase,
    MigrationRunner,
    discover_migrations,
    package_loader,
    packaged_baseline,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.platform.config.secrets import SecretRef
from skm.platform.machine import (
    MachineBinding,
    MachineCheckout,
    MachineCheckoutKey,
    MachinePrincipal,
    MachineProfile,
    MachineRetry,
    MachineRetryKey,
    MachineSession,
)
from skm.platform.system_clock import SystemClock
from support.pg import check_admin_dsn

pytestmark = pytest.mark.pg

_ROLES: Final = ("skm_app", "skm_migrator", "skm_host_app", "skm_host_migrator")


@dataclass(frozen=True)
class Databases:
    project: str = field(repr=False)
    machine: str = field(repr=False)
    project_migrator: str = field(repr=False)
    machine_migrator: str = field(repr=False)
    project_name: str
    machine_name: str


def _runner(dsn: str, database: MigrationDatabase) -> MigrationRunner:
    return MigrationRunner(
        dsn,
        discover_migrations(database=database),
        package_loader(database=database),
        SystemClock(),
        "skm-test-machine",
        database=database,
    )


@pytest.fixture
def databases(pg_dsn: str) -> Iterator[Databases]:
    check_admin_dsn(pg_dsn)
    suffix = uuid4().hex[:12]
    names = {role: f"{role}_{suffix}" for role in _ROLES}
    passwords = {role: token_hex(24) for role in _ROLES}
    project_name, machine_name = f"skm_t_project_{suffix}", f"skm_t_machine_{suffix}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        for role in _ROLES:
            with suppress(psycopg.errors.DuplicateObject, psycopg.errors.UniqueViolation):
                admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        logins: list[str] = []
        created: list[str] = []
        try:
            for role, name in names.items():
                admin.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE {}").format(
                        sql.Identifier(name), sql.Literal(passwords[role]), sql.Identifier(role)
                    )
                )
                logins.append(name)
            for db, migrator, app in (
                (project_name, "skm_migrator", "skm_app"),
                (machine_name, "skm_host_migrator", "skm_host_app"),
            ):
                admin.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                        sql.Identifier(db), sql.Identifier(names[migrator])
                    )
                )
                created.append(db)
                admin.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
                admin.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(db), sql.Identifier(app)
                    )
                )

            def login(db: str, role: str) -> str:
                return make_conninfo(pg_dsn, user=names[role], password=passwords[role], dbname=db)

            yield Databases(
                project=login(project_name, "skm_app"),
                machine=login(machine_name, "skm_host_app"),
                project_migrator=login(project_name, "skm_migrator"),
                machine_migrator=login(machine_name, "skm_host_migrator"),
                project_name=project_name,
                machine_name=machine_name,
            )
        finally:
            for db in reversed(created):
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db)))
            for name in reversed(logins):
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


@pytest.fixture
def migrated_databases(databases: Databases) -> Databases:
    for runner in (
        _runner(databases.project_migrator, "project"),
        _runner(databases.machine_migrator, "machine"),
    ):
        versions = tuple(item.version for item in runner.files)
        assert runner.migrate(dry_run=True) == versions
        assert runner.migrate() == versions
        assert runner.migrate() == ()
        assert runner.verify() == ()
    return databases


def test_empty_databases_require_the_migrator_for_the_selected_track(databases: Databases) -> None:
    attempts: tuple[tuple[str, MigrationDatabase, str], ...] = (
        (databases.project_migrator, "machine", "skm_host_migrator"),
        (databases.machine_migrator, "project", "skm_migrator"),
        (databases.project, "project", "skm_migrator"),
        (databases.machine, "machine", "skm_host_migrator"),
    )
    for dsn, track, role in attempts:
        runner = _runner(dsn, track)
        for dry_run in (True, False):
            with pytest.raises(Forbidden) as caught:
                runner.migrate(dry_run=dry_run)
            assert caught.value.code is ErrorCode.FORBIDDEN
            assert caught.value.details == {
                "reason": "migrator_role_required",
                "database": track,
                "role": role,
            }
        with psycopg.connect(dsn) as conn:
            assert conn.execute(
                "SELECT to_regnamespace('skm_core'), to_regnamespace('skm_host')"
            ).fetchone() == (None, None)


def test_two_app_roles_read_only_their_own_databases(migrated_databases: Databases) -> None:
    databases = migrated_databases
    crossed: tuple[tuple[str, MigrationDatabase], ...] = (
        (databases.project_migrator, "machine"),
        (databases.machine_migrator, "project"),
    )
    for dsn, wrong_schema in crossed:
        with pytest.raises(PreconditionFailed) as wrong_database:
            _runner(dsn, wrong_schema).migrate()
        assert wrong_database.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
        assert wrong_database.value.details["reason"] == "schema_baseline_missing"

    for own, other in (
        (databases.project, databases.machine_name),
        (databases.machine, databases.project_name),
        (databases.project_migrator, databases.machine_name),
        (databases.machine_migrator, databases.project_name),
    ):
        with (
            pytest.raises(psycopg.OperationalError, match="permission denied for database"),
            psycopg.connect(make_conninfo(own, dbname=other), connect_timeout=5),
        ):
            pass

    with psycopg.connect(databases.project, autocommit=True) as project:
        assert project.execute("SELECT to_regnamespace('skm_host')").fetchone() == (None,)
        assert (
            project.execute("SELECT epoch, chain_sha256 FROM skm_core.schema_baseline").fetchone()
            == packaged_baseline()
        )
        assert project.execute("SELECT value FROM skm_config.generation").fetchone() == (0,)
        assert project.execute(
            "SELECT id, kind, config_ref FROM skm_artifacts.storage_backends"
        ).fetchall() == [("local-primary", "local", "paths.blobs_root")]
        assert project.execute(
            """
            SELECT to_regclass('skm_planning.legacy_import_jobs'),
                   to_regclass('skm_planning.legacy_import_objects')
            """
        ).fetchone() == (None, None)
        scope_id = uuid4()
        project.execute("INSERT INTO skm_core.scopes (id, kind) VALUES (%s, 'instance')", (scope_id,))
        assert project.execute("SELECT kind FROM skm_core.scopes WHERE id = %s", (scope_id,)).fetchone() == (
            "instance",
        )
        with pytest.raises(InsufficientPrivilege):
            project.execute("UPDATE skm_core.schema_migrations SET duration_ms = 0")

    store = PostgresMachineStore(databases.machine)
    installation = uuid4()
    assert store.get_installation_id() is None
    store.initialize_installation(installation)
    store.initialize_installation(installation)
    with pytest.raises(ValidationFailed):
        store.initialize_installation(uuid4())
    store.set_operator_setting(installation, "runtimes.binaries", {"codex": "/opt/skm/codex"})
    assert store.get_operator_setting(installation, "runtimes.binaries") == {"codex": "/opt/skm/codex"}
    with psycopg.connect(databases.machine, autocommit=True) as host:
        assert host.execute("SELECT to_regnamespace('skm_core')").fetchone() == (None,)
        assert host.execute(
            "SELECT epoch, chain_sha256 FROM skm_host.schema_baseline"
        ).fetchone() == packaged_baseline(database="machine")
        assert host.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'skm_host' ORDER BY 1"
        ).fetchall() == [
            (name,)
            for name in (
                "bindings",
                "checkouts",
                "installation",
                "operator_settings",
                "profiles",
                "retries",
                "schema_baseline",
                "schema_migrations",
                "sessions",
                "user_settings",
            )
        ]
        assert host.execute(
            "SELECT value FROM skm_host.operator_settings WHERE key = 'runtimes.binaries'"
        ).fetchone() == ({"codex": "/opt/skm/codex"},)
        with pytest.raises(InsufficientPrivilege):
            host.execute("UPDATE skm_host.schema_migrations SET duration_ms = 0")


@pytest.fixture
def store(migrated_databases: Databases) -> tuple[PostgresMachineStore, MachinePrincipal]:
    machine = PostgresMachineStore(migrated_databases.machine)
    installation = machine.get_installation_id()
    if installation is None:
        installation = uuid4()
        machine.initialize_installation(installation)
    return machine, MachinePrincipal(installation, uuid4(), uuid4())


def test_settings_persist_json_null(
    store: tuple[PostgresMachineStore, MachinePrincipal], migrated_databases: Databases
) -> None:
    machine, principal = store
    key = "test.null-value"
    machine.set_operator_setting(principal.installation_id, key, "operator")
    machine.set_user_setting(principal, key, "user")
    machine.set_operator_setting(principal.installation_id, key, None)
    machine.set_user_setting(principal, key, None)
    assert machine.get_operator_setting(principal.installation_id, key) is None
    assert machine.get_user_setting(principal, key) is None
    with psycopg.connect(migrated_databases.machine) as conn:
        assert conn.execute(
            """
            SELECT value IS NULL, jsonb_typeof(value) FROM skm_host.operator_settings WHERE key = %s
            UNION ALL
            SELECT value IS NULL, jsonb_typeof(value) FROM skm_host.user_settings WHERE key = %s
            """,
            (key, key),
        ).fetchall() == [(False, "null"), (False, "null")]


def _token_hash() -> str:
    return sha256(token_hex(32).encode()).hexdigest()


def test_profile_revision_binds_handles_and_revokes_them_on_rebind(
    store: tuple[PostgresMachineStore, MachinePrincipal],
) -> None:
    machine, owner = store
    profile = MachineProfile(
        owner.installation_id,
        "first",
        owner.instance_id,
        "https://first.example",
        "https://first.example/api/v1",
        SecretRef.parse("secret://file/profile-token"),
    )
    assert machine.put_profile(profile)
    stored = machine.get_profile(owner.installation_id, profile.name)
    assert stored is not None
    assert stored.revision is not None
    assert machine.list_profiles(owner.installation_id) == (stored,)
    next_origin = replace(profile, origin="https://second.example", endpoint="https://second.example/api/v1")
    assert not machine.put_profile(replace(next_origin, name="spoof"))
    other = replace(owner, principal_id=uuid4())
    same_uuid = replace(owner, instance_id=uuid4())
    key = "runtimes.model"
    machine.set_user_setting(owner, key, "owner")
    machine.set_user_setting(other, key, "other")
    machine.set_user_setting(same_uuid, key, "separate-instance")
    now = SystemClock().now()
    owner_handle = MachineSession(stored, owner.principal_id, _token_hash(), now + timedelta(minutes=3))
    other_handle = MachineSession(stored, other.principal_id, _token_hash(), now + timedelta(minutes=3))
    assert machine.put_session(owner_handle)
    assert machine.put_session(other_handle)
    for handle, expected, value in ((owner_handle, owner, "owner"), (other_handle, other, "other")):
        principal = machine.get_session(owner.installation_id, handle.handle_hash, now)
        assert principal is not None
        assert principal == expected
        assert machine.get_user_setting(principal, key) == value
        assert machine.get_session(owner.installation_id, handle.handle_hash, handle.expires_at) is None
    assert machine.get_user_setting(same_uuid, key) == "separate-instance"
    assert machine.get_session(uuid4(), owner_handle.handle_hash, now) is None
    assert machine.get_session(owner.installation_id, _token_hash(), now) is None
    machine.delete_session(owner.installation_id, other_handle.handle_hash)
    assert machine.get_session(owner.installation_id, other_handle.handle_hash, now) is None
    assert machine.put_profile(next_origin, expected=stored)
    assert machine.get_session(owner.installation_id, owner_handle.handle_hash, now) is None
    assert not machine.put_session(replace(owner_handle, handle_hash=_token_hash()))
    replacement = machine.get_profile(owner.installation_id, profile.name)
    assert replacement is not None
    assert replacement.origin == next_origin.origin
    assert not machine.delete_profile(stored)
    current_handle = replace(owner_handle, profile=replacement, handle_hash=_token_hash())
    assert machine.put_session(current_handle)
    machine.revoke_sessions(owner)
    assert machine.get_session(owner.installation_id, current_handle.handle_hash, now) is None
    assert machine.delete_profile(replacement)


def test_checkout_and_retry_use_stable_scoped_keys(
    store: tuple[PostgresMachineStore, MachinePrincipal], tmp_path: Path
) -> None:
    machine, principal = store
    checkout_key = MachineCheckoutKey(principal.installation_id, principal.instance_id, uuid4(), uuid4())
    checkout = MachineCheckout(checkout_key, tmp_path / "worktree")
    assert machine.reserve_checkout(checkout) == checkout
    assert (
        machine.reserve_checkout(replace(checkout, key=replace(checkout_key, checkout_id=uuid4())))
        == checkout
    )
    assert machine.get_checkout(replace(checkout_key, host_id=uuid4())) is None
    assert machine.get_checkout(replace(checkout_key, instance_id=uuid4())) is None
    binding = MachineBinding(principal, checkout_key, uuid4(), uuid4(), uuid4())
    machine.put_binding(binding)
    assert machine.get_binding(principal, checkout_key) == binding
    assert machine.get_binding(replace(principal, principal_id=uuid4()), checkout_key) is None

    now = SystemClock().now()
    for operation in ("bind", "verify"):
        key = MachineRetryKey(principal, checkout_key, operation, uuid4(), "checkout")
        assert machine.get_retry(key) is None
        with pytest.raises(NotFound):
            machine.confirm_retry(key, {"ok": True})
        pending = MachineRetry(key, uuid4().hex, {"value": True}, now + timedelta(minutes=1))
        assert machine.begin_retry(pending) == pending
        assert machine.begin_retry(replace(pending, idempotency_key=uuid4().hex, safe_until=now)) == pending
        with pytest.raises(Conflict) as changed:
            machine.begin_retry(replace(pending, payload={"value": 1}))
        assert changed.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
        recovered = machine.get_retry(key)
        assert recovered is not None
        assert recovered == pending
        assert recovered.state(now) == "pending"
        assert recovered.state(pending.safe_until) == "expired"
        confirmed = machine.confirm_retry(key, {"ok": True})
        assert confirmed.state(pending.safe_until) == "confirmed"
        assert machine.confirm_retry(key, {"ok": True}) == confirmed
        with pytest.raises(Conflict):
            machine.confirm_retry(key, {"ok": False})
