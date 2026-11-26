"""Request correlation, isolated logging context and headers on every HTTP result."""

import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.logging.envelope import bind
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

from .errors import problem_response
from .routing import HostMetadataFactory
from .versioning import API_VERSION

__all__ = ["RequestContext", "request_meta"]

_VALID_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_CLOCK = SystemClock()
_IDS = Uuid7Generator(_CLOCK)


class _RequestRedactor(Redactor):
    """Request-local credentials layered over the host's read-only secret registry."""

    def __init__(self, base: Redactor) -> None:
        super().__init__(patterns=())
        self._base = base

    @override
    def text(self, value: str) -> str:
        return super().text(self._base.text(value))

    @override
    def document(self, value: JsonValue) -> JsonValue:
        return super().document(self._base.document(value))


def request_meta(request: Request, *, host_metadata: HostMetadataFactory | None = None) -> RequestMeta:
    meta = RequestMeta(
        request.state.request_id,
        Surface.API,
        request.headers.get("idempotency-key"),
        request.state.received_at,
        client=request.headers.get("skm-client-version"),
        correlation_id=getattr(request.state, "correlation_id", None),
        idempotency_deadline=getattr(request.state, "idempotency_deadline", None),
    )
    if host_metadata is not None and (hosts := request.headers.getlist("skm-host-id")):
        if len(hosts) != 1:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Multiple SKM-Host-Id headers")
        try:
            host_id = HostId(UUID(hosts[0]))
        except ValueError as exc:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid SKM-Host-Id header") from exc
        return replace(
            host_metadata(meta, host_id),
            correlation_id=meta.correlation_id,
            idempotency_deadline=meta.idempotency_deadline,
        )
    return meta


class RequestContext:
    def __init__(
        self,
        app: ASGIApp,
        settings: Mapping[str, JsonValue],
        redactor: Redactor,
        instance_id: UUID | None = None,
        receipt_window: tuple[int, Callable[[], datetime]] | None = None,
    ) -> None:
        self.app, self.settings, self.redactor = app, settings, redactor
        self._instance_id = instance_id
        self._receipt_window = receipt_window
        origins = settings.get("api.cors.origins") or []
        connect = " ".join(str(origin) for origin in origins) if isinstance(origins, list) else ""
        self._csp = (
            f"default-src 'self'; connect-src 'self' {connect}; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )

    def _project_headers(self, result: MutableHeaders, server_time: datetime | None) -> None:
        if self._instance_id is not None:
            result["SKM-Instance-Id"] = str(self._instance_id)
        if server_time is not None and self._receipt_window is not None:
            result["SKM-Server-Time"] = server_time.astimezone(UTC).isoformat()
            result["SKM-Idempotency-Retention-Seconds"] = str(self._receipt_window[0])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        values = request.headers.getlist("x-request-id")
        request_id = (
            values[0] if len(values) == 1 and _VALID_ID.fullmatch(values[0]) else f"req-{_IDS.new_id()}"
        )
        correlations = request.headers.getlist("skm-correlation-id")
        correlation_id = (
            correlations[0] if len(correlations) == 1 and _VALID_ID.fullmatch(correlations[0]) else None
        )
        if correlation_id is not None:
            with suppress(ValueError):
                correlation_id = str(UUID(correlation_id))
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        request.state.received_at = _CLOCK.now()
        server_time = self._receipt_window[1]() if self._receipt_window is not None else None
        redactor: Redactor = self.redactor

        # Mask presented credentials even on admission errors before authentication, without
        # registering attacker-controlled text in the shared host registry.
        def register_request_secret(secret: str) -> None:
            nonlocal redactor
            if len(secret) < 8:
                return
            if redactor is self.redactor:
                redactor = _RequestRedactor(self.redactor)
            redactor.register_secret(secret)

        for authorization in request.headers.getlist("authorization"):
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                register_request_secret(parts[1])
        for cookie_name in ("skm_session", "skm_csrf"):
            cookie_val = request.cookies.get(cookie_name)
            if cookie_val:
                register_request_secret(cookie_val)
        for secret_header in ("x-skm-csrf", "skm-machine-session"):
            for value in request.headers.getlist(secret_header):
                register_request_secret(value)
        request.state.redactor = redactor
        started = False

        async def headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                result = MutableHeaders(scope=message)
                result["X-Request-Id"] = request_id
                result["SKM-Api-Version"] = API_VERSION
                self._project_headers(result, server_time)
                result["Content-Security-Policy"] = self._csp
                result["X-Content-Type-Options"] = "nosniff"
                result["Referrer-Policy"] = "no-referrer"
                result["X-Frame-Options"] = "DENY"
                if request.scope["path"].startswith("/api/"):
                    result["Cache-Control"] = "no-store"
                if getattr(request.state, "cors_origin", None):
                    result["Access-Control-Allow-Origin"] = request.state.cors_origin
                    result.add_vary_header("Origin")
                    result["Access-Control-Expose-Headers"] = (
                        "ETag, Location, X-Request-Id, SKM-Api-Version, "
                        "SKM-Events-Cursor, Idempotency-Replayed, SKM-Instance-Id, "
                        "SKM-Server-Time, SKM-Idempotency-Retention-Seconds"
                    )
            await send(message)

        with bind(request_id=request_id, correlation_id=correlation_id or request_id, surface="api"):
            try:
                await self.app(scope, receive, headers)
            except Exception as error:
                if started:
                    raise
                get_logger("entrypoints.api").error("api.request.failed", exc=error)
                await problem_response(request, error)(scope, receive, headers)
