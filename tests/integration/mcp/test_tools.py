"""Published MCP tools against the same PostgreSQL application over embedded and HTTP clients."""

import json
import secrets
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin, claim, make_case, worker_claim
from contracts.execution.harness import PEPPER, ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_lock_order import expire_now
from fixtures.execution.protocol import add_budget
from integration.api.test_artifacts_routes import put_blob
from integration.api.test_worker_protocol import (
    checked,
    empty_output,
    post,
    prepare_runtime,
    problem,
    prompt_wire,
    worker_api,
)
from integration.api.test_worker_protocol import worker_side as worker_side
from integration.mcp.test_protocol import call, content, exchange, request
from integration.mcp.test_truncation import _Conversation, _latest
from security.api.harness import BASE, TestClient
from skm.adapters.http_client.client import HttpSkmClient
from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.commands import mcp
from skm.entrypoints.cli.main import main
from skm.entrypoints.mcp.registry import tools_digest
from skm.entrypoints.mcp.server import serve
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.actor import Actor
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.execution.ports import StepRepository
from skm.modules.planning import public as planning
from skm.modules.settings import public as settings
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.logging import setup
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

pytestmark = [pytest.mark.pg, pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)]


def authenticate(side: ExecSide, secret: str) -> Actor:
    with side.uow(readonly=True) as uow:
        return access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())


@pytest.fixture
def transport(worker_side: Any) -> Iterator[TestClient]:
    side, _, _ = worker_side
    routes = build_route_table(MODULE_IDS)
    api = create_app(
        replace(side.app, authenticator=lambda value: authenticate(side, value)),
        route_table=routes,
        registry=side.app.bus._registry,
        schema_check=lambda: None,
        no_background=True,
    )
    with TestClient(api, base_url=BASE) as http:
        yield http


def test_disabled_knowledge_routes(worker_side: Any, tmp_path: Path) -> None:
    side, _, owner = worker_side
    change: JsonObject = {"scope": {"level": "instance"}, "key": "modules.knowledge.enabled", "value": False}
    side.client.dispatch(settings.SetValue.from_json({**change, "reason": "Disable knowledge for the test"}))
    env = {"SKM_DATABASE_URL": side.dsn, "SKM_INSTANCE_ID": str(side.app.instance_id)}
    bootstrap = load_bootstrap(None, env, tmp_path)
    overrides = CompositionOverrides(access.RbacAuthorizer(side.clock), StoredScopeChain(), clock=side.clock)
    core = build_app(
        bootstrap, surface=Surface.API, environ=env, invocation={}, backend="postgres", overrides=overrides
    )
    with closing(core):
        registry = core.bus._registry
        api = create_app(
            replace(core, authenticator=lambda secret: authenticate(side, secret)),
            route_table=build_route_table(set(MODULE_IDS) - registry.disabled_modules()),
            registry=registry,
            no_background=True,
        )
        with TestClient(api, base_url=BASE, headers=owner) as http:
            path = f"/api/v1/projects/{side.proj}/memory"
            problem(http.get(path), 409, "MODULE_DISABLED")
            problem(http.post(path, json={}), 409, "MODULE_DISABLED")
            published = http.get("/api/v1/openapi.json").json()["paths"]
            assert not any(set(path.split("/")) & {"memory", "lessons", "graph"} for path in published)


def client_for(
    side: ExecSide, transport: TestClient, root: Path, mode: str, secret: str, *, run_id: UUID | None = None
) -> SkmClient:
    if mode == "embedded":
        return side.app.client(actor=authenticate(side, secret), surface=Surface.MCP)
    return HttpSkmClient(
        BASE,
        SecretValue(SecretRef.parse("secret://env/SKM_TOKEN"), secret),
        build_route_table(MODULE_IDS),
        spool_root=root / "spool",
        storage_budget=build_host_storage(root),
        min_free_bytes=0,
        http=transport,
        run_scope_id=run_id,
    )


def answer(session: McpSession, name: str, args: JsonObject) -> Any:
    [response] = exchange(session, [call("skm_" + name, args)])
    assert "error" not in response, response
    assert response["result"]["isError"] is False, content(response)
    return content(response)


