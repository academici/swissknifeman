"""Security of every request: a pure ASGI middleware in front of the app, for HTTP and WebSocket alike (I9).

Order: (1) ``Host`` must be exactly ``127.0.0.1:<port>``, ``localhost:<port>`` or ``[::1]:<port>`` (DNS
rebinding), before anything else; (2) a present ``Origin`` must be one of the same three ``http://`` origins, and a
WebSocket must send one; (3) a body over 1 MiB is ``PAYLOAD_TOO_LARGE`` and an unsafe method needs
``Content-Type: application/json``; (4) authentication: ``Authorization: Bearer <session secret>`` or the session
cookie (the token exchange ``GET /?t=`` is the only open door), and an unsafe method authenticated by cookie must
carry an ``Origin`` (CSRF); (5) security headers on every response; no CORS header is ever sent.
"""
from __future__ import annotations

import uuid
from http.cookies import CookieError, SimpleCookie
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from ..backend import COOKIE
from ..errors import GuiError, http_status
from .errors import json_body

MAX_BODY = 1024 * 1024
UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
UNAUTHENTICATED_PAGE = (b"<!doctype html><meta charset=\"utf-8\"><title>SKM GUI</title>"
                        b"<p>Not signed in. Open the URL printed by <code>gui open</code>.</p>")


def allowed_hosts(port: int) -> Tuple[str, ...]:
    return (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")


def allowed_origins(port: int) -> Tuple[str, ...]:
    return tuple(f"http://{host}" for host in allowed_hosts(port))


def csp(port: int) -> str:
    sockets = " ".join(f"ws://{host}" for host in allowed_hosts(port))
    return ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            f"connect-src 'self' {sockets}; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'")


def _headers(scope) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for name, value in scope.get("headers", ()):
        found.setdefault(name.decode("latin-1").lower(), []).append(value.decode("latin-1"))
    return found


def _single(headers: Dict[str, List[str]], name: str) -> Optional[str]:
    """The value of a header that must appear at most once; a repeated header counts as invalid (``""``)."""
    values = headers.get(name)
    if not values:
        return None
    return values[0] if len(values) == 1 else ""


def _cookie(headers: Dict[str, List[str]]) -> Optional[str]:
    for raw in headers.get("cookie", ()):
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except CookieError:
            continue
        if COOKIE in jar:
            return jar[COOKIE].value
    return None


def is_exchange(scope) -> bool:
    """``GET /?t=<token>``: the one request that is not authenticated (it creates the cookie)."""
    if scope["type"] != "http" or scope.get("method") != "GET" or scope.get("path") != "/":
        return False
    return "t" in parse_qs(scope.get("query_string", b"").decode("latin-1"))


class SecurityMiddleware:
    def __init__(self, app, state) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        try:
            receive, auth = await self.check(scope, receive)
        except GuiError as error:
            await self.refuse(scope, receive, send, error)
            return
        scope.setdefault("state", {})["auth"] = auth
        await self.app(scope, receive, self.secure(scope, send))

    async def check(self, scope, receive):
        port = self.state.port
        headers = _headers(scope)
        if _single(headers, "host") not in allowed_hosts(port):
            raise GuiError("HOST_REJECTED", "the Host header is not this loopback backend")
        origin = _single(headers, "origin")
        if origin is not None and origin not in allowed_origins(port):
            raise GuiError("ORIGIN_REJECTED", "the Origin is not this backend")
        websocket = scope["type"] == "websocket"
        if websocket and origin is None:
            raise GuiError("ORIGIN_REJECTED", "a WebSocket must send its Origin")
        method = scope.get("method", "GET")
        if not websocket:
            receive = await self.limit_body(scope, headers, receive)
            if method in UNSAFE:
                media = (_single(headers, "content-type") or "").split(";", 1)[0].strip().lower()
                if media != "application/json":
                    raise GuiError("INPUT_INVALID", "a request that changes state must send application/json",
                                   issues=[{"pointer": "", "code": "content_type",
                                            "message": "expected Content-Type: application/json"}])
        if is_exchange(scope):
            return receive, "exchange"
        authorization = _single(headers, "authorization")
        if authorization is not None:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() != "bearer" or not value or not self.state.sessions.bearer_ok(value.strip()):
                raise GuiError("AUTH_INVALID", "the bearer credential is not valid")
            return receive, "bearer"
        cookie = _cookie(headers)
        if cookie is None:
            raise GuiError("AUTH_REQUIRED", "sign in with the URL printed by `gui open`")
        if not self.state.sessions.cookie_ok(cookie):
            raise GuiError("AUTH_INVALID", "the session is not valid; open a new URL with `gui open`")
        if (method in UNSAFE or websocket) and origin is None:
            raise GuiError("ORIGIN_REJECTED", "a cookie-authenticated request that changes state must send Origin")
        return receive, "cookie"

    async def limit_body(self, scope, headers, receive):
        """Read the whole body up front (at most ``MAX_BODY``) and replay it to the app."""
        length = _single(headers, "content-length")
        if length is not None:
            if not length.isdigit():
                raise GuiError("INPUT_INVALID", "invalid Content-Length")
            if int(length) > MAX_BODY:
                raise GuiError("PAYLOAD_TOO_LARGE", f"the body is larger than {MAX_BODY} bytes")
        if scope.get("method", "GET") not in UNSAFE and not length:
            return receive
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            body = message.get("body", b"")
            size += len(body)
            if size > MAX_BODY:
                raise GuiError("PAYLOAD_TOO_LARGE", f"the body is larger than {MAX_BODY} bytes")
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replay = [{"type": "http.request", "body": b"".join(chunks), "more_body": False}]

        async def replayed():
            if replay:
                return replay.pop()
            return await receive()

        return replayed

    def secure(self, scope, send):
        port = self.state.port
        api = scope.get("path", "").startswith("/v1/") or scope.get("path") == "/v1"

        async def sending(message):
            if message["type"] == "http.response.start":
                headers = [(name, value) for name, value in message.get("headers", [])
                           if not name.lower().startswith(b"access-control-")]
                headers += [(b"content-security-policy", csp(port).encode()),
                            (b"x-content-type-options", b"nosniff"),
                            (b"referrer-policy", b"no-referrer"),
                            (b"x-frame-options", b"DENY")]
                if api or is_exchange(scope):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        return sending

    async def refuse(self, scope, receive, send, error: GuiError):
        if scope["type"] == "websocket":
            message = await receive()
            if message["type"] == "websocket.connect":
                code = 4401 if error.code.startswith("AUTH_") else 4403
                await send({"type": "websocket.close", "code": code})
            return
        path = scope.get("path", "")
        browser_page = (error.code in ("AUTH_REQUIRED", "AUTH_INVALID") and scope.get("method") == "GET"
                        and not path.startswith("/v1"))
        if browser_page:
            body, media = UNAUTHENTICATED_PAGE, b"text/html; charset=utf-8"
        else:
            body, media = json_body(error.envelope(uuid.uuid4().hex)), b"application/json"
        start = {"type": "http.response.start", "status": http_status(error.code),
                 "headers": [(b"content-type", media), (b"content-length", str(len(body)).encode())]}
        sending = self.secure(scope, send)
        await sending(start)
        await sending({"type": "http.response.body", "body": body})
