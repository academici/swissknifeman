"""Authenticate and serve the local LLM router over ASGI."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import signal
import sys
from contextlib import ExitStack, asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, override

import uvicorn
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response
from starlette.routing import Route

from skm.bootstrap.router import (
    CHAT,
    COUNT,
    LOOPBACK,
    MESSAGES,
    RESPONSES,
    DedupKey,
    Inflight,
    RouterGeneration,
    RouterState,
    dedup_key,
    serve_router,
)
from skm.kernel.errors import SkmError
from skm.platform.fs.file_lock import LockTimeout

from .exchange import Exchange, Reply, max_response_bytes
from .inference import CONVERSATION_MODEL_PREFIX, Invocation, dispatch, error_reply, json_reply

if TYPE_CHECKING:
    import socket
    from collections.abc import AsyncGenerator, Callable, Mapping

    from starlette.types import Receive, Scope, Send

__all__ = ["create_router_app", "main"]

_PATHS = (MESSAGES, COUNT, CHAT, RESPONSES, "/v1/models")
_PASSTHROUGH = ("anthropic-version", "anthropic-beta", "content-type", "accept")


def _matches(known: str, presented: str) -> bool:
    return hmac.compare_digest(known.encode(), presented.encode())


def _auth(
    headers: Mapping[str, str],
    generation: RouterGeneration,
    state: RouterState,
    *,
    management: bool,
) -> tuple[str, bool] | int:
    authorization = headers.get("authorization", "")
    scheme, _, bearer = authorization.partition(" ")
    api_key = headers.get("x-api-key", "")
    if authorization and (scheme.casefold() != "bearer" or not bearer):
        return 401
    if bearer and api_key and not _matches(bearer, api_key):
        return 401
    token = bearer or api_key
    if not token or len(token) > 8192:
        return 401
    marker = headers.get("x-skm-internal-hop")
    signature = headers.get("x-skm-internal-signature")
    if marker is not None or signature is not None or token.startswith("skm-hop-"):
        client = state.hop.authenticate(token, marker or "", signature or "")
        return (403 if management else (client, True)) if client is not None else 401
    admin = _matches(generation.management_key.reveal(), token)
    client = None
    for client_id, key in generation.client_keys.items():
        if _matches(key.reveal(), token):
            client = client_id
    if admin:
        return ("", False) if management else 403
    if client is not None:
        return 403 if management else (client, False)
    return 401


def _response(reply: Reply) -> Response:
    return Response(reply.body, status_code=reply.status, headers=reply.headers)


def _auth_error(status: int) -> Response:
    reply = error_reply(
        status, "invalid router key" if status == 401 else "router key is not authorized for this route"
    )
    if status == 401:
        reply.headers["www-authenticate"] = "Bearer"
    return _response(reply)


async def _read(request: Request) -> tuple[dict[str, Any], bytes]:
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > max_response_bytes:
            raise OverflowError
        raw.extend(chunk)
    body: object = json.loads(raw.decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("expected a JSON object")
    # Reject non-finite input before canonicalization or translation.
    json.dumps(body, allow_nan=False)
    return cast("dict[str, Any]", body), bytes(raw)


def _conversation(headers: Mapping[str, str], model: str) -> str | None:
    value = headers.get("x-conversation-id")
    if value is None and model.startswith(CONVERSATION_MODEL_PREFIX):
        value = model.removeprefix(CONVERSATION_MODEL_PREFIX)
    if value is not None and (not value.strip() or len(value) > 512):
        raise ValueError("invalid conversation ID")
    return value


async def _disconnect(receive: Receive) -> None:
    while (await receive())["type"] != "http.disconnect":
        pass


class _InferenceResponse(Response):
    def __init__(
        self,
        state: RouterState,
        generation: RouterGeneration,
        work: Invocation,
        inflight: Inflight[tuple[Exchange, tuple[str | None, ...]]],
        key: DedupKey | None,
        resources: ExitStack,
    ) -> None:
        super().__init__()
        self.resources = resources
        self.state, self.generation, self.work, self.inflight, self.key = (
            state,
            generation,
            work,
            inflight,
            key,
        )

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope
        headers = tuple(self.work.headers.get(key) for key in _PASSTHROUGH)
        # The generation must remain available after the endpoint hands off to ASGI.
        with self.resources:

            async def produce(output: Exchange) -> None:
                with self.state.lease(self.generation):
                    await dispatch(self.generation, self.work, output)

            (exchange, _), release = self.inflight.acquire(
                self.key,
                lambda: (Exchange(produce), headers),
                lambda current: current[0].joinable and current[1] == headers,
            )
            subscriber = exchange.subscribe()
            sending = asyncio.create_task(exchange.send(subscriber, send))
            disconnected = asyncio.create_task(_disconnect(receive))
            try:
                done, _ = await asyncio.wait((sending, disconnected), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            except (ClientDisconnect, OSError):
                pass
            finally:
                sending.cancel()
                disconnected.cancel()
                await asyncio.gather(sending, disconnected, return_exceptions=True)
                exchange.leave(subscriber)
                if release():
                    if not exchange.task.done():
                        exchange.task.cancel()
                    await asyncio.gather(exchange.task, return_exceptions=True)


def create_router_app(state: RouterState, *, on_start: Callable[[], None] | None = None) -> Starlette:
    """Build an ASGI app over the validated router composition root."""
    inflights: dict[int, Inflight[tuple[Exchange, tuple[str | None, ...]]]] = {}

    async def inference(request: Request) -> Response:
        path = request.url.path
        if not path.startswith("/v1/"):
            path = "/v1" + path
        with ExitStack() as resources:
            generation = resources.enter_context(state.lease())
            auth = _auth(request.headers, generation, state, management=False)
            if isinstance(auth, int):
                return _auth_error(auth)
            client, internal = auth
            if path == "/v1/models":
                models = sorted(
                    {
                        route.model.name
                        for route in generation.routes
                        if not internal or route.slot.transport != "cli_subprocess"
                    }
                )
                return _response(
                    json_reply(
                        200,
                        {
                            "object": "list",
                            "data": [{"id": model, "object": "model", "owned_by": "skm"} for model in models],
                        },
                    )
                )
            try:
                body, raw = await _read(request)
                model = body.get("model")
                if not isinstance(model, str) or not model.strip():
                    raise ValueError("missing model")
                conversation = _conversation(request.headers, model)
                if "stream" in body and not isinstance(body["stream"], bool):
                    raise ValueError("invalid stream flag")
            except ClientDisconnect:
                return _response(error_reply(400, "request was disconnected"))
            except OverflowError:
                return _response(error_reply(413, "request exceeds the byte limit"))
            except (ValueError, RecursionError, TypeError):
                return _response(error_reply(400, "invalid inference request"))
            headers = dict(request.headers)
            work = Invocation(client, path, model, body, raw, headers, internal, conversation)
            try:
                key = (
                    None
                    if internal or work.stateful
                    else dedup_key(
                        client,
                        request.method,
                        request.url.path,
                        model,
                        body,
                        headers,
                    )
                )
            except (ValueError, RecursionError, UnicodeError):
                return _response(error_reply(400, "invalid inference request"))
            inflight = inflights.setdefault(generation.number, Inflight())
            # Active responses retain their own in-flight table.
            for number in tuple(inflights):
                if number < generation.number:
                    del inflights[number]
            return _InferenceResponse(state, generation, work, inflight, key, resources.pop_all())

    async def admin(request: Request) -> Response:
        with state.lease() as generation:
            auth = _auth(request.headers, generation, state, management=True)
            if isinstance(auth, int):
                return _auth_error(auth)
            match request.url.path:
                case "/admin/reload":
                    try:
                        number = await asyncio.to_thread(state.reload)
                    except SkmError:
                        return _response(error_reply(400, "router reload rejected the configuration"))
                    return _response(json_reply(200, {"status": "reloaded", "generation": number}))
                case "/admin/cooldowns":
                    return _response(json_reply(200, {"cooldowns": generation.scheduler.cooldowns()}))
                case _:
                    return _response(
                        json_reply(
                            200,
                            {
                                "status": "running",
                                "host": LOOPBACK,
                                "port": generation.port,
                                "generation": generation.number,
                                "slots": sorted({route.slot.slot_id for route in generation.routes}),
                            },
                        )
                    )

    routes = [
        Route(path, inference, methods=["GET"] if path.endswith("/models") else ["POST"])
        for canonical in _PATHS
        for path in (canonical, canonical.removeprefix("/v1"))
    ]
    routes.extend(
        (
            Route("/admin/status", admin, methods=["GET"]),
            Route("/admin/reload", admin, methods=["POST"]),
            Route("/admin/cooldowns", admin, methods=["GET"]),
        )
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        if on_start is not None:
            on_start()
        yield

    return Starlette(routes=routes, lifespan=lifespan)


def _serve(state: RouterState, listener: socket.socket, ready: Callable[[], None]) -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            create_router_app(state, on_start=ready),
            host=LOOPBACK,
            port=state.binding[1],
            access_log=False,
            proxy_headers=False,
            timeout_graceful_shutdown=5,
            log_level="warning",
        )
    )
    # Uvicorn replays a handled SIGTERM after shutdown. Return to bootstrap for owned cleanup.
    previous = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        server.run(sockets=[listener])
    finally:
        signal.signal(signal.SIGTERM, previous)
    if not server.started:
        raise OSError("router server startup failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    try:
        serve_router(args.config, args.port, _serve)
    except (OSError, ValueError, SkmError, LockTimeout):
        sys.stderr.write("router could not open its private state, configuration or loopback listener\n")
        return 1
    return 0


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        raise SystemExit(main())
