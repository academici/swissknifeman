"""Security tests for project SSE, per-event RBAC, live revocation, and worker-only publish."""

from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
import pytest
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.types import Message, Scope

from contracts.execution._worker_protocol_support import claim, make_case, worker_claim
from contracts.execution.harness import PEPPER, ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import record_run_event, seed_bundle, seed_run
from integration.api._sse_helpers import _Stream
from integration.api.test_worker_protocol import bearer, problem, worker_api
from integration.api.test_worker_protocol import worker_side as worker_side
from security.api.harness import BASE
from skm.application_bus.ports import EventReader
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.auth import SESSION_COOKIE_NAME
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.actor import PrincipalKind, ScopeGrant
from skm.kernel.ids import PrincipalId, ProjectId, RunId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access import public as access
from skm.modules.access.domain.principal import Principal, PrincipalState
from skm.modules.access.ports import PrincipalRepository
from skm.modules.execution.domain.run import RunStatus
from skm.modules.workspace import public as workspace
from skm.modules.workspace.application.events import WorkspaceCreated
from skm.modules.workspace.domain.slug import Slug
from skm.platform.config.bootstrap import WebAuthConfig

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.parametrize("exec_side", ["memory"], indirect=True),
]

_ADMIN_PASSWORD = "sse-live-security-owner-password-99"
_RETRY = "retry: 3000"
_AT = "2026-11-18T12:00:00.000000Z"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _ensure_local_owner_identity(side: ExecSide) -> None:
    from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT, PrincipalIdentity
    from skm.modules.access.ports import IdentityRepository

    with side.uow() as uow:
        if uow.repo(IdentityRepository).find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT) is None:
            uow.repo(IdentityRepository).add(
                PrincipalIdentity(
                    principal_id=side.owner.principal_id,
                    issuer=LOCAL_ISSUER,
                    subject=LOCAL_OWNER_SUBJECT,
                    created_at=side.clock.now(),
                )
            )
            uow.commit()


def _set_owner_password(side: ExecSide) -> None:
    from skm.modules.access.application.passwords import set_first_password

    _ensure_local_owner_identity(side)
    with side.uow() as uow:
        set_first_password(uow, side.owner.principal_id, _ADMIN_PASSWORD, os.urandom)
        uow.commit()


def _paired_secret(side: ExecSide, scope_grants: tuple[ScopeGrant, ...]) -> str:
    pairing_id = side.new_id()
    with side.uow() as uow:
        pairing_secret = access.issue_pairing_token(
            uow,
            issuer=side.owner,
            workspace_id=side.ws,
            pairing_id=pairing_id,
            now=side.clock.now(),
            expires_at=side.clock.now() + timedelta(minutes=10),
            entropy=os.urandom,
            pepper=PEPPER,
            principal_id=side.owner.principal_id,
            scope_grants=scope_grants,
        )
        uow.commit()
    exchanged = cast(
        "workspace.ExchangePairingTokenResult",
        side.app.bus.dispatch(
            workspace.ExchangePairingToken(
                workspace_id=side.ws,
                pairing_id=pairing_id,
                pairing_secret=pairing_secret,
            ),
            actor=access.SYSTEM_ACTOR,
            meta=RequestMeta(f"pair-{pairing_id}", Surface.TEST, None, side.clock.now()),
        ),
    )
    assert exchanged.token_secret is not None
    return exchanged.token_secret


def _make_api(
    side: ExecSide,
    *,
    web_auth: WebAuthConfig | None = None,
    poll_ms: int = 20,
    heartbeat_seconds: int = 1,
    max_streams_per_token: int = 8,
) -> Starlette:
    def authenticate(secret: str):
        with side.uow(readonly=True) as uow:
            return access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    core = replace(side.app, authenticator=authenticate)
    return create_app(
        core,
        route_table=build_route_table(("access", "workspace", "execution")),
        registry=core.bus._registry,
        schema_check=lambda: None,
        no_background=True,
        web_auth=web_auth or WebAuthConfig(mode="admin_login"),
        settings={
            "api.sse.poll_ms": poll_ms,
            "api.sse.heartbeat_seconds": heartbeat_seconds,
            "api.sse.max_streams_per_token": max_streams_per_token,
        },
    )


