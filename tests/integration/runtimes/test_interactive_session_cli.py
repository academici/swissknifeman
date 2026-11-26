"""Exercise the CLI with real project projections, host settings, and an attached terminal."""

import json
import os
import pty
import sys
import termios
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path
from select import select
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import NOW, dispatch_new, seed_principals
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.projection_wiring import bind_cli_projections
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RbacAuthorizer
from skm.modules.integrations.host.observe import resolve_checkout_for_mount
from skm.modules.integrations.host.sync_projections import sync
from skm.modules.integrations.ports import LocalCheckoutProjections
from skm.modules.runtimes import public as runtimes
from skm.modules.settings.public import ExplainConfig
from skm.modules.workspace import public as workspace
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.machine import MachinePrincipal, MachineStore
from support.git_repo import init_git_repo
from support.seed import SEED

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="interactive sessions use Linux pidfds")

_AGENT = """\
import os
import sys
import termios
from pathlib import Path

assert sys.argv[1:] == ["--model", "routed-model"]
home = Path.home()
assert not (home / ".claude" / "unselected").exists()
if "ANTHROPIC_API_KEY" in os.environ:
    assert os.environ["ANTHROPIC_API_KEY"] == "interactive-fixture-authorized"
    assert not (home / ".claude" / ".credentials.json").exists()
else:
    assert (home / ".claude" / ".credentials.json").read_text() == '{"login":"fixture-selected"}'
protected = {"SKM_DATABASE_URL", "SKM_MACHINE_DATABASE_URL", "SKM_TOKEN", "OPENAI_API_KEY"}
assert not protected & os.environ.keys()
assert "/.skm" in Path(".git/info/exclude").read_text().splitlines()
assert Path("CLAUDE.md").is_file()
print("READY", flush=True)
for line in sys.stdin:
    if line.strip() == "size":
        print("size:" + "x".join(map(str, termios.tcgetwinsize(0))), flush=True)
    else:
        print("reply:" + line.strip(), flush=True)
"""


