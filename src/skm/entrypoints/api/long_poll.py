"""ASGI claim waiting between short, independent bus dispatches."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated, error_for
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta
from skm.modules.execution.public import ClaimAssignment, ClaimAssignmentResult, RecordStepNote
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock

from .auth import request_auth_basis
from .etag import parse_if_none_match
from .middleware import HTTPBoundary
from .request_context import request_meta
from .routes.worker import ROUTES as WORKER_ROUTES
from .routing import Route as WireRoute

__all__ = ["ClaimLongPoll", "mount_worker"]

_CLOCK = SystemClock()


async def _disconnected(request: Request) -> None:
    # The endpoint has already read the complete request body.
    while (await request.receive())["type"] != "http.disconnect":
        pass


class ClaimLongPoll:
    """Share one waiter limit and an optional assignment notification source across requests."""

    def __init__(
        self,
        settings: Mapping[str, JsonValue],
        wake_up: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._limit = cast("int", settings.get("api.worker.max_long_polls", 256))
        self._interval = cast("int", settings.get("api.sse.poll_ms", 2000)) / 1000
        self.wake_up = wake_up
        self._active = 0

    async def dispatch(self, request: Request, dto: ClaimAssignment) -> ClaimAssignmentResult:
        meta = request_meta(request)
        basis = request_auth_basis(request)
        actor = basis.actor
        bus = request.app.state.core.bus

        async def attempt(attempt_meta: RequestMeta) -> ClaimAssignmentResult:
            try:
                return await run_in_threadpool(
                    bus.dispatch, dto, actor=actor, meta=attempt_meta, auth_basis=basis
                )
            except SkmError as error:
                if error.code == ErrorCode.FORBIDDEN and error.details.get("reason_code") == "NO_MEMBERSHIP":
                    # Keep the bus denial audit while hiding workspaces the worker cannot see.
                    raise error_for(ErrorCode.NOT_FOUND, "Workspace not found") from error
                raise

        result = await attempt(meta)
        seconds = dto.get("max_wait_seconds", 0)
        if result.get("outcome") != "nothing_to_claim" or not seconds or self._active >= self._limit:
            return result

        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds

        async def retry() -> ClaimAssignmentResult:
            current = result
            while (remaining := deadline - loop.time()) > 0:
                await self._wait(min(self._interval, remaining))
                if loop.time() >= deadline:
                    break
                retry_meta = replace(
                    meta,
                    request_id=f"req-{uuid4()}",
                    received_at=_CLOCK.now(),
                    correlation_id=meta.request_id,
                )
                current = await attempt(retry_meta)
                if current.get("outcome") != "nothing_to_claim":
                    break
            return current

        self._active += 1
        polling = asyncio.create_task(retry())
        disconnected = asyncio.create_task(_disconnected(request))
        try:
            done, _ = await asyncio.wait((polling, disconnected), return_when=asyncio.FIRST_COMPLETED)
            if disconnected in done:
                disconnected.result()
                return result
            return polling.result()
        finally:
            self._active -= 1
            for task in (polling, disconnected):
                task.cancel()
            await asyncio.gather(polling, disconnected, return_exceptions=True)

    async def _wait(self, interval: float) -> None:
        if self.wake_up is None:
            await asyncio.sleep(interval)
            return
        try:
            async with asyncio.timeout(interval):
                await self.wake_up()
        except TimeoutError:
            pass


def _endpoint(
    route: WireRoute, poll: ClaimLongPoll, schemas: SchemaRegistry
) -> Callable[[Request], Awaitable[JSONResponse]]:
    async def endpoint(request: Request) -> JSONResponse:
        body: Any = {}
        try:
            if await request.body():
                body = await request.json()
        except ValueError as exc:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid JSON body") from exc
        if not isinstance(body, dict):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Body must be an object")
        parse_if_none_match(request.headers.get("if-none-match"))
        dto = route.bind(
            cast("dict[str, Any]", body),
            request.path_params,
            request.query_params,
            actor=request.state.actor,
            schemas=schemas,
        )
        result = await poll.dispatch(request, dto)
        return JSONResponse(result.to_json(), status_code=route.success_status)

    return endpoint


def _note_endpoint(
    endpoint: Callable[[Request], Awaitable[Response]],
) -> Callable[[Request], Awaitable[Response]]:
    async def note(request: Request) -> Response:
        try:
            return await endpoint(request)
        except Unauthenticated as error:
            # A lost fence triggers a receipt lookup. Revocation can win that second
            # admission after the note handler has already rejected the write.
            conflict = error.__context__
            if isinstance(conflict, SkmError) and conflict.code == ErrorCode.LEASE_LOST:
                raise error_for(ErrorCode.LEASE_LOST, "Assignment lease lost") from error
            raise

    return note


def mount_worker(api: Starlette, *, wake_up: Callable[[], Awaitable[None]] | None = None) -> None:
    """Install worker-specific dispatch on the validated routes of a composed API."""
    if api.middleware_stack is not None:
        raise RuntimeError("Mount worker endpoints before ASGI startup")
    if api.state.health.schema_error is not None:
        return
    existing: ClaimLongPoll | None = getattr(api.state, "claim_long_poll", None)
    if existing is not None:
        existing.wake_up = wake_up
        return
    declarations = {
        route.effective_operation_id: route
        for route in WORKER_ROUTES
        if route.command in (ClaimAssignment, RecordStepNote)
    }
    mounted_routes = [
        (i, route)
        for i, route in enumerate(api.routes)
        if isinstance(route, Route) and route.name in declarations
    ]
    if not mounted_routes:
        return
    settings = next(
        (
            entry.kwargs["settings"]
            for entry in api.user_middleware
            if isinstance(entry.cls, type) and issubclass(entry.cls, HTTPBoundary)
        ),
        None,
    )
    if settings is None:
        raise ValueError("Worker endpoints require the shared HTTP admission boundary")
    poll = ClaimLongPoll(cast("Mapping[str, JsonValue]", settings), wake_up)
    schemas = SchemaRegistry.load_default()
    for index, mounted in mounted_routes:
        declaration = declarations[mounted.name]
        endpoint = (
            _endpoint(declaration, poll, schemas)
            if declaration.command is ClaimAssignment
            else _note_endpoint(mounted.endpoint)
        )
        api.routes[index] = Route(mounted.path, endpoint, methods=mounted.methods, name=mounted.name)
    api.state.claim_long_poll = poll