def _create_session(
    side: ExecSide, principal_id: PrincipalId | None = None, ttl_seconds: int = 3600
) -> tuple[UUID, str]:
    sid = uuid4()
    with side.uow() as uow:
        session, secret = access.create_web_session(
            uow,
            principal_id=principal_id or side.owner.principal_id,
            session_id=sid,
            now=side.clock.now(),
            ttl_seconds=ttl_seconds,
            entropy=os.urandom,
            pepper=PEPPER,
        )
        uow.commit()
    return session.id, secret


def _create_second_project(side: ExecSide) -> ProjectId:
    created = cast(
        "Any",
        side.client.dispatch(workspace.CreateProject(workspace_id=side.ws, slug="proj-b", title="Project B")),
    )
    return ProjectId(created.project_id)


def _seed_project_run(side: ExecSide, project_id: ProjectId) -> RunId:
    with side.uow() as uow:
        if project_id == side.proj:
            run = seed_run(side, uow, status=RunStatus.RUNNING)
            seed_bundle(side, uow, run.id)
            uow.commit()
            return run.id
        from skm.kernel.scopes import ScopeKind, ScopeRegistry

        run_id = RunId(side.new_id())
        uow.repo(ScopeRegistry).create(
            ScopeId(run_id), ScopeKind.RUN, parent=ScopeId(project_id), workspace_id=side.ws
        )
        uow.commit()
        return run_id


def _append_run_event(
    side: ExecSide,
    run_id: RunId,
    project_id: ProjectId,
    *,
    paused: bool = False,
) -> None:
    payload: JsonObject = {
        "workspace_id": str(side.ws),
        "project_id": str(project_id),
        "run_id": str(run_id),
        "by": str(side.owner.principal_id),
    }
    if paused:
        payload.update(reason="paused", pause_source="owner")
    with side.uow() as uow:
        record_run_event(side, uow, run_id, "run-paused" if paused else "run-resumed", payload)
        uow.commit()


def _head(side: ExecSide) -> int:
    with side.uow(readonly=True) as uow:
        return uow.repo(EventReader).head_workspace_seq(side.ws)


@asynccontextmanager
async def _open_raw(
    app: Starlette,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: tuple[tuple[str, str], ...] = (),
    method: str = "GET",
    client_peer: tuple[str, int] = ("127.0.0.1", 50000),
    pause: asyncio.Event | None = None,
) -> AsyncIterator[_Stream]:
    incoming = asyncio.Queue[Message]()
    await incoming.put({"type": "http.request", "body": b""})
    messages = asyncio.Queue[Message]()
    req_headers = {"host": "127.0.0.1:8765", **(headers or {})}
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "query_string": urlencode(params).encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in req_headers.items()],
        "client": client_peer,
        "root_path": "",
    }

    async def send(message: Message) -> None:
        await messages.put(message)
        if pause is not None and message.get("more_body"):
            await pause.wait()

    task = asyncio.create_task(app(scope, incoming.get, send))
    try:
        start = await asyncio.wait_for(messages.get(), 4)
        assert start["type"] == "http.response.start"
        yield _Stream(start["status"], Headers(raw=start["headers"]), messages, deque(), task)
    finally:
        await incoming.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 4)


async def _login_cookie(client: httpx.AsyncClient) -> tuple[str, str]:
    csrf_resp = await client.get("/api/v1/auth/csrf")
    assert csrf_resp.status_code == 200
    csrf = csrf_resp.json()["csrf_token"]
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"password": _ADMIN_PASSWORD},
        headers={"Origin": BASE, "X-SKM-CSRF": csrf},
    )
    assert login_resp.status_code == 200, login_resp.text
    session_cookie = client.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie is not None
    return session_cookie, login_resp.json()["csrf_token"]


async def _expect_run_frame(
    stream: _Stream, expected_seq: int, expected_event: str, expected_run: RunId
) -> None:
    frame = await stream.take()
    assert frame is not None
    ident, ev, data = frame.splitlines()
    assert ident == f"id: {expected_seq}"
    assert ev == f"event: {expected_event}"
    envelope = json.loads(data.removeprefix("data: "))
    assert envelope["stream_kind"] == "run"
    assert envelope["stream_id"] == str(expected_run)


# --------------------------------------------------------------------------- Project SSE + AuthBasis