@dataclass
class _Cli:
    backend: Backend
    environ: dict[str, str]
    project: UUID
    host: UUID
    checkout: Path
    machine_settings: JsonObject

    def run(self, *argv: str, expected: int = 0) -> Any:
        out, err = StringIO(), StringIO()

        def connect(*_args: object) -> Backend:
            assert argv[:2] == ("session", "start")
            return self.backend

        code = main(
            ["--json", *argv],
            backend=connect,
            environ=self.environ,
            stdout=out,
            stderr=err,
        )
        assert code == expected, out.getvalue() + err.getvalue()
        document = json.loads(out.getvalue())
        return document["result"] if code == 0 else document["error"]


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[_Cli]:
    checkout = init_git_repo(tmp_path / "checkout").path
    agent = tmp_path / "configured-agent"
    agent.write_text(f"#!{sys.executable}\n{_AGENT}")
    agent.chmod(0o700)
    ambient = tmp_path / ".claude"
    ambient.mkdir(mode=0o700)
    (ambient / "unselected").write_text("another credential")
    credential = ambient / ".credentials.json"
    credential.write_text('{"login":"fixture-selected"}')
    credential.chmod(0o600)
    installation = UUID(int=0xA11)
    environ = {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "SKM_DATABASE_URL": "postgresql://unused",
        "SKM_MACHINE_DATABASE_URL": "postgresql://unused-machine",
        "SKM_INSTALLATION_ID": str(installation),
        "SKM_TOKEN": "interactive-fixture-hub-only",
        "SKM_STATE_DIR": str(tmp_path / "state"),
        "OPENAI_API_KEY": "interactive-fixture-other-provider",
        "INTERACTIVE_ACCOUNT": "interactive-fixture-authorized",
    }
    bootstrap = replace(load_bootstrap(None, environ, tmp_path), instance_id=SEED.instance_id)
    bootstrap.state_dir.mkdir(mode=0o700)
    clock = FrozenClock(NOW)
    overrides = CompositionOverrides(RbacAuthorizer(clock), StoredScopeChain(), clock=clock)
    with closing(
        build_app(bootstrap, surface=Surface.CLI, environ={}, invocation={}, overrides=overrides)
    ) as app:
        owner = seed_principals(app, "memory")
        client = app.client(actor=owner, surface=Surface.CLI)
        ws = dispatch_new(client, workspace.CreateWorkspace("ws", "Workspace")).workspace_id
        project = dispatch_new(client, workspace.CreateProject(ws, "example", "Example")).project_id
        host = dispatch_new(
            client,
            workspace.RegisterHost.from_json({"name": "dev", "platform": {"os": "linux", "arch": "x86_64"}}),
        ).host_id
        repo = dispatch_new(
            client, workspace.RegisterRepository(ws, "repo", "https://github.com/org/repo.git", None)
        ).repository_id
        dispatch_new(client, workspace.AttachRepository(project, repo, "main"))
        dispatch_new(
            client,
            workspace.BindCheckout(
                repo, host, str(checkout), str(checkout), ("github.com/org/repo",), "a" * 40, False, NOW
            ),
        )
        machine_settings: JsonObject = {
            "runtimes.binaries": {"claude_code": str(agent)},
            "runtimes.models.allowed": {"claude_code": {"routed-model": ["default"]}},
            "runtimes.accounts": {"claude_code": {"ANTHROPIC_API_KEY": "secret://env/INTERACTIVE_ACCOUNT"}},
        }
        machine = Mock(spec=MachineStore)
        machine.get_installation_id.return_value = installation
        machine.get_operator_setting.side_effect = lambda _installation, key: machine_settings.get(key)
        machine.get_user_setting.return_value = None
        from skm.bootstrap.hook_subscriptions import bind_cli_subscriptions

        cli_app = bind_cli_subscriptions(app, replace(bootstrap, host_id=host), environ)
        assert cli_app.host is not None
        host_services = bind_cli_projections(cli_app.host, bootstrap.state_dir, client)
        assert host_services is not None
        projection_context = host_context_factory(host_services, client)

        def resolve_local(project_id: ProjectId, mount: str) -> tuple[UUID, Path]:
            location = resolve_checkout_for_mount(projection_context(), project_id, mount)
            assert location.local_locator == str(checkout)
            return location.binding_id, checkout

        projections = SimpleNamespace(
            resolve=resolve_local,
            sync=lambda project_id: sync(
                projection_context(), {"scope": "project", "scope_id": str(project_id)}
            ),
        )
        host_services = replace(
            host_services,
            gateways=GatewayTable(
                {**host_services.gateways.entries, LocalCheckoutProjections: projections}, "host_gateway"
            ),
        )
        ask = client.ask

        def route_or_ask(query: object) -> object:
            assert not (isinstance(query, ExplainConfig) and "runtimes.binaries" in (query.keys or ()))
            if not isinstance(query, runtimes.ExplainRouting):
                return ask(query)
            assert query.host_id == host
            assert query.scope.id == project
            assert query.scope.kind == "project"
            assert query.role.value == "executor"
            assert query.explicit_runtime in (None, "claude_code")
            assert query.explicit_model in (None, "routed-model")
            return runtimes.RouteExplainView.from_json(
                {
                    "role": query.role.value,
                    "scope": {"kind": "project", "id": str(project)},
                    "host_id": str(host),
                    "admission": {},
                    "rejected": [],
                    "config": {},
                    "decision": {"runtime_id": "claude_code", "model": "routed-model"},
                }
            )

        monkeypatch.setattr(client, "ask", route_or_ask)
        backend = Backend(
            client,
            host_factory=host_context_factory(host_services, client),
            state_dir=bootstrap.state_dir,
            machine_store=machine,
            machine_scope=lambda: MachinePrincipal(installation, SEED.instance_id, owner.principal_id),
        )
        invocation = _Cli(backend, environ, project, host, checkout, machine_settings)
        try:
            yield invocation
        finally:
            for item in invocation.run("session", "list"):
                invocation.run("session", "stop", item["session_id"])


def _read_until(master: int, expected: bytes) -> bytes:
    output = b""
    deadline = time.monotonic() + 5
    while expected not in output:
        remaining = deadline - time.monotonic()
        assert remaining > 0, output
        assert select([master], [], [], remaining)[0], output
        output += os.read(master, 4096)
    return output


