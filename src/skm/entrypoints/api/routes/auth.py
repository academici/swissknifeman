"""HTTP authentication routes: CSRF bootstrap, login, logout, session, reload, pairing exchange."""

import os
from collections.abc import Callable
from datetime import timedelta
from time import monotonic
from typing import Any, cast, override
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from skm.application_bus.client import EmbeddedClient
from skm.application_bus.context import AuthBasis
from skm.application_bus.middleware import RecoveryGuard, require_restore_admission
from skm.bootstrap.composition import App
from skm.entrypoints.api.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthRateLimiter,
    authenticate_session_cookie,
    make_csrf_token,
    pepper_for,
    request_auth_basis,
    require_csrf,
    require_same_origin,
)
from skm.entrypoints.api.middleware import BodyPolicy
from skm.entrypoints.api.request_context import request_meta
from skm.kernel.actor import Actor, ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Unauthenticated, ValidationFailed, error_for
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.public import (
    SYSTEM_ACTOR,
    WebSession,
    authenticate_local_owner_password,
    authenticate_web_session,
    create_web_session,
    issue_pairing_token,
    revoke_web_session,
)
from skm.modules.workspace.public import ExchangePairingToken, ExchangePairingTokenResult
from skm.platform.config.bootstrap import WebAuthConfig
from skm.platform.logging.redaction import Redactor
from skm.platform.system_ids import Uuid7Generator

__all__ = ["AUTH_ROUTE_SPECS", "build_auth_routes"]

AUTH_ROUTE_SPECS: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("GET", "/api/v1/auth/csrf", "auth_get_csrf", True, False),
    ("POST", "/api/v1/auth/login", "auth_login", True, True),
    ("POST", "/api/v1/auth/logout", "auth_logout", False, True),
    ("GET", "/api/v1/auth/session", "auth_get_session", False, False),
    ("POST", "/api/v1/auth/session/reload", "auth_reload_session", False, True),
    ("POST", "/api/v1/auth/pairing", "auth_create_pairing", False, False),
    ("POST", "/api/v1/auth/pairing/exchange", "auth_exchange_pairing", True, False),
)


class _ScopedRedactor(Redactor):
    """Per-request secret wrapper so body secrets never enter the shared host redactor."""

    def __init__(self, delegate: Redactor) -> None:
        super().__init__(patterns=())
        self._delegate = delegate

    @override
    def text(self, value: str) -> str:
        return super().text(self._delegate.text(value))

    @override
    def document(self, value: Any) -> Any:
        return super().document(self._delegate.document(value))


def _register_body_secret(request: Request, secret: str) -> None:
    if len(secret) < 8:
        return
    current = getattr(request.state, "redactor", None)
    scoped = _ScopedRedactor(current) if isinstance(current, Redactor) else Redactor()
    scoped.register_secret(secret)
    request.state.redactor = scoped


def _ensure_not_quarantined(core: App, operation: str) -> None:
    guard = getattr(core.bus, "guard", None)
    if isinstance(guard, RecoveryGuard) and guard.receipt() is None:
        require_restore_admission(False, operation)


def _client_peer(request: Request) -> str:
    client = request.scope.get("client")
    return str(client[0]) if client and client[0] else "unknown"


def _is_secure_scheme(request: Request) -> bool:
    return str(request.scope.get("scheme", "http")).lower() == "https"


def _set_session_cookies(
    response: Response,
    *,
    request: Request,
    web_auth: WebAuthConfig,
    session_secret: str,
    csrf_token: str,
) -> None:
    secure = _is_secure_scheme(request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_secret,
        max_age=web_auth.session_ttl_seconds,
        path="/",
        secure=secure,
        httponly=True,
        samesite=web_auth.cookie_samesite,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=web_auth.session_ttl_seconds,
        path="/",
        secure=secure,
        httponly=False,
        samesite=web_auth.cookie_samesite,
    )


def _clear_session_cookies(response: Response, *, request: Request, web_auth: WebAuthConfig) -> None:
    secure = _is_secure_scheme(request)
    for name, httponly in ((SESSION_COOKIE_NAME, True), (CSRF_COOKIE_NAME, False)):
        response.set_cookie(
            name,
            "",
            max_age=0,
            expires=0,
            path="/",
            secure=secure,
            httponly=httponly,
            samesite=web_auth.cookie_samesite,
        )


