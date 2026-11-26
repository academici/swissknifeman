"""Replay the MCP wire example and check JSON-RPC failure isolation."""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from typing import Any, cast, override
from uuid import UUID, uuid4

import pytest

from skm.application_bus.client import SkmClient
from skm.entrypoints.mcp import protocol, registry
from skm.entrypoints.mcp.registry import ToolSpec
from skm.entrypoints.mcp.server import serve
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, Unauthenticated
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access import public as access
from skm.platform.schema.registry import SchemaRegistry

_EXAMPLE = Path(__file__).resolve().parents[3] / "tests/fixtures/corpus/examples/mcp/session.jsonl"
_LIMIT = "api.mcp.max_response_tokens"


def _identity(actor: Actor) -> access.WhoAmIView:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    grant = actor.grant
    assert grant is not None
    return access.WhoAmIView.from_json(
        {
            "principal": {
                "principal_id": str(actor.principal_id),
                "kind": actor.kind.value,
                "display_name": actor.display_name,
                "state": "active",
                "created_at": now.isoformat(),
                "row_version": 1,
                "identities": [],
            },
            "token": {
                "token_id": str(grant.token_id),
                "kind": grant.kind,
                "name": "mcp test",
                "prefix": "abcdefgh",
                "scope_id": None if grant.scope_id is None else str(grant.scope_id),
                "permissions": sorted(grant.permissions) if grant.permissions is not None else None,
                "state": "active",
                "expires_at": None,
                "last_used_at": None,
                "created_at": now.isoformat(),
                "superseded_by": None,
                "assignment_id": None if grant.assignment_id is None else str(grant.assignment_id),
                "step_id": None if grant.step_id is None else str(grant.step_id),
            },
            "memberships": [],
            "effective_permissions": ["plan.read", "project.read"],
            "modules": {"knowledge": False},
            "permissions_by_scope": {},
            "events_cursor": None,
        }
    )


class LiveClient:
    """Keep admission observable while using actual wire contracts in tool responses."""

    def __init__(self, *, assignment: bool = False, limit: int = 10_000) -> None:
        kind = PrincipalKind.WORKER if assignment else PrincipalKind.HUMAN
        grant = (
            TokenGrant(uuid4(), "assignment", ScopeId(uuid4()), None, uuid4(), uuid4())
            if assignment
            else TokenGrant(uuid4(), "personal", None, None)
        )
        actor = Actor(PrincipalId(uuid4()), kind, "Tester", grant)
        self.identity = _identity(actor)
        self.session = McpSession(actor, ProjectId(uuid4()), cast("SkmClient", self), {_LIMIT: limit})
        self.revoked = False
        self.checks: list[UUID | None] = []

    def ask(self, query: object) -> access.WhoAmIView:
        assert isinstance(query, access.WhoAmI)
        self.checks.append(query.scope_id)
        if self.revoked:
            raise Unauthenticated(ErrorCode.UNAUTHENTICATED, "Credential revoked")
        return self.identity


class _FlushedOutput(StringIO):
    flushes: int = 0

    @override
    def flush(self) -> None:
        self.flushes += 1
        super().flush()


def exchange(session: McpSession, requests: Sequence[JsonValue]) -> list[dict[str, Any]]:
    return _exchange_text(session, "\n".join(map(protocol.json_text, requests)) + "\n")


def _exchange_text(session: McpSession, text: str) -> list[dict[str, Any]]:
    output = _FlushedOutput()
    assert serve(None, session, StringIO(text), output) == 0
    lines = output.getvalue().splitlines()
    assert len(lines) == output.flushes
    return [json.loads(line) for line in lines]


def request(method: str, ident: JsonValue = 1, **params: JsonValue) -> JsonObject:
    return {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}


def call(name: str, arguments: JsonValue, ident: int = 1) -> JsonObject:
    return request("tools/call", ident, name=name, arguments=arguments)


def content(response: Mapping[str, Any]) -> Any:
    return json.loads(response["result"]["content"][0]["text"])


def tool(
    name: str,
    handler: Callable[[McpSession, Mapping[str, JsonValue]], JsonValue],
    *,
    description: str = "Show a plan revision.",
    permission: str = "plan.read",
    module: str | None = None,
) -> ToolSpec:
    stem = name.removeprefix("skm_").replace("_", "-")
    return ToolSpec(
        name,
        description,
        f"urn:skm:mcp:tool-input:{stem}:v1",
        f"urn:skm:mcp:tool-output:{stem}:v1",
        permission,
        module,
        handler,
    )