def test_session_start_list_attach_detach_reattach_and_stop(cli: _Cli) -> None:
    assert cli.run("session", "list") == []
    info = cli.run("session", "start", "--project", "ws/example")
    session_id = info["session_id"]
    assert info["project_id"] == str(cli.project)
    assert info["runtime"] == "claude_code"
    assert info["model"] == "routed-model"
    assert info["checkout"] == str(cli.checkout)
    assert cli.run("session", "list") == [info]
    assert cli.run("session", "attach", session_id, expected=1)["code"] == "SCHEMA_INVALID"

    master, slave = pty.openpty()
    original = termios.tcgetattr(slave)
    try:
        with os.fdopen(os.dup(slave), "r") as stdin, os.fdopen(os.dup(slave), "w") as stdout:
            err = StringIO()

            def attach() -> int:
                return main(
                    ["session", "attach", session_id],
                    environ=cli.environ,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=err,
                )

            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(attach)
                try:
                    assert b"READY" in _read_until(master, b"READY")
                    busy = StringIO()
                    assert (
                        main(
                            ["session", "attach", session_id],
                            environ=cli.environ,
                            stdin=stdin,
                            stdout=stdout,
                            stderr=busy,
                        )
                        == 6
                    )
                    assert "already has an attached terminal" in busy.getvalue()
                    os.write(master, b"hello\n")
                    assert b"reply:hello" in _read_until(master, b"reply:hello")
                    termios.tcsetwinsize(slave, (34, 112))
                    os.write(master, b"size\n")
                    assert b"size:34x112" in _read_until(master, b"size:34x112")
                finally:
                    os.write(master, b"\x1d")
                    assert first.result(timeout=5) == 0, err.getvalue()
                assert termios.tcgetattr(slave) == original
                assert cli.run("session", "list") == [info]
                second = pool.submit(attach)
                try:
                    _read_until(master, b"READY")
                    os.write(master, b"again\n")
                    assert b"reply:again" in _read_until(master, b"reply:again")
                finally:
                    assert cli.run("session", "stop", session_id) == info
                    assert second.result(timeout=5) == 0, err.getvalue()
                assert termios.tcgetattr(slave) == original
    finally:
        os.close(master)
        os.close(slave)
    assert cli.run("session", "list") == []
    assert cli.run("session", "stop", session_id, expected=1)["code"] == "NOT_FOUND"


def test_session_start_refuses_projections_that_conflict(cli: _Cli) -> None:
    (cli.checkout / "CLAUDE.md").mkdir()
    error = cli.run(
        "session",
        "start",
        "--project",
        str(cli.project),
        "--runtime",
        "claude_code",
        "--model",
        "routed-model",
        expected=6,
    )
    assert error["code"] == "PROJECTION_CONFLICT"
    assert cli.run("session", "list") == []


def test_session_start_refuses_model_missing_from_machine_policy(cli: _Cli) -> None:
    cli.machine_settings.pop("runtimes.models.allowed")
    error = cli.run("session", "start", "--project", "ws/example", expected=6)
    assert error["code"] == "MODEL_UNAVAILABLE"
    assert cli.run("session", "list") == []


def test_session_start_requires_a_verified_local_checkout(cli: _Cli) -> None:
    host_factory = cli.backend.host_factory
    assert host_factory is not None
    context = host_factory()
    assert isinstance(context.gateways, GatewayTable)
    entries = dict(context.gateways.entries)
    del entries[LocalCheckoutProjections]
    context = replace(context, gateways=GatewayTable(entries, "host_gateway"))
    cli.backend = replace(cli.backend, host_factory=lambda: context)
    error = cli.run("session", "start", "--project", str(cli.project), expected=6)
    assert error["code"] == "CAPABILITY_UNAVAILABLE"
    assert not (cli.checkout / "CLAUDE.md").exists()


def test_session_requires_operator_approval_to_copy_native_account(cli: _Cli) -> None:
    del cli.machine_settings["runtimes.accounts"]
    error = cli.run("session", "start", "--project", str(cli.project), expected=6)
    assert error["code"] == "RUNTIME_AUTH_EXPIRED"
    assert not (cli.checkout / "CLAUDE.md").exists()

    cli.machine_settings["runtimes.credentials.copy"] = {"claude_code": True}
    session = cli.run("session", "start", "--project", str(cli.project))
    state = Path(cli.environ["SKM_STATE_DIR"]) / "sessions" / session["session_id"]
    home = state / "home"
    copied = home / ".claude" / ".credentials.json"
    assert (home.stat().st_mode & 0o777, copied.stat().st_mode & 0o777) == (0o700, 0o600)
    assert copied.read_text() == '{"login":"fixture-selected"}'
    cli.run("session", "stop", session["session_id"])
    assert not state.exists()