def assert_authoring_continuations(session: McpSession, plan: str) -> None:
    output = StringIO()

    def messages() -> Iterator[JsonObject]:
        yield call("skm_plan_entities", {"plan": plan, "limit": 1})
        first = content(_latest(output))
        assert "items" in first, first
        assert len(first["items"]) == 1
        yield call("skm_fetch", {"receipt": first["authoring_receipt"]})
        second = content(_latest(output))
        assert first["source"] == second["source"]
        assert first["items"] != second["items"]
        yield call("skm_plan_read_text", {"plan": plan, "target": "plan", "pointer": "/goal", "max_bytes": 8})
        fragment = content(_latest(output))
        assert "truncated" in fragment, fragment
        assert fragment["truncated"]
        yield call("skm_fetch", {"receipt": fragment["authoring_receipt"]})
        continuation = content(_latest(output))
        assert continuation["offset_bytes"] == fragment["end_offset_bytes"]
        assert continuation["text_digest"] == fragment["text_digest"]

    assert serve(None, session, _Conversation(messages()), output) == 0


@pytest.mark.parametrize("mode", ["embedded", "http"])
def test_authoring_tools(worker_side: Any, transport: TestClient, tmp_path: Path, mode: str) -> None:
    side, _, owner = worker_side
    owner_client = client_for(side, transport, tmp_path, "embedded", owner["Authorization"].split()[1])
    editor = cast(
        "access.CreateTokenResult",
        owner_client.dispatch(
            access.CreateToken(
                name="MCP editor",
                scope_id=side.proj,
                permissions=("project.read", "plan.read", "plan.edit", "plan.publish", "file.read"),
            )
        ),
    )
    client = client_for(side, transport, tmp_path, mode, editor.secret)
    session = McpSession.open(client, project_id=side.proj)
    plan = str(side.plan1)
    listing = answer(session, "plan_list", {"limit": 1})
    assert listing["items"]
    shown = answer(session, "plan_show", {"plan": plan, "revision": 1, "include_tree": False})
    assert shown["revision_no"] == 1
    assert "phases" not in shown
    entity = answer(session, "plan_entity", {"plan": plan, "entity": "P1.1/U1", "revision": 1})
    assert entity["source"]["revision_id"] == str(side.rev1)

    assert_authoring_continuations(session, plan)

    open_args: JsonObject = {"plan": plan, "idempotency_key": "mcp-open"}
    draft = answer(session, "plan_draft_open", open_args)
    assert draft == answer(session, "plan_draft_open", open_args)
    other = answer(session, "plan_draft_open", {"plan": plan, "idempotency_key": "mcp-other"})
    base: JsonObject = {
        "plan": plan,
        "draft_id": draft["draft_id"],
        "expected_edit_version": draft["edit_version"],
    }
    fragment = answer(session, "plan_read_text", {**base, "target": "plan", "pointer": "/goal"})
    change = {
        "op": "replace_text",
        "target": "plan",
        "pointer": "/goal",
        "expected_text_digest": fragment["text_digest"],
        "old_text": fragment["text"],
        "new_text": "Verify authoring through MCP",
    }
    stored = answer(session, "plan_draft_save", {**base, "changes": [change]})
    [stale] = exchange(session, [call("skm_plan_publication_preview", base)])
    assert content(stale)["error"]["code"] == "VERSION_CONFLICT"
    base["expected_edit_version"] = stored["edit_version"]
    preview = answer(session, "plan_publication_preview", base)
    publish_args = {
        **base,
        "expected_content_digest": preview["content_digest"],
        "reason": "MCP publication",
        "idempotency_key": "mcp-publish",
    }
    published = answer(session, "plan_publish", publish_args)
    assert published == answer(session, "plan_publish", publish_args)
    direct = cast(
        "planning.PublishRevisionResult",
        client.dispatch(
            planning.PublishRevision.from_json(
                {
                    **{k: v for k, v in publish_args.items() if k not in {"plan", "idempotency_key"}},
                    "plan_id": plan,
                }
            ),
            idempotency_key="mcp-publish",
        ),
    )
    assert direct.to_json() == published
    assert answer(session, "plan_show", {"plan": plan})["goal"] == "Verify authoring through MCP"

    base.update(draft_id=other["draft_id"], expected_edit_version=other["edit_version"])
    rebased = answer(session, "plan_draft_rebase", {**base, "idempotency_key": "mcp-rebase"})
    assert rebased["edit_version"] > other["edit_version"]
    base["expected_edit_version"] = rebased["edit_version"]
    assert answer(session, "plan_draft_abandon", base)["draft_id"] == other["draft_id"]

    [foreign] = exchange(session, [call("skm_plan_show", {"plan": str(side.plan2_ws2)})])
    assert content(foreign)["error"]["code"] == "NOT_FOUND"

    output = StringIO()

    def revoked_requests() -> Iterator[JsonObject]:
        yield call("skm_plan_entities", {"plan": plan, "limit": 1})
        receipt = content(_latest(output))["authoring_receipt"]
        owner_client.dispatch(access.RevokeToken(editor.token_id), idempotency_key="revoke-editor")
        yield call("skm_fetch", {"receipt": receipt})
        assert content(_latest(output))["error"]["code"] == "UNAUTHENTICATED"
        yield call("skm_plan_publish", publish_args)
        assert content(_latest(output))["error"]["code"] == "UNAUTHENTICATED"

    assert serve(None, session, _Conversation(revoked_requests()), output) == 0


