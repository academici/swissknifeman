"""Select and execute one validated inference stream or response."""

from __future__ import annotations

import asyncio
import json
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, cast
from uuid import uuid4

from skm.bootstrap.router import (
    COUNT,
    CliRequest,
    CliUnavailable,
    ConversationBusy,
    Route,
    RouterGeneration,
    UpstreamError,
    UpstreamResponse,
    cli_prompt,
    cli_result,
    json_schema,
    translate_request,
    translate_response,
    valid_success,
)
from skm.kernel.errors import SkmError

from .exchange import Exchange, Reply, max_response_bytes, max_sse_event_bytes
from .sse import StreamTranslation, cli_frames, events, meaningful, parse_event, terminal

__all__ = ["CONVERSATION_MODEL_PREFIX", "Invocation", "dispatch", "error_reply", "json_reply"]

CONVERSATION_MODEL_PREFIX = "claude-code:"
_RETRY_STATUSES = frozenset({401, 403, 408, 429})


def json_reply(status: int, value: dict[str, Any]) -> Reply:
    return Reply(status, {"content-type": "application/json"}, json.dumps(value, allow_nan=False).encode())


def error_reply(status: int, message: str) -> Reply:
    return json_reply(status, {"error": {"type": "router_error", "message": message}})


@dataclass(frozen=True, slots=True)
class Invocation:
    client: str
    path: str
    model: str
    body: dict[str, Any]
    raw: bytes
    headers: dict[str, str]
    internal: bool
    conversation: str | None

    @property
    def stream(self) -> bool:
        return self.path != COUNT and self.body.get("stream") is True

    @property
    def stateful(self) -> bool:
        return (
            self.conversation is not None
            or "x-skm-cwd" in self.headers
            or bool(self.body.get("previous_response_id") or self.body.get("conversation"))
        )

    @property
    def sticky(self) -> tuple[str, str] | None:
        return (
            (self.client, self.conversation) if self.conversation is not None and not self.internal else None
        )


@dataclass(slots=True)
class _Attempt:
    status: int = 502
    headers: dict[str, str] | None = None
    body: bytes = b""
    committed: bool = False
    success: bool = False


def _routes(generation: RouterGeneration, request: Invocation) -> tuple[Route, ...]:
    conversation_model = request.model.startswith(CONVERSATION_MODEL_PREFIX)
    routes = tuple(
        route
        for route in generation.routes
        if (route.hot_pool if conversation_model else route.model.name == request.model)
        and (not route.hot_pool or request.conversation is not None)
        and generation.path_for(route, request.path) is not None
    )
    return generation.scheduler.candidates(routes, request.sticky, internal=request.internal)


def _floor(generation: RouterGeneration, request: Invocation) -> tuple[Route, ...]:
    if (
        request.internal
        or request.stateful
        or not generation.floor_model
        or generation.floor_model == request.model
    ):
        return ()
    routes = tuple(
        route
        for route in generation.routes
        if route.model.name == generation.floor_model
        and generation.path_for(route, request.path) is not None
        and generation.permits_floor(route, len(request.raw), request.body)
    )
    return generation.scheduler.candidates(routes, None, internal=False)


async def dispatch(generation: RouterGeneration, request: Invocation, output: Exchange) -> None:
    routes = _routes(generation, request)
    fallback: Reply | None = None
    waited = 0.0
    for route in (*routes, *_floor(generation, request)):
        claim = object()
        try:
            for attempt in range(1, 4):
                if not generation.scheduler.eligible(route, claim):
                    break
                result = await _attempt(generation, route, request, output)
                if result.success:
                    generation.scheduler.pin(request.sticky, route)
                if result.committed:
                    return
                if result.status == 400 and result.body and fallback is None:
                    fallback = Reply(400, result.headers or {}, result.body)
                if result.status != 429:
                    break
                if result.body:
                    fallback = Reply(429, result.headers or {}, result.body)
                delay = generation.scheduler.retry_delay(
                    route,
                    result.headers or {},
                    result.body.decode("utf-8", "replace"),
                    attempt,
                    waited,
                    claim,
                )
                if delay is None:
                    break
                waited += delay
                await asyncio.sleep(delay)
        finally:
            generation.scheduler.release_hold(route, claim)
    output.reply(fallback or error_reply(502, "no upstream completed the request"))


async def _attempt(
    generation: RouterGeneration, route: Route, request: Invocation, output: Exchange
) -> _Attempt:
    result = _Attempt()
    try:
        if route.slot.transport == "cli_subprocess":
            await _cli(generation, route, request, output, result)
        else:
            await _remote(generation, route, request, output, result)
    except ConversationBusy:
        output.reply(error_reply(409, "conversation already has a turn or incompatible worker settings"))
        result.committed = True
    except (UpstreamError, CliUnavailable, OSError, SkmError):
        pass
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        # Untrusted upstream JSON may violate either wire protocol.
        if route.slot.transport == "cli_subprocess" and not result.committed:
            output.reply(error_reply(400, "invalid CLI inference request"))
            result.committed = True
    return result


async def _read(response: UpstreamResponse) -> bytes:
    body = bytearray()
    async for chunk in response.chunks():
        if len(body) + len(chunk) > max_response_bytes:
            raise UpstreamError("upstream response exceeds its limit")
        body.extend(chunk)
    return bytes(body)


