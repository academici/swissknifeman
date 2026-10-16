"""The Starlette application of the backend: routes behind :class:`~gui.http.security.SecurityMiddleware`."""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

from . import routes_core, routes_queries, static
from .security import SecurityMiddleware


def routes() -> list:
    """Every route; the frontend catch-all comes last and answers unknown ``/v1`` paths with ``NOT_FOUND``."""
    return [*routes_core.ROUTES, *routes_queries.ROUTES,
            Route("/{path:path}", static.frontend, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])]


def create_app(state) -> Starlette:
    app = Starlette(routes=routes(), middleware=[Middleware(SecurityMiddleware, state=state)])
    app.state.backend = state
    return app
