"""Starlette composition around the synchronous application bus."""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
from contextvars import copy_context
from functools import partial
from importlib import import_module
from importlib.resources import files
from socket import AF_INET, AF_INET6, create_server, socket
from time import monotonic
from types import FrameType
from typing import Any, cast, override

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route
from uvicorn import Config, Server

from skm.application_bus.client import EmbeddedClient, SkmClient
from skm.application_bus.middleware import is_waiting
from skm.application_bus.registry import BusRegistry, IdempotencyMode
from skm.bootstrap.composition import App
from skm.bootstrap.lifecycle import event_listener_for_api, parse_bind, upload_for_api
from skm.bootstrap.machine_access import MachineServerConfig, run_machine_operation
from skm.bootstrap.platform_module import MigrationRunner
from skm.bootstrap.services import build_service_runner
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.public import RbacAuthorizer
from skm.platform.config.bootstrap import WebAuthConfig
from skm.platform.config.keys import MISSING, Chain
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.generated.queries import Doctor, MigrationStatus
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import Redactor
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock

from . import openapi
from .auth import request_auth_basis, uvicorn_proxy_config, validate_web_auth_bind
from .errors import problem_response
from .etag import encode_etag, parse_if_match, parse_if_none_match
from .health import Health, read_schema_error, runner_schema_error
from .live import LIVE_BODY_POLICY, AttemptLive
from .middleware import BodyPolicy, HTTPBoundary
from .request_context import RequestContext, request_meta
from .routes import MODULE_IDS, discover_routes
from .routes.auth import build_auth_routes
from .routing import HostMetadataFactory, RouteTable, build_route_table
from .routing import Route as WireRoute
from .sse import EventWakeups, WorkspaceEvents
from .static import BrowserHistory, serve_static

__all__ = ["build_routes", "call_bus", "create_app", "serve_asgi"]


def _request_client(request: Request, host_metadata: HostMetadataFactory | None = None) -> SkmClient:
    core: App = request.app.state.core
    basis = request_auth_basis(request)
    client = core.client(actor=basis.actor, surface=Surface.API)
    if not isinstance(client, EmbeddedClient):
        raise TypeError("HTTP API requires an embedded control-plane client")
    return client.for_request(request_meta(request, host_metadata=host_metadata), auth_basis=basis)


async def call_bus(
    request: Request, dto: object, *, command: bool = False, host_metadata: HostMetadataFactory | None = None
) -> object:
    """The bus owns authz, forbidden idempotency, receipts and denied audit."""
    client = _request_client(request, host_metadata)
    run_bus = getattr(request.app.state, "run_bus", run_in_threadpool)
    if command:
        return await run_bus(client.dispatch, dto)
    return await run_bus(client.ask, dto)


async def _migrations(request: Request) -> JSONResponse:
    result = await call_bus(request, MigrationStatus())
    return JSONResponse(cast("Any", result).to_json())


async def _details(request: Request) -> JSONResponse:
    result = await call_bus(request, Doctor())
    return JSONResponse(cast("Any", result).to_json())


async def _http_error(request: Request, error: Exception) -> JSONResponse:
    status = cast("HTTPException", error).status_code
    code = ErrorCode.NOT_FOUND if status == 404 else ErrorCode.SCHEMA_INVALID
    response = problem_response(
        request, error_for(code, "Route not found" if status == 404 else "Method not allowed")
    )
    if status == 405:
        response.status_code = 405
        response.headers.update(cast("HTTPException", error).headers or {})
    return response


