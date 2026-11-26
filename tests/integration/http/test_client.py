"""Wire DTOs, response problems, idempotency and cursor behavior of the standalone client."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, cast, override
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from contracts.execution._worker_protocol_support import make_case, worker_claim
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_lock_order import expire_now
from fixtures.execution.protocol import add_budget
from integration.api.test_worker_protocol import (
    CLAIM_PATH,
    checked,
    claim_body,
    post,
    prepare_runtime,
    prompt_wire,
    worker_api,
    worker_side,
)
from skm import __version__
from skm.adapters.http_client.client import HttpSkmClient
from skm.application_bus.client import QueryMeta
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import RouteTable, build_route_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, InternalError, SkmError, ValidationFailed
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import WorkspaceId
from skm.modules.access import public as access
from skm.modules.context import public as context
from skm.modules.planning import public as planning
from skm.modules.settings import public as settings
from skm.modules.settings.generated.results import SetValueResult
from skm.modules.workspace import public as workspace
from skm.modules.workspace.generated.views import ListProjectsView
from skm.platform.config.secrets import SecretRef, SecretValue
from support.http_server import loopback_server
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database", "worker_side"]

TOKEN = "test-private-credential"
WS = WorkspaceId(uuid4())
PROJECT = uuid4()


def secret(value: str = TOKEN) -> SecretValue:
    return SecretValue(SecretRef.parse("secret://env/SKM_API_TOKEN"), value)


@cache
def routes() -> RouteTable:
    return build_route_table(MODULE_IDS)


@pytest.fixture
def client_factory(tmp_path: Path) -> Iterator[Callable[..., HttpSkmClient]]:
    clients: list[httpx.Client] = []

    def build(handler: Callable[[httpx.Request], httpx.Response], **overrides: Any) -> HttpSkmClient:
        http = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(http)
        kwargs = {"sleeper": lambda _: None, **overrides}
        return HttpSkmClient(
            "http://127.0.0.1",
            secret(),
            routes(),
            spool_root=tmp_path / "spool",
            storage_budget=build_host_storage(tmp_path),
            min_free_bytes=0,
            http=http,
            **kwargs,
        )

    yield build
    for client in clients:
        client.close()


def _problem(status: int, code: str, **payload: object) -> httpx.Response:
    return httpx.Response(
        status,
        headers={"Content-Type": "application/problem+json"},
        json={"code": code, "detail": f"Rejected {TOKEN}", "details": {"echo": TOKEN}, **payload},
    )


@pytest.mark.parametrize("policy", ["required", "optional"])
@pytest.mark.parametrize("supplied", [False, True])
def test_retries_reuse_key_and_request(policy: str, supplied: bool, client_factory: Any) -> None:
    requests: list[httpx.Request] = []
    if policy == "required":
        command: object = planning.CreatePlan(project_id=PROJECT, title="Demo")
        path = f"/api/v1/projects/{PROJECT}/plans"
        result = {
            "plan_id": str(uuid4()),
            "workspace_id": str(WS),
            "project_id": str(PROJECT),
            "alias": "P-1",
            "title": "Demo",
            "lifecycle_state": "active",
            "row_version": 1,
            "draft_id": None,
            "edit_version": None,
        }
    else:
        command = settings.SetValue.from_json(
            {
                "scope": {"level": "instance"},
                "key": "worker.capacity",
                "value": 2,
                "expected_row_version": 0,
            }
        )
        path = "/api/v1/config/entries/instance/worker.capacity"
        result = SetValueResult.from_json(
            {
                "entry": {
                    "entry_id": str(uuid4()),
                    "key": "worker.capacity",
                    "scope": {"level": "instance"},
                    "row_version": 1,
                    "op": "set",
                    "locked": False,
                    "value": 2,
                    "updated_by": str(uuid4()),
                    "updated_at": "2026-10-01T00:00:00Z",
                },
                "changed": True,
                "generation": 1,
                "effective": {"key": "worker.capacity", "present": True, "value": 2},
            }
        ).to_json()

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError(TOKEN, request=request)
        if len(requests) == 2:
            return httpx.Response(503)
        return httpx.Response(201, json=result)

    client = client_factory(handle)
    first_key = "explicit-key" if supplied else None
    assert client.dispatch(command, idempotency_key=first_key).to_json() == result
    assert len(requests) == 3
    assert {request.url.path for request in requests} == {path}
    keys = {request.headers["Idempotency-Key"] for request in requests}
    assert len(keys) == 1
    key = keys.pop()
    if first_key is None:
        assert key.startswith("idem_")
        assert UUID(key[5:]).version == 7
    else:
        assert key == first_key
    assert len({request.headers["X-Request-Id"] for request in requests}) == 1
    for request in requests:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["SKM-Client-Version"] == __version__
        assert "Transfer-Encoding" not in request.headers
        if policy == "required":
            assert json.loads(request.content) == {"title": "Demo"}
        else:
            assert request.headers["If-None-Match"] == "*"
            assert "If-Match" not in request.headers
            assert json.loads(request.content) == {
                "value": 2,
                "confirmed": False,
                "mode": "set",
                "reason": "",
            }


def test_bodyless_revoke_sends_empty_json_request(client_factory: Any) -> None:
    token_id = uuid4()

    def handle(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("POST", f"/api/v1/tokens/{token_id}/revoke")
        assert request.headers["Content-Type"] == "application/json"
        assert request.content == b""
        return httpx.Response(200, json={"token_id": str(token_id), "revoked_at": "2026-10-01T00:00:00Z"})

    assert client_factory(handle).dispatch(access.RevokeToken(token_id)).token_id == token_id


def test_optional_without_retries_has_no_key(client_factory: Any) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert "Idempotency-Key" not in request.headers
        assert request.headers["If-Match"] == 'W/"v7"'
        return _problem(409, "VERSION_CONFLICT", retryable=True)

    client = client_factory(handle, max_attempts=1)
    with pytest.raises(Conflict):
        client.dispatch(
            settings.UnsetValue.from_json(
                {
                    "scope": {"level": "instance"},
                    "key": "worker.capacity",
                    "expected_row_version": 7,
                }
            )
        )


@pytest.mark.parametrize(
    ("status", "code"),
    [(409, ErrorCode.VERSION_CONFLICT), (426, ErrorCode.CLIENT_TOO_OLD), (429, ErrorCode.TOO_MANY_STREAMS)],
)
def test_4xx_is_never_retried_and_problem_is_redacted(
    status: int, code: ErrorCode, client_factory: Any
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _problem(status, code, retryable=True)

    with pytest.raises(SkmError) as caught:
        client_factory(handle).dispatch(workspace.CreateProject(workspace_id=WS, slug="demo", title="Demo"))
    assert len(requests) == 1
    assert caught.value.code == code
    assert TOKEN not in str(caught.value)
    assert TOKEN not in str(caught.value.details)
    assert caught.value.__context__ is None


def test_forbidden_key_fails_before_network(client_factory: Any) -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout(TOKEN, request=request)

    client = client_factory(handle)
    # The local key check precedes even serialization of the forbidden DTO.
    cmd = context.FinalizeManifest(manifest_id=str(PROJECT))
    with pytest.raises(ValidationFailed) as caught:
        client.dispatch(cmd, idempotency_key="forbidden")
    assert caught.value.code == ErrorCode.SCHEMA_INVALID
    assert caught.value.details == {"reason": "not_idempotent"}
    assert not calls


def test_query_retry_and_metadata(client_factory: Any) -> None:
    calls: list[httpx.Request] = []
    result = {"items": [], "next": None}

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == f"/api/v1/workspaces/{WS}/projects"
        assert request.url.params["limit"] == "2"
        assert not request.content
        if len(calls) == 1:
            return _problem(500, "BACKEND_UNAVAILABLE", retryable=True)
        return httpx.Response(200, json=result, headers={"SKM-Events-Cursor": "17"})

    view, meta = client_factory(handle).ask_with_meta(workspace.ListProjects(workspace_id=WS, limit=2))
    assert cast("ListProjectsView", view).to_json() == result
    assert meta == QueryMeta(events_cursor=17)
    assert len(calls) == 2


def test_unknown_problem_is_internal(client_factory: Any) -> None:
    with pytest.raises(InternalError):
        client_factory(lambda _: _problem(400, "UNRECOGNIZED")).ask(workspace.ListProjects(workspace_id=WS))


@dataclass
class _Clock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _event(seq: int) -> str:
    envelope = EventEnvelope.from_json(
        {
            "id": str(uuid4()),
            "type": "urn:skm:workspace:event:project-created:v1",
            "schema_version": 1,
            "stream_kind": "project",
            "stream_id": str(PROJECT),
            "stream_seq": 1,
            "workspace_id": str(WS),
            "workspace_seq": seq,
            "global_position": None,
            "actor_id": None,
            "payload": {},
            "occurred_at": "2026-10-01T00:00:00Z",
            "recorded_at": "2026-10-01T00:00:00Z",
            "request_id": None,
            "correlation_id": "sse-test",
            "causation_id": None,
        }
    )
    return f"id: {seq}\nevent: ProjectCreated\ndata: {json.dumps(envelope.to_json())}\n\n"


def test_sse_resumes_from_cursor_and_discards_duplicates(client_factory: Any) -> None:
    clock = _Clock()
    calls: list[httpx.Request] = []
    frames = [
        ": ping\n\n" + _event(3) + "id: 7\nevent: cursor\ndata: {}\n\n",
        _event(3) + _event(7) + _event(8),
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept"] == "text/event-stream"
        assert request.url.params["after"] == "2"
        assert request.url.params["types"] == "ProjectCreated"
        calls.append(request)
        return httpx.Response(200, text=frames.pop(0), headers={"Content-Type": "text/event-stream"})

    client = client_factory(handle, clock=clock, sleeper=clock.sleep)
    events = client.events(workspace_id=WS, after=2, types=frozenset({"ProjectCreated"}), wait_seconds=5)
    try:
        assert next(events).workspace_seq == 3
        assert next(events).workspace_seq == 8
    finally:
        cast("Generator[EventEnvelope]", events).close()
    assert "Last-Event-ID" not in calls[0].headers
    assert calls[1].headers["Last-Event-ID"] == "7"


def test_sse_wait_deadline_applies_to_heartbeat_only_stream(client_factory: Any) -> None:
    clock = _Clock()
    seen: list[int] = []

    class Pings(httpx.SyncByteStream):
        @override
        def __iter__(self) -> Iterator[bytes]:
            for ping in range(10):
                clock.sleep(1)
                seen.append(ping)
                yield b": ping\n\n"

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Pings(), headers={"Content-Type": "text/event-stream"})

    client = client_factory(handle, clock=clock, sleeper=clock.sleep)
    assert list(client.events(workspace_id=WS, after=0, wait_seconds=3)) == []
    assert seen == [0, 1, 2]


@pytest.mark.parametrize("exec_side", [pytest.param("postgres", marks=pytest.mark.pg)], indirect=True)
@pytest.mark.parametrize("loses", ["lease", "fence", "token"])
def test_intrinsic_finalize_rechecks_live_authority(
    worker_side: Any, monkeypatch: Any, tmp_path: Path, loses: str
) -> None:
    side, worker_headers, _ = worker_side
    prepare_runtime(side, monkeypatch)
    run, _, _, assignment = make_case(side, stage_id="execute", stage_type="agent_step", env=True)
    add_budget(side, run)
    headers: list[httpx.Headers] = []
    fault = False
    with (
        loopback_server(
            lambda address: worker_api(
                side,
                settings={"api.bind": address},
            )
        ) as endpoint,
        httpx.Client(base_url=endpoint, headers=worker_headers, trust_env=False) as raw,
    ):
        claimed = checked(post(raw, CLAIM_PATH, claim_body(side), "claim"))
        claim = worker_claim(side, claimed)
        instruction = claimed["instruction"]
        ready = checked(
            post(
                raw,
                f"/api/v1/worker/assignments/{assignment.id}/stages",
                {
                    "claim": claim,
                    "stage_id": instruction["stage_id"],
                    "round_no": instruction["round_no"],
                    "input_digest": instruction["input_digest"],
                    "runtime_token_secret": str(access.generate_secret(lambda count: b"S" * count)),
                },
                "begin",
            ),
            201,
        )
        dto = context.FinalizeManifest.from_json(prompt_wire(raw, side, ready, claim))

        def observe(request: httpx.Request) -> None:
            headers.append(request.headers)
            if fault:
                raise httpx.ReadError("connection lost", request=request)

        with httpx.Client(event_hooks={"request": [observe]}, trust_env=False) as http:
            client = HttpSkmClient(
                endpoint,
                secret(worker_headers["Authorization"].removeprefix("Bearer ")),
                routes(),
                spool_root=tmp_path / "spool",
                storage_budget=build_host_storage(tmp_path),
                min_free_bytes=0,
                http=http,
            )
            first = cast("context.FinalizeManifestResult", client.dispatch(dto))
            assert first["state"] == "final"
            assert client.dispatch(dto) == first
            fault = True
            with pytest.raises(BackendUnavailable):
                client.dispatch(dto)
            assert len(headers) == 3
            fault = False
            if loses == "lease":
                expire_now(side, assignment)
            elif loses == "fence":
                with psycopg.connect(side.dsn) as connection:
                    connection.execute(
                        "UPDATE skm_execution.assignments SET last_fencing_token=last_fencing_token+1 "
                        "WHERE id=%s",
                        (assignment.id,),
                    )
                    connection.execute(
                        "UPDATE skm_execution.assignment_leases SET fencing_token=fencing_token+1 "
                        "WHERE assignment_id=%s",
                        (assignment.id,),
                    )
            else:
                actor = side.worker1_client._actor
                side.client.dispatch(access.RevokeToken(actor.grant.token_id))
            with pytest.raises(SkmError) as caught:
                client.dispatch(dto)
            expected = ErrorCode.UNAUTHENTICATED if loses == "token" else ErrorCode.LEASE_LOST
            assert caught.value.code == expected
    assert len(headers) == 4
    assert all("Idempotency-Key" not in request_headers for request_headers in headers)


def test_standalone_client_import_graph(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys
from pathlib import Path
from uuid import uuid4

prefixes = ("starlette", "uvicorn", "psycopg", "skm.entrypoints.api.app",
            "skm.adapters.postgres", "skm.adapters.runtimes", "skm.adapters.git",
            "skm.adapters.checkout_fs", "skm.adapters.integrations", "skm.bootstrap")

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, *_):
        if name.startswith(prefixes) or (name.startswith("skm.modules.") and name.endswith(".module")):
            raise AssertionError(name)

sys.meta_path.insert(0, Blocker())

import httpx
from skm import __version__
from skm.adapters.http_client.client import HttpSkmClient
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.modules.workspace.public import CreateProject
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity

ws = uuid4()
project = uuid4()
def handle(request):
    assert request.url.path == f"/api/v1/workspaces/{ws}/projects"
    return httpx.Response(201, json={"project_id": str(project), "workspace_id": str(ws),
                                   "slug": "demo", "row_version": 1})

root = Path(sys.argv[1])
storage = StorageBudget(root / "locks", free_bytes=lambda _: 10000000,
                        identity=lambda: StorageOwnerIdentity("boot", 1, "start"),
                        owner_alive=lambda _: True)
with httpx.Client(transport=httpx.MockTransport(handle)) as http:
    token = SecretValue(SecretRef.parse("secret://env/TOKEN"), "secret-token")
    client = HttpSkmClient("http://127.0.0.1/api/v1", token,
                           build_route_table(MODULE_IDS), spool_root=root / "spool",
                           storage_budget=storage, min_free_bytes=0, http=http)
    assert client.dispatch(CreateProject(workspace_id=ws, slug="demo", title="Demo")).project_id == project
""",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
