"""PostgreSQL and owner-protocol wiring for local backup and restore."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable, Generator, Mapping
from contextlib import closing, contextmanager
from functools import partial
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Any, LiteralString, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from skm.adapters.postgres.connection import PgSettings, connect_single, dsn_password
from skm.adapters.postgres.core.schema_version import SchemaVersionReader
from skm.adapters.postgres.execution.integration_slots import PostgresIntegrationSlotRepository
from skm.adapters.postgres.jsonb import to_jsonb
from skm.adapters.postgres.migrations.runner import BASELINE_VERSION, packaged_baseline
from skm.adapters.postgres.uow import PostgresUnitOfWork
from skm.application_bus.bus import Bus
from skm.application_bus.middleware import (
    RecoveryGuard,
    RecoveryPins,
    require_restore_admission,
)
from skm.application_bus.middleware import (
    recovery_wiring as _recovery_wiring,
)
from skm.bootstrap._quarantine_rebind import (
    create_rebinds,
    current_pins,
    dispatch_allowed,
    normalize_execution,
    rebind_checkout,
)
from skm.bootstrap.composition_resources import database_dsn
from skm.bootstrap.instance_secrets import read_private
from skm.bootstrap.platform_module import local_known_version
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, SkmError
from skm.kernel.ids import HostId, PrincipalId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.public import (
    SYSTEM_ACTOR,
    CreateToken,
    CreateTokenResult,
    RbacAuthorizer,
    Role,
    revoke_principal_tokens,
    role_permissions,
)
from skm.modules.artifacts.ports import BlobStore
from skm.modules.execution.ports import IntegrationSlotRepository
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.generated.queries import VerifyStorage
from skm.platform.generated.results import VerifyStorageResult
from skm.platform.storage.backup import (
    Blob,
    ExportedSnapshot,
    Snapshot,
    baseline_document,
    create_backup,
    dependency_inventory,
    fingerprint,
    invalid,
    postgres_environment,
    run_pg_tool,
)
from skm.platform.storage.restore import (
    MARKER,
    RECEIPT,
    STAGING_RECORD,
    RestorePaths,
    VerifiedBackup,
    activate_restore,
    incomplete_staging_records,
    is_incomplete_restore,
    pin_restore_profile,
    prepare_restore_profile,
    read_staging_record,
    restore_backup,
    staging_database,
    verify_backup,
    write_staging_record,
)
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from skm.bootstrap.composition import App

__all__ = [
    "RecoveryGuard",
    "backup_activate",
    "backup_create",
    "backup_rebind",
    "backup_restore",
    "guard_for",
    "pinned_profile",
    "recovery_repositories",
    "recovery_wiring",
    "verify_recovery_actor",
]
_KNOWN_VERSION = local_known_version()
type PgRepositories = Mapping[type, Callable[[Any], object]]


def _connect(dsn: str, *, autocommit: bool = False) -> Any:
    return connect_single(PgSettings(dsn, "skm-recovery"), autocommit=autocommit)


def _pg_parameters(conn: Any, dsn: str) -> dict[str, str]:
    info = conn.info
    parameters = cast("dict[str, str]", info.get_parameters())
    parameters.update(host=info.host, port=str(info.port), dbname=info.dbname, user=info.user)
    if password := dsn_password(dsn):
        parameters["password"] = password
    return parameters


def _tool(
    program: str, args: list[str], parameters: Mapping[str, object], environ: Mapping[str, str]
) -> None:
    run_pg_tool(program, args, postgres_environment(parameters, environ))


_DEPENDENCY_SQL = """
WITH settings AS (
    SELECT e.id::text AS identity,s.workspace_id,CASE WHEN s.kind='host' THEN s.id END AS host_id,
           CASE WHEN s.kind='run' THEN s.id END AS run_id,e.key,e.value
    FROM skm_config.entries e JOIN skm_core.scopes s ON s.id=e.scope_id
    UNION ALL SELECT run_id::text,workspace_id,NULL,run_id,NULL,config_snapshot
    FROM skm_execution.execution_bundles
), writer_settings AS (
    SELECT s.identity,s.workspace_id,s.host_id,s.run_id,w.key
    FROM settings s CROSS JOIN LATERAL jsonb_each(
        CASE WHEN s.key IS NULL THEN s.value->'values' ELSE jsonb_build_object(s.key,s.value) END
    ) AS w(key,value)
    WHERE (w.key='exports.vault.path' AND jsonb_typeof(w.value)='string')
       OR (w.key='exports.vault.candidates' AND jsonb_typeof(w.value)='array' AND w.value<>'[]')
       OR (w.key='hooks.subscriptions' AND jsonb_typeof(w.value)='object' AND w.value<>'{}')
)
SELECT 'git_output' AS kind,false AS captured,o.id::text AS identity,o.workspace_id,a.host_id,o.run_id
FROM skm_execution.attempt_outputs o JOIN skm_execution.attempts a ON a.id=o.attempt_id
UNION ALL SELECT 'prepared_effect',e.receipt IS NOT NULL AND e.state IN ('succeeded','failed'),
       e.id::text,e.workspace_id,a.host_id,e.run_id