def _unused(_session: McpSession, _arguments: Mapping[str, JsonValue]) -> JsonValue:
    raise AssertionError("The handler should never run")


@pytest.mark.parametrize(
    ("requested", "negotiated"),
    [("2024-11-05", "2024-11-05"), ("2025-06-18", "2025-06-18"), ("invalid", "2025-06-18")],
)
def test_initialize_negotiates_version(requested: str, negotiated: str) -> None:
    [answer] = exchange(
        LiveClient().session,
        [
            request("initialize", 7, protocolVersion=requested),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "ping"},
            {"jsonrpc": "2.0", "method": "resources/list"},
        ],
    )
    assert answer["id"] == 7
    assert answer["result"]["protocolVersion"] == negotiated
    assert answer["result"]["capabilities"] == {"tools": {"listChanged": False}}


def test_rejects_batch_and_invalid_requests() -> None:
    [batch, null, version, boolean_id, ping] = exchange(
        LiveClient().session,
        [
            [request("ping")],
            None,
            {"jsonrpc": "1.0", "id": 3, "method": "ping"},
            request("ping", True),
            request("ping", None),
        ],
    )
    for response in (batch, null, version, boolean_id):
        assert response["id"] is None
        assert response["error"]["code"] == -32600
    assert ping == {"jsonrpc": "2.0", "id": None, "result": {}}


def test_broken_json_and_invalid_utf8_are_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    raw = BytesIO(b'\n{broken\n"\xff"\n{"jsonrpc":"2.0","method":"ping","id":"\xc3\xa9"}\n')
    output = BytesIO()
    with TextIOWrapper(raw, encoding="latin1") as stdin, TextIOWrapper(output, encoding="latin1") as stdout:
        assert serve(None, LiveClient().session, stdin, stdout) == 0
        assert output.getvalue() == '{"jsonrpc":"2.0","id":"é","result":{}}\n'.encode()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("mcp.invalid_json") == 2
    assert "broken" not in captured.err


def test_unknown_method_tool_and_invalid_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "TOOLS", (tool("skm_plan_show", _unused),))
    answers = exchange(
        LiveClient().session,
        [
            request("resources/list"),
            call("skm_unknown", {}),
            call("skm_plan_show", {"plan": 7}),
            call("skm_plan_show", []),
            call("skm_plan_show", {"plan": "X", "project_id": str(uuid4())}),
        ],
    )
    assert [answer["error"]["code"] for answer in answers] == [-32601, -32601, -32602, -32602, -32602]
    assert answers[2]["error"]["data"]["issues"][0]["pointer"] == "/plan"
    assert all("result" not in answer for answer in answers)


def test_loop_survives_handler_exception_and_serializes_domain_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_session: McpSession, arguments: Mapping[str, JsonValue]) -> JsonValue:
        if arguments["plan"] == "unknown":
            raise NotFound(ErrorCode.NOT_FOUND, "plan not found in this project", details={"kind": "plan"})
        if arguments["plan"] == "bad-output":
            return {"phases": []}
        raise RuntimeError("private credential, arguments and stack must stay masked")

    monkeypatch.setattr(registry, "TOOLS", (tool("skm_plan_show", fail),))
    [domain, internal, invalid, ping] = exchange(
        LiveClient().session,
        [
            call("skm_plan_show", {"plan": "unknown"}),
            call("skm_plan_show", {"plan": "failure"}, 2),
            call("skm_plan_show", {"plan": "bad-output"}, 3),
            request("ping", 4),
        ],
    )
    assert domain["result"]["isError"] is True
    assert content(domain) == {
        "error": {
            "code": "NOT_FOUND",
            "message": "plan not found in this project",
            "details": {"kind": "plan"},
        }
    }
    assert internal["error"] == invalid["error"] == {"code": -32603, "message": "Internal error"}
    assert ping["result"] == {}
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("mcp.dispatch_failed") == 2
    assert "private credential" not in captured.err


