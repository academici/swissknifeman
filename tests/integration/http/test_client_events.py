"""History and live deadlines on a real, deliberately stalled SSE connection."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from time import monotonic

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from integration.http.test_client import WS, _event, routes, secret
from skm.adapters.http_client.client import HttpSkmClient
from skm.bootstrap.host_services import build_host_storage
from support.http_server import loopback_server


@pytest.mark.integration
@pytest.mark.parametrize("wait_seconds", [0, 1.0])
def test_delayed_history_and_silent_connection(tmp_path: Path, wait_seconds: float) -> None:
    async def stream() -> AsyncIterator[str]:
        yield "retry: 1000\n\n"
        await asyncio.sleep(0.7)
        yield _event(1) + "id: 2\nevent: cursor\ndata: {}\n\n"
        yield _event(3)
        await asyncio.sleep(5)

    async def events(_: Request) -> StreamingResponse:
        return StreamingResponse(stream(), media_type="text/event-stream")

    with loopback_server(lambda _: Starlette(routes=[Route("/api/v1/events", events)])) as endpoint:
        client = HttpSkmClient(
            endpoint,
            secret(),
            routes(),
            spool_root=tmp_path / "spool",
            storage_budget=build_host_storage(tmp_path),
            min_free_bytes=0,
            timeout_seconds=3.0,
        )
        try:
            started = monotonic()
            history = [
                ev.workspace_seq for ev in client.events(workspace_id=WS, after=0, wait_seconds=wait_seconds)
            ]
            elapsed = monotonic() - started
        finally:
            client.close()
    assert history == [1, 3]
    if wait_seconds:
        assert wait_seconds <= elapsed < wait_seconds + 0.25
    else:
        assert elapsed < 1.6