FROM skm_execution.external_effects e JOIN skm_execution.attempts a ON a.id=e.attempt_id
UNION ALL
SELECT 'writer_binding',false,id::text,workspace_id,writer_host_id,NULL FROM skm_execution.integration_slots
UNION ALL
SELECT 'writer_binding',false,id::text,workspace_id,host_id,NULL FROM skm_workspace.checkout_bindings
UNION ALL
SELECT 'writer_binding',false,run_id::text || repository_id::text,workspace_id,host_id,run_id
FROM skm_execution.run_integration_hosts
UNION ALL SELECT 'writer_binding',false,id::text,NULL,NULL,NULL
FROM skm_core.outbox WHERE destination LIKE 'hook:%' AND state <> 'delivered'
UNION ALL SELECT 'writer_binding',false,identity || ':' || key,workspace_id,host_id,run_id
FROM writer_settings
UNION ALL SELECT 'host_configuration',false,id::text,NULL,id,NULL
FROM skm_workspace.hosts WHERE state='active'
UNION ALL SELECT 'host_configuration',true,identity,workspace_id,host_id,run_id
FROM settings WHERE host_id IS NOT NULL OR run_id IS NOT NULL
UNION ALL SELECT 'host_configuration',false,host_id::text||runtime_id,NULL,host_id,NULL
FROM skm_runtimes.host_runtimes WHERE binary_locator IS NOT NULL
UNION ALL
SELECT 'runtime_session',false,s.id::text || coalesce(s.session_ref,''),s.workspace_id,a.host_id,a.run_id
FROM skm_execution.attempt_steps s JOIN skm_execution.attempts a ON a.id=s.attempt_id
WHERE s.session_ref IS NOT NULL OR s.process_identity IS NOT NULL
UNION ALL SELECT 'runtime_session',false,e.id::text,e.workspace_id,e.host_id,a.run_id
FROM skm_execution.execution_environments e JOIN skm_execution.attempts a ON a.id=e.attempt_id
WHERE e.state<>'removed'
UNION ALL SELECT 'secret_provider',false,identity || ref::text,workspace_id,host_id,run_id
FROM settings CROSS JOIN LATERAL jsonb_path_query(value, '$.** ? (@.type() == "string")') AS ref
WHERE ref::text LIKE '%secret://%'
"""


def _snapshot(conn: Any) -> tuple[Snapshot, list[str], list[str]]:
    instance = conn.execute("SELECT id FROM skm_core.scopes WHERE kind='instance'").fetchone()
    version, baseline = SchemaVersionReader(_KNOWN_VERSION).read_fingerprint(conn)
    if instance is None or version is None or baseline is None:
        raise invalid("backup_instance_unavailable")
    if version > _KNOWN_VERSION:
        raise PreconditionFailed(ErrorCode.SCHEMA_TOO_NEW, "Database schema is newer than this installation")
    if version < BASELINE_VERSION:
        raise invalid("backup_schema_baseline_incomplete")
    tables = conn.execute(
        "SELECT schemaname,tablename,format('SELECT count(*) FROM %I.%I',schemaname,tablename) "
        "FROM pg_tables WHERE schemaname LIKE 'skm\\_%' ORDER BY 1,2"
    )
    counts: dict[str, int] = {}
    for schema, table, query in tables:
        counts[f"{schema}.{table}"] = conn.execute(cast("LiteralString", query)).fetchone()[0]
    blobs: list[Blob] = []
    for ws, digest, size, key, backend, state in conn.execute(
        """SELECT b.workspace_id, b.content_digest, b.size_bytes, l.storage_key, l.backend_id, l.state
           FROM skm_artifacts.blobs b LEFT JOIN skm_artifacts.blob_locations l
           ON (b.workspace_id,b.id)=(l.workspace_id,l.blob_id) ORDER BY b.workspace_id,b.content_digest"""
    ):
        blob = Blob(str(ws), f"sha256:{digest}", size)
        if key != blob.key or backend != "local-primary" or state != "present":
            raise invalid("unsupported_or_missing_blob_location")
        blobs.append(blob)
    references = conn.execute(_DEPENDENCY_SQL).fetchall()
    dependencies, blocked = dependency_inventory(references)
    fixed = sorted(
        {
            str(run)
            for kind, captured, _, _, _, run in references
            if kind == "secret_provider" and not captured and run is not None
        }
    )
    snapshot = Snapshot(
        instance[0], version, conn.info.server_version, counts, tuple(blobs), dependencies, baseline
    )
    return snapshot, blocked, fixed


@contextmanager
def _export(dsn: str, environ: Mapping[str, str]) -> Generator[ExportedSnapshot]:
    with _connect(dsn) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        row = conn.execute("SELECT pg_export_snapshot()").fetchone()
        if row is None:
            raise invalid("snapshot_unavailable")
        yield ExportedSnapshot(
            _snapshot(conn)[0],
            lambda path: _tool(
                "pg_dump",
                [f"--snapshot={row[0]}", "--format=custom", "--schema=skm_*", "--file", str(path)],
                _pg_parameters(conn, dsn),
                environ,
            ),
        )


def _meta() -> RequestMeta:
    return RequestMeta(f"restore-{uuid4()}", Surface.CLI, None, SystemClock().now())


def _require_admin(app: App, actor: Actor) -> None:
    with app.uow_factory(_meta(), readonly=True) as uow:
        chain = (uow.repo(ScopeRegistry).instance(),)
        if not RbacAuthorizer(SystemClock()).authorize(uow, actor, "admin.storage", chain).allowed:
            raise Forbidden(ErrorCode.FORBIDDEN, "The admin.storage permission is required")


def _open(config: BootstrapConfig, env: Mapping[str, str]) -> App:
    from skm.bootstrap.composition import build_cli_app

    return build_cli_app(config, environ=env, invocation={})


def backup_create(
    config: BootstrapConfig,
    env: Mapping[str, str],
    output: Path | None,
    token: str | None,
) -> JsonObject:
    from skm.bootstrap.composition import resolve_cli_actor

    config = pinned_profile(config)
    with closing(_open(config, env)) as app:
        _require_admin(app, resolve_cli_actor(app, config, as_token=token))
    dsn = database_dsn(config, env)
    destination = output or config.backups_root / SystemClock().now().strftime("%Y%m%dT%H%M%S%fZ")
    return create_backup(destination, config.blobs_root, lambda: _export(dsn, env))


def _create_database(dsn: str, paths: RestorePaths, marker: JsonObject) -> str:
    target, maintenance = staging_database(dsn)
    with _connect(maintenance, autocommit=True) as conn:
        if conn.info.server_version < 160000:
            raise invalid("postgres_version_unsupported")
        row = conn.execute(
            "SELECT format('CREATE DATABASE %%I TEMPLATE template0', %s::text)",
            (target,),
        ).fetchone()
        try:
            conn.execute(cast("LiteralString", row[0]))
        except Exception as error:
            if getattr(error, "sqlstate", None) == "42P04":
                raise invalid("staging_database_already_exists") from None
            raise
    with _connect(dsn) as conn:
        conn.execute("""CREATE TABLE public.skm_restore_control (
            id uuid PRIMARY KEY, state_dir text NOT NULL, manifest_digest text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            blocked_runs jsonb, fixed_blocks jsonb, receipt jsonb, recovery_token_id uuid
        )""")
        conn.execute(
            "INSERT INTO public.skm_restore_control (id,state_dir,manifest_digest) VALUES (%s,%s,%s)",
            (marker["restore_id"], str(paths.state_dir), marker["manifest_digest"]),
        )
        oid = conn.execute("SELECT oid FROM pg_database WHERE datname = current_database()").fetchone()[0]
        write_staging_record(paths.state_dir, dsn, oid)
    return target


def _require_new_database(dsn: str) -> None:
    """Refuse an existing target before the restore copies the archive's blobs and dump to disk."""
    target, maintenance = staging_database(dsn)
    with _connect(maintenance, autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (target,)).fetchone():
            raise invalid("staging_database_already_exists")


