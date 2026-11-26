"""Native lifecycle, research policy and MCP projection through the CLI and real memory bus."""

import json
import os
import sys
from contextlib import closing
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import NOW, dispatch_new, seed_principals
from skm.adapters.integrations.codex.mcp import build_mcp_servers
from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.hook_subscriptions import bind_cli_subscriptions
from skm.bootstrap.host_services import bind_cli_research
from skm.entrypoints.cli.main import app_backend, main
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RbacAuthorizer
from skm.modules.integrations.host.plan_projection import inputs_from_view
from skm.modules.integrations.public import DesiredProjectionView, GetDesiredProjection
from skm.modules.settings.public import SetValue
from skm.modules.workspace import public as workspace
from skm.modules.workspace.generated.commands import HostArch, HostOs, RegisterHostDefsHostPlatform
from skm.platform.config.bootstrap import load_bootstrap
from support.git_repo import init_git_repo
from support.seed import SEED

_FAKE_CODEGRAPH = """\
import json
import os
import sys
from pathlib import Path

no_color, verb, *args = sys.argv[1:]
assert no_color == "--no-color"
assert os.environ["CODEGRAPH_TELEMETRY"] == "0"
assert "SKM_FAKE_SECRET" not in os.environ
if verb == "query":
    path, root, json_flag, limit_flag, limit, end_options, text = args
    assert (path, json_flag, limit_flag, end_options) == ("--path", "--json", "--limit", "--")
    assert 1 <= int(limit) <= 50
else:
    flag, root = args
    assert flag == {"init": "--yes", "index": "--quiet", "status": "--json"}[verb]

checkout = Path(root)
index = checkout / ".codegraph/index-state.json"
if verb in ("init", "index"):
    assert "/.codegraph/" in (checkout / ".git/info/exclude").read_text().splitlines()
    index.parent.mkdir(exist_ok=True)
    (index.parent / "codegraph.db").touch()
    if verb == "index" or not index.exists():
        index.write_text(json.dumps((checkout / "program.py").read_text().splitlines()))
elif verb == "status":
    print(json.dumps({"initialized": index.exists(), "projectPath": root, "version": "test"}))
else:
    symbols = json.loads(index.read_text())
    hits = []
    for name in symbols:
        if name == text:
            hits.append({"node": {"filePath": "../escaped.py", "qualifiedName": name, "kind": "function",
                                  "startLine": 1, "endLine": 2}})
            hits.append({"node": {"filePath": "program.py", "qualifiedName": name, "kind": "function",
                                  "startLine": 3, "endLine": 4, "signature": "()"}})
    print(json.dumps(hits))
"""


@pytest.fixture
def codegraph_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binary = tmp_path / "codegraph"
    binary.write_text(f"#!{sys.executable}\n{_FAKE_CODEGRAPH}")
    binary.chmod(0o700)
    monkeypatch.setenv("PATH", os.pathsep.join((str(tmp_path), os.environ["PATH"])))
    monkeypatch.setenv("SKM_FAKE_SECRET", "never passed to CodeGraph")
    return binary


def _set_value(client: SkmClient, scope: JsonObject, key: str, value: JsonValue) -> None:
    dispatch_new(
        client,
        SetValue.from_json(
            {"scope": scope, "key": key, "value": value, "reason": "CodeGraph test", "confirmed": True}
        ),
    )


def _bind_project(client: SkmClient, checkout: Path) -> tuple[UUID, UUID, UUID]:
    ws = dispatch_new(client, workspace.CreateWorkspace("ws", "Workspace")).workspace_id
    project = dispatch_new(client, workspace.CreateProject(ws, "graph", "Graph")).project_id
    platform = RegisterHostDefsHostPlatform(HostOs.LINUX, HostArch.X86_64)
    host = dispatch_new(client, workspace.RegisterHost("dev", platform)).host_id
    repository = dispatch_new(
        client, workspace.RegisterRepository(ws, "repo", "https://github.com/org/graph.git", None)
    ).repository_id
    dispatch_new(client, workspace.AttachRepository(project, repository, "backend"))
    binding = dispatch_new(
        client,
        workspace.BindCheckout(
            repository, host, str(checkout), str(checkout), ("github.com/org/graph",), "a" * 40, False, NOW
        ),
    ).binding_id
    return project, host, binding


