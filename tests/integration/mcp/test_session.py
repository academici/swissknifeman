"""MCP session binding and live admission across the real embedded and HTTP clients."""

import json
import secrets
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from contracts.execution._worker_protocol_support import begin, claim, make_case
from contracts.execution.harness import PEPPER, ExecSide
from contracts.execution.harness import exec_side as exec_side
from fixtures.execution.protocol import add_budget
from integration.api.test_worker_protocol import prepare_runtime
from integration.api.test_worker_protocol import worker_side as worker_side
from integration.mcp.test_protocol import call, content, exchange, tool
from security.api.harness import BASE, TestClient, World, make_world
from skm.adapters.http_client.client import HttpSkmClient
from skm.application_bus.client import SkmClient
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import RouteTable, build_route_table
from skm.entrypoints.cli.context import CONTEXT_SCHEMA
from skm.entrypoints.mcp import registry
from skm.entrypoints.mcp.session import DEFAULT_MAX_RESPONSE_TOKENS, McpSession
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, Unauthenticated
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.planning import public as planning
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.config.secrets import SecretRef, SecretValue
from support.pg import TestDatabase
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

_LIMIT = "api.mcp.max_response_tokens"
_MODULES = ("access", "execution", "planning", "settings", "workspace")


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def world(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[World]:
    database = (
        cast("TestDatabase", request.getfixturevalue("clean_test_database")).dsn
        if request.param == "postgres"
        else None
    )
    instance = make_world(tmp_path, database=database)
    try:
        yield instance
    finally:
        instance.core.close()


def _client(world: World, token: str | None = None) -> SkmClient:
    return world.core.client(actor=world.core.authenticate(token or world.secret), surface=Surface.MCP)


def _projects(client: SkmClient) -> tuple[UUID, UUID, UUID]:
    ws = cast(
        "workspace.CreateWorkspaceResult",
        client.dispatch(workspace.CreateWorkspace("mcp-tests", "MCP"), idempotency_key="new-workspace"),
    )
    projects: list[UUID] = []
    for slug in ("first", "second"):
        project = cast(
            "workspace.CreateProjectResult",
            client.dispatch(
                workspace.CreateProject(workspace_id=ws.workspace_id, slug=slug, title=slug),
                idempotency_key="create-" + slug,
            ),
        )
        projects.append(project.project_id)
    return ws.workspace_id, projects[0], projects[1]


def _context(path: Path, project_id: UUID, instance_id: UUID) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": CONTEXT_SCHEMA,
                "project_id": str(project_id),
                "instance_id": str(instance_id),
            }
        ),
        encoding="utf-8",
    )
    return path


def _http(token: str, transport: TestClient, routes: RouteTable, root: Path) -> HttpSkmClient:
    return HttpSkmClient(
        BASE,
        SecretValue(SecretRef.parse("secret://env/SKM_TOKEN"), token),
        routes,
        spool_root=root / "spool",
        storage_budget=build_host_storage(root),
        min_free_bytes=0,
        http=transport,
    )


def test_no_project_refuses_to_start(world: World, tmp_path: Path) -> None:
    owner = _client(world)
    _, project, _ = _projects(owner)
    missing = tmp_path / "missing" / "cli-context.json"
    other = _context(tmp_path / "cli-context.json", project, uuid4())
    for path in (missing, other):
        with pytest.raises(PreconditionFailed) as raised:
            McpSession.open(owner, cli_context_path=path, instance_id=world.core.instance_id)
        assert raised.value.code is ErrorCode.NO_PROJECT_SCOPE


def test_project_selection_precedence_and_foreign_project_isolation(world: World, tmp_path: Path) -> None:
    owner = _client(world)
    workspace_id, first, second = _projects(owner)
    context = _context(tmp_path / "cli-context.json", second, world.core.instance_id)
    assert McpSession.open(owner, project_id=first, cli_context_path=context).project_id == first
    assert McpSession.open(owner, cli_context_path=context).project_id == second

    scoped = cast(
        "access.CreateTokenResult", owner.dispatch(access.CreateToken(name="first", scope_id=first))
    )
    subject = _client(world, scoped.secret)
    assert McpSession.open(subject, cli_context_path=context).project_id == first
    with pytest.raises(Forbidden) as raised:
        McpSession.open(subject, project_id=second, cli_context_path=context)
    assert raised.value.code is ErrorCode.FORBIDDEN

    wider = cast(
        "access.CreateTokenResult",
        owner.dispatch(access.CreateToken(name="workspace", scope_id=workspace_id)),
    )
    assert McpSession.open(_client(world, wider.secret), cli_context_path=context).project_id == second