def test_disabled_module_and_assignment_writes_are_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    live = LiveClient(assignment=True)
    live.identity = replace(
        live.identity,
        permissions_by_scope={
            str(live.session.run_id): ("step.note", "memory.read", "memory.write", "plan.publish")
        },
    )
    monkeypatch.setattr(
        registry,
        "TOOLS",
        (
            tool("skm_plan_show", _unused),
            tool("skm_memory_search", _unused, permission="memory.read", module="knowledge"),
            tool("skm_memory_remember", _unused, permission="memory.write", module="knowledge"),
            tool("skm_plan_publish", _unused, permission="plan.publish"),
            tool("skm_record_note", _unused, permission="step.note"),
        ),
    )
    [before, search] = exchange(
        live.session, [request("tools/list"), call("skm_memory_search", {"query": "a"})]
    )
    assert [item["name"] for item in before["result"]["tools"]] == ["skm_plan_show", "skm_record_note"]
    assert search["result"]["isError"] is True
    error = content(search)["error"]
    assert error["code"] == "MODULE_DISABLED"
    assert error["details"] == {"module": "knowledge"}

    live.identity = replace(live.identity, modules={"knowledge": True})
    [after, remember, publish] = exchange(
        live.session,
        [
            request("tools/list"),
            call("skm_memory_remember", {"text": "x", "key": "fact"}),
            call("skm_plan_publish", {}),
        ],
    )
    assert [item["name"] for item in after["result"]["tools"]] == [
        "skm_plan_show",
        "skm_memory_search",
        "skm_record_note",
    ]
    assert remember["result"]["isError"]
    assert content(remember)["error"]["code"] == "FORBIDDEN"
    assert publish["error"]["code"] == -32602


def test_export_tools_inlines_all_packaged_input_schemas() -> None:
    schemas = SchemaRegistry.load_default()
    for urn in sorted(schemas.urns()):
        if not urn.startswith("urn:skm:mcp:tool-input:"):
            continue
        tool_doc = registry.export_tool(schemas, "example", "example", urn)
        raw = protocol.json_text(tool_doc["inputSchema"])
        assert all(keyword not in raw for keyword in ('"$ref"', '"$id"', '"$schema"', '"x-skm'))
    note_schema = registry.export_tool(
        schemas, "skm_plan_entities", "List entities", "urn:skm:mcp:tool-input:plan-entities:v1"
    )
    assert note_schema["inputSchema"]["properties"]["revision_id"]["format"] == "uuid"  # type: ignore[index]


def test_tools_digest_stable() -> None:
    [one, two] = exchange(LiveClient().session, [request("tools/list"), request("tools/list")])
    assert registry.tools_digest(one["result"]["tools"]) == registry.tools_digest(two["result"]["tools"])
    assert (
        registry.tools_digest([]) == "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    )
    schema = SchemaRegistry.load_default()
    listed = registry.export_tool(
        schema, "skm_plan_show", "Show a plan revision.", "urn:skm:mcp:tool-input:plan-show:v1"
    )
    assert (
        registry.tools_digest([listed])
        == "sha256:12a55b97fe217c20977c429fc4ffc3faf2911125a2c37ebe4dcaa6a7a6d51989"
    )


def test_recorded_initialize_list_call_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [json.loads(line) for line in _EXAMPLE.read_text(encoding="utf-8").splitlines()]
    incoming = [row["msg"] for row in rows if row["dir"] == "c2s"]
    expected = {row["msg"]["id"]: row["msg"] for row in rows if row["dir"] == "s2c"}

    def plan_show(_session: McpSession, arguments: Mapping[str, JsonValue]) -> JsonValue:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "plan not found in this project",
            details={"kind": "plan", "ref": arguments["plan"]},
        )

    entries = expected[2]["result"]["tools"]
    handlers = {
        "skm_plan_show": plan_show,
        "skm_task_context": lambda _s, _a: content(expected[3]),
        "skm_ask_question": lambda _s, _a: content(expected[4]),
        "skm_memory_search": lambda _s, _a: {"items": []},
    }
    monkeypatch.setattr(
        registry,
        "TOOLS",
        tuple(
            tool(entry["name"], handlers.get(entry["name"], _unused), description=entry["description"])
            for entry in entries
        ),
    )

    actual = {response["id"]: response for response in exchange(LiveClient().session, incoming)}
    assert actual.keys() == expected.keys()
    assert actual[1]["result"]["protocolVersion"] == expected[1]["result"]["protocolVersion"]
    assert [entry["name"] for entry in actual[2]["result"]["tools"]] == [entry["name"] for entry in entries]
    for ident in (3, 4, 5):
        assert content(actual[ident]) == content(expected[ident])
        assert actual[ident]["result"]["isError"] is expected[ident]["result"]["isError"]
    assert actual[6]["error"]["code"] == expected[6]["error"]["code"]
    assert actual[7]["result"]["isError"] is False
    assert actual[8] == expected[8]
    assert actual[9] == expected[9]