@pytest.mark.parametrize("knowledge_enabled", [True, False], ids=["knowledge-enabled", "knowledge-disabled"])
def test_native_codegraph_lifecycle_and_research(
    tmp_path: Path, codegraph_cli: Path, knowledge_enabled: bool
) -> None:
    repo = init_git_repo(tmp_path / "checkout")
    program = repo.path / "program.py"
    program.write_text("FirstSymbol\n")
    exclude = repo.path / ".git/info/exclude"
    user_exclude = b"# user rule\n/keep-my-rule\n"
    exclude.write_bytes(user_exclude)
    bootstrap = replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, tmp_path / "boot"),
        instance_id=SEED.instance_id,
    )
    disabled = frozenset() if knowledge_enabled else frozenset({"knowledge", "learning"})
    clock = FrozenClock(NOW)
    overrides = CompositionOverrides(
        RbacAuthorizer(clock), StoredScopeChain(), clock=clock, disabled_modules=disabled
    )
    with closing(
        build_app(bootstrap, surface=Surface.CLI, environ={}, invocation={}, overrides=overrides)
    ) as app:
        owner = seed_principals(app, "memory")
        client = app.client(actor=owner, surface=Surface.CLI)
        project, host, binding = _bind_project(client, repo.path)
        _set_value(
            client,
            {"level": "instance"},
            "context.research.sources",
            {"graph": {"kind": "codegraph", "tier": "codegraph", "capabilities": ["search"]}},
        )

        cli_app = bind_cli_subscriptions(app, replace(bootstrap, host_id=host), {})
        cli_app = replace(cli_app, host=bind_cli_research(cli_app.host, client, cli_app.plugins))
        backend = replace(app_backend(cli_app, owner), close=None)
        assert ("knowledge" in backend.disabled_modules()) is (not knowledge_enabled)

        def invoke(*argv: str, expected: int = 0) -> dict[str, Any]:
            out, err = StringIO(), StringIO()
            code = main(
                ["--json", *argv],
                backend=lambda *_: backend,
                environ={},
                stdout=out,
                stderr=err,
            )
            assert code == expected, out.getvalue() + err.getvalue()
            return json.loads(out.getvalue())

        def graph(verb: str, *, expected: int = 0) -> dict[str, Any]:
            return invoke("graph", verb, "--project", str(project), "--mount", "backend", expected=expected)

        assert graph("status")["result"]["initialized"] is False
        assert graph("doctor", expected=1)["result"]["healthy"] is False
        assert graph("index", expected=6)["error"]["code"] == "INVALID_TRANSITION"
        assert exclude.read_bytes() == user_exclude
        assert graph("init")["result"]["initialized"] is True
        assert graph("init")["result"]["mount"] == "backend"
        doctor = graph("doctor")["result"]
        assert doctor["healthy"]
        assert doctor["installed"]
        assert doctor["mcp"] == {
            "type": "stdio",
            "command": str(codegraph_cli),
            "args": ["serve", "--mcp", "--path", str(repo.path)],
        }
        assert exclude.read_bytes().endswith(user_exclude)
        assert exclude.read_bytes().count(b"/.codegraph/\n") == 1
        assert repo.runner.run(repo.path, ("check-ignore", ".codegraph/codegraph.db")).exit_code == 0

        def research(symbol: str) -> dict[str, Any]:
            (result,) = invoke("research", "query", symbol, "--source", "graph", "--project", str(project))[
                "result"
            ]["results"]
            assert result["tier"] == "codegraph"
            assert result["cache_status"] == "bypass"
            return result

        (doc,) = research("FirstSymbol")["documents"]
        assert doc["origin"] == "mcp:codegraph/backend/program.py#L3"
        assert doc["locator"] == {"line_from": 3, "line_to": 4}
        program.write_text("SecondSymbol\n")
        assert not research("SecondSymbol")["documents"]
        assert graph("index")["result"]["initialized"] is True
        assert graph("status")["result"]["initialized"] is True
        assert research("SecondSymbol")["documents"][0]["title"] == "SecondSymbol"
        if not knowledge_enabled:
            assert invoke("graph", "stats", expected=6)["error"]["code"] == "MODULE_DISABLED"

        project_scope: JsonObject = {"level": "project", "scope_id": str(project)}
        _set_value(client, project_scope, "integrations.mcp.servers", {"codegraph": doctor["mcp"]})
        projection = cast(
            "DesiredProjectionView", client.ask(GetDesiredProjection(project, binding, "codex"))
        )
        servers, _, _ = build_mcp_servers(inputs_from_view(projection))
        assert servers["codegraph"] == {
            "command": str(codegraph_cli),
            "args": ["serve", "--mcp", "--path", str(repo.path)],
        }

        _set_value(client, project_scope, "context.research.disabled_sources", ["graph"])
        denied = invoke(
            "research", "query", "SecondSymbol", "--source", "graph", "--project", str(project), expected=1
        )
        assert denied["error"]["code"] == "NOT_FOUND"
