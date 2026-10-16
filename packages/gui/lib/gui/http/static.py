"""The built frontend (``frontend/dist``), served only after authentication.

A path that names a file inside ``dist`` (after ``realpath``) is that file; any other ``GET`` outside ``/v1`` is
``index.html`` (the single-page app routes itself). Without a build the answer is ``503 FRONTEND_NOT_BUILT``.
"""
from __future__ import annotations

import os

from aicore.util.paths import is_within
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from ..errors import GuiError, http_status
from .errors import error_response
from .routes_core import exchange

HINT = "npm --prefix packages/gui/frontend ci && npm --prefix packages/gui/frontend run build"
NOT_BUILT_PAGE = ("<!doctype html><meta charset=\"utf-8\"><title>SKM GUI</title>"
                  f"<p>The frontend is not built. Run <code>{HINT}</code> and reload.</p>")


async def frontend(request: Request) -> Response:
    if request.scope["state"].get("auth") == "exchange":
        return await exchange(request)
    state = request.app.state.backend
    if request.url.path == "/v1" or request.url.path.startswith("/v1/") or request.method not in ("GET", "HEAD"):
        return error_response(GuiError("NOT_FOUND", f"no endpoint {request.method} {request.url.path}"))
    root = os.path.realpath(state.frontend_dir)
    index = os.path.join(root, "index.html")
    if not os.path.isfile(index):
        error = GuiError("FRONTEND_NOT_BUILT", f"the frontend is not built; run `{HINT}`")
        if "text/html" in request.headers.get("accept", ""):
            return Response(NOT_BUILT_PAGE, status_code=http_status(error.code), media_type="text/html")
        return error_response(error)
    relative = request.url.path.lstrip("/")
    if relative and "\x00" not in relative:
        candidate = os.path.realpath(os.path.join(root, relative))
        if is_within(candidate, root) and os.path.isfile(candidate):
            return FileResponse(candidate)
    return FileResponse(index, headers={"cache-control": "no-cache"})