def test_embedded_and_http_limits_and_live_credential(world: World, tmp_path: Path) -> None:
    owner = _client(world)
    _, project, _ = _projects(owner)
    owner.dispatch(
        settings.SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(project)},
                "key": _LIMIT,
                "value": 612,
            }
        )
    )
    token = cast(
        "access.CreateTokenResult", owner.dispatch(access.CreateToken(name="mcp project", scope_id=project))
    )
    embedded = McpSession.open(_client(world, token.secret))
    routes = build_route_table(_MODULES)
    api = create_app(
        world.core,
        route_table=routes,
        registry=world.core.bus._registry,
        no_background=True,
    )
    with TestClient(api, base_url=BASE) as transport:
        remote = McpSession.open(_http(token.secret, transport, routes, tmp_path / "host"))
        assert remote.project_id == embedded.project_id == project
        assert remote.actor == embedded.actor
        assert remote.max_response_tokens == embedded.max_response_tokens == 612
        assert "project.read" in remote.refresh().effective_permissions
        owner.dispatch(
            settings.SetValue.from_json(
                {
                    "scope": {"level": "project", "scope_id": str(project)},
                    "key": _LIMIT,
                    "value": 500,
                    "expected_row_version": 1,
                }
            )
        )
        assert remote.max_response_tokens == embedded.max_response_tokens == 500
        owner.dispatch(access.RevokeToken(token_id=token.token_id))
        for session in (remote, embedded):
            with pytest.raises(Unauthenticated):
                session.refresh()


@pytest.mark.parametrize("narrowed", [False, True], ids=["default", "project-read-only"])
def test_begin_stage_token_selects_project_on_both_transports(
    worker_side: tuple[ExecSide, object, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    narrowed: bool,
) -> None:
    side, _, _ = worker_side
    if narrowed:
        side.client.dispatch(
            settings.SetValue.from_json(
                {
                    "scope": {"level": "workspace", "scope_id": str(side.ws)},
                    "key": "access.tokens.assignment_permissions",
                    "value": ["project.read"],
                }
            )
        )
    prepare_runtime(side, monkeypatch)
    run, _, _, assignment = make_case(side, stage_id="execute", stage_type="agent_step", env=True)
    add_budget(side, run)
    secret = str(access.generate_secret(secrets.token_bytes))
    ready = begin(side, claim(side), secret=secret)
    step_id = UUID(ready["step"]["step_id"])

    def authenticate(value: str) -> Actor:
        with side.uow(readonly=True) as uow:
            return access.authenticate_token(uow, value, pepper=PEPPER, now=side.clock.now())

    embedded = side.app.client(actor=authenticate(secret), surface=Surface.MCP)
    routes = build_route_table(_MODULES)
    api = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=routes,
        registry=side.app.bus._registry,
        schema_check=lambda: None,
        no_background=True,
    )

    def plan_show(session: McpSession, arguments: Mapping[str, JsonValue]) -> JsonValue:
        plan = cast(
            "planning.PlanRefView",
            session.client.ask(planning.ResolvePlanRef(session.project_id, str(arguments["plan"]))),
        )
        return {
            "plan_id": str(plan.plan_id),
            "alias": plan.alias,
            "title": plan.title,
            "revision_no": 1,
            "goal": "",
            "phases": [],
            "requirements_count": 0,
            "checks_count": 0,
        }

    monkeypatch.setattr(registry, "TOOLS", (tool("skm_plan_show", plan_show),))
    with TestClient(api, base_url=BASE) as transport:
        remote = _http(secret, transport, routes, tmp_path / "host")
        for client in (embedded, remote):
            session = McpSession.open(client)
            assert session.project_id == side.proj
            assert (session.run_id, session.assignment_id, session.step_id) == (
                run.id,
                assignment.id,
                step_id,
            )
            assert session.is_assignment
            assert session.max_response_tokens == DEFAULT_MAX_RESPONSE_TOKENS
            identity = session.refresh()
            assert identity.token is not None
            assert identity.token.token_id == UUID(ready["step"]["runtime_token"]["token_id"])
            if narrowed:
                assert identity.token.permissions == ("project.read",)
                assert identity.effective_permissions == ("project.read",)
                for scope_id in (side.ws, side.proj, side.plan1, run.id):
                    assert identity.permissions_by_scope[str(scope_id)] == ("project.read",)
            else:
                assert {"project.read", "plan.read", "run.read", "step.note"} <= set(
                    identity.token.permissions or ()
                )
            with pytest.raises(Forbidden):
                McpSession.open(client, project_id=side.proj2)
            if narrowed:
                continue
            own, foreign = exchange(
                session,
                [
                    call("skm_plan_show", {"plan": str(side.plan1)}),
                    call("skm_plan_show", {"plan": str(side.plan2_ws2)}, 2),
                ],
            )
            assert content(own)["plan_id"] == str(side.plan1)
            assert foreign["result"]["isError"] is True
            assert content(foreign)["error"]["code"] == "NOT_FOUND"