def _settings(app: App, health: Health, settings: Mapping[str, JsonValue] | None) -> dict[str, JsonValue]:
    """Effective instance and serving-host values, including the process snapshot."""
    if settings is not None:
        return dict(settings)
    if health.schema_error is not None or not health.database_ok:
        # Status-only mode must work before the configuration tables exist.
        values = {
            spec.key: cast("JsonValue", spec.default)
            for spec in app.settings.keys()  # noqa: SIM118 -- typed registry, not a mapping
            if spec.default is not MISSING
        }
        if app.config.process is not None:
            values.update(app.config.process.work)
            values.update(app.config.process.host)
        return values
    meta = RequestMeta("api-startup-config", Surface.API, None, SystemClock().now())
    with app.uow_factory(meta, readonly=True) as uow:
        store, scopes = uow.repo(ConfigStore), uow.repo(ScopeTree)
        work = app.config.effective(store, scopes, None)
        process = app.config.process
        target = None if process is None else process.host_target
        host = app.config.effective(store, scopes, target, Chain.HOST)
        return {
            spec.key: (host if spec.chain is Chain.HOST else work).get(spec.key)
            for spec in app.settings.keys()  # noqa: SIM118 -- typed registry, not a mapping
        }


@asynccontextmanager
async def _event_wakeups(
    listener: EventWakeups | None,
    events: WorkspaceEvents,
    live: AttemptLive | None = None,
) -> AsyncGenerator[None]:
    if listener is None:
        yield
        return
    loop = asyncio.get_running_loop()

    def wake(workspace: WorkspaceId) -> None:
        loop.call_soon_threadsafe(events.notify, workspace)

    def wake_access() -> None:
        loop.call_soon_threadsafe(events.notify_access_changed)
        if live is not None:
            loop.call_soon_threadsafe(live.notify_access_changed)

    set_access = getattr(listener, "set_access_change_callback", None)
    if callable(set_access):
        set_access(wake_access)
    listener.start(wake)
    try:
        yield
    finally:
        await run_in_threadpool(listener.stop)
        if callable(set_access):
            set_access(None)


async def _monitor_health(stopped: asyncio.Event, health: Health) -> None:
    while not stopped.is_set():
        try:
            await asyncio.wait_for(stopped.wait(), timeout=health.interval)
        except TimeoutError:
            await health.refresh()


