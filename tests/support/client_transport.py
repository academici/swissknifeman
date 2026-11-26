"""Loopback HTTP wiring for the client contract suite."""

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from ssl import SSLContext
from typing import Any, cast
from uuid import uuid4

import httpx
import psycopg
from starlette.applications import Starlette

from fakes.clock import FrozenClock
from skm.adapters.http_client.client import HttpSkmClient
from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import App
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.blobs import mount_blobs
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.artifacts.application.upload import bind_embedded_upload
from skm.platform.config.bootstrap import BootstrapConfig, load_bootstrap
from skm.platform.config.keys import MISSING
from skm.platform.config.secrets import SecretRef, SecretValue
from support.seed import SEED

__all__ = ["api_bootstrap", "bearer_embedded_client", "client_api", "http_client"]


class _BearerEmbeddedClient:
    def __init__(self, resolve: Callable[[], SkmClient]) -> None:
        self._resolve = resolve

    def new_idempotency_key(self) -> str:
        return f"idem_{uuid4().hex}"

    def __getattr__(self, name: str) -> Callable[..., Any]:
        # Authenticate on invocation, even if a caller holds a bound method across revocation.
        def invoke(*args: Any, **kwargs: Any) -> Any:
            return getattr(self._resolve(), name)(*args, **kwargs)

        return invoke


def bearer_embedded_client(app: App, secret: str) -> SkmClient:
    return cast(
        "SkmClient",
        _BearerEmbeddedClient(lambda: app.client(actor=app.authenticate(secret), surface=Surface.API)),
    )


class _FrozenMonotonic:
    def __init__(self, clock: FrozenClock) -> None:
        self.clock = clock
        self.origin = clock.now()
        self.elapsed = 0.0

    def monotonic(self) -> float:
        self.elapsed = max(self.elapsed, (self.clock.now() - self.origin).total_seconds())
        return self.elapsed


def http_client(
    stack: ExitStack,
    endpoint: str,
    root: Path,
    secret: str,
    clock: FrozenClock,
    on_response: Callable[[httpx.Response], None] | None = None,
    *,
    verify: SSLContext | bool = True,
) -> SkmClient:
    hooks = {"response": [on_response]} if on_response is not None else None
    http = stack.enter_context(httpx.Client(trust_env=False, event_hooks=hooks, verify=verify))
    return HttpSkmClient(
        endpoint,
        SecretValue(SecretRef.parse("secret://env/SKM_API_TOKEN"), secret),
        build_route_table(MODULE_IDS),
        spool_root=root / "spool",
        storage_budget=build_host_storage(root),
        min_free_bytes=0,
        http=http,
        clock=_FrozenMonotonic(clock),
        sleeper=lambda seconds: clock.advance(timedelta(seconds=seconds)),
    )


def client_api(app: App, authority: str) -> Starlette:
    bus = app.bus
    settings = {
        spec.key: cast("JsonValue", spec.default)
        for spec in app.settings.keys()  # noqa: SIM118 -- typed registry
        if spec.default is not MISSING
    }
    settings["api.allowed_hosts"] = [authority]
    api = create_app(
        app,
        settings=settings,
        route_table=build_route_table(MODULE_IDS),
        registry=bus._registry,
        no_background=True,
    )
    upload, _ = bind_embedded_upload(
        app.uow_factory,
        bus._authorizer,
        bus._scopes,
        app.config,
        app.gateways,
        bus._clock,
        bus._ids,
        bus.dispatch,
        bus.ask,
    )
    mount_blobs(api, upload)
    return api


def api_bootstrap(root: Path, dsn: str | None) -> BootstrapConfig:
    host = None
    if dsn is not None:
        # The API snapshots its host chain to size the database pool at startup.
        host = HostId(uuid4())
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            connection.execute(
                "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) "
                "VALUES (%s, 'host', %s, NULL)",
                (host, SEED.instance_id),
            )
    return replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}, root),
        instance_id=SEED.instance_id,
        host_id=host,
        database_pool_min_size=0,
    )
