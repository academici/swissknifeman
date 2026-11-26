"""End-to-end CLI tests for ``skm integrations`` (plan, apply, drift, adopt, remove, list)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast, override
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from e2e.test_instance_profiles import _Databases
from e2e.test_instance_profiles import databases as databases
from e2e.test_p04_workspace import (
    Sandbox,
    _checkout_executable,
    _checkout_hub,
    _CheckoutTransport,
    _installed_cli,
    rows,
)
from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.git.repo_inspect import GitRepositoryInspector
from skm.application_bus.host import HostServices
from skm.bootstrap.machine import machine_socket_path
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.context import CliOptions
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.main import Backend, production_backend
from skm.entrypoints.cli.main import main as cli_main
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.ports_uow import Surface as PortSurface
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.managed_block import render_block
from skm.modules.integrations.domain.merged_json import OwnedKeyPath
from skm.modules.integrations.domain.observed import extract_managed_digest
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import (
    CheckoutFs,
    IntegrationTarget,
    IntegrationTargetRegistry,
    LocalCheckoutProjections,
)
from skm.modules.workspace.ports import RepositoryInspector
from skm.platform.config.sources.bootstrap import ProfileCatalog
from skm.platform.system_clock import SystemClock
from support.git_repo import init_git_repo

pytestmark = [pytest.mark.e2e, pytest.mark.pg]

PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")


def _make_desired(
    target: TargetId, surface: Surface, relative_path: str, boundary: ManagedBoundary, managed_bytes: bytes
) -> DesiredFile:
    digest, ok = extract_managed_digest(managed_bytes, boundary)
    assert ok
    assert digest is not None
    return DesiredFile(
        target=target,
        surface=surface,
        relative_path=relative_path,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=digest,
        source_refs=(),
        renderer=f"{target.value}.{surface.value}@1",
    )


class _CliTestTarget:
    def __init__(self, target_id: TargetId, files: Sequence[DesiredFile]) -> None:
        self.target_id = target_id
        self.renderer_version = f"{target_id.value}@1"
        self.files = tuple(files)

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            target=self.target_id,
            surfaces=dict.fromkeys(Surface, SurfaceSupport.NATIVE),
            hook_surfaces={},
            tested_client_version="1.0.0",
            verified_at=date(2026, 11, 1),
        )

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        _ = inputs
        return self.files

    def normalize_hook_payload(self, event_name: str, payload: Mapping[str, Any]) -> Any:
        raise NotImplementedError

    def render_hook_decision(self, event: Any, decision: Any) -> Any:
        raise NotImplementedError

    def client_layers(self, fs: Any, home: Any) -> tuple[Any, ...]:
        return ()

    def instruction_paths(self) -> tuple[str, ...]:
        return ()

    def summarize_session(self, payload: Mapping[str, Any], fs: Any) -> None:
        return None


class _CliTestRegistry:
    def __init__(self, targets: Mapping[TargetId, _CliTestTarget]) -> None:
        self._targets = dict(targets)

    def get(self, target: TargetId) -> IntegrationTarget:
        if target not in self._targets:
            raise NotFound(ErrorCode.NOT_FOUND, f"unknown target {target}")
        return self._targets[target]

    def all(self) -> tuple[IntegrationTarget, ...]:
        return tuple(self._targets.values())


@dataclass
class CliSandbox:
    root: Path
    dsn: str
    repo_dir: Path
    targets: dict[TargetId, _CliTestTarget]
    machine_env: Mapping[str, str] = field(default_factory=dict, repr=False)

    def env(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        env.update(
            HOME=str(self.root / "home"),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            XDG_DATA_HOME=str(self.root / "data"),
            USER="int-owner",
            PYTHONDONTWRITEBYTECODE="1",
            SKM_DATABASE_URL=self.dsn,
        )
        return {**env, **self.machine_env}

    def backend(
        self,
        options: CliOptions,
        environ: Mapping[str, str],
        on_secret: Callable[[str], None] = lambda _value: None,
    ) -> Backend:
        be = production_backend(options, environ, on_secret)
        if be.state_dir is not None:
            host_path = be.state_dir / "host.json"
            if host_path.is_file():
                raw_host_id = json.loads(host_path.read_text(encoding="utf-8")).get("host_id")
                if isinstance(raw_host_id, str) and raw_host_id:
                    local = (
                        be.host_factory().gateways.get(LocalCheckoutProjections) if be.host_factory else None
                    )
                    host = HostServices(
                        host_id=HostId(UUID(raw_host_id)),
                        surface=PortSurface.CLI,
                        gateways=GatewayTable(
                            {
                                RepositoryInspector: GitRepositoryInspector(clock=SystemClock()),
                                CheckoutFs: LocalCheckoutFs(self.repo_dir, state_dir=be.state_dir),
                                IntegrationTargetRegistry: _CliTestRegistry(self.targets),
                                LocalCheckoutProjections: local,
                            },
                            "host_gateway",
                        ),
                        host_config=dict,
                        operations={
                            spec.name: spec for manifest in MANIFESTS for spec in manifest.host_operations
                        },
                    )
                    return replace(be, host_factory=host_context_factory(host, be.client))
        return be

    def run_json(self, *argv: str) -> tuple[int, dict[str, Any]]:
        out, err = io.StringIO(), io.StringIO()
        code = cli_main(
            ["--json", *argv],
            stdin=io.StringIO(""),
            stdout=out,
            stderr=err,
            environ=self.env(),
            backend=self.backend,
        )
        raw = out.getvalue().strip()
        assert raw, f"empty stdout (code={code}, stderr={err.getvalue()})"
        return code, cast("dict[str, Any]", json.loads(raw))

    def run_human(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli_main(
            list(argv),
            stdin=io.StringIO(""),
            stdout=out,
            stderr=err,
            environ=self.env(),
            backend=self.backend,
        )
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def cli_box(tmp_path: Path, databases: _Databases) -> CliSandbox:
    repo = init_git_repo(tmp_path / "repos/skm-main")
    repo.commit_file("README.md", "# SKM\n", message="Initial commit")
    repo.add_remote("origin", "https://github.com/org/skm.git")

    blk_bnd = ManagedBoundary(Ownership.MANAGED_BLOCK, block_ids=("skm.core",))
    file_bnd = ManagedBoundary(Ownership.MANAGED_FILE)
    targets = {
        TargetId.CLAUDE_CODE: _CliTestTarget(
            TargetId.CLAUDE_CODE,
            (
                _make_desired(
                    TargetId.CLAUDE_CODE,
                    Surface.INSTRUCTIONS,
                    "CLAUDE.md",
                    blk_bnd,
                    render_block("skm.core", "Follow SKM v1.\n"),
                ),
                _make_desired(
                    TargetId.CLAUDE_CODE,
                    Surface.INSTRUCTIONS,
                    ".claude/rules/skm-core.md",
                    file_bnd,
                    b"# Core v1\n",
                ),
            ),
        ),
        TargetId.CODEX: _CliTestTarget(TargetId.CODEX, ()),
    }
    box = CliSandbox(tmp_path / "box", databases.projects[0], repo.path, targets, databases.machine_env)
    assert box.run_json("init", "--host-name", "devbox")[0] == 0
    assert box.run_json("project", "create", "skm", "--workspace", "personal", "--title", "SKM")[0] == 0
    assert box.run_json("use", "personal/skm")[0] == 0
    assert box.run_json("host", "register", "devbox", "--os", "linux", "--arch", "x86_64")[0] == 0
    bind_args = ("repo", "bind", "--path", str(repo.path), "--mount", "main", "--register", "--write-marker")
    assert box.run_json(*bind_args)[0] == 0
    return box


def test_cli_plan_apply_list_drift_conflict_and_confirm(cli_box: CliSandbox) -> None:
    h_code, h_out, _ = cli_box.run_human("integrations", "plan", "--target", "claude_code")
    assert h_code == 0
    assert "nothing written (plan only)" in h_out
    assert not (cli_box.repo_dir / "CLAUDE.md").exists()

    p_code, p_env = cli_box.run_json("integrations", "plan", "--target", "claude_code")
    assert (p_code, p_env["schema"], p_env["ok"]) == (0, "urn:skm:cli:envelope:v1", True)
    assert p_env["result"][0]["schema"] == "urn:skm:integrations:host:projection-plan:v1"

    a_code, a_env = cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")
    assert (a_code, a_env["result"][0]["state"]) == (0, "in_sync")
    assert (cli_box.repo_dir / ".claude/rules/skm-core.md").read_text(encoding="utf-8") == "# Core v1\n"

    l_code, l_env = cli_box.run_json("integrations", "list")
    assert (l_code, l_env["result"]["items"][0]["state"]) == (0, "in_sync")

    d0_code, d0_env = cli_box.run_json("integrations", "drift", "--target", "claude_code")
    assert (d0_code, d0_env["result"][0]["drifted"]) == (0, 0)

    rule_path = cli_box.repo_dir / ".claude/rules/skm-core.md"
    rule_path.write_text("# User local tweak\n", encoding="utf-8")
    d1_code, d1_env = cli_box.run_json("integrations", "drift", "--target", "claude_code")
    assert (d1_code, d1_env["ok"], d1_env["result"][0]["state"]) == (6, True, "drifted")

    cli_box.targets[TargetId.CLAUDE_CODE].files = (
        cli_box.targets[TargetId.CLAUDE_CODE].files[0],
        _make_desired(
            TargetId.CLAUDE_CODE,
            Surface.INSTRUCTIONS,
            ".claude/rules/skm-core.md",
            ManagedBoundary(Ownership.MANAGED_FILE),
            b"# Core v2\n",
        ),
    )
    nc_code, nc_env = cli_box.run_json("integrations", "apply", "--target", "claude_code")
    assert (nc_code, nc_env["ok"], nc_env["error"]["code"]) == (1, False, "SCHEMA_INVALID")

    cf_code, cf_env = cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")
    assert (cf_code, cf_env["ok"]) == (6, True)
    assert cf_env["result"][0]["conflicts"] == [".claude/rules/skm-core.md"]
    assert (cli_box.repo_dir / ".claude/rules/skm-core.md.skm-new").read_text(
        encoding="utf-8"
    ) == "# Core v2\n"


def test_cli_adopt_and_remove_restore_pre_image(cli_box: CliSandbox) -> None:
    claude_md = cli_box.repo_dir / "CLAUDE.md"
    claude_md.write_bytes(b"# Existing Repo Doc\n")
    rule_md = cli_box.repo_dir / ".claude/rules/skm-core.md"
    rule_md.parent.mkdir(parents=True, exist_ok=True)
    original = b"# Existing Repo Rule\n" + str(cli_box.repo_dir).encode()
    rule_md.write_bytes(original)
    generated = cli_box.repo_dir / ".claude/rules/skm-new-rule.md"
    cli_box.targets[TargetId.CLAUDE_CODE].files += (
        _make_desired(
            TargetId.CLAUDE_CODE,
            Surface.INSTRUCTIONS,
            str(generated.relative_to(cli_box.repo_dir)),
            ManagedBoundary(Ownership.MANAGED_FILE),
            b"# Newly managed\n",
        ),
    )

    na_code, na_env = cli_box.run_json(
        "integrations", "adopt", ".claude/rules/skm-core.md", "--target", "claude_code", "--reason", "adopt"
    )
    assert (na_code, na_env["error"]["code"]) == (1, "SCHEMA_INVALID")

    ad_code, ad_env = cli_box.run_json(
        "integrations",
        "adopt",
        ".claude/rules/skm-core.md",
        "--target",
        "claude_code",
        "--reason",
        "adopt",
        "--yes",
    )
    assert ad_code == 0, ad_env
    assert ad_env["result"]["pre_image_file_version_id"]
    assert ad_env["result"]["pre_image_storage"] == "machine"

    ap_code, ap_env = cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")
    assert (ap_code, ap_env["result"][0]["state"]) == (0, "in_sync")
    assert "Existing Repo Doc" in claude_md.read_text(encoding="utf-8")
    assert rule_md.read_bytes() == b"# Core v1\n"
    assert generated.read_bytes() == b"# Newly managed\n"

    nr_code, nr_env = cli_box.run_json(
        "integrations", "remove", "--target", "claude_code", "--restore-pre-image"
    )
    assert (nr_code, nr_env["error"]["code"]) == (1, "SCHEMA_INVALID")

    _assert_missing_caller_original_is_safe(
        cli_box, rule_md, generated, ad_env["result"]["pre_image_file_version_id"]
    )
    rm_code, rm_env = cli_box.run_json(
        "integrations", "remove", "--target", "claude_code", "--restore-pre-image", "--yes"
    )
    assert (rm_code, rm_env["result"]["state"]) == (0, "removed")
    assert claude_md.read_bytes() == b"# Existing Repo Doc\n"
    assert rule_md.read_bytes() == original
    assert not generated.exists()


def _assert_missing_caller_original_is_safe(
    box: CliSandbox, rule: Path, generated: Path, backup_id: str
) -> None:
    state = box.root / "state/skm/integrations/pre-images"
    (backup,) = state.glob(f"*/*/*/*/{backup_id}")
    assert backup.stat().st_mode & 0o777 == 0o600
    scope = backup.parent.parent
    other = scope.parent / str(uuid4()) / backup.parent.name / backup.name
    other.parent.mkdir(mode=0o700, parents=True)
    saved = backup.read_bytes()
    backup.rename(other)
    try:
        code, reply = box.run_json(
            "integrations", "remove", "--target", "claude_code", "--restore-pre-image", "--yes"
        )
        assert code != 0, reply
        assert reply["error"]["code"] == "INTEGRATION_UNSAFE_TARGET"
        assert reply["error"]["details"]["reason"] == "pre_image_unavailable"
        assert rule.read_bytes() == b"# Core v1\n"
        assert generated.read_bytes() == b"# Newly managed\n"
        assert other.read_bytes() == saved
        assert not backup.exists()
    finally:
        other.rename(backup)


@pytest.fixture
def machine_state() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="a3m.", dir="/var/tmp") as directory:
        yield Path(directory)


def test_installed_fleet_projections_on_two_checkouts(  # noqa: PLR0915 -- full installed lifecycle
    tmp_path: Path, databases: _Databases, machine_state: Path
) -> None:
    hub_path, laptop_path = tmp_path / "hub", tmp_path / "client"
    hub_path.mkdir()
    laptop_path.mkdir()
    transport = _FleetTransport()
    dsn = databases.projects[0]
    hub = Sandbox(hub_path, dsn)
    laptop = Sandbox(laptop_path, "", databases.machine_env)
    env = laptop.env()
    del env["SKM_DATABASE_URL"]
    env["XDG_STATE_HOME"] = str(machine_state)
    checkouts: list[tuple[Path, str]] = []
    with _checkout_hub(hub, transport) as (endpoint, ca, token):
        env["A03_OPERATOR_TOKEN"] = token
        _installed_cli(
            env,
            laptop_path,
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
            "secret://env/A03_OPERATOR_TOKEN",
        )
        env["SKM_INSTANCE"] = "project-hub"
        host = _installed_cli(env, laptop_path, "host", "register", "a03-laptop")["host_id"]
        for suffix in ("one", "two"):
            project = _installed_cli(env, laptop_path, "project", "create", suffix, "--workspace", "personal")
            project_id = project["project_id"]
            _installed_cli(env, laptop_path, "use", f"personal/{suffix}")
            repo = init_git_repo(tmp_path / f"checkout-{suffix}")
            repo.commit_file("README.md", f"user-owned {suffix}\n", message="Initial commit")
            repo.add_remote("origin", f"https://repo.example/team/{suffix}.git")
            _installed_cli(env, repo.path, "repo", "bind", "--register", "--write-marker", "--yes")
            settings = repo.path / ".claude/settings.json"
            settings.parent.mkdir()
            settings.write_text(json.dumps({"env": _private_settings(repo.path)}) + "\n")
            checkouts.append((repo.path, project_id))

        root, project = checkouts[0]
        selector = ("--project", project, "--target", "claude_code")
        plan = _installed_cli(env, root, "integrations", "plan", *selector)
        assert plan[0]["plan_digest"]
        settings = root / ".claude/settings.json"
        assert json.loads(settings.read_text()) == {"env": _private_settings(root)}
        first = _installed_cli(env, root, "integrations", "apply", *selector, "--yes")[0]
        assert first["state"] == "in_sync"
        assert first["written"]
        replay = _installed_cli(env, root, "integrations", "apply", *selector, "--yes")[0]
        assert not replay["written"]
        assert replay["projection_id"] == first["projection_id"]
        status, envelope = _projection_console(env, root, "integrations", "doctor", *selector)
        assert status in {0, 1}
        assert envelope["ok"] is True
        report = envelope["result"]
        assert report["project_id"] == project
        assert report["host_id"] == host
        assert report["checks"]

        sync = _installed_cli(env, root, "workspace", "sync-projections", "personal")
        assert {item["project_id"] for item in sync["checkouts"]} == {item[1] for item in checkouts}
        for path, project_id in checkouts:
            rendered = json.loads((path / ".claude/settings.json").read_text())
            assert rendered["env"] == _private_settings(path)
            assert "permissions" in rendered
            assert "hooks" in rendered
            mcp = json.loads((path / ".mcp.json").read_text())
            assert mcp["mcpServers"]["skm"]["command"] == "skm"
            assert (path / "README.md").read_text().startswith("user-owned ")
            assert "/.skm\n" in (path / ".git/info/exclude").read_text()
            fleet = _installed_cli(env, path, "integrations", "list", "--project", project_id)
            assert len(fleet["items"]) == 1
            assert fleet["items"][0]["host_id"] == host
            assert str(path) not in json.dumps(fleet)

        _assert_fleet_requires_current_rights(env, root, project, host)
        _assert_fleet_machine_transport(env, root, project, token)
        _assert_fleet_conflict_preserves_user_content(env, root, project)

    report = _installed_cli(env, checkouts[0][0], "integrations", "doctor", "--offline")
    assert any(check["check_id"] == "local.live_authority" for check in report["checks"])
    assert all(
        "not checked" in item["detail"]
        for item in report["checks"]
        if item["check_id"] == "local.live_authority"
    )
    assert len(rows(dsn, "SELECT id FROM skm_integrations.projections")) == 2
    assert rows(
        dsn,
        "SELECT count(*) FROM skm_integrations.projection_files WHERE pre_image_file_version_id IS NOT NULL",
    ) == [(0,)]
    for path, _ in checkouts:
        for _, body, _ in transport.requests:
            assert str(path).encode() not in body
            assert quote(str(path), safe="").encode() not in body
            assert b"synthetic-local-file-secret" not in body


class _FleetTransport(_CheckoutTransport):
    @override
    def wrap(self, app: ASGIApp) -> ASGIApp:
        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            wire = bytearray(scope["query_string"])

            async def capture() -> Message:
                message = await receive()
                if message["type"] == "http.request":
                    wire.extend(message.get("body", b""))
                return message

            try:
                await app(scope, capture, send)
            finally:
                self.requests.append((scope["path"], bytes(wire), ""))

        return wrapped


def _private_settings(root: Path) -> dict[str, str]:
    return {
        "MY_LOCAL_VALUE": "unchanged",
        "LOCAL_ROOT": str(root),
        "PRIVATE_VALUE": "synthetic-local-file-secret",
    }


def _assert_fleet_machine_transport(env: dict[str, str], root: Path, project: str, token: str) -> None:
    home = Path(env["HOME"])
    config = ProfileCatalog.read(None, env, home).config("project-hub")
    assert config.installation_id is not None
    socket = machine_socket_path(env, home, config.installation_id)
    runtime = {key: value for key, value in env.items() if key != "PYTHONPATH"}
    process = subprocess.Popen(  # noqa: TID251 - real private local server
        [_checkout_executable(), "serve", "--machine"],
        cwd=root,
        env=runtime,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = monotonic() + 25
        while not socket.is_socket() and process.poll() is None and monotonic() < deadline:
            sleep(0.05)
        assert socket.is_socket(), process.poll()
        with httpx.Client(
            base_url="http://skm-machine/api/v1/machine", transport=httpx.HTTPTransport(uds=str(socket))
        ) as api:
            assert api.post("/integrations/list", json={"project_id": project}).status_code == 401
            api.headers["Authorization"] = "Bearer " + token
            fleet = api.post("/integrations/list", json={"project_id": project})
            assert fleet.status_code == 200, fleet.text
            assert len(fleet.json()["items"]) == 1
            payload = {"project_id": project, "targets": ["claude_code"]}
            plan = api.post("/integrations/plan", json=payload)
            assert plan.status_code == 200, plan.text
            hostile = api.post(
                "/integrations/apply", json={**payload, "plans": [{"write_path": "README.md"}]}
            )
            assert hostile.status_code == 422, hostile.text
            stale = api.post("/integrations/apply", json={**payload, "plan_digests": ["sha256:" + "0" * 64]})
            assert stale.status_code == 409, stale.text
            confirmed = {**payload, "plan_digests": [item["plan_digest"] for item in plan.json()]}
            replay = api.post("/integrations/apply", json=confirmed)
            assert replay.status_code == 200, replay.text
            assert replay.json()[0]["written"] == []
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)


def _projection_console(env: Mapping[str, str], root: Path, *args: str) -> tuple[int, dict[str, Any]]:
    finished = subprocess.run(
        [_checkout_executable(), "--json", *args],
        cwd=root,
        env={key: value for key, value in env.items() if key != "PYTHONPATH"},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert finished.stdout, finished.stderr
    return finished.returncode, cast("dict[str, Any]", json.loads(finished.stdout))


def _assert_fleet_requires_current_rights(env: dict[str, str], root: Path, project: str, host: str) -> None:
    token_file = root.parent / "projection-read.token"
    workspace = _installed_cli(env, root, "workspace", "show", "personal")
    _installed_cli(
        env,
        root,
        "token",
        "create",
        "read-projection",
        "--scope",
        f"workspace:{workspace['workspace_id']}",
        "--permission",
        "workspace.read",
        "--permission",
        "project.read",
        "--permission",
        "checkout.read_locator",
        "--permission",
        "integration.read",
        "--permission",
        "config.read",
        "--save",
        str(token_file),
    )
    read_actor = ("--as-token", token_file.read_text().strip())
    before = (root / ".claude/settings.json").read_bytes()
    _installed_cli(
        env,
        root,
        *read_actor,
        "integrations",
        "apply",
        "--project",
        project,
        "--target",
        "claude_code",
        "--yes",
        error="FORBIDDEN",
    )
    assert (root / ".claude/settings.json").read_bytes() == before
    other = _installed_cli(env, root, "host", "register", "--replace", "a03-other-host")["host_id"]
    assert other != host
    assert not _installed_cli(env, root, "integrations", "list", "--project", project)["items"]
    # Restore the test host in the profile's local host selector.
    config = ProfileCatalog.read(None, env, Path(env["HOME"])).config("project-hub")
    host_file = config.state_dir / "host.json"
    document = host_file.read_text()
    assert other in document
    host_file.write_text(document.replace(other, host))


def _assert_fleet_conflict_preserves_user_content(env: dict[str, str], root: Path, project: str) -> None:
    settings = root / ".claude/settings.json"
    altered = json.loads(settings.read_text())
    altered["permissions"]["allow"].append("Bash(user-local-command)")
    settings.write_text(json.dumps(altered))
    before = settings.read_bytes()
    _installed_cli(
        env,
        root,
        "config",
        "set",
        "integrations.hooks.mode",
        '{"git_guardrails":"off"}',
        "--scope",
        f"project:{project}",
    )
    plan = _installed_cli(env, root, "integrations", "plan", "--project", project, "--target", "claude_code")
    assert any(decision["decision"] == "conflict_write_new" for decision in plan[0]["decisions"])
    code, marked = _projection_console(
        env, root, "integrations", "apply", "--project", project, "--target", "claude_code", "--yes"
    )
    assert code == 6, marked
    assert ".claude/settings.json" in marked["result"][0]["conflicts"]
    assert settings.read_bytes() == before
    assert settings.with_name("settings.json.skm-new").is_file()


def _merged_mcp(servers: dict[str, Any]) -> DesiredFile:
    owned = (OwnedKeyPath(("mcpServers", "skm"), "replace"),)
    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=owned)
    raw = (json.dumps({"mcpServers": servers}, indent=2) + "\n").encode()
    return _make_desired(TargetId.CLAUDE_CODE, Surface.MCP, ".mcp.json", boundary, raw)


def test_cli_remove_deletes_the_files_it_created_and_keeps_the_rest(cli_box: CliSandbox) -> None:
    repo = cli_box.repo_dir
    target = cli_box.targets[TargetId.CLAUDE_CODE]
    target.files += (_merged_mcp({"skm": {"command": "skm-mcp"}}),)
    assert cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")[0] == 0
    assert (repo / ".mcp.json").is_file()
    assert (repo / "CLAUDE.md").is_file()
    assert (repo / ".claude/rules/skm-core.md").is_file()

    code, env = cli_box.run_json("integrations", "remove", "--target", "claude_code", "--yes")
    assert (code, env["result"]["state"]) == (0, "removed")
    # Before: `{}` / an empty CLAUDE.md / the emptied `.claude/rules` were left behind.
    assert not (repo / ".mcp.json").exists()
    assert not (repo / "CLAUDE.md").exists()
    assert not (repo / ".claude").exists()
    assert (repo / "README.md").is_file()


def test_cli_remove_keeps_a_created_file_once_the_user_added_content(cli_box: CliSandbox) -> None:
    repo = cli_box.repo_dir
    target = cli_box.targets[TargetId.CLAUDE_CODE]
    target.files += (_merged_mcp({"skm": {"command": "skm-mcp"}}),)
    assert cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")[0] == 0
    mcp = repo / ".mcp.json"
    document = json.loads(mcp.read_text(encoding="utf-8"))
    document["mcpServers"]["mine"] = {"command": "mine"}
    mcp.write_text(json.dumps(document), encoding="utf-8")
    (repo / ".claude/rules/mine.md").write_text("# mine\n", encoding="utf-8")

    assert cli_box.run_json("integrations", "remove", "--target", "claude_code", "--yes")[0] == 0
    assert json.loads(mcp.read_text(encoding="utf-8")) == {"mcpServers": {"mine": {"command": "mine"}}}
    assert (repo / ".claude/rules/mine.md").is_file()
    assert not (repo / ".claude/rules/skm-core.md").exists()


def test_cli_remove_keeps_a_file_that_existed_before_the_first_apply(cli_box: CliSandbox) -> None:
    repo = cli_box.repo_dir
    (repo / ".mcp.json").write_text('{"mcpServers": {}}\n', encoding="utf-8")
    cli_box.targets[TargetId.CLAUDE_CODE].files += (_merged_mcp({"skm": {"command": "skm-mcp"}}),)
    assert cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")[0] == 0

    assert cli_box.run_json("integrations", "remove", "--target", "claude_code", "--yes")[0] == 0
    assert (repo / ".mcp.json").is_file()  # not SKM's to delete, even though nothing of SKM's is left in it


def test_remove_preserves_existing_directories_and_toml_comments(cli_box: CliSandbox) -> None:
    root = cli_box.repo_dir
    rules = root / ".claude/rules"
    rules.mkdir(parents=True)
    path = root / "agent.toml"
    boundary = ManagedBoundary(Ownership.MERGED_TOML, owned_keys=(OwnedKeyPath(("tool",), "replace"),))
    target = cli_box.targets[TargetId.CLAUDE_CODE]
    target.files += (
        _make_desired(TargetId.CLAUDE_CODE, Surface.MCP, "agent.toml", boundary, b'tool = "skm"\n'),
    )
    assert cli_box.run_json("integrations", "apply", "--target", "claude_code", "--yes")[0] == 0
    path.write_bytes(b"# operator note\n" + path.read_bytes())
    assert cli_box.run_json("integrations", "remove", "--target", "claude_code", "--yes")[0] == 0
    assert path.read_text().strip() == "# operator note"
    assert rules.is_dir()


def test_remove_preserves_a_recreated_file_adopted_on_a_later_apply(cli_box: CliSandbox) -> None:
    args = ("--target", "claude_code", "--yes")
    assert cli_box.run_json("integrations", "apply", *args)[0] == 0
    path = cli_box.repo_dir / ".claude/rules/skm-core.md"
    content = path.read_bytes()
    assert cli_box.run_json("integrations", "remove", *args)[0] == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    assert cli_box.run_json("integrations", "apply", *args)[0] == 0
    assert cli_box.run_json("integrations", "remove", *args)[0] == 0
    assert path.read_bytes() == content