@contextmanager
def _staging_lock(dsn: str) -> Generator[None]:
    """Serialize the ownership check, recovery and publication across SKM restore processes."""
    name, maintenance = staging_database(dsn)
    with _connect(maintenance, autocommit=True) as conn:
        locked = conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended('skm.restore:' || %s, 0))", (name,)
        ).fetchone()
        if not locked[0]:
            raise invalid("staging_restore_in_progress")
        yield


def _drop_incomplete_staging(state_dir: Path, dsn: str) -> bool:
    target, maintenance = staging_database(dsn)
    record = read_staging_record(state_dir)
    if (
        record is None
        or target != record.name
        or not record.matches_target(dsn)
        or not is_incomplete_restore(state_dir)
    ):
        return False
    try:
        attempt_id = UUID(state_dir.name)
    except ValueError:
        return False
    retired = f"skm_retired_{attempt_id.hex}"
    with _connect(maintenance, autocommit=True) as admin:
        # A crash between RENAME and DROP leaves a recoverable, attempt-specific name.
        names = {
            row[0]
            for row in admin.execute(
                "SELECT datname FROM pg_database WHERE datname IN (%s, %s)", (target, retired)
            )
        }
        if not names:
            return False
        current = retired if retired in names else target
        url = urlsplit(dsn)._replace(path="/" + current).geturl()
        with _connect(url) as conn:
            if not conn.execute("SELECT to_regclass('public.skm_restore_control')").fetchone()[0]:
                return False
            owned = conn.execute(
                "SELECT d.oid FROM pg_database d, public.skm_restore_control s "
                "WHERE d.datname = current_database() AND s.id::text = %s AND s.state_dir = %s "
                "AND s.receipt IS NULL",
                (state_dir.name, str(state_dir)),
            ).fetchone()
            if owned is None or owned[0] != record.oid:
                return False
        if current != retired:
            # RENAME refuses live connections. Recheck the OID under its database lock.
            with admin.transaction():
                rename = admin.execute(
                    "SELECT format('ALTER DATABASE %%I RENAME TO %%I', %s::text, %s::text)", (target, retired)
                ).fetchone()[0]
                admin.execute(cast("LiteralString", rename))
                row = admin.execute("SELECT oid FROM pg_database WHERE datname = %s", (retired,)).fetchone()
                if row is None or row[0] != owned[0]:
                    raise invalid("staging_database_identity_changed")
        drop = admin.execute("SELECT format('DROP DATABASE %%I', %s::text)", (retired,)).fetchone()[0]
        admin.execute(cast("LiteralString", drop))
    rmtree(state_dir)
    return True