async def test_project_sse_supports_bearer_cookie_and_local_owner(exec_side: ExecSide) -> None:
    side = exec_side
    _set_owner_password(side)
    run_p1 = _seed_project_run(side, side.proj)

    # Project-only scoped Bearer token WITHOUT workspace.read!
    project_secret = _paired_secret(
        side, (ScopeGrant(ScopeId(side.proj), frozenset({"project.read", "run.read"})),)
    )

    head = _head(side)
    _append_run_event(side, run_p1, side.proj)

    # 1. Project-only Bearer token works on /projects/{p1}/events/stream (and is refused on /events)
    api = _make_api(side, web_auth=WebAuthConfig(mode="admin_login"))
    async with api.router.lifespan_context(api):
        path = f"/api/v1/projects/{side.proj}/events/stream"
        async with _open_raw(
            api, path, headers={"Authorization": f"Bearer {project_secret}", "Last-Event-ID": str(head)}
        ) as stream:
            assert stream.status == 200
            assert await stream.take() == _RETRY
            await _expect_run_frame(stream, head + 1, "RunResumed", run_p1)

        # Same project-only token cannot open workspace SSE (lacks workspace.read)
        async with _open_raw(
            api,
            "/api/v1/events",
            headers={"Authorization": f"Bearer {project_secret}"},
            params=(("workspace_id", str(side.ws)),),
        ) as denied:
            assert denied.status == 403
            assert json.loads(await denied.take() or "")["code"] == "FORBIDDEN"

        # 2. Web session cookie works on BOTH project SSE and workspace SSE
        _sid, session_cookie = _create_session(side)
        async with _open_raw(
            api,
            path,
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}", "Last-Event-ID": str(head)},
        ) as cookie_stream:
            assert cookie_stream.status == 200
            assert await cookie_stream.take() == _RETRY
            await _expect_run_frame(cookie_stream, head + 1, "RunResumed", run_p1)

        async with _open_raw(
            api,
            "/api/v1/events",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}", "Last-Event-ID": str(head)},
            params=(("workspace_id", str(side.ws)),),
        ) as ws_cookie_stream:
            assert ws_cookie_stream.status == 200
            assert await ws_cookie_stream.take() == _RETRY
            await _expect_run_frame(ws_cookie_stream, head + 1, "RunResumed", run_p1)

        # Error cases: unknown project -> 404, workspace ID as project -> 404, invalid UUID -> 422
        async with _open_raw(
            api,
            f"/api/v1/projects/{uuid4()}/events/stream",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
        ) as missing:
            assert missing.status == 404
        async with _open_raw(
            api,
            f"/api/v1/projects/{side.ws}/events/stream",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
        ) as wrong_kind:
            assert wrong_kind.status == 404
        async with _open_raw(
            api,
            "/api/v1/projects/not-a-uuid/events/stream",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
        ) as bad_uuid:
            assert bad_uuid.status == 422

    # 3. Loopback web_auth.mode='none' local_owner works on project SSE
    # Seed local_owner identity if absent in harness
    from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT, PrincipalIdentity
    from skm.modules.access.ports import IdentityRepository

    with side.uow() as uow:
        if uow.repo(IdentityRepository).find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT) is None:
            uow.repo(IdentityRepository).add(
                PrincipalIdentity(
                    principal_id=side.owner.principal_id,
                    issuer=LOCAL_ISSUER,
                    subject=LOCAL_OWNER_SUBJECT,
                    created_at=side.clock.now(),
                )
            )
            uow.commit()

    none_api = _make_api(side, web_auth=WebAuthConfig(mode="none"))
    async with (
        none_api.router.lifespan_context(none_api),
        _open_raw(
            none_api,
            f"/api/v1/projects/{side.proj}/events/stream",
            headers={"Last-Event-ID": str(head)},
            client_peer=("127.0.0.1", 50000),
        ) as none_stream,
    ):
        assert none_stream.status == 200
        assert await none_stream.take() == _RETRY
        await _expect_run_frame(none_stream, head + 1, "RunResumed", run_p1)


# ----------------------------------------------------------------- Per-event RBAC & Cross-Project Isolation


