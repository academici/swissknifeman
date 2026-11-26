"""P04.Z end-to-end acceptance tests for ``access`` and ``workspace`` on PostgreSQL.

Exercises the Phase P04 CLI lifecycle on a fresh scratch database created from
``SKM_TEST_DATABASE_URL``: ``skm init``, ``skm workspace create``, ``skm project create``,
``skm use``, ``skm host register``, ``skm repo bind --mount main --register``,
``skm repo list``, ``skm worker register``, worker token scope restrictions and
self-rotation, archival refusal invariants, and denied-audit persistence.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from e2e.test_instance_profiles import _Databases
from e2e.test_instance_profiles import databases as databases
from skm.adapters.git.runner import GitRunner
from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.bootstrap.composition import build_app, open_cli_app
from skm.bootstrap.machine import machine_socket_path
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.main import main as cli_main
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RbacAuthorizer
from skm.modules.workspace.public import checkout_id_from_locator
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.sources.bootstrap import ProfileCatalog
from support.git_repo import commit_file, init_git_repo
from support.http_server import loopback_certificate, loopback_server

pytestmark = [pytest.mark.e2e, pytest.mark.pg]

ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"
PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")
OWNER_USER = "p04-owner"


def _checked_admin(dsn: str) -> None:
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("P04.Z e2e creates databases only on a local server through '*_test'", pytrace=False)


@dataclass(frozen=True)
class ScratchDb:
    admin_dsn: str
    name: str
    dsn: str


@pytest.fixture
def scratch_db(pg_dsn: str) -> Iterator[ScratchDb]:
    _checked_admin(pg_dsn)
    name = f"skm_t_p04_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield ScratchDb(pg_dsn, name, make_conninfo(pg_dsn, dbname=name))
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def rows(dsn: str, query: str, *params: object) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return [tuple(row) for row in conn.execute(query, params).fetchall()]  # pyright: ignore[reportArgumentType]


@dataclass(frozen=True)
class Sandbox:
    root: Path
    dsn: str
    machine_env: Mapping[str, str] = field(default_factory=dict)

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def state_dir(self) -> Path:
        return self.root / "state/skm"

    @property
    def owner_token_file(self) -> Path:
        return self.state_dir / "secrets/owner.token"

    @property
    def cli_context_file(self) -> Path:
        return self.state_dir / "cli-context.json"

    @property
    def host_file(self) -> Path:
        return self.state_dir / "host.json"

    def env(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            XDG_DATA_HOME=str(self.root / "data"),
            USER=OWNER_USER,
            PYTHONDONTWRITEBYTECODE="1",
            SKM_DATABASE_URL=self.dsn,
        )
        return {**env, **self.machine_env}


def run_cli(box: Sandbox, *argv: str) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    err = io.StringIO()
    code = cli_main(
        ["--json", *argv],
        stdout=out,
        stderr=err,
        environ=box.env(),
    )
    raw = out.getvalue().strip()
    assert raw, f"empty stdout (code={code}, stderr={err.getvalue()})"
    return code, cast("dict[str, Any]", json.loads(raw))


def ok(box: Sandbox, *argv: str) -> dict[str, Any]:
    code, payload = run_cli(box, *argv)
    assert code == 0, f"expected exit 0 for {argv}, got {code}: {payload}"
    assert payload["ok"] is True
    return cast("dict[str, Any]", payload["result"])


def failed(box: Sandbox, expected_code: int, *argv: str) -> dict[str, Any]:
    code, payload = run_cli(box, *argv)
    assert code == expected_code, f"expected exit {expected_code} for {argv}, got {code}: {payload}"
    assert payload["ok"] is False
    return cast("dict[str, Any]", payload["error"])


def run_subprocess(box: Sandbox, *argv: str) -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-c", ENTRY, "--json", *argv],
        env=box.env(),
        cwd=box.root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return cast("dict[str, Any]", json.loads(done.stdout)["result"])


def _verify_repo_and_worker(
    box: Sandbox,
    tmp_path: Path,
    ws_id: UUID,
    proj_id: UUID,
    host_id: UUID,
) -> UUID:
    """Binds a git repo, verifies mounts/checkouts, and registers a worker in personal/skm."""
    repo_fixture = init_git_repo(tmp_path / "repos/skm-main")
    head_sha = repo_fixture.commit_file("README.md", "# SKM\n", message="Initial commit")
    repo_fixture.add_remote("origin", "https://github.com/org/skm.git")
    repo_dir = repo_fixture.path

    bind_res = ok(
        box,
        "repo",
        "bind",
        "--path",
        str(repo_dir),
        "--mount",
        "main",
        "--register",
        "--write-marker",
    )
    repo_id = UUID(bind_res["repository_id"])
    assert bind_res["mount_name"] == "main"
    assert bind_res["state"] == "active"
    assert bind_res["local_locator"] == str(repo_dir.resolve())
    assert bind_res["marker_written"] is True

    marker_path = repo_dir / ".skm/project.json"
    assert marker_path.is_file()
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert (UUID(marker["workspace_id"]), UUID(marker["project_id"])) == (ws_id, proj_id)
    assert (UUID(marker["repository_id"]), marker["mount_name"]) == (repo_id, "main")

    repo_list = ok(box, "repo", "list")
    assert [UUID(item["repository_id"]) for item in repo_list["items"]] == [repo_id]
    assert repo_list["items"][0]["canonical_remote"] == "github.com/org/skm"

    mount_list = ok(box, "repo", "list", "--mounts")
    assert len(mount_list["items"]) == 1
    mount_entry = mount_list["items"][0]
    assert (mount_entry["mount_name"], mount_entry["role"]) == ("main", "primary")
    assert UUID(mount_entry["repository"]["repository_id"]) == repo_id
    assert mount_entry["repository"]["canonical_remote"] == "github.com/org/skm"
    assert mount_entry["binding"]["state"] == "active"
    assert checkout_id_from_locator(mount_entry["binding"]["local_locator"]) is not None

    verify_res = ok(box, "repo", "verify", "--mount", "main")
    assert len(verify_res["items"]) == 1
    assert verify_res["items"][0]["state"] == "active"
    assert rows(
        box.dsn,
        "SELECT observed_head FROM skm_workspace.checkout_bindings WHERE repository_id = %s",
        repo_id,
    ) == [(head_sha,)]

    worker_res = ok(
        box,
        "worker",
        "register",
        "worker-1",
        "--runtime",
        "claude_code",
        "--isolation",
        "worktree",
    )
    worker_id = UUID(worker_res["worker_id"])
    worker_principal_id = UUID(worker_res["principal_id"])
    token_file = Path(worker_res["token_file"])
    assert token_file.is_file()
    assert (token_file.stat().st_mode & 0o777) == 0o600
    assert (token_file.parent.stat().st_mode & 0o777) == 0o700
    assert token_file.read_text(encoding="utf-8").strip().startswith("skm_")

    db_workers = rows(
        box.dsn,
        "SELECT workspace_id, host_id, principal_id, state FROM skm_workspace.workers WHERE id = %s",
        worker_id,
    )
    assert db_workers == [(ws_id, host_id, worker_principal_id, "offline")]
    return repo_id


def _verify_archival_invariants(box: Sandbox, repo_id: UUID) -> None:
    """Verifies confirmation requirements and PROJECT_ARCHIVED refusals on archived scopes."""
    no_confirm = failed(box, 1, "project", "archive", "skm")
    assert no_confirm["code"] == "SCHEMA_INVALID"
    assert no_confirm["details"]["reason"] == "confirmation_required"

    ok(box, "project", "create", "legacy", "--title", "Legacy")
    arch_proj = ok(box, "project", "archive", "legacy", "--yes")
    assert arch_proj["state"] == "archived"

    use_arch = failed(box, 6, "use", "personal/legacy")
    assert use_arch["code"] == "PROJECT_ARCHIVED"

    attach_arch = failed(
        box,
        6,
        "repo",
        "attach",
        str(repo_id),
        "--project",
        "legacy",
        "--mount",
        "main",
    )
    assert attach_arch["code"] == "PROJECT_ARCHIVED"

    legacy_shown = ok(box, "project", "show", "legacy")
    assert legacy_shown["state"] == "archived"

    ok(box, "workspace", "create", "old-ws", "--title", "Old Workspace")
    arch_ws = ok(box, "workspace", "archive", "old-ws", "--yes")
    assert arch_ws["state"] == "archived"

    proj_in_arch_ws = failed(box, 6, "project", "create", "p1", "--workspace", "old-ws", "--title", "P1")
    assert proj_in_arch_ws["code"] == "PROJECT_ARCHIVED"

    repo_in_arch_ws = failed(
        box,
        6,
        "repo",
        "register",
        "--workspace",
        "old-ws",
        "--title",
        "r1",
        "--remote",
        "https://github.com/org/r1.git",
    )
    assert repo_in_arch_ws["code"] == "PROJECT_ARCHIVED"


def test_e2e_full_lifecycle(tmp_path: Path, scratch_db: ScratchDb, databases: _Databases) -> None:
    """Full P04 CLI scenario: init, workspace, project, use, host, repo bind/list, worker, archive."""
    box = Sandbox(tmp_path / "box", scratch_db.dsn, databases.machine_env)
    expected_migrations = [m.version for m in discover_migrations()]

    init_res = ok(
        box,
        "init",
        "--no-workspace",
        "--database-url",
        scratch_db.dsn,
        "--host-name",
        "devbox",
    )
    assert init_res["already_initialized"] is False
    assert init_res["migrations"] == {"applied": expected_migrations, "current": expected_migrations[-1]}
    assert init_res["workspace"] is None
    assert box.owner_token_file.is_file()
    assert (box.owner_token_file.stat().st_mode & 0o777) == 0o600
    owner_id = UUID(init_res["owner_principal_id"])

    rerun = ok(box, "init", "--no-workspace", "--database-url", scratch_db.dsn)
    assert rerun["already_initialized"] is True
    assert rerun["migrations"] == {"applied": [], "current": expected_migrations[-1]}
    assert UUID(rerun["owner_principal_id"]) == owner_id

    ws_res = ok(box, "workspace", "create", "personal", "--title", "Personal")
    ws_id = UUID(ws_res["workspace_id"])
    assert ws_res["slug"] == "personal"

    dup_ws = failed(box, 6, "workspace", "create", "personal", "--title", "Personal")
    assert dup_ws["code"] == "ALREADY_EXISTS"

    proj_res = ok(
        box,
        "project",
        "create",
        "skm",
        "--workspace",
        "personal",
        "--title",
        "Swiss Knife Man",
    )
    proj_id = UUID(proj_res["project_id"])
    assert proj_res["slug"] == "skm"

    shown = ok(box, "project", "show", "skm", "--workspace", "personal")
    assert UUID(shown["project_id"]) == proj_id
    assert shown["repositories"] == []

    use_res = ok(box, "use", "personal/skm")
    assert (UUID(use_res["workspace_id"]), UUID(use_res["project_id"])) == (ws_id, proj_id)
    assert (use_res["workspace_slug"], use_res["project_slug"]) == ("personal", "skm")
    assert not box.cli_context_file.exists()

    sub_projects = run_subprocess(box, "project", "list")
    assert [item["slug"] for item in sub_projects["items"]] == ["skm"]

    host_res = ok(box, "host", "register", "devbox", "--os", "linux", "--arch", "x86_64")
    host_id = UUID(host_res["host_id"])
    assert UUID(json.loads(box.host_file.read_text(encoding="utf-8"))["host_id"]) == host_id

    repo_id = _verify_repo_and_worker(box, tmp_path, ws_id, proj_id, host_id)
    _verify_archival_invariants(box, repo_id)


def test_e2e_worker_token_restricted(tmp_path: Path, scratch_db: ScratchDb) -> None:
    """Worker token cannot execute owner/admin/unrelated commands; denied audits are persisted."""
    box = Sandbox(tmp_path / "box", scratch_db.dsn)
    init_res = ok(box, "init", "--database-url", scratch_db.dsn, "--host-name", "devbox")
    owner_token = box.owner_token_file.read_text(encoding="utf-8").strip()
    assert init_res["already_initialized"] is False

    ok(box, "project", "create", "skm", "--workspace", "personal", "--title", "SKM")
    ok(box, "use", "personal/skm")
    ok(box, "host", "register", "devbox", "--os", "linux", "--arch", "x86_64")

    worker_res = ok(
        box,
        "worker",
        "register",
        "worker-1",
        "--runtime",
        "claude_code",
        "--isolation",
        "worktree",
    )
    worker_principal_id = UUID(worker_res["principal_id"])
    token_file = Path(worker_res["token_file"])
    worker_token = token_file.read_text(encoding="utf-8").strip()

    who = ok(box, "--as-token", worker_token, "whoami")
    assert UUID(who["principal"]["principal_id"]) == worker_principal_id
    assert who["principal"]["kind"] == "worker"

    unauth = failed(box, 5, "--as-token", "skm_w_invalid_token_secret", "whoami")
    assert unauth["code"] == "UNAUTHENTICATED"

    for argv in (
        ("workspace", "create", "hacked", "--title", "Hacked"),
        ("project", "create", "p2", "--workspace", "personal", "--title", "P2"),
        ("config", "set", "execution.review.max_rounds", "3", "--scope", "instance"),
        ("host", "register", "rogue-host", "--os", "linux", "--arch", "x86_64"),
        ("worker", "register", "worker-2", "--runtime", "claude_code", "--isolation", "worktree"),
    ):
        err = failed(box, 5, "--as-token", worker_token, *argv)
        assert err["code"] == "FORBIDDEN"

    rot_res = ok(
        box,
        "--as-token",
        worker_token,
        "worker",
        "register",
        "--rotate",
        "--force",
        "--grace-minutes",
        "0",
    )
    new_worker_token = token_file.read_text(encoding="utf-8").strip()
    assert new_worker_token != worker_token
    assert rot_res["rotated"] is True

    old_auth = failed(box, 5, "--as-token", worker_token, "whoami")
    assert old_auth["code"] == "UNAUTHENTICATED"

    new_who = ok(box, "--as-token", new_worker_token, "whoami")
    assert UUID(new_who["principal"]["principal_id"]) == worker_principal_id

    denied_rows = rows(
        scratch_db.dsn,
        "SELECT action, decision, reason_code FROM skm_core.audit_records "
        "WHERE actor_id = %s AND decision = 'denied' ORDER BY recorded_at, id",
        worker_principal_id,
    )
    denied_actions = {row[0] for row in denied_rows}
    assert {
        "workspace.create_workspace",
        "workspace.create_project",
        "settings.get_schema",
        "workspace.register_worker",
    }.issubset(denied_actions)
    assert all(row[1] == "denied" and isinstance(row[2], str) and bool(row[2]) for row in denied_rows)

    leaks = rows(
        scratch_db.dsn,
        "SELECT count(*) FROM skm_core.domain_events "
        "WHERE payload::text LIKE %s OR payload::text LIKE %s OR payload::text LIKE %s",
        f"%{owner_token}%",
        f"%{worker_token}%",
        f"%{new_worker_token}%",
    )
    assert leaks == [(0,)]


def test_no_bypass_authorizers_in_production(tmp_path: Path, scratch_db: ScratchDb) -> None:
    """Production code has no bypass authorizers and wires RbacAuthorizer + StoredScopeChain."""
    src_root = Path(__file__).resolve().parents[2] / "src/skm"
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "AllowAllAuthorizer" not in text, f"Forbidden bypass authorizer in {path}"
        assert "SingleOwnerAuthorizer" not in text, f"Forbidden bypass authorizer in {path}"

    box = Sandbox(tmp_path / "box", scratch_db.dsn)
    ok(box, "init", "--database-url", scratch_db.dsn)
    env = box.env()
    bootstrap = load_bootstrap(None, env, box.home, instance=None)
    app, _actor = open_cli_app(bootstrap, environ=env, invocation={}, as_token=None)
    try:
        assert isinstance(app.bus._authorizer, RbacAuthorizer)
        assert type(app.bus._scopes).__name__ == "StoredScopeChain"
    finally:
        app.close()


def _checkout_executable() -> Path:
    candidate = os.environ.get("A02_TEST_WHEEL_EXECUTABLE")
    executable = Path(candidate) if candidate is not None else Path(sys.executable).with_name("skm")
    assert executable.is_absolute(), executable
    assert executable.is_file(), executable
    return executable


def _installed_cli(env: Mapping[str, str], cwd: Path, *args: str, error: str | None = None) -> Any:
    executable = _checkout_executable()
    runtime = {key: value for key, value in env.items() if key != "PYTHONPATH"}
    finished = subprocess.run(
        [executable, "--json", *args],
        cwd=cwd,
        env=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert finished.stdout, finished.stderr
    for key, secret in runtime.items():
        if key.endswith(("_TOKEN", "DATABASE_URL", "MIGRATOR_URL")):
            assert secret not in finished.stdout + finished.stderr
    result = json.loads(finished.stdout)
    if error is not None:
        assert finished.returncode != 0, result
        assert result["error"]["code"] == error, result
        return result["error"]
    assert finished.returncode == 0, result
    return result["result"]


@dataclass
class _CheckoutTransport:
    """Observe the real HTTP boundary and suppress replies after the bus commits."""

    blocked: str | None = None
    requests: list[tuple[str, bytes, str]] = field(default_factory=list)

    def wrap(self, app: ASGIApp) -> ASGIApp:
        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            path = str(scope.get("path", ""))
            if scope["type"] != "http" or not (
                "/checkout-bindings" in path or path.endswith("/checkout") or path.endswith("/repositories")
            ):
                await app(scope, receive, send)
                return
            wire = bytearray()
            key = dict(scope.get("headers", [])).get(b"idempotency-key", b"").decode()

            async def capture() -> Message:
                message = await receive()
                if message["type"] == "http.request":
                    wire.extend(message.get("body", b""))
                return message

            async def reply(message: Message) -> None:
                if (
                    message["type"] == "http.response.start"
                    and message["status"] < 300
                    and self.blocked == path
                ):
                    message = {**message, "status": 503}
                await send(message)

            try:
                await app(scope, capture, reply)
            finally:
                self.requests.append((path, bytes(wire), key))

        return wrapped


@contextmanager
def _checkout_hub(box: Sandbox, transport: _CheckoutTransport) -> Iterator[tuple[str, Path, str]]:
    env = box.env()
    _installed_cli(env, box.root, "init")
    ca, key = loopback_certificate(box.root / "tls")
    config = load_bootstrap(None, env, box.home)
    with closing(build_app(config, surface=Surface.API, environ=env, invocation={})) as core:

        def create(address: str) -> ASGIApp:
            project = create_app(
                core,
                route_table=build_route_table(MODULE_IDS),
                registry=core.bus._registry,
                no_background=True,
                settings={"api.bind": address},
            )
            return transport.wrap(project)

        with loopback_server(create, tls=(ca, key)) as endpoint:
            yield endpoint, ca, box.owner_token_file.read_text().strip()


def _project_and_repo(env: Mapping[str, str], cwd: Path, tmp_path: Path) -> tuple[Path, str, str]:
    assert _installed_cli(env, cwd, "whoami")["principal"]["kind"] == "human"
    project = _installed_cli(env, cwd, "project", "create", "demo", "--workspace", "personal")
    selection = _installed_cli(env, cwd, "use", "personal/demo")
    assert selection["project_id"] == project["project_id"]
    host = _installed_cli(env, cwd, "host", "register", "checkout-box")
    repo = init_git_repo(tmp_path / "private-absolute-checkout")
    repo.commit_file("README.md", "checkout smoke\n", message="Initialize")
    repo.add_remote(
        "origin",
        "https://git-user:synthetic-git-password@repo.example/team/checkout.git?token=synthetic-query",
    )
    return repo.path, project["project_id"], host["host_id"]


def _binding_rows(dsn: str) -> list[tuple[Any, ...]]:
    return rows(dsn, "SELECT id, host_id, local_locator, row_version FROM skm_workspace.checkout_bindings")


@pytest.mark.parametrize("mode", ["standalone", "https"])
def test_installed_checkout_commands(tmp_path: Path, databases: _Databases, mode: str) -> None:  # noqa: PLR0915 -- actual lifecycle and both fault paths
    project_dsn = databases.projects[0]
    transport = _CheckoutTransport()
    client_root = tmp_path / "client"
    client_root.mkdir()
    box = Sandbox(client_root, project_dsn if mode == "standalone" else "", databases.machine_env)
    env = box.env()
    with ExitStack() as stack:
        env["XDG_STATE_HOME"] = stack.enter_context(tempfile.TemporaryDirectory(prefix="a2.", dir="/var/tmp"))
        if mode == "https":
            hub_root = tmp_path / "hub"
            hub_root.mkdir()
            hub = Sandbox(hub_root, project_dsn)
            endpoint, ca, token = stack.enter_context(_checkout_hub(hub, transport))
            del env["SKM_DATABASE_URL"]
            env["A02_CALLER_TOKEN"] = token
            _installed_cli(
                env,
                client_root,
                "instance",
                "add",
                "project-hub",
                "--mode",
                "http",
                "--api-endpoint",
                endpoint + "/api/v1",
                "--ca-bundle",
                str(ca),
                "--credential",
                "secret://env/A02_CALLER_TOKEN",
            )
            _installed_cli(env, client_root, "instance", "use", "project-hub")
        else:
            _installed_cli(env, client_root, "init")

        repo, project_id, host_id = _project_and_repo(env, client_root, tmp_path)
        bind = ("repo", "bind", "--register", "--write-marker", "--yes")
        if mode == "standalone":
            bind = (*bind, "--request-id", str(uuid4()))
        marker_dir = repo / ".skm"
        marker = marker_dir / "project.json"
        if mode == "https":
            transport.blocked = "/api/v1/checkout-bindings"
            _installed_cli(env, repo, *bind, error="BACKEND_UNAVAILABLE")
            assert not marker.exists()
            transport.blocked = None
        else:
            marker_dir.mkdir(mode=0o500)
            try:
                _installed_cli(env, repo, *bind, error="REPOSITORY_UNSAFE")
                assert not marker.exists()
            finally:
                marker_dir.chmod(0o700)
        (committed,) = _binding_rows(project_dsn)
        assert (str(committed[1]), committed[3]) == (host_id, 1)
        assert checkout_id_from_locator(committed[2]) is not None
        if mode == "https":
            _assert_changed_default_bind_requires_explicit_request(env, repo, bind, transport)
            assert _binding_rows(project_dsn) == [committed]

        result = _installed_cli(env, repo, *bind)
        assert result["binding_id"] == str(committed[0])
        assert result["marker_written"]
        assert result["local_locator"] == str(repo)
        assert json.loads(marker.read_text())["project_id"] == project_id
        assert _installed_cli(env, repo, *bind)["binding_id"] == str(committed[0])
        assert _binding_rows(project_dsn) == [committed]
        assert rows(project_dsn, "SELECT count(*) FROM skm_workspace.repositories") == [(1,)]
        assert rows(project_dsn, "SELECT count(*) FROM skm_workspace.project_repositories") == [(1,)]

        wrong = _installed_cli(env, repo, "repo", "register", "https://repo.example/team/other.git")
        _installed_cli(
            env, repo, "repo", "bind", "--repo", wrong["repository_id"], "--yes", error="CHECKOUT_MISMATCH"
        )
        assert _binding_rows(project_dsn) == [committed]
        if mode == "https":
            verify_path = f"/api/v1/checkout-bindings/{committed[0]}/verification"
            transport.blocked = verify_path
            verify = ("repo", "verify", "--request-id", str(uuid4()))
            _installed_cli(env, repo, *verify, error="BACKEND_UNAVAILABLE")
            transport.blocked = None
            assert _binding_rows(project_dsn)[0][3] == 2
            assert _installed_cli(env, repo, *verify)["items"][0]["row_version"] == 2
            assert _binding_rows(project_dsn)[0][3] == 2
            _exercise_expired_checkout_retry(env, repo, databases, project_dsn, transport, verify_path)
            for path, body, _ in transport.requests:
                assert str(repo).encode() not in body
                assert b"synthetic-git-password" not in body
                assert b"synthetic-query" not in body
                if body and "/checkout-bindings" in path:
                    payload = json.loads(body)
                    for field in ("observed_toplevel", "local_locator"):
                        if payload.get(field) is not None:
                            assert checkout_id_from_locator(payload[field]) is not None
        else:
            verification = _installed_cli(env, repo, "repo", "verify")
            assert verification["items"][0]["row_version"] == 2
        _verify_through_machine_socket(env, repo, project_id, str(committed[0]))


def _assert_changed_default_bind_requires_explicit_request(
    env: Mapping[str, str], repo: Path, bind: tuple[str, ...], transport: _CheckoutTransport
) -> None:
    git = GitRunner()
    original = git.run(repo, ("rev-parse", "HEAD"), check=True).stdout.strip()
    commit_file(repo, rel_path="changed.txt", content="different observation\n", message="Drift checkout")
    path = "/api/v1/checkout-bindings"
    sent = sum(entry[0] == path for entry in transport.requests)
    refused = _installed_cli(env, repo, *bind, error="IDEMPOTENCY_KEY_REUSED")
    assert UUID(refused["details"]["request_id"]).version == 5
    assert sum(entry[0] == path for entry in transport.requests) == sent
    git.run(repo, ("switch", "--detach", original), check=True)


def _exercise_expired_checkout_retry(
    env: Mapping[str, str],
    repo: Path,
    databases: _Databases,
    project_dsn: str,
    transport: _CheckoutTransport,
    verify_path: str,
) -> None:
    request_id = str(uuid4())
    verify = ("repo", "verify", "--request-id", request_id)
    transport.blocked = verify_path
    _installed_cli(env, repo, *verify, error="BACKEND_UNAVAILABLE")
    transport.blocked = None
    (pending,) = rows(
        databases.machine_admin,
        "SELECT idempotency_key, receipt FROM skm_host.retries "
        "WHERE request_id=%s AND step='verify_checkout'",
        request_id,
    )
    assert pending[1] is None
    with psycopg.connect(databases.machine_admin) as machine:
        machine.execute(
            "UPDATE skm_host.retries SET safe_until=now()-interval '1 minute' WHERE request_id=%s",
            (request_id,),
        )
    with psycopg.connect(project_dsn) as project:
        project.execute("DELETE FROM skm_core.idempotency_receipts WHERE key=%s", (pending[0],))
    before = len([path for path, _, _ in transport.requests if path == verify_path])
    assert _binding_rows(project_dsn)[0][3] == 3
    refused = _installed_cli(env, repo, *verify, error="INVALID_TRANSITION")
    assert refused["details"]["reason"] == "idempotency_window_closed"
    after = len([path for path, _, _ in transport.requests if path == verify_path])
    assert after == before
    assert _binding_rows(project_dsn)[0][3] == 3


def _verify_through_machine_socket(
    env: Mapping[str, str], cwd: Path, project_id: str, binding_id: str
) -> None:
    home = Path(env["HOME"])
    catalog = ProfileCatalog.read(None, env, home)
    profile = catalog.select(None, cwd)
    config = catalog.config(profile)
    assert config.installation_id is not None
    socket = machine_socket_path(env, home, config.installation_id)
    token = env.get("A02_CALLER_TOKEN") or (config.state_dir / "secrets/owner.token").read_text().strip()
    executable = _checkout_executable()
    runtime = {key: value for key, value in env.items() if key != "PYTHONPATH"}
    process = subprocess.Popen(  # noqa: TID251 -- exercise the installed process and Unix socket shutdown
        [executable, "serve", "--machine"],
        cwd=cwd,
        env=runtime,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 25
        while not socket.is_socket() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert socket.is_socket(), process.poll()
        with httpx.Client(
            base_url="http://skm-machine", transport=httpx.HTTPTransport(uds=str(socket))
        ) as api:
            path = "/api/v1/machine/repo/verify"
            headers = {"Idempotency-Key": str(uuid4())}
            payload = {"project_id": project_id, "mount_name": "main"}
            assert api.post(path, json=payload, headers=headers).status_code == 401
            headers["Authorization"] = "Bearer " + token
            first = api.post(path, json=payload, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["items"][0]["binding_id"] == binding_id
            replay = api.post(path, json=payload, headers=headers)
            assert replay.status_code == 200, replay.text
            assert replay.json() == first.json()
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
