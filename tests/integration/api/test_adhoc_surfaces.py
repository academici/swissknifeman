"""Round trips for ad hoc execution and context through the HTTP client and bus."""

import asyncio
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from starlette.applications import Starlette

from contracts.execution.harness import PEPPER, ExecSide
from security.api.harness import BASE
from skm.adapters.http_client.client import HttpSkmClient
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api import auth
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ids import ContextManifestId, RunId
from skm.modules.access import public as access
from skm.modules.context import public as context
from skm.modules.context.ports import ContextRepository
from skm.modules.execution import public as execution
from skm.modules.execution.application._adhoc_spec import task_instructions
from skm.modules.execution.application._state import load_state
from skm.modules.execution.ports import RunRepository, TaskRepository
from skm.platform.config.secrets import SecretRef, SecretValue
from support.adhoc import adhoc_side as adhoc_side
from support.adhoc import assembly, workflow


def _http(api: Starlette, monkeypatch: pytest.MonkeyPatch, **options: Any) -> httpx.Client:
    async def run_bus(function: Any, *args: object) -> object:
        return function(*args)

    # Drive the ASGI app without a listening socket or a separate lifespan thread.
    api.state.run_bus = run_bus
    monkeypatch.setattr(auth, "run_in_threadpool", run_bus)

    def exchange(request: httpx.Request) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api)) as client:
                response = await client.send(request)
                return httpx.Response(
                    response.status_code, headers=response.headers, content=response.content
                )

        return asyncio.run(send())

    return httpx.Client(base_url=BASE, transport=httpx.MockTransport(exchange), **options)


def _auth_token(side: ExecSide) -> tuple[Starlette, str]:
    token = cast("access.CreateTokenResult", side.client.dispatch(access.CreateToken(name="adhoc-http")))

    def authenticate(secret: str):
        with side.uow(readonly=True) as uow:
            return access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    api = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=build_route_table(MODULE_IDS),
        registry=side.app.bus._registry,
        schema_check=lambda: None,
        no_background=True,
    )
    return api, token.secret


def test_http_clients_round_trip_adhoc_and_manifest_routes(
    adhoc_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = adhoc_side
    table = build_route_table(MODULE_IDS)
    api, secret = _auth_token(side)
    with (
        _http(api, monkeypatch) as http,
        closing(
            HttpSkmClient(
                BASE,
                SecretValue(SecretRef.parse("secret://env/SKM_TOKEN"), secret),
                table,
                spool_root=tmp_path / "spool",
                storage_budget=build_host_storage(tmp_path),
                min_free_bytes=0,
                http=http,
            )
        ) as client,
    ):
        dto = execution.RunAdhoc.from_json(
            {"project_id": str(side.proj), "prompt": "Inspect the modules.", "workflow": workflow()}
        )
        started = cast("execution.StartRunResult", client.dispatch(dto, idempotency_key="adhoc-run"))
        assert client.dispatch(dto, idempotency_key="adhoc-run") == started
        assert started.task_count == 1
        assert started.status == "running"
        with side.uow(readonly=True) as uow:
            run = uow.repo(RunRepository).get(RunId(started.run_id))
            (task,) = uow.repo(TaskRepository).list_for_run(run.id)
            _, pinned = load_state(uow, task.id)
            assert [stage.id for stage in pinned.stages] == ["setup", "respond", "finish"]
            assert task_instructions(uow, run) == "Inspect the modules."

        assemble = context.AssembleContext.from_json({"project_id": str(side.proj), **assembly()})
        draft = cast(
            "context.AssembleContextResult", client.dispatch(assemble, idempotency_key="context-draft")
        )
        assert client.dispatch(assemble, idempotency_key="context-draft") == draft
        explain = context.ExplainContextRequest.from_json(
            {"project_id": str(side.proj), "manifest_id": str(draft.manifest_id)}
        )
        assert cast("context.ContextExplainResponse", client.ask(explain))["state"] == "draft"
        diff = context.DiffContextsRequest.from_json(
            {
                "project_id": str(side.proj),
                "base_manifest_id": str(draft.manifest_id),
                "target_manifest_id": str(draft.manifest_id),
            }
        )
        assert cast("context.ContextDiffResponse", client.ask(diff))["counts"]["changed"] == 0
        with side.uow(readonly=True) as uow:
            saved = uow.repo(ContextRepository).get(ContextManifestId(draft.manifest_id))
            assert saved.owner_ref == f"standalone:{side.owner.principal_id}"


def test_step_routes_scope_both_manifests_and_require_base(
    adhoc_side: ExecSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = adhoc_side
    steps = [str(side.new_id()), str(side.new_id())]
    base, target = [side.make_final_manifest(step_ref=f"step:{step}") for step in steps]
    api, secret = _auth_token(side)
    with _http(api, monkeypatch, headers={"Authorization": f"Bearer {secret}"}) as http:
        explain = f"/api/v1/steps/{steps[1]}/context"
        diff = f"/api/v1/projects/{side.proj}/steps/{steps[1]}/context/diff"
        assert http.get(explain, params={"project_id": str(side.proj)}).json()["state"] == "final"
        assert http.get(explain, params={"project_id": str(side.proj2)}).status_code == 404
        assert http.get(diff, params={"base_manifest_id": str(base)}).status_code == 200
        assert http.get(diff).status_code == 422
        assert http.get(explain).status_code == 422
        target_diff = f"/api/v1/projects/{side.proj2}/context-manifests/{target}/diff"
        assert http.get(target_diff, params={"base_manifest_id": str(base)}).status_code == 404


@pytest.mark.parametrize("prompt", ["", "   ", "\x00"])
def test_invalid_adhoc_prompt_rolls_back(adhoc_side: ExecSide, prompt: str) -> None:
    from skm.kernel.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        adhoc_side.client.dispatch(execution.RunAdhoc(adhoc_side.proj, prompt))
    with adhoc_side.uow(readonly=True) as uow:
        assert not uow.repo(RunRepository).list_active_ids(limit=10)
