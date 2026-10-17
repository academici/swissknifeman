"""The Starlette application of the backend: routes behind :class:`~gui.http.security.SecurityMiddleware`.

The lifespan starts the backend state before the first request (runs of an earlier backend become ``lost``,
heartbeats and project journals start) and on shutdown cancels the active runs.
"""
from __future__ import annotations

import contextlib

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

from . import routes_config, routes_core, routes_events, routes_plugins, routes_queries, routes_runs, static
from .security import SecurityMiddleware


def routes() -> list:
    """Every route; the frontend catch-all comes last and answers unknown ``/v1`` paths with ``NOT_FOUND``."""
    return [*routes_core.ROUTES, *routes_queries.ROUTES, *routes_runs.ROUTES, *routes_config.ROUTES,
            *routes_plugins.ROUTES, *routes_events.ROUTES,
            Route("/{path:path}", static.frontend, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])]


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    state = app.state.backend
    await state.start()
    try:
        yield
    finally:
        await state.stop()


def create_app(state) -> Starlette:
    app = Starlette(routes=routes(), middleware=[Middleware(SecurityMiddleware, state=state)], lifespan=lifespan)
    app.state.backend = state
    return app
