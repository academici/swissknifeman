"""Local episodic memory through the trusted MCP entry point."""

import json
from dataclasses import replace
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest

from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from integration.mcp.test_protocol import LiveClient, call, content, exchange, request
from skm.bootstrap.composition import App
from skm.bootstrap.local_memory import local_episodic_memory
from skm.entrypoints.cli.commands import mcp
from skm.entrypoints.cli.main import main
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.data_classification import HOST_PRIVATE
from skm.kernel.errors import BackendUnavailable, Forbidden
from skm.kernel.json_types import JsonObject
from skm.platform.config.bootstrap import load_bootstrap
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

_TOOLS = {"skm_local_memory_record", "skm_local_memory_search", "skm_local_memory_summarize"}


def _bootstrap(tmp_path: Path, mode: str) -> Path:
    bootstrap = tmp_path / f"{mode}.toml"
    bootstrap.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{uuid4()}"\n'
        f'[paths]\nstate_dir = "{tmp_path / "state"}"\n'
        f'[access]\nmode = "{mode}"\n'
        '[api]\nendpoint = "https://hub.example/api/v1"\ncredential = "secret://env/SKM_TOKEN"\n'
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n',
        encoding="utf-8",
    )
    return bootstrap


def _cli(bootstrap: Path, args: list[str], *messages: JsonObject) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    code = main(
        ["--bootstrap", str(bootstrap), *args],
        environ={"SKM_TOKEN": "synthetic-mcp-credential"},
        stdin=StringIO("".join(json.dumps(message) + "\n" for message in messages)),
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def test_host_mcp_consumption_stays_in_the_local_receipt(
    exec_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary = f"host-episode-{uuid4()}"
    bootstrap = _bootstrap(tmp_path, "embedded")
    session_id = uuid4()
    side = exec_side
    permissions = ["project.read", "memory.read", "memory.write"]
    owner = side.restricted_client(permissions, owner_token=True)
    actor = McpSession.open(owner, project_id=side.proj).actor

    def app(*_args: object, **_kwargs: object) -> App:
        return replace(side.app, authenticator=lambda _: actor, host=None, closers=(), closed=[False])

    monkeypatch.setattr(mcp, "build_app", app)
    command = ["mcp", "--project", str(side.proj), "--local-memory-session", str(session_id)]
    code, out, err = _cli(
        bootstrap,
        command,
        request("tools/list"),
        call("skm_local_memory_record", {"kind": "fact", "text": canary}),
        call("skm_local_memory_search", {"query": "host-episode"}),
        call("skm_local_memory_summarize", {}),
        call("skm_memory_remember", {"key": "context", "text": canary}),
    )
    assert (code, err) == (0, "")
    listed, recorded, found, summary, denied = map(json.loads, out.splitlines())
    assert {tool["name"] for tool in listed["result"]["tools"]} == _TOOLS
    assert content(recorded) == {"classification": HOST_PRIVATE, "status": "recorded"}
    assert content(found)["items"][0]["text"] == canary
    assert content(summary) == {"classification": HOST_PRIVATE, "summary": f"- fact: {canary}"}
    assert denied["error"]["code"] == -32601
    assert canary not in repr(denied)

    for mcp_session in (McpSession.open(owner, project_id=side.proj), LiveClient(assignment=True).session):
        listing, attempted = exchange(
            mcp_session, [request("tools/list"), call("skm_local_memory_search", {})]
        )
        assert not _TOOLS.intersection(tool["name"] for tool in listing["result"]["tools"])
        assert attempted["error"]["code"] == -32601
        assert canary not in repr(attempted)

    local = local_episodic_memory(load_bootstrap(str(bootstrap), {}, tmp_path))
    with pytest.raises(Forbidden, match="consumed HOST_PRIVATE") as caught:
        local.require_syncable(session_id)
    assert canary not in str(caught.value)
    local.require_syncable(uuid4())


def test_http_profile_cannot_open_host_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Remote MCP must refuse before opening a client or reading the local database")

    monkeypatch.setattr(mcp, "open_http_client", unexpected)
    code, out, err = _cli(_bootstrap(tmp_path, "http"), ["mcp", "--local-memory-session", str(uuid4())])
    assert code != 0
    assert "requires embedded host mode" in err
    assert not out
    assert not (tmp_path / "state" / "episodic-memory").exists()


def test_assignment_cannot_opt_in(tmp_path: Path) -> None:
    bootstrap = load_bootstrap(str(_bootstrap(tmp_path, "embedded")), {}, tmp_path)
    live = LiveClient(assignment=True)
    with pytest.raises(Forbidden, match="requires a human credential"):
        McpSession.open(live.session.client, local_memory=(local_episodic_memory(bootstrap), uuid4()))


def test_local_receipt_verification_fails_closed_when_unavailable(tmp_path: Path) -> None:
    bootstrap = load_bootstrap(str(_bootstrap(tmp_path, "embedded")), {}, tmp_path)
    with pytest.raises(BackendUnavailable, match="Local episodic memory is unavailable"):
        local_episodic_memory(bootstrap).require_syncable(uuid4())
    assert not (tmp_path / "state" / "episodic-memory").exists()
