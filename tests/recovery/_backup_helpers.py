"""PostgreSQL, Git and shipped-entry-point fixtures for the backup rehearsal."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Generator
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from jsonschema import Draft202012Validator
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from referencing import Registry, Resource

from contracts.execution import _worker_protocol_support, seed_helpers
from contracts.execution.harness import PEPPER
from fixtures.execution.harness import RecoverySide
from skm.bootstrap.composition import App
from skm.bootstrap.instance import init_instance
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.main import main
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import CreateToken, CreateTokenResult, WhoAmI
from skm.modules.execution.domain.environment import BaselineEntry
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.storage.backup import MANIFEST, URN
from support.http_server import loopback_server
from support.pg import check_admin_dsn


@pytest.fixture
def database_pair(pg_dsn: str) -> Generator[tuple[str, str]]:
    check_admin_dsn(pg_dsn)
    parts = {key: str(value) for key, value in conninfo_to_dict(pg_dsn).items()}
    names = [f"skm_t_backup_{uuid4().hex}" for _ in range(2)]
    auth = f"{quote(parts['user'], safe='')}:{quote(parts['password'], safe='')}"
    endpoint = f"{parts['host']}:{parts['port']}"
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(names[0])))
        try:
            yield (f"postgresql://{auth}@{endpoint}/{names[0]}", f"postgresql://{auth}@{endpoint}/{names[1]}")
        finally:
            for name in reversed(names):
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def cli(env: dict[str, str], *args: str, status: int = 0) -> Any:
    out, err = StringIO(), StringIO()
    code = main([*args, "--json"], environ=env, stdout=out, stderr=err)
    assert code == status, (out.getvalue(), err.getvalue())
    envelope = json.loads(out.getvalue())
    return envelope.get("outcome") if status == 4 else envelope["result" if status == 0 else "error"]


def source(tmp: Path, dsn: str) -> tuple[dict[str, str], Path, Path]:
    profile, state, blobs = (tmp / name for name in ("source.toml", "instance", "source-blobs"))
    env = {"HOME": str(tmp), "XDG_STATE_HOME": str(tmp / "state"), "SKM_DATABASE_URL": dsn}
    init_instance(profile, database_url=dsn, state_dir=state, blobs_root=blobs, environ=env, home=tmp)
    env["SKM_BOOTSTRAP"] = str(profile)
    return env, state, blobs


def assert_quarantined_http(app: App, recovery_token: str, side: RecoverySide) -> None:
    route_table = build_route_table(MODULE_IDS)

    def api(address: str) -> Any:
        return create_app(
            app,
            no_background=True,
            schema_check=lambda: None,
            route_table=route_table,
            registry=app.bus._registry,
            settings={"api.bind": address},
        )

    with loopback_server(api) as endpoint, httpx.Client(base_url=endpoint) as http:
        headers = {"Authorization": f"Bearer {recovery_token}", "SKM-Client-Version": "2.0.0"}
        assert http.get("/api/v1/me", headers=headers).status_code == 200
        claim_body = {
            "worker_id": str(side.worker1),
            "workspace_id": str(side.ws),
            "host_id": str(side.host1),
            "offer": {
                "capabilities": [],
                "labels": [],
                "environment_kinds": [],
                "isolation_profiles": [],
            },
        }
        denied = http.post(
            "/api/v1/worker/assignments/claim",
            json=claim_body,
            headers={**headers, "Idempotency-Key": "quarantined-claim"},
        )
        assert denied.json()["details"]["reason"] == "restore_quarantine"


def assert_normalized_database(target: str, effect_id: str) -> None:
    with psycopg.connect(target) as conn:
        runs = conn.execute(
            "SELECT status,pause_source,stop_code,row_version FROM skm_execution.runs"
        ).fetchall()
        assert runs.count(("paused", "owner", None, 2)) == 5
        assert runs.count(("succeeded", None, None, 1)) == 1
        assert conn.execute(
            "SELECT count(*) FROM skm_core.domain_events WHERE event_type LIKE '%:run-paused:%'"
        ).fetchone() == (5,)
        assert conn.execute(
            "SELECT state,emergency,session_started_at IS NOT NULL FROM skm_execution.autopilot_states"
        ).fetchone() == ("stopped", False, True)
        assert conn.execute(
            "SELECT state FROM skm_execution.external_effects WHERE id=%s", (effect_id,)
        ).fetchone() == ("failed",)
        assert conn.execute("SELECT count(*) FROM skm_execution.assignment_leases").fetchone() == (0,)
        assert conn.execute(
            "SELECT state,attempts FROM skm_core.outbox WHERE destination='hook:sentinel'"
        ).fetchone() == ("pending", 0)


def assert_schema_compatibility(directory: Path) -> None:
    expected = Path(__file__).resolve().parents[2] / "tests/fixtures/corpus/examples/schemas"
    schema = json.loads((expected / "platform" / MANIFEST).read_bytes())
    definitions = json.loads((expected / "kernel/defs.v1.json").read_bytes())
    registry = Registry().with_resource(definitions["$id"], Resource.from_contents(definitions))
    manifest = json.loads((directory / MANIFEST).read_bytes())
    legacy_fields = {key: value for key, value in manifest.items() if key != "schema_baseline"}
    Draft202012Validator(schema, registry=registry).validate(legacy_fields)
    SchemaRegistry.load_default().require_valid(URN, manifest)


def source_authority(side: RecoverySide, root: Path) -> dict[str, str]:
    token = cast("CreateTokenResult", side.client.dispatch(CreateToken("backup-recovery-test")))
    profile = root / "source.toml"
    state = root / "source-state"
    state.mkdir(mode=0o700)
    (state / "secrets").mkdir(mode=0o700)
    atomic_write(state / "secrets/owner.token", token.secret.encode(), mode=0o600)
    profile.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{side.app.instance_id}"\n'
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/SKM_DATABASE_URL"\n'
        "[paths]\n"
        f'state_dir = "{state}"\n'
        "[secrets]\n"
        'token_pepper = "secret://env/RECOVERY_TEST_PEPPER"\n'
    )
    return {
        "HOME": str(root),
        "SKM_BOOTSTRAP": str(profile),
        "SKM_DATABASE_URL": str(side.dsn),
        "RECOVERY_TEST_PEPPER": PEPPER.decode(),
    }


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],  # noqa: S607 - standard Git test fixture
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def checkout_for_recovery(path: Path, patch: pytest.MonkeyPatch) -> str:
    path.mkdir()
    git(path, "init", "--initial-branch=recovery-source")
    git(path, "remote", "add", "origin", "https://production-sentinel.invalid/not-m3.git")
    (path / "file").write_text("base")
    git(path, "add", "file")
    author = ("-c", "user.name=Recovery test", "-c", "user.email=recovery@example.invalid")
    git(path, *author, "commit", "-m", "base")
    base = git(path, "rev-parse", "HEAD")
    (path / "file").write_text("output")
    git(path, "add", "file")
    git(path, *author, "commit", "-m", "output")

    def baseline(mount: str, repo: Any, _base: str, _head: str, dirty: Any) -> BaselineEntry:
        return BaselineEntry(mount, repo, base, base, dirty)

    patch.setattr(_worker_protocol_support, "BaselineEntry", baseline)
    patch.setattr(seed_helpers, "COMMIT_1", base)
    patch.setattr(seed_helpers, "COMMIT_2", git(path, "rev-parse", "HEAD"))
    patch.setattr(seed_helpers, "TREE_1", git(path, "rev-parse", "HEAD^{tree}"))
    return base


def write_journal(path: Path, branch: str, effect: str, request: Any, digest: str) -> None:
    destination = path / ".git/skm-integration" / sha256(branch.encode()).hexdigest()
    destination.mkdir(parents=True, mode=0o700)
    (destination / "writer.lock").touch(mode=0o600)
    atomic_write(
        destination / f"{effect}.json",
        json.dumps(
            {"effect_id": effect, "request": request, "request_digest": digest, "reaped": True}
        ).encode(),
        mode=0o600,
    )


def git_snapshot(path: Path) -> dict[str, str]:
    return {
        rel.as_posix(): sha256(file.read_bytes()).hexdigest()
        for file in path.rglob("*")
        if file.is_file()
        for rel in (file.relative_to(path),)
    }


def assert_pinned_entrypoints(
    env: dict[str, str],
    profile: Path,
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skm.adapters.git.hook_state import LocalHookState
    from skm.bootstrap import _http_mode, lifecycle
    from skm.entrypoints.api import app as api_app
    from skm.entrypoints.cli.commands import local

    state = profile.parent
    boot = profile.read_text().replace("[database]\n", "[database]\nmigrate_on_start = true\n")
    profile.write_text(boot)
    native_bin = Path(env["HOME"]) / "native-hook-fixture"
    native_bin.mkdir()
    claude = native_bin / "claude"
    claude.write_text("#!/bin/sh\nprintf '2.1.295 (Claude Code)\\n'\n", encoding="utf-8")
    claude.chmod(0o700)
    sentinel_env = {
        **env,
        "PATH": str(native_bin),
        "SKM_BOOTSTRAP": str(profile),
        "SKM_STATE_DIR": str(Path(env["HOME"]) / "production-state"),
        "SKM_DATABASE_URL": "postgresql://production-sentinel@127.0.0.1:1/production",
        "SKM_API_ENDPOINT": "http://production-sentinel.invalid:1234/api/v1",
        "SKM_API_TOKEN": "production-credential-sentinel",
        "SKM_HOST_ID": str(uuid4()),
    }
    calls: list[str] = []
    original = lifecycle.embedded_dsn

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        calls.append("production boundary accessed")
        pytest.fail("the restored entry point reached a live operation")

    def staged_dsn(*args: Any, **kwargs: Any) -> str:
        dsn = original(*args, **kwargs)
        assert dsn == target
        calls.append("staging DSN")
        return dsn

    def staged_api(app: Any, *_args: Any, **_kwargs: Any) -> None:
        token = (state / "secrets/owner.token").read_text().strip()
        assert app.client(actor=app.authenticate(token), surface=Surface.API).ask(WhoAmI()) is not None
        calls.append("staging API")

    with monkeypatch.context() as patch:
        patch.setattr(local, "postgres_up", forbidden)
        patch.setattr(local, "provision_local_postgres", forbidden)
        patch.setattr(local, "local_migrate", forbidden)
        patch.setattr(local, "embedded_dsn", forbidden)
        assert cli(sentinel_env, "local", "up", status=6)["details"]["reason"] == "restore_quarantine"
        assert calls == []
        patch.setattr(lifecycle, "embedded_dsn", staged_dsn)
        patch.setattr(lifecycle, "local_migrate", forbidden)
        patch.setattr(api_app, "serve_asgi", staged_api)
        assert cli(sentinel_env, "serve", "--no-background")["status"] == "stopped"

        patch.setattr(LocalHookState, "load_with_snapshot", forbidden)
        patch.setattr(_http_mode, "build_http_client", forbidden)
        patch.setattr(_http_mode, "build_http_hook_app", forbidden)
        out, err = StringIO(), StringIO()
        code = main(
            [
                "hook",
                "PreToolUse",
                "--target",
                "claude_code",
                "--surface",
                "lifecycle.git_guardrails",
                "--project",
                str(uuid4()),
                "--class",
                "enforcement",
            ],
            environ={**sentinel_env, "SKM_ACCESS_MODE": "http"},
            stdin=StringIO('{"cwd":"/repo","tool_name":"Bash","tool_input":{"command":"git status"}}'),
            stdout=out,
            stderr=err,
        )
        assert code == 0, (out.getvalue(), err.getvalue())
        assert "deny" in out.getvalue()
        assert "HOOK_BACKEND_UNAVAILABLE" in out.getvalue()
        assert calls == ["staging DSN", "staging API"]
    profile.write_text(boot.replace("migrate_on_start = true\n", ""))


def workflow_cursor(dsn: str, run: UUID) -> tuple[list[Any], list[Any]]:
    with psycopg.connect(dsn) as conn:
        tasks = conn.execute(
            "SELECT id,status,row_version FROM skm_execution.run_tasks WHERE run_id=%s ORDER BY id", (run,)
        ).fetchall()
        attempts = conn.execute(
            "SELECT id,state,row_version FROM skm_execution.attempts WHERE run_id=%s ORDER BY id", (run,)
        ).fetchall()
    return tasks, attempts