@pytest.mark.parametrize("mode", ["embedded", "http"])
def test_edit_only_draft_by_project_ref(
    worker_side: Any, transport: TestClient, tmp_path: Path, mode: str
) -> None:
    side, _, owner = worker_side
    owner_client = client_for(side, transport, tmp_path, "embedded", owner["Authorization"].split()[1])
    ref = cast("planning.PlanRefView", owner_client.ask(planning.ResolvePlanRef(side.proj, str(side.plan1))))
    editor = cast(
        "access.CreateTokenResult",
        owner_client.dispatch(
            access.CreateToken(
                name="MCP draft editor", scope_id=side.proj, permissions=("project.read", "plan.edit")
            )
        ),
    )
    session = McpSession.open(
        client_for(side, transport, tmp_path, mode, editor.secret), project_id=side.proj
    )
    listed, read, fetch, invalid, foreign, lessons = exchange(
        session,
        [
            request("tools/list"),
            call("skm_plan_show", {"plan": ref.alias}),
            call("skm_fetch", {"receipt": "0" * 32}),
            call("skm_plan_show", {}),
            call("skm_plan_draft_open", {"plan": str(side.plan2_ws2), "idempotency_key": "foreign-open"}),
            call("skm_lessons_list", {}),
        ],
    )
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {"skm_plan_draft_open", "skm_plan_draft_save", "skm_plan_draft_abandon"} <= names
    assert not {"skm_plan_show", "skm_fetch", "skm_lessons_list"} & names
    for denied in (read, fetch, lessons):
        assert denied["result"]["isError"]
        assert content(denied)["error"]["code"] == "FORBIDDEN"
    assert invalid["error"]["code"] == -32602
    assert content(foreign)["error"]["code"] == "NOT_FOUND"

    draft = answer(session, "plan_draft_open", {"plan": ref.alias, "idempotency_key": "edit-only-open"})
    saved = answer(
        session,
        "plan_draft_save",
        {
            "plan": str(side.plan1),
            "draft_id": draft["draft_id"],
            "expected_edit_version": draft["edit_version"],
            "merge_patch": {"goal": "Updated by the draft editor"},
        },
    )
    assert saved["edit_version"] > draft["edit_version"]
    abandoned = answer(
        session,
        "plan_draft_abandon",
        {
            "plan": ref.alias,
            "draft_id": draft["draft_id"],
            "expected_edit_version": saved["edit_version"],
        },
    )
    assert abandoned["draft_id"] == draft["draft_id"]