async def _parse_json_object(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        raise error_for(ErrorCode.SCHEMA_INVALID, "JSON body is required")
    try:
        parsed = await request.json()
    except ValueError as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid JSON body") from exc
    if not isinstance(parsed, dict):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Body must be a JSON object")
    return cast("dict[str, Any]", parsed)


class _AuthHandlers:
    def __init__(
        self,
        core: App,
        web_auth: WebAuthConfig,
        *,
        rate_limit_clock: Callable[[], float] | None = None,
        on_access_change: Callable[[], None] | None = None,
    ) -> None:
        self._core = core
        self._web_auth = web_auth
        self._on_access_change = on_access_change
        self._limiter = AuthRateLimiter(
            web_auth.login_rate_limit_max,
            web_auth.login_rate_limit_window_seconds,
            clock=rate_limit_clock or monotonic,
        )
        self._ids = Uuid7Generator(core.clock)

    async def get_csrf(self, request: Request) -> JSONResponse:
        pepper = pepper_for(self._core)
        subject = "anon"
        cookie_secret = request.cookies.get(SESSION_COOKIE_NAME)
        if cookie_secret:
            try:
                _actor, session = await run_in_threadpool(
                    authenticate_session_cookie, self._core, cookie_secret
                )
            except Unauthenticated:
                subject = "anon"
            else:
                subject = str(session.id)
        token = make_csrf_token(pepper, subject=subject)
        response = JSONResponse({"csrf_token": token})
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            max_age=self._web_auth.session_ttl_seconds,
            path="/",
            secure=_is_secure_scheme(request),
            httponly=False,
            samesite=self._web_auth.cookie_samesite,
        )
        return response

    async def login(self, request: Request) -> JSONResponse:
        _ensure_not_quarantined(self._core, "auth.login")
        self._limiter.check(_client_peer(request))
        require_same_origin(request)
        pepper = pepper_for(self._core)
        subjects: list[str] = ["anon"]
        existing_cookie = request.cookies.get(SESSION_COOKIE_NAME)
        if existing_cookie:
            try:
                _existing_actor, existing_session = await run_in_threadpool(
                    authenticate_session_cookie, self._core, existing_cookie
                )
            except Unauthenticated:
                pass
            else:
                subjects.append(str(existing_session.id))
        require_csrf(request, pepper, subjects=subjects)
        body = await _parse_json_object(request)
        password = body.get("password")
        if not isinstance(password, str) or not password:
            raise error_for(ErrorCode.SCHEMA_INVALID, "password must be a non-empty string")
        _register_body_secret(request, password)

        def _do_login() -> tuple[Actor, WebSession, str]:
            now = self._core.clock.now()
            meta = RequestMeta(request.state.request_id, Surface.API, None, now)
            with self._core.uow_factory(meta, readonly=False) as uow:
                actor = authenticate_local_owner_password(uow, password)
                session, secret = create_web_session(
                    uow,
                    principal_id=actor.principal_id,
                    session_id=self._ids.new_id(),
                    now=now,
                    ttl_seconds=self._web_auth.session_ttl_seconds,
                    entropy=os.urandom,
                    pepper=pepper,
                )
                uow.commit()
            return actor, session, secret

        actor, session, secret = await run_in_threadpool(_do_login)
        csrf_token = make_csrf_token(pepper, subject=str(session.id))
        response = JSONResponse(
            {
                "session_id": str(session.id),
                "principal_id": str(actor.principal_id),
                "kind": actor.kind.value,
                "display_name": actor.display_name,
                "expires_at": session.expires_at.isoformat(),
                "csrf_token": csrf_token,
            }
        )
        _set_session_cookies(
            response, request=request, web_auth=self._web_auth, session_secret=secret, csrf_token=csrf_token
        )
        return response

    async def logout(self, request: Request) -> JSONResponse:
        session = cast("WebSession | None", getattr(request.state, "web_session", None))
        if session is None:
            raise error_for(ErrorCode.UNAUTHENTICATED, "Active web session is required")
        require_same_origin(request)
        require_csrf(request, pepper_for(self._core), subjects=(str(session.id),))

        def _do_logout() -> None:
            now = self._core.clock.now()
            meta = RequestMeta(request.state.request_id, Surface.API, None, now)
            with self._core.uow_factory(meta, readonly=False) as uow:
                revoke_web_session(uow, session.id, now=now)
                uow.commit()

        await run_in_threadpool(_do_logout)
        if self._on_access_change is not None:
            self._on_access_change()
        response = JSONResponse({"status": "logged_out"})
        _clear_session_cookies(response, request=request, web_auth=self._web_auth)
        return response

    async def get_session(self, request: Request) -> JSONResponse:
        basis = request_auth_basis(request)
        actor = basis.actor
        session = cast("WebSession | None", getattr(request.state, "web_session", None))
        expires_at = session.expires_at if session is not None else basis.session_expires_at
        return JSONResponse(
            {
                "authenticated": True,
                "mode": self._web_auth.mode,
                "auth_method": basis.auth_method,
                "principal_id": str(actor.principal_id),
                "kind": actor.kind.value,
                "display_name": actor.display_name,
                "session_id": None if basis.session_id is None else str(basis.session_id),
                "expires_at": None if expires_at is None else expires_at.isoformat(),
            }
        )

    async def reload_session(self, request: Request) -> JSONResponse:
        _ensure_not_quarantined(self._core, "auth.session.reload")
        session = cast("WebSession | None", getattr(request.state, "web_session", None))
        if session is None:
            raise error_for(ErrorCode.UNAUTHENTICATED, "Active web session is required")
        require_same_origin(request)
        pepper = pepper_for(self._core)
        require_csrf(request, pepper, subjects=(str(session.id),))
        cookie_secret = request.cookies.get(SESSION_COOKIE_NAME)
        if not cookie_secret:
            raise error_for(ErrorCode.UNAUTHENTICATED, "Active web session is required")

        def _do_reload() -> tuple[Actor, WebSession, str]:
            now = self._core.clock.now()
            meta = RequestMeta(request.state.request_id, Surface.API, None, now)
            with self._core.uow_factory(meta, readonly=False) as uow:
                actor, current = authenticate_web_session(uow, cookie_secret, pepper=pepper, now=now)
                if not revoke_web_session(uow, current.id, now=now):
                    raise error_for(ErrorCode.UNAUTHENTICATED, "Session is no longer active")
                fresh, secret = create_web_session(
                    uow,
                    principal_id=actor.principal_id,
                    session_id=self._ids.new_id(),
                    now=now,
                    ttl_seconds=self._web_auth.session_ttl_seconds,
                    entropy=os.urandom,
                    pepper=pepper,
                )
                uow.commit()
            return actor, fresh, secret

        actor, fresh, secret = await run_in_threadpool(_do_reload)
        if self._on_access_change is not None:
            self._on_access_change()
        csrf_token = make_csrf_token(pepper, subject=str(fresh.id))
        response = JSONResponse(
            {
                "session_id": str(fresh.id),
                "principal_id": str(actor.principal_id),
                "kind": actor.kind.value,
                "display_name": actor.display_name,
                "expires_at": fresh.expires_at.isoformat(),
                "csrf_token": csrf_token,
            }
        )
        _set_session_cookies(
            response, request=request, web_auth=self._web_auth, session_secret=secret, csrf_token=csrf_token
        )
        return response

    async def create_pairing(self, request: Request) -> JSONResponse:
        _ensure_not_quarantined(self._core, "auth.pairing.create")
        basis = request_auth_basis(request)
        body = await _parse_json_object(request)
        try:
            workspace_id = WorkspaceId(UUID(str(body.get("workspace_id", ""))))
        except ValueError:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid workspace_id") from None
        raw_ttl = body.get("ttl_seconds", 900)
        if type(raw_ttl) is not int or not 1 <= raw_ttl <= 3600:
            raise error_for(ErrorCode.SCHEMA_INVALID, "ttl_seconds must be an integer between 1 and 3600")
        worker_reg_raw = body.get("worker_registration")
        if worker_reg_raw is not None and not isinstance(worker_reg_raw, dict):
            raise error_for(ErrorCode.SCHEMA_INVALID, "worker_registration must be an object")
        worker_registration = cast("JsonObject | None", worker_reg_raw)
        principal_id: PrincipalId | None = None
        if body.get("principal_id") is not None:
            try:
                principal_id = PrincipalId(UUID(str(body["principal_id"])))
            except ValueError:
                raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid principal_id") from None
        replaces: UUID | None = None
        if body.get("replaces") is not None:
            try:
                replaces = UUID(str(body["replaces"]))
            except ValueError:
                raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid replaces") from None
        scope_grants_raw = body.get("scope_grants")
        scope_grants: tuple[ScopeGrant, ...] = ()
        if scope_grants_raw is not None:
            if not isinstance(scope_grants_raw, dict):
                raise error_for(ErrorCode.SCHEMA_INVALID, "scope_grants must be an object")
            parsed_grants: list[ScopeGrant] = []
            for raw_scope, raw_perms in cast("dict[str, Any]", scope_grants_raw).items():
                try:
                    scope_id = ScopeId(UUID(str(raw_scope)))
                except ValueError:
                    raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid scope_id in scope_grants") from None
                if not isinstance(raw_perms, list):
                    raise error_for(ErrorCode.SCHEMA_INVALID, "scope_grants permissions must be string lists")
                perm_items = cast("list[object]", raw_perms)
                if not all(isinstance(p, str) for p in perm_items):
                    raise error_for(ErrorCode.SCHEMA_INVALID, "scope_grants permissions must be string lists")
                parsed_grants.append(
                    ScopeGrant(scope_id=scope_id, permissions=frozenset(cast("list[str]", perm_items)))
                )
            scope_grants = tuple(parsed_grants)

        def _do_issue() -> tuple[UUID, str, str]:
            now = self._core.clock.now()
            expires_at = now + timedelta(seconds=raw_ttl)
            pairing_id = self._ids.new_id()
            meta = RequestMeta(request.state.request_id, Surface.API, None, now)
            pepper = pepper_for(self._core)
            with self._core.uow_factory(meta, readonly=False) as uow:
                secret = issue_pairing_token(
                    uow,
                    issuer=basis.actor,
                    workspace_id=workspace_id,
                    pairing_id=pairing_id,
                    now=now,
                    expires_at=expires_at,
                    entropy=os.urandom,
                    pepper=pepper,
                    worker_registration=worker_registration,
                    principal_id=principal_id,
                    scope_grants=scope_grants,
                    replaces=replaces,
                )
                uow.commit()
            return pairing_id, secret, expires_at.isoformat()

        pairing_id, secret, expires_at = await run_in_threadpool(_do_issue)
        return JSONResponse(
            {
                "pairing_id": str(pairing_id),
                "workspace_id": str(workspace_id),
                "pairing_secret": secret,
                "expires_at": expires_at,
            },
            status_code=201,
        )

    async def exchange_pairing(self, request: Request) -> JSONResponse:
        _ensure_not_quarantined(self._core, "auth.pairing.exchange")
        self._limiter.check(_client_peer(request))
        body = await _parse_json_object(request)
        raw_secret = body.get("pairing_secret")
        if isinstance(raw_secret, str):
            _register_body_secret(request, raw_secret)
        try:
            cmd = ExchangePairingToken.from_json(body)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid pairing exchange payload") from exc
        client = self._core.client(actor=SYSTEM_ACTOR, surface=Surface.API)
        if not isinstance(client, EmbeddedClient):
            raise TypeError("HTTP API requires an embedded control-plane client")
        bound = client.for_request(request_meta(request), auth_basis=AuthBasis.system(SYSTEM_ACTOR))
        run_bus = getattr(request.app.state, "run_bus", run_in_threadpool)
        result = cast("ExchangePairingTokenResult", await run_bus(bound.dispatch, cmd))
        return JSONResponse(result.to_json())