async def test_project_sse_isolates_sibling_project_and_enforces_per_event_rbac(exec_side: ExecSide) -> None:
    side = exec_side
    proj2 = _create_second_project(side)
    run_p1 = _seed_project_run(side, side.proj)
    run_p2 = _seed_project_run(side, proj2)

    head = _head(side)
    # Record a workspace-level event, a P2 run event, and a P1 run event.
    with side.uow() as uow:
        uow.record(WorkspaceCreated(workspace_id=side.ws, slug=Slug("ws-ev"), title="WS Ev"))
        uow.commit()
    _append_run_event(side, run_p2, proj2, paused=True)
    _append_run_event(side, run_p1, side.proj, paused=False)
    _append_run_event(side, run_p2, proj2, paused=False)

    owner_token = cast("access.CreateTokenResult", side.client.dispatch(access.CreateToken(name="owner-sse")))
    # Project-only token with project.read ONLY (NO run.read)
    p1_no_run_secret = _paired_secret(side, (ScopeGrant(ScopeId(side.proj), frozenset({"project.read"})),))
    # Multi-scope token with workspace.read + P1 run.read ONLY (NO P2 permissions)
    ws_p1_only_secret = _paired_secret(
        side,
        (
            ScopeGrant(ScopeId(side.ws), frozenset({"workspace.read"})),
            ScopeGrant(ScopeId(side.proj), frozenset({"project.read", "run.read"})),
        ),
    )

    api = _make_api(side)
    async with api.router.lifespan_context(api):
        # Even as full OWNER, P1 stream NEVER leaks workspace-level or P2 events, nor cursor frames for P2!
        async with _open_raw(
            api,
            f"/api/v1/projects/{side.proj}/events/stream",
            headers={"Authorization": f"Bearer {owner_token.secret}", "Last-Event-ID": str(head)},
        ) as p1_stream:
            assert p1_stream.status == 200
            assert await p1_stream.take() == _RETRY
            await _expect_run_frame(p1_stream, head + 3, "RunResumed", run_p1)
            # P2 event at head + 4 must NOT emit a cursor frame revealing sibling-project activity.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(p1_stream.take(), timeout=0.15)

        # Caller with project.read on P1 but WITHOUT run.read NEVER sees run events or cursor leaks in P1.
        async with _open_raw(
            api,
            f"/api/v1/projects/{side.proj}/events/stream",
            headers={"Authorization": f"Bearer {p1_no_run_secret}", "Last-Event-ID": str(head)},
        ) as restricted_p1:
            assert restricted_p1.status == 200
            assert await restricted_p1.take() == _RETRY
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(restricted_p1.take(), timeout=0.15)

        # Caller with P1-only token cannot open P2's project SSE stream -> 403 FORBIDDEN.
        async with _open_raw(
            api,
            f"/api/v1/projects/{proj2}/events/stream",
            headers={"Authorization": f"Bearer {p1_no_run_secret}"},
        ) as forbidden_p2:
            assert forbidden_p2.status == 403
            assert json.loads(await forbidden_p2.take() or "")["code"] == "FORBIDDEN"

        # Workspace SSE with multi-scope grant delivers workspace + P1 run, NEVER P2 runs!
        async with _open_raw(
            api,
            "/api/v1/events",
            headers={"Authorization": f"Bearer {ws_p1_only_secret}", "Last-Event-ID": str(head)},
            params=(("workspace_id", str(side.ws)),),
        ) as ws_stream:
            assert ws_stream.status == 200
            assert await ws_stream.take() == _RETRY
            ws_frame = await ws_stream.take()
            assert ws_frame is not None
            assert "event: WorkspaceCreated" in ws_frame
            await _expect_run_frame(ws_stream, head + 3, "RunResumed", run_p1)
            assert await ws_stream.take() == f"id: {head + 4}\nevent: cursor\ndata: {{}}"

        # Opening project SSE without after/Last-Event-ID keeps workspace head internal (no initial cursor).
        async with _open_raw(
            api,
            f"/api/v1/projects/{side.proj}/events/stream",
            headers={"Authorization": f"Bearer {owner_token.secret}"},
        ) as live_p1:
            assert live_p1.status == 200
            assert await live_p1.take() == _RETRY
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(live_p1.take(), timeout=0.15)
            _append_run_event(side, run_p2, proj2, paused=True)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(live_p1.take(), timeout=0.15)
            _append_run_event(side, run_p1, side.proj, paused=True)
            await _expect_run_frame(live_p1, head + 6, "RunPaused", run_p1)


# --------------------------------------------------------------------------- Mid-Stream Revocation in SSE


