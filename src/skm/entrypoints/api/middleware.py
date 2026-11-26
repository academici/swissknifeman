"""Ordered HTTP admission; bounded bodies are checked before handlers and authentication IO."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from skm.bootstrap.composition import App
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.config.bootstrap import WebAuthConfig
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.system_clock import SystemClock

from .auth import (
    authenticate,
    is_db_free_public,
    is_loopback_host,
    is_loopback_peer,
)
from .health import Health
from .versioning import check_version

__all__ = ["BodyPolicy", "HTTPBoundary"]

_GRAPH_IMPORT_LIMIT = "knowledge.graph.import_max_bytes"
_DEFAULT_LIMIT = 1_048_576
_ENVELOPE = 65_536
_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_DIGITS = re.compile(r"[0-9]+")
_ALLOW_HEADERS = (
    "Authorization, Content-Type, Idempotency-Key, If-Match, If-None-Match, X-Request-Id, "
    "X-SKM-CSRF, Last-Event-ID, SKM-Client-Version, SKM-Expected-Digest, SKM-Host-Id, "
    "SKM-Instance-Id, SKM-Idempotency-Deadline"
)


@dataclass(frozen=True, slots=True)
class BodyPolicy:
    """Route admission metadata; DTO binding belongs to the routing leaf."""

    method: str
    path: str
    body_limit_key: str = "api.limits.max_body_bytes"
    media_type: str | None = None
    length_required: bool = False
    allow_empty_body: bool = False


_DEFAULT_BODY_POLICY = BodyPolicy("", "")


def _allowed_hosts(settings: Mapping[str, JsonValue], web_auth: WebAuthConfig) -> frozenset[str]:
    bind = str(settings.get("api.bind", "127.0.0.1:8765"))
    host, port = bind.rsplit(":", 1)
    loopback_defaults = [f"{name}:{port}" for name in ("127.0.0.1", "localhost", "[::1]")]
    if port == "80":
        loopback_defaults.extend(("127.0.0.1", "localhost", "[::1]"))
    allowed = cast("list[str]", settings.get("api.allowed_hosts") or [])
    if web_auth.mode == "none":
        # Loopback-only mode never accepts non-loopback Host headers, regardless of api.allowed_hosts.
        if allowed:
            candidates = [str(item).lower() for item in allowed if is_loopback_host(str(item))]
            return frozenset(candidates)
        return frozenset(item.lower() for item in loopback_defaults)
    if not allowed:
        allowed = (
            [f"{name}:{port}" for name in ("127.0.0.1", "localhost", "[::1]")]
            if host.lower() in {"127.0.0.1", "localhost", "[::1]"}
            else [bind]
        )
    return frozenset(str(host).lower() for host in allowed)


class HTTPBoundary:
    def __init__(
        self,
        app: ASGIApp,
        core: App,
        settings: Mapping[str, JsonValue],
        health: Health,
        policies: Sequence[BodyPolicy] = (),
        web_auth: WebAuthConfig | None = None,
    ) -> None:
        self.app, self.core, self.settings, self.health = app, core, settings, health
        self._web_auth = web_auth if web_auth is not None else core.web_auth
        self.policies = tuple((policy, compile_path(policy.path)[0]) for policy in policies)
        self._allowed_hosts = _allowed_hosts(settings, self._web_auth)
        self._cors_origins = frozenset(
            str(origin) for origin in cast("list[str]", settings.get("api.cors.origins") or [])
        )
        self._min_client_version = str(settings.get("api.min_client_version", "0.1.0"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        self._peer(request)
        self._host(request)
        self._origin(request)
        if request.method == "OPTIONS":
            headers = {}
            if getattr(request.state, "cors_origin", None):
                headers = {
                    "Access-Control-Allow-Headers": _ALLOW_HEADERS,
                    "Access-Control-Allow-Methods": "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Max-Age": "600",
                }
            await Response(status_code=204, headers=headers)(scope, receive, send)
            return
        policy = next(
            (
                p
                for p, pattern in self.policies
                if p.method == request.method and pattern.fullmatch(request.scope["path"])
            ),
            _DEFAULT_BODY_POLICY,
        )
        body = await self._body(request, receive, policy)
        self._content_type(request, policy, body)
        check_version(request, self._min_client_version)
        if request.scope["path"] != "/health/live":
            await self.health.refresh()
        if self.health.schema_error is not None and not (
            request.scope["path"] in {"/health/live", "/health/ready"}
            or (request.scope["path"] == "/api/v1/admin/migrations" and request.method == "GET")
        ):
            raise error_for(self.health.schema_error, "Database schema is incompatible; run skm db migrate")
        if not self.health.database_ok and not is_db_free_public(request.method, request.scope["path"]):
            raise error_for(
                ErrorCode.BACKEND_UNAVAILABLE,
                "Database is unavailable",
                retryable=True,
            )
        self._instance(request)
        await authenticate(request, self.core, self._web_auth)
        keys = request.headers.getlist("idempotency-key")
        if len(keys) > 1 or (keys and _KEY.fullmatch(keys[0]) is None):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid Idempotency-Key")
        self._retry_deadline(request, has_key=bool(keys))

        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)

    def _instance(self, request: Request) -> None:
        values = request.headers.getlist("skm-instance-id")
        if not values:
            return
        try:
            (value,) = values
            expected = UUID(value)
        except ValueError:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid SKM-Instance-Id") from None
        if expected != self.core.instance_id:
            raise error_for(
                ErrorCode.CONFIG_INVALID,
                "Backend instance_id differs from the expected instance_id",
                details={"expected": str(expected), "actual": str(self.core.instance_id)},
            )

    def _retry_deadline(self, request: Request, *, has_key: bool) -> None:
        values = request.headers.getlist("skm-idempotency-deadline")
        if not values:
            return
        try:
            (value,) = values
            deadline = datetime.fromisoformat(value)
            if (
                len(value) > 40
                or deadline.tzinfo is None
                or request.method in _SAFE
                or not has_key
                or deadline.astimezone(UTC) > self.core.bus.safe_retry_deadline()
            ):
                raise ValueError
        except (ValueError, OverflowError):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid SKM-Idempotency-Deadline") from None
        request.state.idempotency_deadline = deadline

    def _peer(self, request: Request) -> None:
        if self._web_auth.mode == "none" and not is_loopback_peer(request.scope.get("client")):
            raise error_for(
                ErrorCode.FORBIDDEN,
                "web_auth.mode='none' requires a loopback TCP peer",
                details={"reason": "non_loopback_peer"},
            )

    def _host(self, request: Request) -> None:
        hosts = request.headers.getlist("host")
        if (
            len(hosts) != 1
            or hosts[0].lower() not in self._allowed_hosts
            or (self._web_auth.mode == "none" and not is_loopback_host(hosts[0]))
        ):
            raise error_for(ErrorCode.HOST_REJECTED, "The Host is not allowed")

    def _origin(self, request: Request) -> None:
        origins = request.headers.getlist("origin")
        if not origins:
            return
        if (
            len(origins) != 1
            or origins[0] == "null"
            or (
                origins[0] != f"{request.scope['scheme']}://{request.headers['host']}"
                and origins[0] not in self._cors_origins
            )
        ):
            raise error_for(ErrorCode.ORIGIN_REJECTED, "The Origin is not allowed")
        if origins[0] in self._cors_origins:
            request.state.cors_origin = origins[0]

    def _graph_import_limit(self, request: Request) -> int:
        meta = RequestMeta(request.state.request_id, Surface.API, None, SystemClock().now())
        with self.core.uow_factory(meta, readonly=True) as uow:
            config = self.core.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
            return cast("int", config.get(_GRAPH_IMPORT_LIMIT))

    async def _body(self, request: Request, receive: Receive, policy: BodyPolicy) -> bytes:
        limit = int(cast("int", self.settings.get(policy.body_limit_key, _DEFAULT_LIMIT)))
        if policy.body_limit_key == _GRAPH_IMPORT_LIMIT:
            limit = await run_in_threadpool(self._graph_import_limit, request)
        if policy.body_limit_key == "planning.drafts.max_document_bytes":
            limit += _ENVELOPE
        lengths = request.headers.getlist("content-length")
        if len(lengths) > 1 or (lengths and _DIGITS.fullmatch(lengths[0]) is None):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid Content-Length")
        if not lengths and policy.length_required:
            raise error_for(ErrorCode.LENGTH_REQUIRED, "Content-Length is required")
        digits = (lengths[0].lstrip("0") or "0") if lengths else ""
        maximum = str(limit)
        if digits and (len(digits) > len(maximum) or (len(digits) == len(maximum) and digits > maximum)):
            raise error_for(ErrorCode.PAYLOAD_TOO_LARGE, "Request body exceeds the route limit")
        length = int(digits) if digits else None
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise error_for(ErrorCode.SCHEMA_INVALID, "Request body was interrupted")
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                raise error_for(ErrorCode.PAYLOAD_TOO_LARGE, "Request body exceeds the route limit")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if length is not None and length != len(body):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Content-Length does not match the body")
        return bytes(body)

    @staticmethod
    def _content_type(request: Request, policy: BodyPolicy, body: bytes) -> None:
        if request.method in _SAFE:
            return
        values = request.headers.getlist("content-type")
        if not values and not body and policy.allow_empty_body:
            return
        expected = policy.media_type or (
            "application/merge-patch+json" if request.method == "PATCH" else "application/json"
        )
        if len(values) != 1 or values[0].split(";", 1)[0].strip().lower() != expected:
            raise error_for(ErrorCode.UNSUPPORTED_MEDIA_TYPE, f"Content-Type must be {expected}")
