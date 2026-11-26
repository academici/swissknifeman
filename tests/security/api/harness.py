"""A real memory composition, access authentication and bus behind the ASGI boundary."""

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# Starlette 0.52 uses this alias in an import-time type annotation (AnyIO 4.15).
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message="The anyio.abc.BlockingPortal alias is deprecated", category=DeprecationWarning
    )
    from starlette.testclient import TestClient

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from skm.application_bus.platform.migrations import AppliedMigration, PackagedMigration, SchemaVersionReader
from skm.bootstrap.composition import App, CompositionOverrides, build_app
from skm.entrypoints.api.app import call_bus, create_app
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.access.public import (
    SYSTEM_ACTOR,
    CreateToken,
    RbacAuthorizer,
    TokenPepperSource,
    WhoAmI,
    authenticate_token,
)
from skm.platform.config.bootstrap import load_bootstrap
from support.seed import SEED, seed_backend

NOW = datetime(2026, 11, 18, tzinfo=UTC)
PEPPER = b"api-boundary-test-pepper-32-bytes!"
BASE = "http://127.0.0.1:8765"


class Pepper:
    def pepper(self) -> bytes:
        return PEPPER


class History:
    def packaged(self):
        return (PackagedMigration(1, "core", "sha256:a"),)

    def applied(self):
        return (AppliedMigration(1, "core", "sha256:a", NOW),)

    def check_baseline(self) -> None:
        pass


async def me(request: Request) -> JSONResponse:
    result = await call_bus(request, WhoAmI())
    return JSONResponse(result.to_json())  # type: ignore[attr-defined]


async def token(request: Request) -> JSONResponse:
    dto = CreateToken.from_json(await request.json())
    result = await call_bus(request, dto, command=True)
    return JSONResponse(result.to_json())  # type: ignore[attr-defined]


@dataclass
class World:
    core: App
    secret: str
    owner: Any
    backend: Any

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}

    def client(self, **kwargs: Any) -> TestClient:
        routes = [Route("/api/v1/me", me), Route("/api/v1/tokens", token, methods=["POST"])]
        routes.extend(kwargs.pop("routes", []))
        return TestClient(create_app(self.core, routes=routes, **kwargs), base_url=BASE)

    def meta(self) -> RequestMeta:
        return RequestMeta("fixture", Surface.TEST, None, NOW)

    def restart(self, tmp_path: Path, database: str) -> None:
        """Recompose after a schema change; the new process cannot reuse the old config snapshot."""
        self.core.close()
        clock = FrozenClock(NOW)
        bs = load_bootstrap(None, home=tmp_path, environ={"SKM_DATABASE_URL": database})
        app = build_app(
            bs,
            surface=Surface.API,
            environ={},
            invocation={},
            backend="postgres",
            overrides=CompositionOverrides(
                authorizer=RbacAuthorizer(clock),
                scopes=FakeScopeChain(),
                clock=clock,
                gateways=GatewayTable({TokenPepperSource: Pepper()}, "control_plane_gateway"),
            ),
        )

        def auth(secret: str):
            with app.uow_factory(self.meta(), readonly=True) as uow:
                return authenticate_token(uow, secret, pepper=PEPPER, now=clock.now())

        self.core = replace(app, authenticator=auth)

    @property
    def audits(self):
        return self.backend.committed.core.audit


def make_world(
    tmp_path: Path, *, database: str | None = None, gateways: Mapping[type[object], object] | None = None
) -> World:
    clock = FrozenClock(NOW)
    bs = load_bootstrap(None, home=tmp_path, environ={"SKM_DATABASE_URL": database or "postgresql://unused"})
    if database:
        import psycopg

        host_id = uuid4()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) "
                "VALUES (%s, 'host', %s, NULL)",
                (host_id, SEED.instance_id),
            )
        bs = replace(bs, host_id=host_id)
    app = build_app(
        bs,
        surface=Surface.API,
        environ={},
        invocation={},
        backend="postgres" if database else "memory",
        overrides=CompositionOverrides(
            authorizer=RbacAuthorizer(clock),
            scopes=FakeScopeChain(),
            clock=clock,
            instance_id=SEED.instance_id,
            repositories={} if database else {SchemaVersionReader: lambda _state: History()},
            gateways=GatewayTable({TokenPepperSource: Pepper(), **(gateways or {})}, "control_plane_gateway"),
        ),
    )
    if database is None:
        seed_backend(app.uow_factory)
    meta = RequestMeta("bootstrap", Surface.TEST, None, NOW)
    owner = cast(
        "Any", app.bus.dispatch(BootstrapLocalOwner(display_name="API owner"), actor=SYSTEM_ACTOR, meta=meta)
    )

    def auth(secret: str):
        with app.uow_factory(meta, readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=clock.now())

    app = replace(app, authenticator=auth)
    backend = None if database else app.uow_factory._backend  # type: ignore[attr-defined]
    return World(app, owner.token_secret, owner, backend)