def _bus_executor(api: Starlette, size: int) -> ThreadPoolExecutor:
    executor = ThreadPoolExecutor(max_workers=size)

    async def run_bus(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        call = partial(copy_context().run, fn, *args, **kwargs)
        return await asyncio.get_running_loop().run_in_executor(executor, call)

    api.state.run_bus = run_bus
    return executor


def _include_disabled_routes(table: RouteTable, disabled_routes: tuple[WireRoute, ...]) -> RouteTable:
    if not disabled_routes:
        return table
    declared = {(r.method, r.path): r for r in table.describe()}
    for route in disabled_routes:
        declared.setdefault((route.method, route.path), route)
    return RouteTable(declared.values())


def _openapi_endpoint(disabled_routes: tuple[WireRoute, ...]) -> Callable[[Request], Any]:
    if not disabled_routes:
        return openapi.endpoint
    document = json.loads(files("skm.entrypoints.api").joinpath("openapi.json").read_bytes())
    paths = cast("dict[str, dict[str, object]]", document["paths"])
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    for route in disabled_routes:
        path = route.path.removeprefix("/api/v1")
        if (item := paths.get(path)) is not None:
            item.pop(route.method.lower(), None)
            if methods.isdisjoint(item):
                del paths[path]
    body = json.dumps(document).encode()

    async def endpoint(_request: Request) -> Response:
        return Response(body, media_type="application/json")

    return endpoint


def _bind_table_routes(
    route_table: RouteTable | None,
    registry: BusRegistry | None,
    disabled_routes: tuple[WireRoute, ...],
    routes: Sequence[BaseRoute],
    body_policies: Sequence[BodyPolicy],
) -> tuple[Sequence[BaseRoute], Sequence[BodyPolicy]]:
    if route_table is None:
        return routes, body_policies
    if registry is None:
        raise ValueError("Route binding requires the BusRegistry")
    merged = _include_disabled_routes(route_table, disabled_routes)
    extra_policies = tuple(
        BodyPolicy(
            r.method,
            r.path,
            r.body_limit_key,
            "application/merge-patch+json"
            if r.body == "merge_patch"
            else "application/json"
            if r.body == "json"
            else None,
        )
        for r in merged.describe()
    )
    return (*routes, *build_routes(merged, registry)), (*body_policies, *extra_policies)


def _mount_operational(
    app: App,
    effective_web_auth: WebAuthConfig,
    events: WorkspaceEvents,
    live: AttemptLive,
    routes: Sequence[BaseRoute],
    body_policies: Sequence[BodyPolicy],
    declared_get_paths: set[str],
    rate_limit_clock: Callable[[], float] | None,
) -> tuple[list[BaseRoute], Sequence[BodyPolicy]]:
    def _notify_access_changed() -> None:
        events.notify_access_changed()
        live.notify_access_changed()

    auth_routes, auth_policies = build_auth_routes(
        app,
        effective_web_auth,
        rate_limit_clock=rate_limit_clock,
        on_access_change=_notify_access_changed,
    )
    mounted: list[BaseRoute] = []
    if "/health/details" not in declared_get_paths:
        mounted.append(Route("/health/details", _details, methods=["GET"]))
    mounted.extend(
        [
            *auth_routes,
            Route("/api/v1/events", events.endpoint, methods=["GET"]),
            Route(
                "/api/v1/projects/{project_id}/events/stream",
                events.project_endpoint,
                methods=["GET"],
            ),
            *live.routes(),
            *routes,
            Route("/", serve_static),
            Route("/assets/{path:path}", serve_static),
        ]
    )
    return mounted, (*body_policies, LIVE_BODY_POLICY, *auth_policies)


def _background_stop(
    request_stop: Callable[[], None], join_threads: Callable[[], None]
) -> Callable[[], asyncio.Task[None]]:
    join: asyncio.Task[None] | None = None

    def stop() -> asyncio.Task[None]:
        nonlocal join
        if join is None:
            request_stop()
            join = asyncio.create_task(asyncio.to_thread(join_threads))
        return join

    return stop


def create_app(  # noqa: PLR0913 -- explicit composition inputs; no implicit bus registry
    app: App,
    *,
    settings: Mapping[str, JsonValue] | None = None,
    routes: Sequence[BaseRoute] = (),
    body_policies: Sequence[BodyPolicy] = (),
    route_table: RouteTable | None = None,
    registry: BusRegistry | None = None,
    migration_runner: MigrationRunner | None = None,
    schema_check: Callable[[], ErrorCode | None] | None = None,
    redactor: Redactor | None = None,
    no_background: bool = False,
    event_listener: EventWakeups | None = None,
    web_auth: WebAuthConfig | None = None,
    rate_limit_clock: Callable[[], float] | None = None,
) -> Starlette:
    """Use a composed App; no environment reads, migration writes or implicit credentials."""
    effective_web_auth = web_auth if web_auth is not None else app.web_auth
    composed_registry = app.bus._registry  # pyright: ignore[reportPrivateUsage] -- composed module selection
    disabled_routes = discover_routes(composed_registry.disabled_modules())
    routes, body_policies = _bind_table_routes(route_table, registry, disabled_routes, routes, body_policies)
    check = schema_check or (
        (lambda: runner_schema_error(migration_runner))
        if migration_runner is not None
        else lambda: read_schema_error(app)
    )
    health = Health(check)
    health.background_enabled = not no_background
    values = _settings(app, health, settings)
    health.interval = float(cast("int", values.get("api.schema_check_interval_seconds", 30)))
    redactor = redactor or Redactor()
    events = WorkspaceEvents(app, values, RbacAuthorizer(getattr(app, "clock", None) or SystemClock()))
    live = (
        AttemptLive(app, values, events._counts, redactor)  # pyright: ignore[reportPrivateUsage] -- shared SSE quota
        if health.schema_error is None
        else None
    )

    @asynccontextmanager
    async def lifespan(_api: Starlette) -> AsyncGenerator[None]:
        stop_background = None
        if not no_background and health.schema_error is None and health.database_ok and app.services:
            runner = build_service_runner(
                app.services, config=values, clock=SystemClock(), log=get_logger("entrypoints.api")
            )
            await run_in_threadpool(runner.start)
            health.on_incompatible = runner.request_stop

            stop_background = _background_stop(
                runner.request_stop, lambda: runner.stop(timeout_seconds=_api.state.shutdown_remaining())
            )
            _api.state.stop_background = stop_background
        stopped = asyncio.Event()

        executor = _bus_executor(_api, cast("int", values.get("api.threadpool.size", 16)))
        watcher = asyncio.create_task(_monitor_health(stopped, health))
        try:
            async with _event_wakeups(event_listener if health.schema_error is None else None, events, live):
                yield
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            stopped.set()
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
            health.on_incompatible = None
            if stop_background is not None:
                await stop_background()

    declared_get_paths = (
        {r.path for r in routes if isinstance(r, Route) and r.methods and "GET" in r.methods}
        if health.schema_error is None
        else set[str]()
    )
    mounted: list[BaseRoute] = [
        Route("/health/live", health.live, methods=["GET"]),
        Route("/health/ready", health.ready, methods=["GET"]),
        Route("/api/v1/openapi.json", _openapi_endpoint(disabled_routes), methods=["GET"]),
    ]
    if "/api/v1/admin/migrations" not in declared_get_paths:
        mounted.append(Route("/api/v1/admin/migrations", _migrations, methods=["GET"]))
    if health.schema_error is None:
        assert live is not None  # noqa: S101 -- constructed above when schema is compatible
        op_routes, body_policies = _mount_operational(
            app,
            effective_web_auth,
            events,
            live,
            routes,
            body_policies,
            declared_get_paths,
            rate_limit_clock,
        )
        mounted.extend(op_routes)
    api = Starlette(
        routes=mounted,
        lifespan=lifespan,
        exception_handlers={HTTPException: _http_error},
        middleware=[
            Middleware(
                RequestContext,
                settings=values,
                redactor=redactor,
                instance_id=app.instance_id,
                receipt_window=(int(app.bus.idempotency_retention.total_seconds()), app.clock.now),
            ),
            Middleware(BrowserHistory),
            Middleware(
                HTTPBoundary,
                core=app,
                settings=values,
                health=health,
                policies=body_policies,
                web_auth=effective_web_auth,
            ),
        ],
    )
    api.state.run_bus = run_in_threadpool
    api.state.core, api.state.health = app, health
    api.state.web_auth = effective_web_auth
    api.state.shutdown_remaining = lambda: float(cast("int", values.get("api.shutdown.grace_seconds", 10)))
    if route_table is not None and health.schema_error is None:
        try:
            lp_mod = import_module("skm.entrypoints.api.long_poll")
        except ModuleNotFoundError:
            pass
        else:
            cast("Callable[[Starlette], None]", lp_mod.mount_worker)(api)
    return api


async def _disabled_route(request: Request, *, error: SkmError) -> JSONResponse:
    return problem_response(request, error)


def build_routes(table: RouteTable, registry: BusRegistry) -> tuple[BaseRoute, ...]:
    """Cross-check enabled declarations and bind disabled routes to their catalog error."""
    schemas = SchemaRegistry.load_default()
    routes: list[BaseRoute] = []
    for route in table.describe():
        try:
            if route.command is not None:
                spec = registry.command(route.command)
            else:
                spec = registry.query(cast("type[object]", route.query))
        except SkmError as error:
            if error.code is not ErrorCode.MODULE_DISABLED:
                raise
            endpoint = partial(_disabled_route, error=error.with_traceback(None))
        else:
            if (
                spec.internal
                or spec.name != route.bus_name
                or spec.result is not getattr(route, "bus_result_type", route.result_type)
                or getattr(spec, "idempotency", IdempotencyMode.FORBIDDEN) != route.idempotency
            ):
                raise ValueError(f"Route/bus metadata drift: {route.bus_name}")
            endpoint = _endpoint(route, schemas)
        routes.append(Route(route.path, endpoint, methods=[route.method], name=route.effective_operation_id))
    return tuple(routes)


def _request_version(request: Request, *, required: bool, create_only: bool) -> int | None:
    matches = request.headers.getlist("if-match")
    if len(matches) > 1:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Multiple If-Match headers")
    if create_only:
        if matches:
            raise error_for(ErrorCode.SCHEMA_INVALID, "If-Match conflicts with If-None-Match: *")
        return 0
    return parse_if_match(matches[0] if matches else None, required=required)


def _route_response(
    route: WireRoute, payload: dict[str, Any], status: int, headers: dict[str, str]
) -> Response:
    if route.path.endswith(".md"):
        headers["Content-Disposition"] = f'attachment; filename="{route.path.rsplit("/", 1)[-1]}"'
        return Response(payload["markdown"], status_code=status, headers=headers, media_type="text/markdown")
    project_response = getattr(route, "response_body", None)
    return JSONResponse(
        payload if project_response is None else project_response(payload),
        status_code=status,
        headers=headers,
    )


def _endpoint(route: WireRoute, schemas: SchemaRegistry) -> Callable[[Request], Any]:
    requires_if_match = route.requires_if_match(schemas)
    supports_create_only = route.if_match_to == "expected_row_version" and route.bus_name in {
        "settings.set_value",
        "settings.unset_value",
    }

    async def endpoint(request: Request) -> Response:
        body: Any = {}
        if route.body != "none":
            raw = await request.body()
            try:
                body = await request.json() if raw else {}
            except ValueError as exc:
                raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid JSON body") from exc
            if not isinstance(body, dict):
                raise error_for(ErrorCode.SCHEMA_INVALID, "Body must be an object")
        if_none_match = parse_if_none_match(request.headers.get("if-none-match"))
        create_only = supports_create_only and if_none_match == "*"
        version = (
            _request_version(request, required=requires_if_match, create_only=create_only)
            if route.if_match_to
            else None
        )
        dto = route.bind(
            cast("dict[str, Any]", body),
            request.path_params,
            request.query_params,
            actor=request.state.actor,
            schemas=schemas,
            version=version,
        )
        cursor: int | None = None
        try:
            if route.command is not None:
                result = await call_bus(request, dto, command=True, host_metadata=route.host_metadata)
            else:
                client = _request_client(request, route.host_metadata)
                run_bus = getattr(request.app.state, "run_bus", run_in_threadpool)
                result, meta = await run_bus(client.ask_with_meta, dto)
                cursor = meta.events_cursor
        except SkmError as error:
            if (
                create_only
                and error.code == ErrorCode.VERSION_CONFLICT
                and error.details.get("expected") == 0
            ):
                raise error_for(
                    ErrorCode.ALREADY_EXISTS, "Config entry already exists", details=error.details
                ) from error
            raise
        payload = cast("Any", result).to_json()
        outcome = payload.get("outcome")
        waiting = is_waiting(result) or (
            isinstance(outcome, dict) and cast("dict[str, Any]", outcome).get("kind") == "waiting"
        )
        headers: dict[str, str] = {}
        if not waiting and route.success_status == 201:
            if route.bus_name == "workspace.create_workspace":
                headers["Location"] = f"/api/v1/workspaces/{payload['workspace_id']}"
            elif route.bus_name == "workspace.create_project":
                headers["Location"] = f"/api/v1/projects/{payload['project_id']}"
            elif route.bus_name == "planning.publish_revision":
                plan_id = request.path_params["plan_id"]
                headers["Location"] = f"/api/v1/plans/{plan_id}/revisions/{payload['revision_id']}"
        if cursor is not None:
            headers["SKM-Events-Cursor"] = str(cursor)
        if route.etag_from and not waiting:
            tag = encode_etag(payload[route.etag_from])
            headers["ETag"] = tag
            if (
                route.method == "GET"
                and if_none_match is not None
                and (if_none_match == "*" or if_none_match.removeprefix("W/") == tag.removeprefix("W/"))
            ):
                return Response(status_code=304, headers=headers)
        return _route_response(route, payload, 200 if waiting else route.success_status, headers)

    return endpoint


class _GracefulServer(Server):
    """Share one deadline across the request drain and background shutdown."""

    def __init__(self, config: Config, api: Starlette, grace: int) -> None:
        super().__init__(config)
        self.api = api
        self.grace = grace
        self.deadline: float | None = None

    def remaining(self) -> float:
        return float(self.grace) if self.deadline is None else max(0.0, self.deadline - monotonic())

    @override
    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        # Uvicorn restores the original handlers. The CLI returns its own shutdown status.
        if self.deadline is None:
            self.deadline = monotonic() + self.grace
            with suppress(RuntimeError):
                loop = asyncio.get_running_loop()
                loop.call_soon(self.api.state.on_shutdown, self.deadline)
                loop.call_soon(getattr(self.api.state, "stop_background", lambda: None))
        self.should_exit = True

    @override
    async def shutdown(self, sockets: list[socket] | None = None) -> None:
        # Uvicorn pauses for 100 ms after closing its listeners.
        self.config.timeout_graceful_shutdown = cast("int", max(0.0, self.remaining() - 0.1))
        await super().shutdown(sockets)


def serve_asgi(
    core: App | MachineServerConfig,
    bind: str | None = None,
    *,
    no_background: bool = False,
    redactor: Redactor | None = None,
    on_shutdown: Callable[[float], None] = lambda _deadline: None,
) -> None:
    """Run the selected HTTP surface in the calling thread."""
    if isinstance(core, MachineServerConfig):
        from .machine import create_machine_api, serve_machine_api

        api = create_machine_api(
            core.authority,
            default_profile=core.profile,
            run_operation=run_machine_operation,
            redactor=redactor,
        )
        serve_machine_api(api, core.socket)
        return
    if bind is None:
        raise ValueError("Project API bind address is required")
    from .blobs import mount_blobs

    validate_web_auth_bind(bind, core.web_auth)
    host, port = parse_bind(bind)
    registry = core.bus._registry  # pyright: ignore[reportPrivateUsage] -- bind the composed bus registration
    values = _settings(core, Health(lambda: read_schema_error(core)), None)
    values["api.bind"] = bind
    modules = set(MODULE_IDS) - registry.disabled_modules()
    api = create_app(
        core,
        route_table=build_route_table(modules),
        registry=registry,
        settings=values,
        no_background=no_background,
        redactor=redactor,
        event_listener=event_listener_for_api(core),
    )
    if "artifacts" in modules and api.state.health.schema_error is None:
        mount_blobs(api, upload_for_api(core))
    grace = cast("int", values["api.shutdown.grace_seconds"])
    proxy_headers, forwarded_allow_ips = uvicorn_proxy_config(core.web_auth, values)
    config = Config(
        api,
        host=host,
        port=port,
        workers=1,
        lifespan="on",
        proxy_headers=proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
        access_log=False,
    )
    server = _GracefulServer(config, api, grace)
    api.state.on_shutdown = on_shutdown
    api.state.shutdown_remaining = server.remaining
    # Reserve the listener before startup, so a busy port leaves no background services running.
    try:
        listener = create_server((host, port), family=AF_INET6 if ":" in host else AF_INET)
    except OSError:
        raise error_for(ErrorCode.BACKEND_UNAVAILABLE, "Could not bind the HTTP listener") from None
    with listener:
        try:
            server.run(sockets=[listener])
        except SystemExit:
            raise error_for(ErrorCode.BACKEND_UNAVAILABLE, "HTTP server startup failed") from None
    if not server.started or getattr(server.lifespan, "shutdown_failed", False):
        raise error_for(ErrorCode.BACKEND_UNAVAILABLE, "HTTP server lifecycle failed")
