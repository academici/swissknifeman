"""Build routers with real config parsing and an in-memory upstream transport."""

import asyncio
import os
import warnings
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
import pytest

from skm.bootstrap.router import RouterState
from skm.entrypoints.api.router.app import create_router_app

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message="The anyio.abc.BlockingPortal alias is deprecated", category=DeprecationWarning
    )
    from starlette.testclient import TestClient


class _PipeWakeupLoop(asyncio.SelectorEventLoop):
    """Wake the in-process ASGI harness even when socket.send is sandboxed."""

    def _make_self_pipe(self) -> None:
        self._read_wakeup, self._write_wakeup = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        self._add_reader(self._read_wakeup, self._drain_wakeup)  # pyright: ignore[reportAttributeAccessIssue]

    def _drain_wakeup(self) -> None:
        with suppress(BlockingIOError):
            os.read(self._read_wakeup, 65_536)

    def _write_to_self(self) -> None:
        with suppress(BlockingIOError):
            os.write(self._write_wakeup, b"\0")

    def _close_self_pipe(self) -> None:
        self._remove_reader(self._read_wakeup)  # pyright: ignore[reportAttributeAccessIssue]
        os.close(self._read_wakeup)
        os.close(self._write_wakeup)


def asgi_client(state: RouterState) -> TestClient:
    return TestClient(
        create_router_app(state),
        base_url="http://127.0.0.1",
        backend_options={"loop_factory": _PipeWakeupLoop},
    )


AUTH = {"Authorization": "Bearer client-one"}
MANAGEMENT = {"Authorization": "Bearer router-admin"}

type Slot = tuple[str, str, str, int]


def slot_toml(slot: Slot) -> str:
    name, provider, model, tier = slot
    return f"""
[slots.{name}]
runtime_id = "codex"
transport = "http_api"
tier = {tier}
provider = "{provider}"
base_url = "https://{name}.example/v1"
api_key_ref = "secret://env/ROUTER_UPSTREAM_KEY"
models = [{{name = "{model}", is_compat = false}}]
"""


@pytest.fixture
def router_factory(tmp_path: Path) -> Iterator[Callable[..., RouterState]]:
    states: list[RouterState] = []

    def build(*slots: Slot, overrides: str = "", extra: str = "") -> RouterState:
        path = tmp_path / f"pool-{len(states)}.toml"
        path.touch(mode=0o600)
        path.write_text(
            'schema_version = 2\n[router]\nmanagement_key = "router-admin"\n'
            'client_keys = {one = "client-one", two = "client-two"}\n'
            + overrides
            + "".join(map(slot_toml, slots or (("primary", "anthropic", "model", 1),)))
            + extra,
            encoding="utf-8",
        )
        state = RouterState(path, tmp_path, {"ROUTER_UPSTREAM_KEY": "provider-key"}, tmp_path)
        states.append(state)
        return state

    yield build
    for state in states:
        state.close()


@pytest.fixture
def http_router(monkeypatch: pytest.MonkeyPatch) -> Callable[..., TestClient]:
    original = httpx.AsyncClient

    def build(state: RouterState, handler: Callable[[httpx.Request], httpx.Response]) -> TestClient:
        def client(**kwargs: Any) -> httpx.AsyncClient:
            assert kwargs["trust_env"] is False
            return original(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", client)
        return asgi_client(state)

    return build


def upstream(payload: bytes, *, status: int = 200, media: str = "application/json") -> httpx.Response:
    # Supplying a stream exercises the same streaming transport path as an actual HTTP server.
    return httpx.Response(status, stream=httpx.ByteStream(payload), headers={"content-type": media})