def _storage_check(app: App) -> None:
    checked = cast("VerifyStorageResult", app.bus.ask(VerifyStorage(), actor=SYSTEM_ACTOR, meta=_meta()))
    if checked.counts.error:
        raise invalid("restored_storage_has_errors")


def _revoke_ephemeral_credentials(conn: Any, now: Any) -> None:
    """Revoke every active web session and pairing token in the restored database."""
    conn.execute("UPDATE skm_access.web_sessions SET revoked_at = %s WHERE revoked_at IS NULL", (now,))
    conn.execute("UPDATE skm_access.pairing_tokens SET revoked_at = %s WHERE revoked_at IS NULL", (now,))


def verify_recovery_actor(
    actor: Actor,
    expected_token_id: UUID | None,
    active_tokens: list[tuple[UUID, str]],
    restore_id: UUID,
) -> None:
    """Only the exact personal recovery token_id issued by ``_rotate`` may activate a restore.

    Password login, web session cookies, ``local_owner`` (``grant is None``), or any other token
    belonging to the same person must never substitute for the issued recovery token.
    """
    if (
        expected_token_id is None
        or actor.grant is None
        or actor.grant.kind != "personal"
        or actor.grant.token_id != expected_token_id
        or active_tokens != [(expected_token_id, f"restore-{restore_id}")]
    ):
        raise invalid("restore_recovery_token_required")