def build_auth_routes(
    core: App,
    web_auth: WebAuthConfig,
    *,
    rate_limit_clock: Callable[[], float] | None = None,
    on_access_change: Callable[[], None] | None = None,
) -> tuple[tuple[BaseRoute, ...], tuple[BodyPolicy, ...]]:
    """Construct standalone HTTP authentication routes and their body policies."""
    handlers = _AuthHandlers(
        core,
        web_auth,
        rate_limit_clock=rate_limit_clock,
        on_access_change=on_access_change,
    )
    routes: tuple[BaseRoute, ...] = (
        Route("/api/v1/auth/csrf", handlers.get_csrf, methods=["GET"], name="auth_get_csrf"),
        Route("/api/v1/auth/login", handlers.login, methods=["POST"], name="auth_login"),
        Route("/api/v1/auth/logout", handlers.logout, methods=["POST"], name="auth_logout"),
        Route("/api/v1/auth/session", handlers.get_session, methods=["GET"], name="auth_get_session"),
        Route(
            "/api/v1/auth/session/reload",
            handlers.reload_session,
            methods=["POST"],
            name="auth_reload_session",
        ),
        Route(
            "/api/v1/auth/pairing",
            handlers.create_pairing,
            methods=["POST"],
            name="auth_create_pairing",
        ),
        Route(
            "/api/v1/auth/pairing/exchange",
            handlers.exchange_pairing,
            methods=["POST"],
            name="auth_exchange_pairing",
        ),
    )
    policies: tuple[BodyPolicy, ...] = (
        BodyPolicy("POST", "/api/v1/auth/login", media_type="application/json"),
        BodyPolicy("POST", "/api/v1/auth/logout", media_type="application/json", allow_empty_body=True),
        BodyPolicy(
            "POST", "/api/v1/auth/session/reload", media_type="application/json", allow_empty_body=True
        ),
        BodyPolicy("POST", "/api/v1/auth/pairing", media_type="application/json"),
        BodyPolicy("POST", "/api/v1/auth/pairing/exchange", media_type="application/json"),
    )
    return routes, policies
