"""Memory MCP admission, schema validation and project-scoped dispatch."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from contracts.execution.harness import ExecSide, exec_side
from contracts.knowledge.test_lessons import _candidate
from integration.knowledge.test_serena_import import _host, _marked_repository
from integration.mcp.test_protocol import LiveClient, call, content, exchange, request
from skm.adapters.git.repo_inspect import MARKER_FILENAME
from skm.entrypoints.mcp.protocol import json_text
from skm.entrypoints.mcp.registry import TOOLS
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge import public as knowledge
from skm.modules.settings.public import SetValue
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.tokens.heuristic import estimate_tokens
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


@pytest.mark.parametrize(("enabled", "assignment"), [(False, False), (False, True), (True, True)])
def test_memory_admission(enabled, assignment):
    live = LiveClient(assignment=assignment)
    live.identity = replace(
        live.identity,
        modules={"knowledge": enabled},
        effective_permissions=("project.read", "memory.write", "memory.read"),
    )
    listing, response, unknown = exchange(
        live.session,
        [
            request("tools/list"),
            call("skm_memory_remember", {"key": "context", "text": "Private"}),
            call("skm_graph_neighbors", {"node_key": "doc:missing"})
            if not enabled
            else call("skm_unknown", {}),
        ],
    )
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert "skm_memory_remember" not in names
    assert ("skm_memory_search" in names) == enabled
    assert ({"skm_graph_neighbors", "skm_graph_path"} <= names) == enabled
    assert content(response)["error"]["code"] == ("FORBIDDEN" if assignment else "MODULE_DISABLED")
    if enabled:
        assert unknown["error"]["code"] == -32601
    else:
        assert content(unknown)["error"]["code"] == "MODULE_DISABLED"


def test_schemas_exclude_scope_overrides():
    registry = SchemaRegistry.load_default()
    for tool in (tool for tool in TOOLS if tool.module == "knowledge"):
        schema = registry.get(tool.input_schema_urn)
        assert schema["additionalProperties"] is False
        properties = schema["properties"]
        assert isinstance(properties, dict)
        assert "project_id" not in properties
        assert "workspace_id" not in properties
        assert registry.validate(tool.input_schema_urn, {"scope": "global", "namespace": "other"})


def test_project_scoped_lesson_token(exec_side: ExecSide):
    side = exec_side
    with side.uow() as uow:
        knowledge.promote_lesson(
            uow,
            _candidate(side.ws, side.proj, "Wait for the pool"),
            actor=side.owner,
            now=side.clock.now(),
            supersedes=None,
        )
        uow.commit()
    reader = side.restricted_client(["project.read", "lesson.read"], scope_id=side.proj, owner_token=True)
    listing, response = exchange(
        McpSession.open(reader, project_id=side.proj),
        [request("tools/list"), call("skm_lessons_list", {"query": "Pool"})],
    )
    assert "skm_lessons_list" in {tool["name"] for tool in listing["result"]["tools"]}
    assert content(response)["items"][0]["body"] == "Wait for the pool"


def test_round_trip(exec_side: ExecSide):
    side = exec_side
    client = side.restricted_client(
        ["project.read", "memory.read", "memory.write", "lesson.read"], owner_token=True
    )
    session = McpSession.open(client, project_id=side.proj)

    def invoke(name, args):
        [response] = exchange(session, [call("skm_" + name, args)])
        assert not response["result"]["isError"], content(response)
        return content(response)

    entry = invoke("memory_remember", {"key": "active-handoff", "text": "Pool unavailable"})
    assert invoke("memory_search", {"query": "Pool"})["items"][0]["entry_id"] == entry["entry_id"]
    invoke("memory_remember", {"key": "context", "text": "Pool " + "p" * 700})
    bounded = replace(session, limits={"api.mcp.max_response_tokens": 90})
    [response] = exchange(bounded, [call("skm_memory_search", {"query": "Pool"})])
    compact = content(response)
    assert compact["items_truncated"]["truncated"]
    assert compact["items_truncated"]["returned_count"] == len(compact["items"])
    assert compact["items_truncated"]["total_count"] == 2
    assert invoke("memory_forget", {"entry_id": entry["entry_id"]}) == {"forgotten": 1}


def test_forget_with_write_only_permission(exec_side: ExecSide):
    side = exec_side
    side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(side.proj)},
                "key": "knowledge.memory.namespaces",
                "value": ["squad-a"],
            }
        )
    )
    shared: Any = side.client.dispatch(
        knowledge.Remember.from_json(
            {
                "project_id": str(side.proj),
                "scope": {"kind": "namespace", "namespace": "squad-a"},
                "kind": "context",
                "body": "Shared pool status",
                "ttl_hours": None,
                "source": "api",
            }
        ),
        idempotency_key=side.client.new_idempotency_key(),
    )
    writer = side.restricted_client(["project.read", "memory.write"], scope_id=side.proj, owner_token=True)
    session = McpSession.open(writer, project_id=side.proj)
    listing, remembered = exchange(
        session,
        [request("tools/list"), call("skm_memory_remember", {"key": "context", "text": "Private pool"})],
    )
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert "skm_memory_forget" in names
    assert "skm_memory_search" not in names
    forgotten, denied = exchange(
        session,
        [
            call("skm_memory_forget", {"entry_id": content(remembered)["entry_id"]}),
            call("skm_memory_forget", {"entry_id": shared["entry_id"]}),
        ],
    )
    assert content(forgotten) == {"forgotten": 1}
    assert content(denied)["error"]["code"] == "NOT_FOUND"


def test_graph_tools_are_project_scoped_and_report_evidence(
    exec_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    side = exec_side
    root_path = tmp_path / "checkout"
    _host(side, root_path)
    repo = _marked_repository(root_path, side)
    revision = repo.commit_file()
    monkeypatch.chdir(root_path)
    root, neighbor, outside = "doc:root", "doc:neighbor", "doc:outside"
    payload = {
        "workspace_id": str(side.ws),
        "project_id": str(side.proj),
        "repository_id": str(side.repo_id),
        "source": "mcp-test",
        "index": {
            "revision": revision,
            "dirty": False,
            "languages": ["python"],
            "basis_default": "declared",
            "tool_name": "fixture",
            "tool_version": "1",
            "indexed_at": side.clock.now().isoformat(),
            "completeness": "complete",
            "limitations": [],
            "files_indexed": 2,
            "files_skipped": 0,
        },
        "nodes": [
            {"node_key": root, "type": "doc", "attrs": {"text": "a" * 3000}},
            {"node_key": neighbor, "type": "doc", "attrs": {"text": "b" * 3000}},
        ],
        "edges": [
            {
                "src_key": root,
                "dst_key": neighbor,
                "type": "references",
                "attrs": {"text": "c" * 3000},
                "source_key": "",
            }
        ],
    }
    side.client.dispatch(
        knowledge.ImportGraph.from_json(payload), idempotency_key=side.client.new_idempotency_key()
    )
    side.client.dispatch(
        knowledge.ImportGraph.from_json(
            {
                **payload,
                "project_id": None,
                "source": "workspace-test",
                "nodes": [{"node_key": outside, "type": "doc", "attrs": {}}],
                "edges": [],
            }
        ),
        idempotency_key=side.client.new_idempotency_key(),
    )
    reader = side.restricted_client(["project.read", "memory.read"], scope_id=side.proj, owner_token=True)
    session = McpSession.open(reader, project_id=side.proj)
    neighbors: JsonObject = {"node_key": root, "at_revision": "b" * 40}
    path: JsonObject = {"src_key": root, "dst_key": neighbor, "at_revision": revision}
    listing, fresh, denied, foreign = exchange(
        session,
        [
            request("tools/list"),
            call("skm_graph_neighbors", neighbors),
            call("skm_graph_path", {**path, "project_id": str(side.proj2)}),
            call("skm_graph_neighbors", {"node_key": outside}),
        ],
    )
    for tool in listing["result"]["tools"]:
        if tool["name"] in {"skm_graph_neighbors", "skm_graph_path"}:
            assert "freshness.state" in tool["description"]
            assert "completeness" in tool["description"]
    assert content(fresh)["freshness"]["state"] == "fresh"
    assert content(fresh)["freshness"]["at_revision"] == revision
    repo.add_remote("origin", "https://example.invalid/skm.git")
    (root_path / MARKER_FILENAME).unlink()
    head = repo.commit_file(content="HEAD moved")
    [stale] = exchange(session, [call("skm_graph_path", path)])
    assert content(stale)["freshness"]["at_revision"] == head
    assert content(fresh)["completeness"] == "complete"
    assert content(stale)["freshness"]["state"] == "stale"
    assert content(stale)["path"] == [root, neighbor]
    assert denied["error"]["code"] == -32602
    assert content(foreign)["error"]["code"] == "NOT_FOUND"
    limit = 700
    bounded = replace(session, limits={"api.mcp.max_response_tokens": limit})
    [response] = exchange(bounded, [call("skm_graph_neighbors", neighbors)])
    compact = content(response)
    assert estimate_tokens(json_text(compact)) <= limit
    assert compact["freshness"]["state"] == "stale"
    assert compact["completeness"] == "complete"
    assert compact["nodes_truncated"]["total_count"] == 2
    assert compact["nodes_truncated"]["returned_count"] == len(compact["nodes"])
    assert compact["edges_truncated"]["total_count"] == 1
    assert compact["edges_truncated"]["returned_count"] == len(compact["edges"])

    side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(side.proj)},
                "key": "knowledge.graph.enabled",
                "value": False,
            }
        )
    )
    [disabled] = exchange(session, [call("skm_graph_neighbors", neighbors)])
    assert content(disabled)["error"]["code"] == "MODULE_DISABLED"
