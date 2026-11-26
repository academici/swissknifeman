"""Check token fitting and continuation of pinned authoring responses over stdio."""

import json
from collections.abc import Iterator, Mapping
from io import StringIO
from typing import Any, override
from uuid import uuid4

import pytest

from integration.mcp.test_protocol import LiveClient, call, content, exchange, request, tool
from skm.entrypoints.mcp import protocol, registry
from skm.entrypoints.mcp.server import serve
from skm.entrypoints.mcp.session import McpSession
from skm.entrypoints.mcp.truncation import fit
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.tokens.heuristic import estimate_tokens


def test_truncation_receipt_fits_maximal_prefix_of_largest_top_level_list() -> None:
    limit = 150
    items: list[JsonValue] = ["кириллица" * 9] * 12
    names: list[JsonValue] = ["x"] * 15
    payload: JsonObject = {"items": items, "names": names, "next": "owner-cursor"}
    out, receipt = fit(payload, limit)
    assert isinstance(out, dict)
    assert receipt is not None
    assert receipt.truncated
    assert 0 < receipt.returned_count < receipt.total_count == len(items)
    assert out == {**payload, "items": items[: receipt.returned_count], "items_truncated": receipt.to_json()}
    assert estimate_tokens(protocol.json_text(out)) <= limit
    # The next item cannot fit, even before any extra receipt digits are counted.
    next_out: JsonObject = {**out, "items": items[: receipt.returned_count + 1]}
    assert estimate_tokens(protocol.json_text(next_out)) > limit


def test_root_lists_and_compact_json() -> None:
    values: list[JsonValue] = ["x" * 85] * 20
    fitted, receipt = fit(values, 100)
    assert receipt is not None
    assert fitted == {"items": values[: receipt.returned_count], **receipt.to_json()}
    short: JsonObject = {"items": [1, 2, 3]}
    assert fit(short, estimate_tokens(protocol.json_text(short))) == (short, None)


def test_errors_never_truncated_and_overflow_without_list_is_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    details: list[JsonValue] = ["private details" * 100] * 4
    error: JsonObject = {"error": {"details": details}}
    assert fit(error, 100, is_error=True) == (error, None)
    assert capsys.readouterr().err == ""
    original: JsonObject = {"text": "long " * 100}
    assert fit(original, 100) == (original, None)
    assert "mcp.response_over_budget" in capsys.readouterr().err


class _Conversation(StringIO):
    """Produce requests from previous responses while keeping a single server session."""

    def __init__(self, requests: Iterator[JsonValue]) -> None:
        super().__init__()
        self.requests = requests

    @override
    def readline(self, size: int | None = -1) -> str:
        item = next(self.requests, None)
        return "" if item is None else protocol.json_text(item) + "\n"


def _latest(output: StringIO) -> dict[str, Any]:
    return json.loads(output.getvalue().splitlines()[-1])


def _source(kind: str) -> JsonObject:
    out: JsonObject = {"plan_id": str(uuid4()), "kind": kind, "document_digest": "sha256:" + "a" * 64}
    if kind == "draft":
        out.update(draft_id=str(uuid4()), edit_version=5)
    else:
        out["revision_id"] = str(uuid4())
    return out


