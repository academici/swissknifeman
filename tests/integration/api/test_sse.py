"""Workspace SSE over the real HTTP boundary, access policy, and PostgreSQL event store."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from threading import Event
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb
from starlette.applications import Starlette

from contracts.execution.harness import PEPPER, ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import record_run_event, seed_bundle, seed_run
from integration.api._sse_helpers import _append, _cursor, _expect_event, _open, _record
from integration.api._sse_helpers import _Stream as _Stream
from security.api.harness import BASE
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.events import EventListener
from skm.application_bus.ports import EventReader, OutboxStore
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.api.sse import EventWakeups
from skm.kernel.ids import RunId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import CreateToken, CreateTokenResult, RevokeToken, authenticate_token
from skm.modules.execution.domain.run import RunStatus
from skm.modules.policy.public import ProposeIntent, ProposeIntentResult
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.system_clock import SystemClock
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.policy.application.harness import push_args

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.pg,
    pytest.mark.parametrize("exec_side", ["postgres"], indirect=True),
]

_RETRY = "retry: 3000"
_LISTENER = "skm-sse-integration-listener"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def side(exec_side: ExecSide) -> ExecSide:
    # The harness seeds a deterministic historical instant. New API tokens use the server's wall clock.
    exec_side.clock.advance(SystemClock().now() - exec_side.clock.now())
    return exec_side


def _token(side: ExecSide, **restrictions) -> CreateTokenResult:
    token = side.client.dispatch(CreateToken(name=f"sse-{uuid4()}", **restrictions))
    assert isinstance(token, CreateTokenResult)
    return token


def _application(
    side: ExecSide, *, listener: EventWakeups | None = None, redactor: Redactor | None = None, **options: int
) -> Starlette:
    def authenticate(secret: str):
        with side.uow(readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=SystemClock().now())

    assert side.dsn is not None
    return create_app(
        replace(side.app, authenticator=authenticate),
        route_table=build_route_table(("access", "workspace", "execution")),
        registry=side.app.bus._registry,
        no_background=True,
        redactor=redactor,
        settings={f"api.sse.{name}": value for name, value in {"poll_ms": 30, **options}.items()},
        event_listener=listener or EventListener(PgSettings(side.dsn, _LISTENER, pool_timeout_seconds=2)),
    )


def _headers(token: CreateTokenResult) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.secret}"}


def _head(side: ExecSide) -> int:
    with side.uow(readonly=True) as uow:
        return uow.repo(EventReader).head_workspace_seq(side.ws)


def _run(side: ExecSide, *, status: RunStatus = RunStatus.RUNNING, foreign: bool = False) -> RunId:
    with side.uow() as uow:
        run = seed_run(
            side,
            uow,
            status=status,
            **(
                {"ws": side.ws2, "proj": side.proj2, "plan_id": side.plan2_ws2, "rev_id": side.rev_ws2}
                if foreign
                else {}
            ),
        )
        seed_bundle(side, uow, run.id)
        uow.commit()
    return run.id


async def test_sse_reconnect_no_gaps(side: ExecSide) -> None:
    token, run = _token(side), _run(side)
    app, head = _application(side, batch_size=1), _head(side)
    _append(side, run, paused=True)
    async with app.router.lifespan_context(app):
        async with _open(app, token, side.ws, last=head) as stream:
            assert stream.status == 200
            assert stream.headers["content-type"] == "text/event-stream; charset=utf-8"
            assert stream.headers["cache-control"] == "no-store"
            assert stream.headers["x-accel-buffering"] == "no"
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 1, "RunPaused", run)

        _append(side, run)
        _append(side, run, paused=True)
        async with _open(app, token, side.ws, last=head + 1, params=(("after", "invalid"),)) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 2, "RunResumed", run)
            await _expect_event(stream, head + 3, "RunPaused", run)


async def test_sse_stream_filter_isolates_runs(side: ExecSide) -> None:
    token, run, other = _token(side), _run(side), _run(side)
    complete = _run(side, status=RunStatus.SUCCEEDED)
    app, head = _application(side, batch_size=2), _head(side)
    _append(side, run)
    _append(side, other)
    _append(side, run, paused=True)
    _append(side, complete)
    filters = (
        ("stream", f"run:{run}"),
        ("stream", f"run:{uuid4()}"),
        ("types", "RunResumed,urn:skm:execution:event:run-paused:v1"),
    )
    async with app.router.lifespan_context(app):
        async with _open(app, token, side.ws, last=head, params=filters) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 1, "RunResumed", run)
            assert await stream.take() == _cursor(head + 2)
        async with _open(app, token, side.ws, last=head + 2, params=filters) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 3, "RunPaused", run)
            assert await stream.take() == _cursor(head + 4)
        async with _open(app, token, side.ws, params=(("stream", f"run:{complete}"),)) as stream:
            assert await stream.take() == _RETRY
            assert await stream.take() == _cursor(head + 4)
            _append(side, other)
            assert await stream.take() == _cursor(head + 5)


async def test_sse_initial_cursor_without_gaps(side: ExecSide) -> None:
    token, run = _token(side), _run(side)
    app, head = _application(side), _head(side)
    staged, commit = Event(), Event()

    def write() -> None:
        with side.uow() as uow:
            _record(side, uow, run)
            staged.set()
            assert commit.wait(4)
            uow.commit()

    async with app.router.lifespan_context(app):
        writer = asyncio.create_task(asyncio.to_thread(write))
        try:
            assert await asyncio.to_thread(staged.wait, 4)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
                result = await client.get(f"/api/v1/runs/{run}", headers=_headers(token))
                assert result.status_code == 200, result.text
                assert result.headers["SKM-Events-Cursor"] == str(head)
                cached = await client.get(
                    f"/api/v1/runs/{run}",
                    headers={**_headers(token), "If-None-Match": result.headers["etag"]},
                )
                assert cached.status_code == 304
                assert cached.headers["SKM-Events-Cursor"] == str(head)
        finally:
            commit.set()
            await writer
        resume = (("after", result.headers["SKM-Events-Cursor"]),)
        async with _open(app, token, side.ws, params=resume) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 1, "RunResumed", run)

        async with _open(app, token, side.ws) as stream:
            assert await stream.take() == _RETRY
            assert await stream.take() == _cursor(head + 1)
            _append(side, run, paused=True)
            await _expect_event(stream, head + 2, "RunPaused", run)


async def test_workspace_and_project_get_cursor_on_200_and_304(side: ExecSide) -> None:
    token, run, app = _token(side), _run(side), _application(side)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client,
    ):
        for path in (f"/api/v1/workspaces/{side.ws}", f"/api/v1/projects/{side.proj}"):
            head = _head(side)
            response = await client.get(path, headers=_headers(token))
            assert response.status_code == 200, response.text
            assert response.headers["SKM-Events-Cursor"] == str(head)
            _append(side, run)
            cached = await client.get(
                path, headers={**_headers(token), "If-None-Match": response.headers["etag"]}
            )
            assert cached.status_code == 304
            assert cached.headers["SKM-Events-Cursor"] == str(head + 1)


async def test_intent_replay_with_policy_read_without_token_own(side: ExecSide) -> None:
    reader = _token(side, scope_id=side.ws, permissions=("workspace.read", "policy.read"))
    restricted = _token(side, scope_id=side.ws, permissions=("workspace.read",))
    app, head = _application(side), _head(side)
    intent = side.client.dispatch(
        ProposeIntent.from_json(
            {
                "scope_id": str(side.proj),
                "subject_ref": f"project:{side.proj}",
                "kind": "git_push",
                "args": push_args(),
                "reason": "SSE replay",
            }
        )
    )
    assert isinstance(intent, ProposeIntentResult)
    async with app.router.lifespan_context(app):
        async with _open(app, reader, side.ws, last=head) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 1, "IntentProposed", intent.intent_id, "intent")
        async with _open(app, restricted, side.ws, last=head) as stream:
            assert await stream.take() == _RETRY
            assert await stream.take() == _cursor(_head(side))


async def test_lesson_candidate_and_vault_note_replay(side: ExecSide) -> None:
    lessons = _token(side, scope_id=side.ws, permissions=("workspace.read", "lesson.read"))
    plans = _token(side, scope_id=side.ws, permissions=("workspace.read", "plan.read"))
    app, head = _application(side), _head(side)
    lesson, candidate, note, local_candidate = uuid4(), uuid4(), uuid4(), uuid4()
    history: list[tuple[str, str, UUID, JsonObject]] = [
        (
            "lesson",
            "urn:skm:knowledge:event:lesson-promoted:v1",
            lesson,
            {"lesson_id": str(lesson), "candidate_id": str(candidate)},
        ),
        (
            "candidate",
            "urn:skm:learning:event:candidate-reviewed:v1",
            candidate,
            {
                "candidate_id": str(candidate),
                "review_id": str(uuid4()),
                "verdict": "approve",
                "reviewer_id": str(side.owner.principal_id),
            },
        ),
        (
            "vault_note",
            "urn:skm:exports:event:vault-note-written:v1",
            note,
            {
                "note_id": str(note),
                "vault_id": str(uuid4()),
                "generation": 1,
                "host_id": str(side.host1),
                "relative_path": "plan.md",
                "outcome": "created",
            },
        ),
    ]
    for project, owner in ((side.proj, local_candidate), (side.proj2, uuid4())):
        history.append(
            (
                "candidate",
                "urn:skm:learning:event:candidate-extracted:v1",
                owner,
                {
                    "candidate_id": str(owner),
                    "project_id": str(project),
                    "detector": "workaround",
                    "consolidation": "add",
                    "conflicts_with_id": None,
                    "pathology_code": None,
                },
            )
        )
    # Seed committed history for optional modules whose command handlers are not registered yet.
    assert side.dsn is not None
    with psycopg.connect(side.dsn) as conn:
        for seq, (kind, urn, owner, payload) in enumerate(history, head + 1):
            side.app.schemas.require_valid(urn, payload)
            conn.execute(
                "INSERT INTO skm_core.domain_events (id, workspace_id, stream_kind, stream_id, stream_seq, "
                "workspace_seq, event_type, correlation_id, payload, occurred_at) "
                "VALUES (%s, %s, %s, %s, 1, %s, %s, 'sse-replay', %s, now())",
                (uuid4(), side.ws, kind, owner, seq, urn, Jsonb(payload)),
            )
    async with app.router.lifespan_context(app):
        async with _open(app, lessons, side.ws, last=head) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 1, "LessonPromoted", lesson, "lesson")
            await _expect_event(stream, head + 2, "CandidateReviewed", candidate, "candidate")
            await _expect_event(stream, head + 4, "CandidateExtracted", local_candidate, "candidate")
            assert await stream.take() == _cursor(head + 5)
        async with _open(app, plans, side.ws, last=head) as stream:
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 3, "VaultNoteWritten", note, "vault_note")
            assert await stream.take() == _cursor(head + 5)


async def test_sse_instance_events_not_streamed(side: ExecSide) -> None:
    token, run, foreign = _token(side), _run(side), _run(side, foreign=True)
    app, head = _application(side), _head(side)
    with side.uow(readonly=True) as uow:
        global_events = uow.repo(EventReader).after_global_position(0, limit=100)
        assert {"pack-installed", "host-registered"} <= {event.type.split(":")[-2] for event in global_events}
    _append(side, foreign)  # A workspace row with an unresolved/foreign owning scope.
    _append(side, run)
    types = (("types", "PackInstalled,HostRegistered,RunResumed"),)
    async with app.router.lifespan_context(app), _open(app, token, side.ws, last=0, params=types) as stream:
        assert await stream.take() == _RETRY
        await _expect_event(stream, head + 2, "RunResumed", run)


async def test_sse_requires_workspace_and_stream_permissions(side: ExecSide) -> None:
    token = _token(side, scope_id=side.ws, permissions=("workspace.read",))
    run, app, head = _run(side), _application(side), _head(side)
    _append(side, run)
    async with app.router.lifespan_context(app):
        async with _open(app, token, side.ws, last=head) as stream:
            assert await stream.take() == _RETRY
            assert await stream.take() == _cursor(head + 1)
        async with _open(app, token, side.ws2) as stream:
            assert stream.status == 403
            assert json.loads(await stream.take() or "")["code"] == "FORBIDDEN"
        async with _open(app, token, WorkspaceId(uuid4())) as stream:
            assert stream.status == 404
            assert stream.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize("check", ["batch", "heartbeat"])
async def test_sse_revocation_closes_open_stream(side: ExecSide, check: str) -> None:
    token, run = _token(side), _run(side)
    app = (
        _application(side, poll_ms=10000, heartbeat_seconds=1) if check == "heartbeat" else _application(side)
    )
    head = _head(side)
    async with app.router.lifespan_context(app), _open(app, token, side.ws) as stream:
        assert await stream.take() == _RETRY
        assert await stream.take() == _cursor(head)
        if check == "heartbeat":
            ping = await stream.take()
            assert ping is not None
            assert ping.startswith(": ping ")
            assert ping.removeprefix(": ping ").isdecimal()
        else:
            _append(side, run)
            await _expect_event(stream, head + 1, "RunResumed", run)
        side.client.dispatch(RevokeToken(token.token_id))
        if check == "batch":
            _append(side, run, paused=True)
        assert await stream.take() is None


async def test_sse_stream_limit_is_per_token_and_released_on_disconnect(side: ExecSide) -> None:
    token, other = _token(side), _token(side)
    app = _application(side, max_streams_per_token=1)
    async with app.router.lifespan_context(app):
        async with _open(app, token, side.ws) as stream:
            assert await stream.take() == _RETRY
            async with _open(app, token, side.ws2) as excess:
                assert excess.status == 429
                assert json.loads(await excess.take() or "")["code"] == "TOO_MANY_STREAMS"
            async with _open(app, other, side.ws) as independent:
                assert independent.status == 200
        async with _open(app, token, side.ws2) as reopened:
            assert reopened.status == 200


async def test_sse_slow_consumer_closes_on_queue_overflow(side: ExecSide) -> None:
    class Wakeups:
        def start(self, wake: Callable[[WorkspaceId], None]) -> None:
            self.wake = wake

        def stop(self) -> None:
            pass

    listener, token = Wakeups(), _token(side)
    app = _application(side, listener=listener, queue_size=1, max_streams_per_token=1)
    writable = asyncio.Event()
    async with app.router.lifespan_context(app), _open(app, token, side.ws, pause=writable) as stream:
        assert await stream.take() == _RETRY
        assert await stream.take() == _cursor(_head(side))
        listener.wake(side.ws)
        listener.wake(side.ws)
        async with _open(app, token, side.ws) as reopened:
            assert reopened.status == 200
            assert await reopened.take() == _RETRY
            await asyncio.wait_for(asyncio.shield(stream.task), 4)
            assert not writable.is_set()


async def test_sse_notify_loss_falls_back_to_polling(side: ExecSide) -> None:
    token, run = _token(side), _run(side)
    app, head = _application(side), _head(side)
    async with app.router.lifespan_context(app), _open(app, token, side.ws) as stream:
        assert await stream.take() == _RETRY
        assert await stream.take() == _cursor(head)
        # No SSE relay runs in this application. Both rows remain pending in the durable outbox.
        _append(side, run)
        await _expect_event(stream, head + 1, "RunResumed", run)
        _append(side, run, paused=True)
        await _expect_event(stream, head + 2, "RunPaused", run)


async def test_sse_listen_wakes_only_the_matching_feed(side: ExecSide) -> None:
    token, run = _token(side), _run(side)
    app, head = _application(side, poll_ms=10000), _head(side)
    assert side.dsn is not None
    async with app.router.lifespan_context(app), _open(app, token, side.ws) as stream:
        assert await stream.take() == _RETRY
        assert await stream.take() == _cursor(head)
        async with await psycopg.AsyncConnection.connect(side.dsn, autocommit=True) as conn:
            async with asyncio.timeout(4):
                while True:
                    result = await conn.execute(
                        "SELECT 1 FROM pg_stat_activity WHERE application_name = %s AND query = %s",
                        (_LISTENER, "LISTEN skm_events"),
                    )
                    if await result.fetchone() is not None:
                        break
                    await asyncio.sleep(0.01)
            # Let the initial empty scan finish, then commit a row without running the background relay.
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.15):
                    await stream.take()
            _append(side, run)
            found = await conn.execute(
                "SELECT o.id FROM skm_core.outbox o JOIN skm_core.domain_events e ON e.id = o.event_id "
                "WHERE o.destination = 'sse' AND e.workspace_id = %s AND e.workspace_seq = %s",
                (side.ws, head + 1),
            )
            row = await found.fetchone()
            assert row is not None
            notice = f"{side.ws2}:{head + 1}"
            await conn.execute("SELECT pg_notify('skm_events', %s)", (notice,))
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.15):
                    await stream.take()
            with side.uow() as uow:
                assert uow.repo(OutboxStore).mark_delivered(row[0], at=side.clock.now())
                uow.commit()
            await _expect_event(stream, head + 1, "RunResumed", run)


async def test_history_snapshot_to_filtered_stream_then_resume_and_revoke(side: ExecSide) -> None:
    token = _token(side, permissions=("workspace.read", "project.read", "run.read"))
    watched, other = _run(side), _run(side)
    _append(side, other)
    _append(side, watched)
    app, head = _application(side), _head(side)
    assert head > 1
    path = f"/api/v1/runs/{watched}/history"
    filters = (("stream", f"run:{watched}"),)
    staged, commit = Event(), Event()

    def later() -> None:
        with side.uow() as uow:
            _record(side, uow, other, paused=True)
            _record(side, uow, watched, paused=True)
            staged.set()
            assert commit.wait(5)
            uow.commit()

    async with app.router.lifespan_context(app):
        writer = asyncio.create_task(asyncio.to_thread(later))
        try:
            assert await asyncio.to_thread(staged.wait, 5)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
                snapshot = await http.get(path, headers=_headers(token))
            assert snapshot.status_code == 200, snapshot.text
            assert snapshot.json()["through_seq"] == 1
            assert snapshot.headers["SKM-Events-Cursor"] == str(head)
        finally:
            commit.set()
            await writer
        after = (("after", snapshot.headers["SKM-Events-Cursor"]),)
        async with _open(app, token, side.ws, params=filters + after) as stream:
            assert stream.status == 200
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 2, "RunPaused", watched, stream_seq=2)
            _append(side, other)
            assert await stream.take() == _cursor(head + 3)

        _append(side, watched)
        async with _open(app, token, side.ws, last=head + 3, params=filters) as stream:
            assert stream.status == 200
            assert await stream.take() == _RETRY
            await _expect_event(stream, head + 4, "RunResumed", watched, stream_seq=3)
            side.client.dispatch(RevokeToken(token.token_id))
            _append(side, watched, paused=True)
            assert await stream.take() is None


async def test_sse_keeps_run_identity_and_filters_diagnostic_content(side: ExecSide) -> None:
    from security._security_helpers import canaries

    values = canaries()
    owner = _token(side)
    reader = _token(side, permissions=("workspace.read", "run.read"))
    run = _run(side)
    correlation, (app, head) = str(uuid4()), (_application(side), _head(side))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http,
        _open(app, reader, side.ws, last=head, params=(("stream", f"run:{run}"),)) as stream,
    ):
        assert await stream.take() == _RETRY
        response = await http.post(
            f"/api/v1/runs/{run}/cancel",
            json={"reason": f"{values.document} {values.secret}"},
            headers={**_headers(owner), "SKM-Correlation-Id": correlation},
        )
        assert response.status_code == 200
        frame = await stream.take()
        assert frame is not None
        assert frame.startswith(f"id: {head + 1}\nevent: RunCancelled\n")
        assert str(run) in frame
        envelope = json.loads(frame.splitlines()[-1].removeprefix("data: "))
        assert values.document not in frame
        assert values.secret not in frame
        assert envelope["correlation_id"] == correlation


@pytest.mark.parametrize("kind", ["cancelled", "paused"])
async def test_sse_projects_legacy_run_control_rows(side: ExecSide, kind: str) -> None:
    from security._security_helpers import canaries

    values = canaries()
    token, run, head = _token(side), _run(side), _head(side)
    actor = str(side.owner.principal_id)
    values.redactor.register_secret(actor)
    stop_key = "stop_code" if kind == "paused" else "previous_stop_code"
    cause: JsonObject = {
        "trigger_kind": "subscription" if kind == "paused" else "cancel",
        "advance_rule": "R6" if kind == "paused" else "R10",
        "reason_codes": ["BUDGET_EXHAUSTED"],
        "refs": [{"kind": "run", "id": str(run)}],
        "source_event_id": str(uuid4()),
    }
    payload: JsonObject = {
        "workspace_id": str(side.ws),
        "project_id": str(side.proj),
        "run_id": str(run),
        "by": actor,
        "reason": values.document,
        stop_key: "BUDGET_EXHAUSTED",
        "cause": cause,
    }
    if kind == "paused":
        payload["pause_source"] = "system"
    with side.uow() as uow:
        record_run_event(side, uow, run, f"run-{kind}", payload)
        uow.commit()
    app = _application(side, redactor=values.redactor)
    async with app.router.lifespan_context(app), _open(app, token, side.ws, last=head) as stream:
        assert await stream.take() == _RETRY
        frame = await stream.take()
        assert frame is not None
        identifier, event, data = frame.splitlines()
        assert (identifier, event) == (f"id: {head + 1}", f"event: Run{kind.title()}")
        assert values.document not in frame
        envelope = json.loads(data.removeprefix("data: "))
        safe = envelope["payload"]
        assert (safe["by"], safe["run_id"], safe[stop_key]) == (MASK, str(run), "BUDGET_EXHAUSTED")
        assert safe["reason"] == ("BUDGET_EXHAUSTED" if kind == "paused" else "RUN_CANCELLED")
        assert safe["cause"] == cause
        assert (envelope["stream_seq"], envelope["workspace_seq"]) == (1, head + 1)