def _rotate(app: App, paths: RestorePaths, marker: JsonObject) -> UUID:
    with app.uow_factory(_meta(), readonly=False) as uow:
        conn = cast("PostgresUnitOfWork", uow).connection
        for (principal,) in conn.execute(
            "SELECT DISTINCT principal_id FROM skm_access.api_tokens ORDER BY 1"
        ):
            revoke_principal_tokens(
                uow, PrincipalId(principal), by=SYSTEM_PRINCIPAL_ID, now=SystemClock().now(), disable=False
            )
        owner = conn.execute(
            """SELECT p.id FROM skm_access.principals p JOIN skm_access.memberships m ON m.principal_id=p.id
               JOIN skm_core.scopes s ON s.id=m.scope_id WHERE s.kind='instance' AND m.role='owner'
               AND p.kind='human' AND p.state='active' ORDER BY p.id LIMIT 1"""
        ).fetchone()
        if owner is None:
            raise invalid("restore_owner_unavailable")
        instance_id = uow.repo(ScopeRegistry).instance().id
        _revoke_ephemeral_credentials(conn, SystemClock().now())
        uow.commit()
    dto = CreateToken(
        name=f"restore-{marker['restore_id']}",
        principal_id=owner[0],
        scope_id=instance_id,
        permissions=tuple(sorted(role_permissions(Role.OWNER))),
    )
    result = cast("CreateTokenResult", Bus.dispatch(app.bus, dto, actor=SYSTEM_ACTOR, meta=_meta()))
    with app.uow_factory(_meta(), readonly=False) as uow:
        conn = cast("PostgresUnitOfWork", uow).connection
        conn.execute(
            "UPDATE public.skm_restore_control SET recovery_token_id = %s WHERE id = %s",
            (result.token_id, marker["restore_id"]),
        )
        _revoke_ephemeral_credentials(conn, SystemClock().now())
        uow.commit()
    atomic_write(
        paths.state_dir / "secrets/owner.token", (result.secret + "\n").encode(), mode=0o600, private=True
    )
    return result.token_id


def _require_history_acl(conn: Any) -> None:
    with conn.transaction():
        conn.execute("SET LOCAL ROLE skm_app")
        rows = conn.execute("""
            SELECT has_schema_privilege('skm_core', 'USAGE'),
                   has_table_privilege(name, 'SELECT'),
                   has_table_privilege(name, 'DELETE, TRUNCATE, TRIGGER, SELECT WITH GRANT OPTION'),
                   has_any_column_privilege(name, 'INSERT, UPDATE, REFERENCES')
            FROM (VALUES ('skm_core.schema_migrations'), ('skm_core.schema_baseline')) AS history(name)
        """).fetchall()
        conn.execute("RESET ROLE")
        if rows != [(True, True, False, False)] * 2:
            raise invalid("restored_history_acl_mismatch")


def _stage(
    archive: VerifiedBackup,
    paths: RestorePaths,
    marker: JsonObject,
    dump: Path,
    dsn: str,
    env: Mapping[str, str],
) -> None:
    try:
        _stage_into_database(archive, paths, marker, dump, dsn, env)
        (paths.state_dir / STAGING_RECORD).unlink()
    except KeyboardInterrupt:
        _drop_incomplete_staging(paths.state_dir, dsn)
        raise


def _stage_into_database(
    archive: VerifiedBackup,
    paths: RestorePaths,
    marker: JsonObject,
    dump: Path,
    dsn: str,
    env: Mapping[str, str],
) -> None:
    # Deliver a normal termination only once the new catalog has committed its ownership proof.
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        target = _create_database(dsn, paths, marker)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    with _connect(dsn) as conn:
        parameters = _pg_parameters(conn, dsn)
    flags = ["--single-transaction", "--exit-on-error", "--no-owner", "--no-privileges"]
    _tool("pg_restore", [f"--dbname={target}", *flags, str(dump)], parameters, env)
    with _connect(dsn) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        snapshot, blocked, fixed = _snapshot(conn)
        archive.require_snapshot(snapshot)
        # The archive carries no authority to grant privileges on the restored database.
        conn.execute("GRANT USAGE ON SCHEMA skm_core TO skm_app")
        conn.execute("GRANT SELECT ON skm_core.schema_migrations, skm_core.schema_baseline TO skm_app")
        _require_history_acl(conn)
        create_rebinds(conn)
        conn.execute(
            "UPDATE public.skm_restore_control SET blocked_runs=%s, fixed_blocks=%s",
            (to_jsonb(blocked), to_jsonb(fixed)),
        )
        # Keep history, but remove active production delivery and plugin settings from the staged copy.
        conn.execute(
            "DELETE FROM skm_config.entries WHERE split_part(key,'.',1) "
            "IN ('exports','hooks','integrations','runtimes','plugins')"
        )
        _revoke_ephemeral_credentials(conn, SystemClock().now())
    config, profile = prepare_restore_profile(paths, archive, dsn)
    with closing(_open(config, {})) as app:
        _storage_check(app)
        _rotate(app, paths, marker)
    atomic_write(paths.profile, profile, mode=0o600, private=True)


