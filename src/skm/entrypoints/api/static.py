"""Serve the packaged Vite build and resolve browser history URLs to its entry point."""

import mimetypes
import os
import stat
from importlib.resources import files
from pathlib import Path
from typing import cast

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["BrowserHistory", "serve_static"]


class BrowserHistory:
    """Route an unclaimed browser URL through the ordinary admission rules for GET /."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in {"GET", "HEAD"}:
            path: str = scope["path"]
            parts = path.split("/")
            if (
                path.startswith("/")
                and path != "/"
                and parts[1] not in {"", "api", "health", "assets"}
                and ".." not in parts
                and "\x00" not in path
                and all(route.matches(scope)[0] == Match.NONE for route in scope["app"].routes)
            ):
                scope = {**scope, "path": "/", "raw_path": b"/", "skm.spa_path": path}
        await self.app(scope, receive, send)


def _bundle() -> tuple[Path, tuple[str, ...]]:
    package = files("skm")
    if not isinstance(package, Path):
        raise HTTPException(404)
    if package.parent.name == "src" and not (package / "_web").exists():
        return package.parent.parent, ("web", "dist")
    return package, ("_web",)


def _file_response(parts: tuple[str, ...], *, head: bool) -> Response:
    root, directories = _bundle()
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(root, directory_flags)
    try:
        for name in (*directories, *parts[:-1]):
            child = os.open(name, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise HTTPException(404)
        media_type = mimetypes.guess_type(parts[-1])[0] or "application/octet-stream"
        if head:
            return Response(media_type=media_type, headers={"Content-Length": str(info.st_size)})
        with open(fd, "rb", closefd=False) as stream:
            return Response(stream.read(), media_type=media_type)
    finally:
        os.close(fd)


def serve_static(request: Request) -> Response:
    """Read only regular files through anchored descriptors. Missing browser routes use index.html."""
    browser_path = cast("str | None", request.scope.get("skm.spa_path"))
    path = browser_path.rstrip("/") if browser_path else request.scope["path"]
    parts = ("index.html",) if path == "/" else tuple(path.removeprefix("/").split("/"))
    if any(not part or part.startswith(".") or "\x00" in part for part in parts):
        raise HTTPException(404)
    head = request.method == "HEAD"
    try:
        try:
            return _file_response(parts, head=head)
        except FileNotFoundError:
            if browser_path is None:
                raise
            return _file_response(("index.html",), head=head)
    except OSError as error:
        raise HTTPException(404) from error