@pytest.mark.parametrize(
    "revoke_mode",
    ["logout", "reload", "session_expired", "token_revoke", "disable_principal", "revoke_membership"],
)
async def test_project_sse_closes_promptly_on_mid_stream_revocation(
    exec_side: ExecSide, revoke_mode: str
) -> None:
    side = exec_side
    _set_owner_password(side)
    api = _make_api(side, poll_ms=25, heartbeat_seconds=60)
    path = f"/api/v1/projects/{side.proj}/events/stream"

    async with (
        api.router.lifespan_context(api),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as http,
    ):
        extra_principal: PrincipalId | None = None
        token_id: UUID | None = None
        csrf_token = ""

        if revoke_mode in {"logout", "reload"}:
            cookie, csrf_token = await _login_cookie(http)
            stream_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"}
        elif revoke_mode == "session_expired":
            _sid, cookie = _create_session(side, ttl_seconds=60)
            stream_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"}
        elif revoke_mode == "token_revoke":
            tok = cast("access.CreateTokenResult", side.client.dispatch(access.CreateToken(name="rev-sse")))
            token_id = tok.token_id
            stream_headers = {"Authorization": f"Bearer {tok.secret}"}
        else:
            # Create a separate human principal so we can disable it or revoke its membership.
            extra_principal = PrincipalId(uuid4())
            with side.uow() as uow:
                uow.repo(PrincipalRepository).add(
                    Principal(
                        id=extra_principal,
                        kind=PrincipalKind.HUMAN,
                        display_name="Reader",
                        state=PrincipalState.ACTIVE,
                        row_version=1,
                        created_at=side.clock.now(),
                        created_by=side.owner.principal_id,
                    )
                )
                uow.commit()
            side.client.dispatch(
                access.GrantMembership.from_json(
                    {"scope_id": str(side.ws), "principal_id": str(extra_principal), "role": "viewer"}
                )
            )
            _sid, cookie = _create_session(side, principal_id=extra_principal)
            stream_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"}

        async with _open_raw(api, path, headers=stream_headers) as stream:
            assert stream.status == 200
            assert await stream.take() == _RETRY

            if revoke_mode == "logout":
                resp = await http.post(
                    "/api/v1/auth/logout",
                    headers={"Origin": BASE, "X-SKM-CSRF": csrf_token},
                )
                assert resp.status_code == 200
            elif revoke_mode == "reload":
                resp = await http.post(
                    "/api/v1/auth/session/reload",
                    headers={"Origin": BASE, "X-SKM-CSRF": csrf_token},
                )
                assert resp.status_code == 200
            elif revoke_mode == "session_expired":
                side.clock.advance(timedelta(seconds=61))
            elif revoke_mode == "token_revoke":
                assert token_id is not None
                side.client.dispatch(access.RevokeToken(token_id))
            elif revoke_mode == "disable_principal":
                assert extra_principal is not None
                side.client.dispatch(
                    access.DisablePrincipal(extra_principal, expected_row_version=1, reason="revoked")
                )
            elif revoke_mode == "revoke_membership":
                assert extra_principal is not None
                side.client.dispatch(access.RevokeMembership(side.ws, extra_principal))

            assert await stream.take() is None


# ----------------------------------------------------------------- Worker-Only Live Publish & Live Revocation


def _ndjson_text(seq: int, text: str = "hello") -> bytes:
    event = {"type": "text_delta", "seq": seq, "at": _AT, "channel": "assistant", "text": text}
    return (json.dumps(event, separators=(",", ":")) + "\n").encode()


def _publish_headers(auth_headers: dict[str, str], claim_doc: dict[str, Any]) -> dict[str, str]:
    return {
        **auth_headers,
        "Content-Type": "application/x-ndjson",
        "SKM-Worker-Claim": json.dumps(claim_doc),
    }