def start_step(side: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    prepare_runtime(side, monkeypatch)
    run, task, _, assignment = make_case(side, stage_id="execute", stage_type="agent_step", env=True)
    add_budget(side, run)
    claimed = claim(side)
    secret = str(access.generate_secret(secrets.token_bytes))
    ready = begin(side, claimed, secret=secret)
    return run, task, assignment, worker_claim(side, claimed), ready, secret


def finalize_question(side: Any, headers: dict[str, str], claim_data: Any, ready: Any) -> None:
    assignment_id, stage_id = claim_data["assignment_id"], ready["stage_record_id"]
    step_id = ready["step"]["step_id"]
    path = f"/api/v1/worker/assignments/{assignment_id}"
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as http:
        finalize = prompt_wire(http, side, ready, claim_data)
        checked(post(http, f"/api/v1/context-manifests/{finalize['manifest_id']}/finalize", finalize))
        checked(
            post(
                http,
                path + "/heartbeat",
                {
                    "claim": claim_data,
                    "progress": {"phase": "runtime_started", "stage_record_id": stage_id, "step_id": step_id},
                },
                "mcp-start",
            )
        )
        output = checked(
            post(
                http,
                path + "/outputs",
                {
                    "claim": claim_data,
                    "stage_record_id": stage_id,
                    "step_id": step_id,
                    "source": "executor",
                    "manifest": empty_output(side),
                },
                "mcp-output",
            ),
            201,
        )
        role_result = {
            "schema": "urn:skm:execution:role-result:executor:v1",
            "status": "done",
            "summary": "Completed",
            "changed_paths": [],
            "checks_run": [],
            "open_issues": [],
            "self_check": {"performed": True},
        }
        evidence = checked(
            put_blob(http, side.ws, json.dumps(role_result).encode(), "application/json", "mcp-result"), 201
        )
        checked(
            post(
                http,
                path + f"/stages/{stage_id}/result",
                {
                    "claim": claim_data,
                    "outcome_kind": "success",
                    "outcome": {
                        "step_id": step_id,
                        "role_result": role_result,
                        "output_id": output["output_id"],
                    },
                    "evidence": [
                        {
                            "staged_blob": evidence,
                            "filename": "result.json",
                            "media_type": "application/json",
                            "owner": "step",
                            "owner_id": step_id,
                            "role": "raw_result",
                        }
                    ],
                },
                "mcp-complete",
            )
        )


@pytest.mark.parametrize("mode", ["embedded", "http"])
@pytest.mark.parametrize("terminal", ["advance", "expire"])
def test_assignment_tools(
    worker_side: Any,
    transport: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    terminal: str,
) -> None:
    side, headers, owner = worker_side
    run, task, assignment, claim_data, ready, secret = start_step(side, monkeypatch)
    client = client_for(side, transport, tmp_path, mode, secret, run_id=run.id)
    session = McpSession.open(client)
    assert session.assignment_id == assignment.id
    assert session.step_id == UUID(ready["step"]["step_id"])
    owner_session = McpSession.open(
        client_for(side, transport, tmp_path, mode, owner["Authorization"].split()[1]), project_id=side.proj
    )
    question: JsonObject = {
        "question": "Which design do you want?",
        "why_blocked": "The contract leaves the design open.",
        "urgency": "high",
        "options": [{"key": "a", "text": "Design A"}, {"key": "b", "text": "Design B"}],
    }
    [listed, hidden, remember, forget, foreign_step, foreign_run] = exchange(
        session,
        [
            request("tools/list"),
            call("skm_plan_draft_open", {"plan": str(side.plan1), "idempotency_key": "must-not-write"}),
            call("skm_memory_remember", {"text": "design", "key": "context"}),
            call("skm_memory_forget", {"entry_id": str(side.new_id())}),
            call("skm_ask_question", {**question, "step_id": str(side.new_id())}),
            call("skm_run_status", {"run": f"run:{side.new_id()}"}),
        ],
    )
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {
        "skm_plan_show",
        "skm_task_context",
        "skm_ask_question",
        "skm_record_note",
        "skm_memory_search",
        "skm_lessons_list",
    } <= names
    assert not {"skm_plan_publish", "skm_plan_draft_open", "skm_memory_remember", "skm_memory_forget"} & names
    for denied in (hidden, remember, forget):
        assert denied["result"]["isError"]
        assert content(denied)["error"]["code"] == "FORBIDDEN"
    assert foreign_step["error"]["code"] == -32602
    assert content(foreign_run)["error"]["code"] == "NOT_FOUND"
    assert answer(session, "memory_search", {"query": "design"})["items"] == []
    assert answer(session, "lessons_list", {})["items"] == []
    assert answer(session, "plan_show", {"plan": str(side.plan1)})["plan_id"] == str(side.plan1)
    plan_list = answer(session, "plan_list", {})
    assert [item["plan_id"] for item in plan_list["items"]] == [str(side.plan1)]
    assert plan_list["next"] is None
    assert answer(session, "plan_entity", {"plan": str(side.plan1), "entity": task.display_key})
    assert answer(session, "task_context", {})["task_key"] == task.display_key
    assert answer(session, "task_status", {"task": task.display_key})["attempts"] == 1
    assert answer(session, "run_status", {})["run_id"] == str(run.id)
    history = answer(session, "run_history", {"run": f"run:{run.id}", "limit": 1})
    assert history["run_id"] == str(run.id)
    if history["next_after"]:
        next_page = answer(
            session,
            "run_history",
            {
                "run": f"run:{run.id}",
                "after": history["next_after"],
            },
        )
        assert next_page["through_seq"] == history["through_seq"]

    note = answer(session, "record_note", {"kind": "progress", "text": "Checking the contract"})
    asked = answer(session, "ask_question", question)
    assert answer(owner_session, "inbox_list", {})["items"] == []
    assert session.step_id is not None
    with side.uow(readonly=True) as uow:
        recorded = {str(row.id): row for row in uow.repo(StepRepository).notes_for_step(session.step_id)}
        assert set(recorded) == {note["note_id"], asked["note_id"]}
        assert recorded[asked["note_id"]].options[0]["id"] == "a"
        assert recorded[asked["note_id"]].urgency == "blocking"

    if terminal == "advance":
        finalize_question(side, headers, claim_data, ready)
        inbox = answer(owner_session, "inbox_list", {"kind": "question"})
        assert [(item["task_key"], item["summary"]) for item in inbox["items"]] == [
            (task.display_key, question["question"]),
        ]
        status = answer(owner_session, "run_status", {"run": str(run.id)})
        assert status["waiting"][0]["request_id"] == inbox["items"][0]["request_id"]
        expected = "UNAUTHENTICATED"
    else:
        expire_now(side, assignment)
        expected = "LEASE_LOST"
    late = exchange(
        session,
        [
            call("skm_record_note", {"kind": "risk", "text": "late"}),
            call("skm_ask_question", question),
        ],
    )
    assert [content(response)["error"]["code"] for response in late] == [expected, expected]
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StepRepository).notes_for_step(session.step_id)) == 2