def backup_restore(
    config: BootstrapConfig,
    directory: Path,
    target: str,
    parent: Path,
    env: Mapping[str, str],
    *,
    yes: bool,
    token: str | None,
) -> JsonObject:
    from skm.bootstrap.composition import resolve_cli_actor

    if not yes:
        raise invalid("staging_restore_confirmation_required")
    config = pinned_profile(config)
    with closing(_open(config, env)) as app:
        actor = resolve_cli_actor(app, config, as_token=token)
        _require_admin(app, actor)
        archive = verify_backup(directory, _KNOWN_VERSION, expected_baseline=packaged_baseline(), environ=env)
        if cast("int", archive.manifest["schema_version"]) < BASELINE_VERSION:
            raise invalid("backup_schema_baseline_incomplete")
        if str(app.instance_id) != archive.manifest["instance_id"]:
            raise Forbidden(ErrorCode.FORBIDDEN, "Restore requires admin.storage on the archived instance")
    try:
        name, _maintenance = staging_database(target)
        with _staging_lock(target):
            for state_dir, record in incomplete_staging_records(parent.resolve()):
                if record.name == name and _drop_incomplete_staging(state_dir, target):
                    break
            _require_new_database(target)
            return restore_backup(archive, parent, lambda a, p, m, d: _stage(a, p, m, d, target, env))
    except Exception as error:
        if hasattr(error, "sqlstate"):
            raise invalid("staging_database_failed") from None
        raise


def pinned_profile(config: BootstrapConfig) -> BootstrapConfig:
    return pin_restore_profile(config, lambda path: read_private(path, 65536).decode())


def guard_for(config: BootstrapConfig, dsn: str, surface: Surface) -> RecoveryGuard | None:
    with _connect(dsn) as conn:
        exists = conn.execute("SELECT to_regclass(%s)", ("public.skm_restore_control",)).fetchone()
        if exists is None or exists[0] is None:
            require_restore_admission(
                not any(os.path.lexists(config.state_dir / name) for name in (MARKER, RECEIPT)),
                "bootstrap.restore_database",
            )
            return None
        row = conn.execute("SELECT id,state_dir,manifest_digest FROM public.skm_restore_control").fetchone()
    if (
        row is None
        or Path(row[1]) != config.state_dir.resolve()
        or (config.blobs_root.resolve() != config.state_dir / "blobs")
    ):
        raise invalid("restore_profile_binding_mismatch")

    def committed() -> JsonObject | None:
        with _connect(dsn) as conn:
            found = conn.execute("SELECT receipt FROM public.skm_restore_control").fetchone()
            return None if found is None else cast("JsonObject | None", found[0])

    def allowed(name: str, identity: str) -> bool:
        with _connect(dsn) as conn:
            return dispatch_allowed(conn, name, identity)

    def recovery_token_id() -> UUID | None:
        with _connect(dsn) as conn:
            found = conn.execute("SELECT recovery_token_id FROM public.skm_restore_control").fetchone()
            return None if found is None else cast("UUID | None", found[0])

    guard = RecoveryGuard(
        config.state_dir,
        row[0],
        row[2],
        committed,
        allowed,
        recovery_token_id=recovery_token_id,
    )
    if surface in {Surface.WORKER, Surface.HOOK}:
        guard.host(None, surface)
    return guard


recovery_wiring = partial(_recovery_wiring, blob_type=BlobStore)


def recovery_repositories(guard: RecoveryGuard | None, extra: PgRepositories) -> PgRepositories:
    if guard is None:
        return extra
    return {
        **extra,
        IntegrationSlotRepository: lambda conn: RecoveryPins(
            PostgresIntegrationSlotRepository(conn), guard, lambda: current_pins(conn)
        ),
    }