async def test_live_publish_enforces_worker_only_across_all_auth_bases(worker_side: Any) -> None:
    side, worker_headers, human_headers = worker_side
    _set_owner_password(side)
    run, _task, _attempt, assignment = make_case(side)
    claim_doc = worker_claim(side, claim(side))
    publish_path = f"/api/v1/worker/attempts/{claim_doc['attempt_id']}/live"

    # Also create a service principal personal token and a worker assignment token.
    service_res = cast(
        "Any",
        side.client.dispatch(
            access.CreatePrincipal.from_json({"kind": "service", "display_name": "svc-live"})
        ),
    )
    side.client.dispatch(
        access.GrantMembership.from_json(
            {"scope_id": str(side.ws), "principal_id": str(service_res.principal_id), "role": "member"}
        )
    )
    service_tok = cast(
        "access.CreateTokenResult",
        side.client.dispatch(access.CreateToken(name="svc-tok", principal_id=service_res.principal_id)),
    )

    assignment_secret_obj = access.generate_secret(os.urandom)
    with side.uow() as uow:
        access.issue_assignment_token(
            uow,
            worker=side.worker1_client._actor,
            secret=assignment_secret_obj,
            run_scope_id=ScopeId(run.id),
            assignment_id=assignment.id,
            step_id=side.new_id(),
            expires_at=side.clock.now() + timedelta(hours=1),
            permissions=frozenset({"step.note", "run.read"}),
            pepper=PEPPER,
            now=side.clock.now(),
        )
        uow.commit()
    assignment_secret = str(assignment_secret_obj)

    api = worker_api(side, web_auth=WebAuthConfig(mode="admin_login"), settings={"api.sse.poll_ms": 20})
    async with (
        api.router.lifespan_context(api),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as http,
    ):
        # 1. Human Bearer token -> 403 FORBIDDEN
        r_human = await http.post(
            publish_path, content=_ndjson_text(1), headers=_publish_headers(human_headers, claim_doc)
        )
        problem(r_human, 403, "FORBIDDEN")

        # 2. Service Bearer token -> 403 FORBIDDEN
        r_svc = await http.post(
            publish_path,
            content=_ndjson_text(1),
            headers=_publish_headers(bearer(service_tok.secret), claim_doc),
        )
        problem(r_svc, 403, "FORBIDDEN")

        # 3. Worker assignment token -> 403 FORBIDDEN
        r_assign = await http.post(
            publish_path,
            content=_ndjson_text(1),
            headers=_publish_headers(bearer(assignment_secret), claim_doc),
        )
        problem(r_assign, 403, "FORBIDDEN")

        # 4. WebSession cookie (even with valid Origin + CSRF!) -> 403 FORBIDDEN
        _cookie, csrf = await _login_cookie(http)
        r_session = await http.post(
            publish_path,
            content=_ndjson_text(1),
            headers=_publish_headers({"Origin": BASE, "X-SKM-CSRF": csrf}, claim_doc),
        )
        problem(r_session, 403, "FORBIDDEN")

        # 5. Valid worker Bearer token (sent without owner cookie) -> 202 Accepted
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as worker_http:
            r_worker = await worker_http.post(
                publish_path,
                content=_ndjson_text(1, "worker-ok"),
                headers=_publish_headers(worker_headers, claim_doc),
            )
            assert r_worker.status_code == 202, r_worker.text

    # 6. Loopback web_auth.mode='none' local_owner -> 403 FORBIDDEN
    from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT, PrincipalIdentity
    from skm.modules.access.ports import IdentityRepository

    with side.uow() as uow:
        if uow.repo(IdentityRepository).find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT) is None:
            uow.repo(IdentityRepository).add(
                PrincipalIdentity(
                    principal_id=side.owner.principal_id,
                    issuer=LOCAL_ISSUER,
                    subject=LOCAL_OWNER_SUBJECT,
                    created_at=side.clock.now(),
                )
            )
            uow.commit()

    none_api = worker_api(side, web_auth=WebAuthConfig(mode="none"))
    async with (
        none_api.router.lifespan_context(none_api),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=none_api, client=("127.0.0.1", 50000)),
            base_url=BASE,
        ) as http_none,
    ):
        r_none = await http_none.post(
            publish_path, content=_ndjson_text(2), headers=_publish_headers({}, claim_doc)
        )
        problem(r_none, 403, "FORBIDDEN")