@pytest.mark.parametrize("mode", ["embedded", "http"])
def test_mcp_cli(
    worker_side: Any,
    transport: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    side, _, owner = worker_side
    owner_secret = owner["Authorization"].split()[1]
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    bootstrap = tmp_path / "bootstrap.toml"
    profile = '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n' if mode == "embedded" else ""
    bootstrap.write_text(
        f'schema = "urn:skm:config:bootstrap:v1"\ninstance_id = "{side.app.instance_id}"\n'
        f'[paths]\nstate_dir = "{tmp_path / "state"}"\n'
        f'[access]\nmode = "{mode}"\n'
        f'[api]\nendpoint = "{BASE}/api/v1"\ncredential = "secret://env/MCP_FALLBACK"\n' + profile,
        encoding="utf-8",
    )
    attached_runs: list[UUID | None] = []

    def http_client(*args: Any, **kwargs: Any) -> HttpSkmClient:
        attached_runs.append(kwargs["run_scope_id"])
        return HttpSkmClient(*args, **kwargs, http=transport)

    def embedded(*args: Any, **kwargs: Any) -> Any:
        assert mode == "embedded", "HTTP bootstrap must never build a local application"
        assert kwargs["surface"] is Surface.MCP
        return replace(
            side.app,
            authenticator=lambda value: authenticate(side, value),
            closers=(),
            host=None,
            closed=[False],
        )

    monkeypatch.setattr(mcp, "build_app", embedded)
    monkeypatch.setattr("skm.adapters.http_client.client.HttpSkmClient", http_client)

    def run(argv: list[str], environ: dict[str, str], *messages: JsonObject) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        code = main(
            ["--bootstrap", str(bootstrap), "mcp", *argv],
            environ=environ,
            stdin=StringIO("".join(json.dumps(message) + "\n" for message in messages)),
            stdout=out,
            stderr=err,
        )
        return code, out.getvalue(), err.getvalue()

    project = f"project:{side.proj}"
    code, out, err = run(["tools", "--project", project, "--json"], {"MCP_FALLBACK": owner_secret})
    assert (code, err) == (0, "")
    listed = json.loads(out)["result"]
    assert listed["tools_digest"] == tools_digest(listed["tools"])
    assert {
        "skm_plan_publish",
        "skm_memory_search",
        "skm_memory_remember",
        "skm_memory_forget",
        "skm_lessons_list",
    } <= {tool["name"] for tool in listed["tools"]}
    code, out, err = run(
        ["--project", project, "tools", "--token-env", "MCP_CUSTOM"],
        {"MCP_CUSTOM": owner_secret, "SKM_TOKEN": "invalid", "MCP_FALLBACK": "invalid"},
    )
    assert (code, err) == (0, "")
    assert listed["tools_digest"] in out
    assert all(name in out for name in ("skm_plan_publish", "skm_graph_neighbors", "skm_graph_path"))
    code, out, err = run(["--project", project], {"SKM_TOKEN": owner_secret}, request("tools/list"))
    assert (code, err) == (0, "")
    assert json.loads(out)["result"]["tools"] == listed["tools"]

    code, out, err = run(["--project", project], {})
    assert (code, out) == (5, "")
    assert "UNAUTHENTICATED" in err
    code, out, err = run([], {"SKM_TOKEN": owner_secret})
    assert (code, out) == (6, "")
    assert "NO_PROJECT_SCOPE" in err

    run_view, _, _, _, _, assignment_secret = start_step(side, monkeypatch)
    code, out, err = run(
        [],
        {"SKM_TOKEN": assignment_secret},
        call("skm_record_note", {"kind": "progress", "text": "CLI note"}),
    )
    assert code == 0, err
    assert assignment_secret not in err + out
    response = json.loads(out)
    assert response["result"]["isError"] is False, response
    assert content(response)["note_id"]
    if mode == "http":
        assert attached_runs[-2:] == [None, run_view.id]