def _activate(
    app: App,
    actor: Actor,
    archive: VerifiedBackup,
    marker: JsonObject,
    state: Path,
) -> JsonObject:
    _storage_check(app)
    if any(
        fingerprint(state / "blobs", blob.key) != (blob.digest, blob.size_bytes) for blob in archive.blobs
    ):
        raise invalid("restored_blob_closure_mismatch")
    with app.uow_factory(_meta(), readonly=False) as uow:
        conn = cast("PostgresUnitOfWork", uow).connection
        row = conn.execute(
            "SELECT id,manifest_digest,blocked_runs,receipt,recovery_token_id "
            "FROM public.skm_restore_control FOR UPDATE"
        ).fetchone()
        if row is None or str(row[0]) != marker["restore_id"] or row[1] != archive.manifest_digest:
            raise invalid("restore_profile_binding_mismatch")
        tokens = conn.execute(
            """SELECT id,name FROM skm_access.api_tokens
               WHERE revoked_at IS NULL AND superseded_by IS NULL
               AND (expires_at IS NULL OR expires_at>now()) FOR UPDATE"""
        ).fetchall()
        verify_recovery_actor(actor, cast("UUID | None", row[4]), tokens, cast("UUID", row[0]))
        _revoke_ephemeral_credentials(conn, SystemClock().now())
        if row[3] is not None:
            uow.commit()
            return cast("JsonObject", row[3])
        version, baseline = SchemaVersionReader(_KNOWN_VERSION).read_fingerprint(conn)
        if (
            version != archive.manifest["schema_version"]
            or baseline is None
            or baseline_document(baseline) != archive.manifest.get("schema_baseline")
        ):
            raise invalid("restored_snapshot_baseline_mismatch")
        _require_history_acl(conn)
        normalize_execution(uow, app)
        bindings = current_pins(conn)
        rebound: JsonObject = {str(pin.effect_id): str(pin.host_id) for pin in bindings}
        pins: JsonObject = {f"{pin.run_id}:{pin.repository_id}": str(pin.host_id) for pin in bindings}
        projects = conn.execute(
            "SELECT DISTINCT project_id::text FROM skm_execution.runs WHERE id=ANY(%s::uuid[]) ORDER BY 1",
            (row[2],),
        ).fetchall()
        receipt: JsonObject = {
            "restore_id": str(row[0]),
            "backup_id": archive.manifest["backup_id"],
            "manifest_digest": row[1],
            "binding_identity": str(uuid4()),
            "state": "activated",
            "blocked_runs": row[2],
            "blocked_projects": cast("list[JsonValue]", [p[0] for p in projects]),
            "rebound_effects": rebound,
            "rebound_pins": pins,
            "external_delivery": "requires_rebind",
        }
        conn.execute("UPDATE public.skm_restore_control SET receipt=%s", (to_jsonb(receipt),))
        uow.commit()
        return receipt


def backup_activate(config: BootstrapConfig, env: Mapping[str, str], *, yes: bool) -> JsonObject:
    if not yes:
        raise invalid("restore_activation_confirmation_required")
    config = pinned_profile(config)
    state = config.state_dir
    with closing(_open(config, env)) as app:
        try:
            actor = app.authenticate(read_private(state / "secrets/owner.token", 4096).decode().strip())
        except (SkmError, UnicodeError):
            raise invalid("restore_recovery_token_required") from None
        _require_admin(app, actor)
        guard = getattr(app.bus, "guard", None)
        if not isinstance(guard, RecoveryGuard):
            raise invalid("restore_marker_missing")
        return activate_restore(
            state,
            _KNOWN_VERSION,
            confirmed=yes,
            activated_receipt=guard.receipt,
            activate=lambda archive, marker: _activate(app, actor, archive, marker, state),
            environ=env,
        )


def backup_rebind(
    config: BootstrapConfig, env: Mapping[str, str], effect: UUID, checkout: Path, token: str | None
) -> JsonObject:
    from skm.bootstrap.composition import resolve_cli_actor
    from skm.platform.config.bootstrap import validate_worker_host

    config = pinned_profile(config)
    with closing(_open(config, env)) as app:
        guard = getattr(app.bus, "guard", None)
        if not isinstance(guard, RecoveryGuard):
            raise invalid("restore_marker_missing")
        actor = resolve_cli_actor(app, config, as_token=token)
        _require_admin(app, actor)
        host = validate_worker_host(config).host_id
        return rebind_checkout(app, actor, _meta(), cast("HostId", host), effect, checkout)