async def _remote(
    generation: RouterGeneration,
    route: Route,
    request: Invocation,
    output: Exchange,
    result: _Attempt,
) -> None:
    target = generation.path_for(route, request.path)
    if target is None:
        return
    try:
        body = translate_request(
            request.path, target, request.body, route.model.name, is_compat=route.model.is_compat
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        # Another slot may support the caller's protocol natively.
        out = error_reply(400, "request cannot be translated to the upstream protocol")
        result.status, result.body, result.headers = out.status, out.body or b"", out.headers
        return
    raw = (
        request.raw
        if body == request.body and target == request.path
        else json.dumps(body, allow_nan=False).encode()
    )
    upstream = await asyncio.to_thread(generation.upstream, route)
    async with upstream.request(target, request.headers, raw, body) as response:
        result.status, result.headers = response.status, response.headers
        if 200 <= response.status < 300 and request.stream:
            if (
                response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "text/event-stream"
            ):
                return
            await _remote_stream(request.path, target, response, output, result)
            return
        result.body = await _read(response)
    if 200 <= result.status < 300:
        payload: object = json.loads(result.body.decode("utf-8"))
        if not valid_success(target, payload):
            return
        if request.path != target:
            value = translate_response(
                target, request.path, cast("dict[str, Any]", payload), is_compat=route.model.is_compat
            )
            if not valid_success(request.path, value) and not _refusal(value):
                return
            reply = json_reply(result.status, value)
            if len(reply.body or b"") > max_response_bytes:
                raise UpstreamError("translated response exceeds its limit")
            output.reply(reply)
        else:
            output.reply(Reply(result.status, result.headers or {}, result.body))
        result.committed = result.success = True
    elif 400 <= result.status < 500 and result.status not in _RETRY_STATUSES:
        output.reply(Reply(result.status, result.headers or {}, result.body))
        result.committed = True


def _refusal(body: dict[str, Any]) -> bool:
    choices: object = body.get("choices")
    if not isinstance(choices, list):
        return False
    for choice in cast("list[object]", choices):
        if isinstance(choice, dict):
            message = cast("dict[str, object]", choice).get("message")
            if isinstance(message, dict) and cast("dict[str, object]", message).get("refusal"):
                return True
    return False


async def _remote_stream(
    path: str,
    target: str,
    response: UpstreamResponse,
    output: Exchange,
    result: _Attempt,
) -> None:
    translation = StreamTranslation(path) if path != target else None
    preface: list[bytes] = []
    buffered = observed = 0
    async with aclosing(events(response.chunks())) as stream:
        async for event in stream:
            if not result.committed:
                observed += len(event.wire)
                if observed > max_sse_event_bytes:
                    raise UpstreamError("upstream SSE preface exceeds its limit")
            # Upstream error frames must abort the attempt even when translated.
            native_content = meaningful(target, event)
            valid = translation is None and native_content
            frames = (event.wire,) if translation is None else tuple(translation.convert(event))
            for wire in frames:
                if len(wire) > max_sse_event_bytes:
                    raise UpstreamError("translated SSE event exceeds its limit")
                if result.committed:
                    await output.push(wire)
                else:
                    buffered += len(wire)
                    if buffered > max_sse_event_bytes:
                        raise UpstreamError("upstream SSE preface exceeds its limit")
                    preface.append(wire)
                    if translation is not None and not valid:
                        valid = meaningful(path, parse_event(wire))
            if not result.committed and valid:
                output.reply(Reply(response.status, response.headers))
                result.committed = result.success = True
                for wire in preface:
                    await output.push(wire)
                preface.clear()
            if terminal(target, event):
                break


async def _cli(
    generation: RouterGeneration,
    route: Route,
    request: Invocation,
    output: Exchange,
    result: _Attempt,
) -> None:
    bridge = generation.cli
    if bridge is None:
        return
    system, prompt = cli_prompt(request.path, request.body, latest_only=route.hot_pool)
    initial = cli_prompt(request.path, request.body, latest_only=False)[1] if route.hot_pool else None
    raw_cwd = request.headers.get("x-skm-cwd")
    work = CliRequest(
        request.client,
        request.conversation,
        route.slot.slot_id,
        route.model.name,
        system,
        prompt,
        cwd=Path(raw_cwd) if raw_cwd is not None else None,
        schema=json_schema(request.path, request.body),
        hot=route.hot_pool,
        initial_prompt=initial,
    )
    cancellation = Event()
    task = asyncio.create_task(asyncio.to_thread(bridge.run, work, cancellation))
    try:
        while request.stream:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=15)
            except TimeoutError:
                if not result.committed:
                    output.reply(Reply(200, {"content-type": "text/event-stream"}))
                    result.committed = True
                await output.push(b": ping\n\n")
            else:
                break
        answer = await asyncio.shield(task)
    except asyncio.CancelledError:
        cancellation.set()
        await asyncio.gather(task, return_exceptions=True)
        raise
    data = cli_result(
        request.path,
        route.model.name,
        f"skm_{uuid4().hex}",
        answer.text,
        answer.refusal,
        answer.input_tokens,
        answer.output_tokens,
    )
    if request.stream:
        if not result.committed:
            output.reply(Reply(200, {"content-type": "text/event-stream"}))
            result.committed = True
        for wire in cli_frames(request.path, data):
            await output.push(wire)
    else:
        reply = json_reply(200, data)
        if len(reply.body or b"") > max_response_bytes:
            raise CliUnavailable("worker response exceeds the limit")
        output.reply(reply)
    result.committed = result.success = True
