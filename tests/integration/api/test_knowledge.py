"""Exercise scoped knowledge routes, stale handoffs and lesson HTTP preconditions."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from contracts.execution.harness import ExecSide, exec_side
from contracts.knowledge.test_lessons import _candidate
from integration.api.test_planning import ok, problem
from integration.knowledge.test_serena_import import _export, _host
from integration.mcp.test_tools import authenticate, client_for
from security.api.harness import BASE, TestClient
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access
from skm.modules.knowledge import public as knowledge
from skm.modules.knowledge.host.import_code_graph import import_code_graph
from skm.modules.settings.public import SetValue
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


def _api(side: ExecSide):
    core = replace(side.app, authenticator=lambda secret: authenticate(side, secret))
    registry = core.bus._registry
    return create_app(
        core,
        route_table=build_route_table(set(MODULE_IDS) - registry.disabled_modules()),
        registry=registry,
        schema_check=lambda: None,
        no_background=True,
    )


def test_knowledge_routes(exec_side: ExecSide):
    side = exec_side
    token: Any = side.client.dispatch(access.CreateToken(name="knowledge HTTP"))
    api = _api(side)
    memory = f"/api/v1/projects/{side.proj}/memory"
    lessons = f"/api/v1/workspaces/{side.ws}/lessons"
    with TestClient(api, base_url=BASE, headers={"Authorization": f"Bearer {token.secret}"}) as http:

        def post(path, body, **headers):
            return http.post(path, json=body, headers={"Idempotency-Key": str(uuid4()), **headers})

        body = {"kind": "active_handoff", "body": "Waiting for pool", "ttl_hours": None, "source": "api"}
        first = ok(post(memory, body), 201)["entry_id"]
        replacement = {**body, "body": "Pool available", "expected_handoff_id": first}

        def embedded_replace() -> Any:
            command = knowledge.Remember.from_json({**replacement, "project_id": str(side.proj)})
            try:
                return side.client.dispatch(command, idempotency_key=str(uuid4()))
            except Conflict as error:
                return error

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(embedded_replace)
            response = post(memory, replacement)
            winner = pending.result(timeout=10)
        if isinstance(winner, Conflict):
            assert winner.code.value == "VERSION_CONFLICT"
            current = ok(response, 201)["entry_id"]
        else:
            problem(response, 409, "VERSION_CONFLICT")
            current = winner["entry_id"]
        for shared in ("false", "true"):
            assert (
                ok(http.get(memory, params={"q": "available", "include_shared": shared}))["items"][0]["id"]
                == current
            )
        assert ok(http.get(memory + "/entries"))["items"][0]["id"] == current
        ok(post(memory, {**body, "kind": "context", "body": "Pool status available"}), 201)
        query = {"q": "available"}
        recalled = ok(http.get(memory, params=query))
        assert len(recalled["items"]) == 2
        limited = ok(http.get(memory, params={**query, "limit": 1}))
        assert limited == {"items": recalled["items"][:1], "truncated": True}
        for invalid_limit in ("0", "1.5"):
            problem(http.get(memory, params={"limit": invalid_limit}), 422, "SCHEMA_INVALID")
        foreign = f"/api/v1/projects/{side.proj2}/memory"
        problem(post(f"{foreign}/{current}/forget", {}), 404, "NOT_FOUND")
        assert ok(post(f"{memory}/{current}/forget", {})) == {"forgotten": 1}

        with side.uow() as uow:
            lesson = knowledge.promote_lesson(
                uow,
                _candidate(side.ws, side.proj, "Wait"),
                actor=side.owner,
                now=side.clock.now(),
                supersedes=None,
            )
            uow.commit()
        detail = f"{lessons}/{lesson.lesson_id}"
        shown = http.get(detail)
        assert ok(shown)["state"] == "curated"
        assert ok(http.get(lessons, params={"project_id": str(side.proj)}))["items"][0]["id"] == str(
            lesson.lesson_id
        )
        problem(http.get(detail.replace(str(side.ws), str(side.ws2))), 404, "NOT_FOUND")
        problem(
            http.get(lessons.replace(str(side.ws), str(side.ws2)), params={"project_id": str(side.proj)}),
            404,
            "NOT_FOUND",
        )
        assert shown.headers["etag"] == 'W/"v1"'
        change = detail + "/deprecate"
        assert post(change, {"reason": "Retired"}).status_code == 428
        assert (
            ok(post(change, {"reason": "Retired"}, **{"If-Match": shown.headers["etag"]}))["state"]
            == "deprecated"
        )


def test_graph_import_chunking_matches_embedded_and_http(exec_side: ExecSide, tmp_path: Path) -> None:
    side = exec_side
    initial_limit = 1_048_576
    limit = 1_200_000

    def set_limit(value: int) -> None:
        side.client.dispatch(
            SetValue.from_json(
                {"scope": {"level": "instance"}, "key": "knowledge.graph.import_max_bytes", "value": value}
            )
        )

    set_limit(initial_limit)
    ctx = _host(side, tmp_path / "checkout", **{"knowledge.graph.import_max_bytes": limit})
    export = _export(tmp_path / "checkout", side)
    snapshot = json.loads(export.read_text(encoding="utf-8"))
    snapshot["symbols"].extend(
        {"path": "src/app.py", "qualified_name": f"extra_{number}", "metadata": "⚙" * 4000}
        for number in range(100)
    )
    export.write_text(json.dumps(snapshot), encoding="utf-8")
    request: JsonObject = {"project_id": str(side.proj), "mount": "repo"}
    token: Any = side.client.dispatch(access.CreateToken(name="graph HTTP"))
    headers = {"Authorization": f"Bearer {token.secret}"}
    graph = f"/api/v1/workspaces/{side.ws}/graph"
    first, second = (f"symbol:{side.repo_id}:src/app.py#{name}" for name in ("Runner.execute", "run"))
    roots = {"roots": [first, second], "depth": 0, "edge_types": ["references"]}
    indexes = knowledge.ListGraphIndexes.from_json({"workspace_id": str(side.ws), "source": "serena"})
    with TestClient(_api(side), base_url=BASE, headers=headers) as http:

        def oversized_stream():
            pytest.fail("HTTP admission read the body despite an oversized Content-Length")
            yield b""

        rejected = http.post(
            graph + "/import",
            content=oversized_stream(),
            headers={"Content-Length": str(limit), "Content-Type": "application/json"},
        )
        problem(rejected, 413, "PAYLOAD_TOO_LARGE")
        set_limit(limit)
        remote = client_for(side, http, tmp_path, "http", token.secret)
        # Both transports ingest the same synthetic host snapshot.
        embedded = import_code_graph(ctx, request)
        via_http = import_code_graph(replace(ctx, client=remote), request)
        assert via_http["chunks"] == embedded["chunks"] == 2
        for field in ("nodes_upserted", "edges_added", "edges_rejected"):
            assert via_http[field] == embedded[field]
        assert via_http["generation"] == 2 * cast("int", embedded["generation"])

        answer = ok(http.get(graph + "/subgraph", params=roots))
        assert answer == remote.ask(
            knowledge.GraphSubgraph.from_json({"workspace_id": str(side.ws), **roots})
        )
        assert {node["node_key"] for node in answer["nodes"]} == {first, second}
        revision = snapshot["index"]["revision"]
        fresh = ok(http.get(graph + "/subgraph", params={**roots, "at_revision": revision}))
        assert fresh["freshness"]["state"] == "fresh"
        moved = ok(http.get(graph + "/subgraph", params={**roots, "at_revision": "b" * 40}))
        assert moved["freshness"]["state"] == "stale"
        neighbors = {"node": first, "depth": 3}
        assert ok(http.get(graph + "/neighbors", params=neighbors)) == remote.ask(
            knowledge.GraphNeighbors.from_json({"workspace_id": str(side.ws), "node_key": first, "depth": 3})
        )
        assert [edge["type"] for edge in answer["edges"]] == ["references"]
        latest: Any = remote.ask(indexes)
        assert latest == side.client.ask(indexes)
        assert ok(http.get(graph + "/indexes", params={"source": "serena"})) == latest["items"]
        assert [(row["source"], row["generation"]) for row in latest["items"]] == [
            ("serena", via_http["generation"])
        ]

        url = graph + "/import"
        wrong_workspace = url.replace(str(side.ws), str(side.ws2))
        body = {
            "project_id": str(side.proj),
            "repository_id": str(side.repo_id),
            "source": "serena",
            "index": snapshot["index"],
            "nodes": [],
            "edges": [],
        }
        idem_headers = {"Idempotency-Key": str(uuid4())}
        problem(http.post(wrong_workspace, json=body, headers=idem_headers), 404, "NOT_FOUND")
        oversized = {
            **body,
            "nodes": [
                {"node_key": f"doc:{side.repo_id}:src/{n}.py", "type": "doc", "attrs": {"data": "x" * 12000}}
                for n in range(100)
            ],
        }
        with pytest.raises(ValidationFailed) as rejected:
            side.client.dispatch(
                knowledge.ImportGraph.from_json({"workspace_id": str(side.ws), **oversized}),
                idempotency_key=str(uuid4()),
            )
        assert rejected.value.details["reason"] == "too_large"
        problem(http.post(url, json=oversized, headers=idem_headers), 413, "PAYLOAD_TOO_LARGE")
        streamed = http.post(
            url,
            content=iter((b" " * limit, b" ")),
            headers={**idem_headers, "Content-Type": "application/json"},
        )
        problem(streamed, 413, "PAYLOAD_TOO_LARGE")
        assert remote.ask(indexes) == latest


def test_http_neighbors_depth_cap(exec_side: ExecSide) -> None:
    side = exec_side
    token: Any = side.client.dispatch(access.CreateToken(name="graph depth"))
    url = f"/api/v1/workspaces/{side.ws}/graph/neighbors"
    with TestClient(_api(side), base_url=BASE, headers={"Authorization": f"Bearer {token.secret}"}) as http:
        problem(http.get(url, params={"node": "doc:root", "depth": 4}), 422, "SCHEMA_INVALID")
        api_contract = ok(http.get("/api/v1/openapi.json"))
        operation = api_contract["paths"]["/workspaces/{workspace_id}/graph/neighbors"]["get"]
        depth = next(parameter for parameter in operation["parameters"] if parameter["name"] == "depth")
        assert depth["schema"]["maximum"] == 3


def test_graph_reads_refuse_disabled_effective_scope(exec_side: ExecSide) -> None:
    side = exec_side
    token: Any = side.client.dispatch(access.CreateToken(name="graph disabled"))
    base = f"/api/v1/workspaces/{side.ws}/graph"

    with TestClient(_api(side), base_url=BASE, headers={"Authorization": f"Bearer {token.secret}"}) as http:
        for level, scope_id, queries in (
            (
                "project",
                side.proj,
                [
                    ("neighbors", {"node": "doc:root", "project_id": str(side.proj)}),
                    ("path", {"from": "doc:root", "to": "doc:target", "project_id": str(side.proj)}),
                    ("stats", {"project_id": str(side.proj)}),
                ],
            ),
            (
                "workspace",
                side.ws,
                [
                    ("neighbors", {"node": "doc:root"}),
                    ("path", {"from": "doc:root", "to": "doc:target"}),
                    ("subgraph", {"roots": "doc:root"}),
                    ("stats", {}),
                    ("indexes", {}),
                ],
            ),
        ):
            side.client.dispatch(
                SetValue.from_json(
                    {
                        "scope": {"level": level, "scope_id": str(scope_id)},
                        "key": "knowledge.graph.enabled",
                        "value": False,
                    }
                )
            )
            for verb, params in queries:
                problem(http.get(f"{base}/{verb}", params=params), 409, "MODULE_DISABLED")