@pytest.mark.parametrize("revoke_mode", ["logout", "reload", "token_revoke", "revoke_membership"])
async def test_live_subscribe_supports_cookie_and_closes_on_mid_stream_revocation(
    worker_side: Any, revoke_mode: str
) -> None:
    side, worker_headers, _human_headers = worker_side
    _set_owner_password(side)
    _, _, _, _assignment = make_case(side)
    claim_doc = worker_claim(side, claim(side))
    publish_path = f"/api/v1/worker/attempts/{claim_doc['attempt_id']}/live"
    subscribe_path = f"/api/v1/attempts/{claim_doc['attempt_id']}/live"

    api = worker_api(
        side,
        web_auth=WebAuthConfig(mode="admin_login"),
        settings={"api.sse.poll_ms": 25, "api.sse.heartbeat_seconds": 60},
    )
    async with (
        api.router.lifespan_context(api),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as http,
    ):
        csrf_token = ""
        token_id: UUID | None = None
        extra_principal: PrincipalId | None = None

        if revoke_mode in {"logout", "reload"}:
            cookie, csrf_token = await _login_cookie(http)
            stream_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"}
        elif revoke_mode == "token_revoke":
            tok = cast("access.CreateTokenResult", side.client.dispatch(access.CreateToken(name="live-rev")))
            token_id = tok.token_id
            stream_headers = {"Authorization": f"Bearer {tok.secret}"}
        else:
            extra_principal = PrincipalId(uuid4())
            with side.uow() as uow:
                uow.repo(PrincipalRepository).add(
                    Principal(
                        id=extra_principal,
                        kind=PrincipalKind.HUMAN,
                        display_name="LiveViewer",
                        state=PrincipalState.ACTIVE,
                        row_version=1,
                        created_at=side.clock.now(),
                        created_by=side.owner.principal_id,
                    )
                )
                uow.commit()
            side.client.dispatch(
                access.GrantMembership.from_json(
                    {"scope_id": str(side.ws), "principal_id": str(extra_principal), "role": "viewer"}
                )
            )
            _sid, cookie = _create_session(side, principal_id=extra_principal)
            stream_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"}

        # Publish an initial frame as the worker (cookieless client).
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as worker_http:
            pub = await worker_http.post(
                publish_path,
                content=_ndjson_text(1, "live-chunk-1"),
                headers=_publish_headers(worker_headers, claim_doc),
            )
            assert pub.status_code == 202

        async with _open_raw(api, subscribe_path, headers=stream_headers) as stream:
            assert stream.status == 200
            first = await stream.take()
            assert first is not None
            assert "live-chunk-1" in first

            if revoke_mode == "logout":
                resp = await http.post(
                    "/api/v1/auth/logout",
                    headers={"Origin": BASE, "X-SKM-CSRF": csrf_token},
                )
                assert resp.status_code == 200
            elif revoke_mode == "reload":
                resp = await http.post(
                    "/api/v1/auth/session/reload",
                    headers={"Origin": BASE, "X-SKM-CSRF": csrf_token},
                )
                assert resp.status_code == 200
            elif revoke_mode == "token_revoke":
                assert token_id is not None
                side.client.dispatch(access.RevokeToken(token_id))
            elif revoke_mode == "revoke_membership":
                assert extra_principal is not None
                side.client.dispatch(access.RevokeMembership(side.ws, extra_principal))

            assert await stream.take() is None


async def test_session_stream_quota_shared_across_project_sse_and_live(worker_side: Any) -> None:
    side, _worker_headers, _human_headers = worker_side
    _, _, _, _assignment = make_case(side)
    claim_doc = worker_claim(side, claim(side))
    api = worker_api(
        side,
        web_auth=WebAuthConfig(mode="admin_login"),
        settings={"api.sse.poll_ms": 25, "api.sse.max_streams_per_token": 1},
    )
    _sid1, cookie1 = _create_session(side)
    _sid2, cookie2 = _create_session(side)

    async with api.router.lifespan_context(api):
        async with _open_raw(
            api,
            f"/api/v1/projects/{side.proj}/events/stream",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie1}"},
        ) as s1:
            assert s1.status == 200
            assert await s1.take() == _RETRY

            # Same session hitting live attempt stream gets 429 TOO_MANY_STREAMS
            async with _open_raw(
                api,
                f"/api/v1/attempts/{claim_doc['attempt_id']}/live",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie1}"},
            ) as excess:
                assert excess.status == 429
                assert json.loads(await excess.take() or "")["code"] == "TOO_MANY_STREAMS"

            # Different session has its own independent quota
            async with _open_raw(
                api,
                f"/api/v1/attempts/{claim_doc['attempt_id']}/live",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie2}"},
            ) as s2:
                assert s2.status == 200

        # Once s1 disconnects, quota is released
        async with _open_raw(
            api,
            f"/api/v1/attempts/{claim_doc['attempt_id']}/live",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie1}"},
        ) as reopened:
            assert reopened.status == 200