@pytest.mark.parametrize("limit", [1, 200], ids=["receipt-too-large", "no-item-fits"])
def test_authoring_call_reports_budget_that_cannot_fit_an_item_and_receipt(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    item: JsonObject = {
        "entity_id": str(uuid4()),
        "entity_kind": "unit",
        "display_key": "P1.2/U1",
        "title": "x" * 1000,
        "parent_id": None,
        "position": 1,
        "children_count": 0,
    }
    page: JsonObject = {"source": _source("revision"), "items": [item], "next_cursor": "next"}
    name = "skm_plan_entities"
    monkeypatch.setattr(registry, "TOOLS", (tool(name, lambda _session, _args: page),))

    (response,) = exchange(LiveClient(limit=limit).session, [call(name, {"plan": "PLAN1"})])
    assert response["result"]["isError"] is True
    error = content(response)["error"]
    assert error["code"] == "PAYLOAD_TOO_LARGE"
    assert error["details"] == {"tool": name, "max_response_tokens": limit}


def test_fetch_preserves_owner_cursor_and_filters_while_finishing_a_trimmed_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source("revision")
    new_revision = {**source, "revision_id": str(uuid4())}
    current: JsonObject = source
    seen: list[JsonObject] = []
    items: list[JsonValue] = [
        {
            "entity_id": str(uuid4()),
            "entity_kind": "unit",
            "display_key": f"P1.2/U{index}",
            "title": "Unit with a long Cyrillic title: " + "Пример " * 30,
            "parent_id": None,
            "position": index,
            "children_count": 0,
        }
        for index in range(8)
    ]

    def list_entities(_session: McpSession, arguments: Mapping[str, JsonValue]) -> JsonValue:
        seen.append(dict(arguments))
        chosen = source if arguments.get("revision_id") == source["revision_id"] else current
        if arguments["after"] == "owner-next":
            return {"items": [], "source": chosen, "next_cursor": None}
        return {"items": items, "source": chosen, "next_cursor": "owner-next"}

    monkeypatch.setattr(registry, "TOOLS", (tool("skm_plan_entities", list_entities),))
    output = StringIO()
    original: JsonObject = {"plan": "PLAN1", "kinds": ["unit"], "limit": 8, "after": "owner-start"}

    def requests() -> Iterator[JsonValue]:
        nonlocal current
        yield request("tools/list")
        assert [row["name"] for row in _latest(output)["result"]["tools"]] == [
            "skm_plan_entities",
            "skm_fetch",
        ]
        yield call("skm_plan_entities", original)
        current = new_revision
        assembled: list[JsonValue] = []
        for _ in range(len(items)):
            page = content(_latest(output))
            assert page["source"] == source
            assert page["next_cursor"] == "owner-next"
            assert estimate_tokens(protocol.json_text(page)) <= 360
            assembled.extend(page["items"])
            assert page["authoring_receipt"]
            if len(assembled) == len(items):
                assert "items_truncated" not in page
                yield call("skm_fetch", {"receipt": page["authoring_receipt"]})
                assert content(_latest(output)) == {"items": [], "source": source, "next_cursor": None}
                break
            assert page["items_truncated"]["truncated"]
            yield call("skm_fetch", {"receipt": page["authoring_receipt"]})
        assert assembled == items

    live = LiveClient(limit=360)
    assert serve(None, live.session, _Conversation(requests()), output) == 0
    assert seen[0] == original
    pinned = {**original, "plan": source["plan_id"], "revision_id": source["revision_id"]}
    assert seen[1:-1]
    assert all(arguments == pinned for arguments in seen[1:-1])
    assert seen[-1] == {**pinned, "after": "owner-next"}
    assert live.checks == [live.session.project_id] * (len(seen) + 1)


def test_over_budget_text_fragment_returns_a_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "skm_plan_read_text"
    fragment: JsonObject = {
        "source": _source("revision"),
        "target_entity_id": None,
        "pointer": "/goal",
        "text_digest": "sha256:" + "b" * 64,
        "total_bytes": 1024,
        "offset_bytes": 0,
        "end_offset_bytes": 512,
        "text": "x" * 512,
        "truncated": True,
        "omitted_bytes": 512,
        "next_offset_bytes": 512,
    }
    monkeypatch.setattr(registry, "TOOLS", (tool(name, lambda _session, _args: fragment),))
    (response,) = exchange(
        LiveClient(limit=100).session, [call(name, {"plan": "PLAN1", "target": "root", "pointer": "/goal"})]
    )
    assert response["result"]["isError"] is True
    assert content(response)["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_fetch_rejects_parameter_substitution_stale_sources_and_revocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source("draft")
    live = LiveClient()
    output = StringIO()
    seen: list[JsonObject] = []
    deny_read = False

    def read_text(_session: McpSession, arguments: Mapping[str, JsonValue]) -> JsonValue:
        seen.append(dict(arguments))
        if deny_read:
            raise Forbidden(ErrorCode.FORBIDDEN, "plan.read is no longer granted")
        offset = arguments.get("offset_bytes", 0)
        return {
            "source": source,
            "target_entity_id": None,
            "pointer": "/goal",
            "text_digest": "sha256:" + "b" * 64,
            "total_bytes": 20,
            "offset_bytes": offset,
            "end_offset_bytes": 10,
            "text": "abcdefghij",
            "truncated": True,
            "omitted_bytes": 10,
            "next_offset_bytes": 10,
        }

    monkeypatch.setattr(registry, "TOOLS", (tool("skm_plan_read_text", read_text),))
    original: JsonObject = {
        "plan": "PLAN1",
        "draft_id": source["draft_id"],
        "expected_edit_version": 5,
        "target": "root",
        "pointer": "/goal",
        "max_bytes": 10,
    }

    def requests() -> Iterator[JsonValue]:
        nonlocal deny_read
        yield call("skm_plan_read_text", original)
        first = content(_latest(output))
        token = first["authoring_receipt"]
        for replacement in ({"expected_edit_version": 6}, {"pointer": "/title"}, {"offset_bytes": 18}):
            yield call("skm_fetch", {"receipt": token, **replacement})
            assert _latest(output)["error"]["code"] == -32602
        assert len(seen) == 1
        deny_read = True
        yield call("skm_fetch", {"receipt": token})
        assert content(_latest(output))["error"]["code"] == "FORBIDDEN"
        deny_read = False
        source["edit_version"] = 6
        yield call("skm_fetch", {"receipt": token})
        stale = _latest(output)
        assert stale["result"]["isError"] is True
        assert content(stale)["error"]["code"] == "VERSION_CONFLICT"
        live.revoked = True
        yield call("skm_fetch", {"receipt": token})
        assert content(_latest(output))["error"]["code"] == "UNAUTHENTICATED"
        yield request("ping")
        assert _latest(output)["result"] == {}

    assert serve(None, live.session, _Conversation(requests()), output) == 0
    pinned = {**original, "plan": source["plan_id"], "offset_bytes": 10}
    assert seen == [original, pinned, pinned]
