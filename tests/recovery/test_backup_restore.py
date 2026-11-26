"""Real PostgreSQL rehearsal for the SKM archive and staging profile."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from contextlib import ExitStack, closing
from pathlib import Path
from stat import S_IMODE
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from contracts.execution.seed_helpers import seed_run
from fixtures.execution.harness import RecoverySide, clean_test_database, pg_session, recovery, test_database
from integration.artifacts.test_upload_flow import add_file_dto, dispatch_new
from recovery._backup_helpers import (
    assert_normalized_database,
    assert_pinned_entrypoints,
    assert_quarantined_http,
    assert_schema_compatibility,
    checkout_for_recovery,
    cli,
    database_pair,
    git,
    git_snapshot,
    source,
    source_authority,
    workflow_cursor,
    write_journal,
)
from skm.adapters.postgres.migrations.runner import packaged_baseline
from skm.application_bus.host import HostServices
from skm.bootstrap import _quarantine
from skm.bootstrap.composition import KNOWN_SCHEMA_VERSION, build_app
from skm.bootstrap.lifecycle import add_background_services
from skm.entrypoints.cli.errors import EXIT_TERMINATED, Terminated
from skm.entrypoints.cli.main import main
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, ProjectId, WorkspaceId
from skm.kernel.module_manifest import HostOperationSpec
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import (
    SYSTEM_ACTOR,
    CreatePrincipal,
    CreatePrincipalResult,
    CreateToken,
    CreateTokenResult,
    WhoAmI,
    WhoAmIView,
)
from skm.modules.execution.application._worker_dtos import digest
from skm.modules.execution.application.commands.reconcile_external_effect import (
    ReconcileExternalEffect,
    ReconcileExternalEffectResult,
)
from skm.modules.execution.application.commands.schedule_ready_tasks import ScheduleReadyTasks
from skm.modules.execution.application.commands.start_autopilot import StartAutopilot, StartAutopilotResult
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.generated.commands import ResumeRun
from skm.modules.execution.public import ResumeRunResult
from skm.modules.workspace.public import (
    CreateProject,
    CreateWorkspace,
    WorkspaceView,
)
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.storage import restore
from skm.platform.storage.backup import (
    CLOSURE,
    INVENTORY,
    MANIFEST,
    baseline_document,
    bytes_digest,
    create_backup,
    json_bytes,
)
from skm.platform.storage.restore import MARKER, RECEIPT, verify_backup
from unit.execution.application._integration_case import integrated_case, local_request, record
from unit.execution.application._support import set_setting

__all__ = ["clean_test_database", "database_pair", "pg_session", "recovery", "test_database"]

pytestmark = [pytest.mark.pg, pytest.mark.integration]


def test_staging_credentials_and_quarantine(  # noqa: PLR0915
    tmp_path: Path,
    database_pair: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, target = database_pair
    env, state, _ = source(tmp_path, live)
    secret = (state / "secrets/owner.token").read_text().strip()
    config = load_bootstrap(None, env, tmp_path)
    with closing(build_app(config, surface=Surface.CLI, environ=env, invocation={})) as original:
        old_actor = original.authenticate(secret)
        owner = original.client(actor=old_actor, surface=Surface.CLI)
        reader = cast(
            "CreatePrincipalResult",
            owner.dispatch(CreatePrincipal.from_json({"kind": "human", "display_name": "Archive reader"})),
        )
        reader_token = cast(
            "CreateTokenResult", owner.dispatch(CreateToken("reader", principal_id=reader.principal_id))
        ).secret
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))
    manifest = json.loads((archive / MANIFEST).read_bytes())
    assert manifest["schema_baseline"] == baseline_document(packaged_baseline())
    assert_schema_compatibility(archive)
    assert cli({}, "backup", "verify", str(archive))["state"] == "verified"
    denied = cli(
        env,
        "--as-token",
        reader_token,
        "backup",
        "restore",
        str(archive),
        "--target-database-url",
        target,
        "--yes",
        status=5,
    )
    assert denied["code"] == "FORBIDDEN"
    with psycopg.connect(live) as conn:
        assert not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (conninfo_to_dict(target)["dbname"],)
        ).fetchone()
    assert not (tmp_path / "state/skm/restores").exists()
    cli(env, "backup", "restore", str(archive), "--target-database-url", live, "--yes", status=6)
    staged = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes")
    profile = Path(staged["profile"])
    new_state = profile.parent
    assert (new_state / MARKER).is_file()
    new_secret = (new_state / "secrets/owner.token").read_text().strip()
    assert new_secret != secret
    assert (new_state / "secrets/token-pepper").read_bytes() != (state / "secrets/token-pepper").read_bytes()
    assert S_IMODE((new_state / "secrets").stat().st_mode) == 0o700
    assert S_IMODE((new_state / "secrets/owner.token").stat().st_mode) == 0o600
    assert S_IMODE((new_state / "secrets/token-pepper").stat().st_mode) == 0o600
    assert_pinned_entrypoints(env, profile, target, monkeypatch)

    # Even an inherited live DSN is superseded by the staged profile's private binding.
    staged_env = {**env, "SKM_BOOTSTRAP": str(profile)}
    staged_config = load_bootstrap(None, staged_env, tmp_path)
    with ExitStack() as stack:
        app = stack.enter_context(
            closing(build_app(staged_config, surface=Surface.CLI, environ=staged_env, invocation={}))
        )
        actor = app.authenticate(new_secret)
        client = app.client(actor=actor, surface=Surface.CLI)
        assert cast("WhoAmIView", client.ask(WhoAmI())).principal.principal_id == actor.principal_id
        with pytest.raises(SkmError) as revoked:
            app.client(actor=old_actor, surface=Surface.CLI).ask(WhoAmI())
        assert revoked.value.code is ErrorCode.UNAUTHENTICATED
        with pytest.raises(SkmError):
            app.authenticate(secret)
        with pytest.raises(SkmError, match="restore recovery"):
            app.client(actor=SYSTEM_ACTOR, surface=Surface.BACKGROUND).dispatch(
                ScheduleReadyTasks.from_json({})
            )
        with pytest.raises(SkmError, match="restore recovery"):
            build_app(staged_config, surface=Surface.WORKER, environ=staged_env, invocation={})
        with pytest.raises(SkmError, match="restore recovery"):
            build_app(staged_config, surface=Surface.HOOK, environ=staged_env, invocation={})
        observed = []
        op = HostOperationSpec(
            "test.host.write",
            lambda *_: observed.append("write"),
            dict,
            dict,
            frozenset({Surface.CLI}),
        )
        host = HostServices(
            HostId(uuid4()),
            Surface.CLI,
            GatewayTable({}, "host_gateway"),
            dict,
            {op.name: op},
        )
        with pytest.raises(SkmError, match="restore recovery"):
            host.run(op.name, {}, client=client, cancel=CancelSource().token)
        assert observed == []
        cli(staged_env, "backup", "activate", status=6)
        with psycopg.connect(target, autocommit=True) as conn:
            conn.execute("GRANT UPDATE ON skm_core.schema_baseline TO skm_app")
            rejected = cli(staged_env, "backup", "activate", "--yes", status=6)
            assert rejected["details"]["reason"] == "restored_history_acl_mismatch"
            assert (new_state / MARKER).is_file()
            assert not (new_state / RECEIPT).exists()
            conn.execute("REVOKE UPDATE ON skm_core.schema_baseline FROM skm_app")
        activated = cli(staged_env, "backup", "activate", "--yes")
        assert activated["state"] == "activated"
        assert not (new_state / MARKER).exists()
        assert (new_state / RECEIPT).is_file()
        assert (
            cli(staged_env, "backup", "activate", "--yes")["binding_identity"]
            == activated["binding_identity"]
        )
        with pytest.raises(SkmError):
            app.client(actor=old_actor, surface=Surface.CLI).ask(WhoAmI())
    with psycopg.connect(live) as conn:
        assert conn.execute(
            "SELECT count(*) FROM skm_access.api_tokens WHERE revoked_at IS NULL"
        ).fetchone() == (2,)


def test_unrecognized_backup_baseline_cannot_create_a_staging_database(
    tmp_path: Path, database_pair: tuple[str, str]
) -> None:
    live, target = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))
    manifest_file = archive / MANIFEST
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["schema_baseline"] == baseline_document(packaged_baseline())
    manifest["schema_baseline"]["epoch"] = "unknown-project-baseline"
    manifest_file.write_bytes(json_bytes(manifest))
    problem = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    assert problem["details"]["reason"] == "backup_schema_baseline_mismatch"
    with psycopg.connect(live) as conn:
        assert not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (conninfo_to_dict(target)["dbname"],)
        ).fetchone()


def test_restore_recomputes_the_staged_history(
    tmp_path: Path, database_pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live, target = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))
    tool = _quarantine._tool

    def corrupt(
        program: str, args: list[str], parameters: Mapping[str, object], environ: Mapping[str, str]
    ) -> None:
        tool(program, args, parameters, environ)
        if program == "pg_restore":
            with psycopg.connect(target) as conn:
                conn.execute("UPDATE skm_core.schema_migrations SET name = 'corrupted' WHERE version = 1")

    monkeypatch.setattr(_quarantine, "_tool", corrupt)
    rejected = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    assert rejected["code"] == "MIGRATION_CHECKSUM_MISMATCH"
    assert rejected["details"]["reason"] == "schema_baseline_mismatch"


def test_corrupt_inventory_and_newer_schema(tmp_path: Path, database_pair: tuple[str, str]) -> None:
    live, target = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))
    complete = (archive / MANIFEST).read_bytes()
    incoming = json.loads(complete)
    incoming["schema_version"] = KNOWN_SCHEMA_VERSION + 1
    (archive / MANIFEST).write_text(json.dumps(incoming))
    with pytest.raises(SkmError) as newer:
        verify_backup(archive, KNOWN_SCHEMA_VERSION, environ=os.environ)
    assert newer.value.code is ErrorCode.SCHEMA_TOO_NEW
    cli({}, "backup", "verify", str(archive), status=6)
    incoming = json.loads(complete)
    incoming["schema_baseline"]["chain_sha256"] = "0" * 64
    (archive / MANIFEST).write_bytes(json_bytes(incoming))
    tampered = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    assert tampered["details"]["reason"] == "backup_schema_baseline_mismatch"
    (archive / MANIFEST).write_bytes(complete)
    (archive / "blobs.jsonl").write_bytes(b"{}\n")
    cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    with psycopg.connect(live) as conn:
        assert not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (conninfo_to_dict(target)["dbname"],)
        ).fetchone()


def test_lost_token_commit_remains_quarantined(
    tmp_path: Path, database_pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live, target = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))

    def lose_owner_file(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == "owner.token":
            raise OSError("simulated crash after token commit")
        original(path, *args, **kwargs)

    original = _quarantine.atomic_write
    monkeypatch.setattr(_quarantine, "atomic_write", lose_owner_file)
    cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    (staging,) = (tmp_path / "state/skm/restores").iterdir()
    assert (staging / MARKER).is_file()
    assert not (staging / "bootstrap.toml").exists()
    assert not (staging / "secrets/owner.token").exists()
    with psycopg.connect(target) as conn:
        assert conn.execute(
            "SELECT count(*) FROM skm_access.api_tokens WHERE revoked_at IS NULL"
        ).fetchone() == (1,)


def test_existing_target_is_refused_before_the_archive_is_copied(
    tmp_path: Path, database_pair: tuple[str, str]
) -> None:
    live, _ = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))
    error = cli(env, "backup", "restore", str(archive), "--target-database-url", live, "--yes", status=6)
    assert error["details"]["reason"] == "staging_database_already_exists"
    restores = tmp_path / "state/skm/restores"
    assert not restores.exists() or list(restores.iterdir()) == []


def test_exported_snapshot_freezes_blob_and_database_closure(
    tmp_path: Path, database_pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live, target = database_pair
    env, state, blob_root = source(tmp_path, live)
    config = load_bootstrap(None, env, tmp_path)
    owner_token = (state / "secrets/owner.token").read_text().strip()
    archive = tmp_path / "archive"
    with closing(build_app(config, surface=Surface.CLI, environ=env, invocation={})) as app:
        actor = app.authenticate(owner_token)
        client = app.client(actor=actor, surface=Surface.CLI)
        workspace = WorkspaceId(
            cast(
                "WorkspaceView",
                client.dispatch(
                    CreateWorkspace(slug="backup-test", title="Backup test"),
                    idempotency_key="archive-workspace",
                ),
            ).workspace_id
        )
        project = ProjectId(dispatch_new(client, CreateProject(workspace, "archive", "Archive")).project_id)

        def add(content: bytes) -> str:
            blob = client.upload_blob(workspace, (content,), size=len(content), media_type="text/markdown")
            dispatch_new(client, add_file_dto(workspace, project, blob))
            return blob.digest

        first = add(b"pinned by the exported view\n")
        client.upload_blob(workspace, (b"staging",), size=7)
        (state / "secrets/production-sentinel").write_text("sentinel-not-in-archive")
        original = _quarantine._tool

        def concurrent(
            program: str, args: list[str], parameters: Mapping[str, object], environ: Mapping[str, str]
        ) -> None:
            if program == "pg_dump":
                add(b"committed after the snapshot\n")
            original(program, args, parameters, environ)

        with monkeypatch.context() as patch:
            patch.setattr(_quarantine, "_tool", concurrent)
            cli(env, "backup", "create", "--output", str(archive))
        checked = verify_backup(archive, KNOWN_SCHEMA_VERSION, environ=os.environ)
        assert [b.digest for b in checked.blobs] == [first]
        assert not (archive / "blobs/staging").exists()
        assert not any(
            b"sentinel-not-in-archive" in f.read_bytes() for f in archive.rglob("*") if f.is_file()
        )
        cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes")
        with psycopg.connect(target) as conn:
            assert conn.execute("SELECT count(*) FROM skm_artifacts.files").fetchone() == (1,)
            assert conn.execute("SELECT count(*) FROM skm_artifacts.blob_locations").fetchone() == (1,)

    manifest, inventory, closure = (archive / name for name in (MANIFEST, INVENTORY, CLOSURE))
    originals = {path: path.read_bytes() for path in (manifest, inventory, closure)}
    rebuilt_closure = json.loads(originals[closure])
    rebuilt_closure["inventory_digest"] = bytes_digest(b"")
    closure.write_bytes(json_bytes(rebuilt_closure))
    inventory.write_bytes(
        json_bytes({"inventory_size_bytes": 0, "closure_digest": bytes_digest(closure.read_bytes())})
    )
    rebuilt_manifest = json.loads(originals[manifest])
    rebuilt_manifest["blobs"].update(
        count=0, total_bytes=0, inventory_digest=bytes_digest(inventory.read_bytes())
    )
    manifest.write_bytes(json_bytes(rebuilt_manifest))
    assert (
        cli({}, "backup", "verify", str(archive), status=6)["details"]["reason"]
        == "dump_blob_closure_mismatch"
    )
    for path, data in originals.items():
        path.write_bytes(data)

    blob = checked.blobs[0]
    bad_bytes = archive / blob.path
    bad_bytes.unlink()
    bad_bytes.write_bytes(b"z" * blob.size_bytes)
    cli({}, "backup", "verify", str(archive), status=6)
    (blob_root / blob.key).unlink()
    incomplete = tmp_path / "incomplete"
    cli(env, "backup", "create", "--output", str(incomplete), status=6)
    assert not (incomplete / MANIFEST).exists()


def test_activation_normalizes_restored_history_and_allows_only_rebound_observation(  # noqa: PLR0915
    recovery: RecoverySide, database_pair: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    side, target = recovery, database_pair[1]
    locator = tmp_path / "rebound-checkout"
    before = checkout_for_recovery(locator, monkeypatch)
    claimed, ready, output, _ = integrated_case(side)
    target_input, _, request, envelope = local_request(side, claimed, ready)
    request["before_sha"] = before
    envelope["request_digest"] = digest(
        {"effect_id": envelope["effect_id"], "kind": envelope["kind"], "request": request}
    )
    branch = target_input["target_branch"]
    record(side, claimed, envelope, "intended", request=request)
    effect_id = envelope["effect_id"]
    record(side, claimed, envelope, "executing")
    with side.uow() as uow:
        for state in (
            RunStatus.CREATED,
            RunStatus.READY,
            RunStatus.WAITING,
            RunStatus.PAUSED,
            RunStatus.SUCCEEDED,
        ):
            seed_run(side, uow, status=state)
        uow.commit()

    assert side.dsn is not None
    with psycopg.connect(side.dsn) as conn:
        conn.execute(
            """INSERT INTO skm_execution.autopilot_states
                 (project_id,workspace_id,state,session_started_at,updated_by,updated_at)
               VALUES (%s,%s,'running',now(),%s,now())""",
            (side.proj, side.ws, side.owner.principal_id),
        )
        conn.execute(
            """UPDATE skm_execution.runs SET pause_source='system',stop_code='ITEM_BLOCKED'
               WHERE status='paused'"""
        )
        conn.execute(
            """INSERT INTO skm_core.outbox (id,event_id,destination,available_at)
               SELECT %s,id,'hook:sentinel',now() FROM skm_core.domain_events LIMIT 1""",
            (uuid4(),),
        )
    set_setting(side, "execution.autopilot.allowed", True)
    set_setting(side, "execution.autopilot.enabled", True)
    vault = "/production-vault-sentinel"
    set_setting(side, "exports.vault.path", vault)
    with psycopg.connect(side.dsn) as conn:
        row = conn.execute("SELECT id FROM skm_config.entries WHERE key='exports.vault.path'").fetchone()
        assert row is not None
        identity = f"writer_binding:{bytes_digest(f'{row[0]}:exports.vault.path'.encode())}"
    env = source_authority(side, tmp_path)
    archive = tmp_path / "archive"
    create_backup(archive, side.boot.blobs_root, lambda: _quarantine._export(str(side.dsn), env))
    checked = verify_backup(archive, KNOWN_SCHEMA_VERSION, environ=os.environ)
    assert {"git_output", "prepared_effect", "writer_binding", "host_configuration", "runtime_session"} <= {
        str(dep["kind"]) for dep in checked.dependencies if dep["state"] == "requires_rebind"
    }
    assert any(
        dep["kind"] == "host_configuration" and dep.get("captured_in") == "database"
        for dep in checked.dependencies
    )
    assert any(
        dep["identity"] == identity and dep["state"] == "requires_rebind" for dep in checked.dependencies
    )
    assert vault.encode() not in (archive / MANIFEST).read_bytes()
    assert b"/owned/" not in (archive / MANIFEST).read_bytes()
    report = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes")
    profile = Path(report["profile"])
    env["SKM_BOOTSTRAP"] = str(profile)
    config = load_bootstrap(None, env, tmp_path)
    recover_secret = (profile.parent / "secrets/owner.token").read_text().strip()
    with closing(build_app(config, surface=Surface.CLI, environ=env, invocation={})) as app:
        owner = app.authenticate(recover_secret)
        client = app.client(actor=owner, surface=Surface.CLI)
        for worker in add_background_services(app).services:
            if worker.name == "scheduler":
                with pytest.raises(SkmError, match="restore recovery"):
                    worker.tick()
        assert_quarantined_http(app, recover_secret, side)
        host = cli(env, "host", "register", "rebound")["host_id"]
        command = ("backup", "rebind", effect_id, "--checkout", str(locator))
        observed = git_snapshot(locator)
        assert cli(env, *command, status=6)["details"]["reason"] == "restore_rebind_repository_mismatch"
        assert git_snapshot(locator) == observed
        git(locator, "remote", "set-url", "origin", "https://example.invalid/m3.git")
        assert cli(env, *command, status=6)["details"]["reason"] == "restore_rebind_branch_missing"
        git(locator, "branch", branch, before)
        write_journal(locator, branch, effect_id, request, envelope["request_digest"])
        observed = git_snapshot(locator)
        replace = restore.os.replace

        def stop_after_commit(source: Path, target: Path) -> None:
            if source.name == MARKER and target.name == RECEIPT:
                raise OSError("simulated crash after the database activation commit")
            replace(source, target)

        with monkeypatch.context() as patch:
            patch.setattr(restore.os, "replace", stop_after_commit)
            cli(env, "backup", "activate", "--yes", status=6)
        assert (profile.parent / MARKER).is_file()
        assert not (profile.parent / RECEIPT).exists()
        with pytest.raises(SkmError, match="restore recovery"):
            client.dispatch(ReconcileExternalEffect(effect_id=effect_id))
        activated = cli(env, "backup", "activate", "--yes")
        assert activated["rebound_effects"] == {}
        with pytest.raises(SkmError, match="restore recovery"):
            client.dispatch(ReconcileExternalEffect(effect_id=effect_id))
        assert cli(env, *command)["state"] == "verified"
        assert git_snapshot(locator) == observed
        assert cli(env, "backup", "activate", "--yes") == activated
        start = StartAutopilot.from_json({"project_id": str(side.proj), "reason": "owner recovery"})
        with pytest.raises(SkmError, match="restore recovery"):
            client.dispatch(ResumeRun(output.run_id))
        with pytest.raises(SkmError, match="restore recovery"):
            client.dispatch(start)
        worker = cli(
            env,
            "--scope",
            f"ws:{side.ws}",
            "worker",
            "register",
            "--host",
            host,
            "--name",
            "rebound-observer",
            "--runtime",
            "codex_cli",
            "--isolation",
            "landlock",
            "--skm-version",
            "2.0.0",
        )["worker_id"]
        worker_start = ("-vv", "--scope", f"ws:{side.ws}", "worker", "start", "--worker", worker, "--once")
        assert cli(env, *worker_start, status=4)["code"] == "NOTHING_TO_CLAIM"
        issued = cast(
            "ReconcileExternalEffectResult", client.dispatch(ReconcileExternalEffect(effect_id=effect_id))
        )
        assert issued["assignment_id"]
        frozen_cursor = workflow_cursor(target, output.run_id)
        cli(env, *worker_start)
        assert workflow_cursor(target, output.run_id) == frozen_cursor
        assert git_snapshot(locator) == observed
        assert_normalized_database(target, effect_id)
        assert cast("ResumeRunResult", client.dispatch(ResumeRun(output.run_id))).status == "running"
        assert cast("StartAutopilotResult", client.dispatch(start))["state"] == "running"


def _catalog_exists(url: str) -> bool:
    target, maintenance = restore.staging_database(url)
    with psycopg.connect(maintenance, autocommit=True) as conn:
        return (
            conn.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (target,)).fetchone()
            is not None
        )


def test_a_killed_restore_drops_the_staging_database_it_created(
    tmp_path: Path, database_pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live, target = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))
    created = _quarantine._create_database

    def create_then_interrupt(dsn: str, paths: restore.RestorePaths, marker: dict[str, Any]) -> str:
        created(dsn, paths, marker)
        raise Terminated  # what SIGTERM becomes after S9

    monkeypatch.setattr(_quarantine, "_create_database", create_then_interrupt)
    parent = tmp_path / "state/skm/restores"
    # Go through main() so PATH is kept (direct backup_restore would hide pg_restore from the operator path).
    code = main(
        ["backup", "restore", str(archive), "--target-database-url", target, "--yes", "--json"],
        environ=env,
    )
    assert code == EXIT_TERMINATED == 143
    # Before: the catalog remained and the next restore failed with staging_database_already_exists.
    assert not _catalog_exists(target)
    assert not parent.exists() or list(parent.iterdir()) == []


def test_the_next_restore_drops_a_leftover_staging_database(
    tmp_path: Path, database_pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live, target = database_pair
    env, _, _ = source(tmp_path, live)
    archive = tmp_path / "archive"
    cli(env, "backup", "create", "--output", str(archive))

    def lose_owner_file(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == "owner.token":
            raise OSError("simulated crash after token commit")
        original(path, *args, **kwargs)

    original = _quarantine.atomic_write
    monkeypatch.setattr(_quarantine, "atomic_write", lose_owner_file)
    cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    assert _catalog_exists(target)  # a non-signal failure still leaves the catalog
    monkeypatch.setattr(_quarantine, "atomic_write", original)
    (journal,) = tmp_path.rglob(restore.STAGING_RECORD)
    original_record = journal.read_bytes()
    replaced = json.loads(original_record)
    replaced["oid"] += 1
    journal.write_text(json.dumps(replaced))
    refused = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes", status=6)
    assert refused["details"]["reason"] == "staging_database_already_exists"
    assert _catalog_exists(target)
    journal.write_bytes(original_record)
    report = cli(env, "backup", "restore", str(archive), "--target-database-url", target, "--yes")
    assert report["state"] == "quarantined"
    assert Path(report["profile"]).is_file()


def test_a_second_restore_cannot_claim_the_live_target(database_pair: tuple[str, str]) -> None:
    _source, target = database_pair
    with (
        _quarantine._staging_lock(target),
        pytest.raises(SkmError) as refused,
        _quarantine._staging_lock(target),
    ):
        pytest.fail("two restores entered the same catalog")
    assert refused.value.details["reason"] == "staging_restore_in_progress"


def test_a_record_alone_does_not_claim_an_existing_catalog(
    tmp_path: Path, database_pair: tuple[str, str]
) -> None:
    existing, _target = database_pair
    state = tmp_path / str(uuid4())
    state.mkdir()
    with psycopg.connect(existing) as connection:
        row = connection.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()
        assert row is not None
        restore.write_staging_record(state, existing, row[0])
    with _quarantine._staging_lock(existing):
        assert not _quarantine._drop_incomplete_staging(state, existing)
    assert _catalog_exists(existing)
    assert state.is_dir()
