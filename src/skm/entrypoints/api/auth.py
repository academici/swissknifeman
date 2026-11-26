"""HTTP admission for Bearer tokens, web session cookies, CSRF, loopback mode, and rate limiting."""

import base64
import hmac
import math
import os
import re
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from ipaddress import IPv6Address, ip_address
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from skm.application_bus.context import AuthBasis, AuthBasisKind
from skm.application_bus.middleware import RecoveryGuard
from skm.bootstrap.composition import App
from skm.bootstrap.lifecycle import parse_bind
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Unauthenticated, ValidationFailed, error_for
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.public import (
    TokenPepperSource,
    WebSession,
    authenticate_web_session,
    resolve_local_owner,
)
from skm.platform.config.bootstrap import WebAuthConfig

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "DB_FREE_PUBLIC_ROUTES",
    "PUBLIC_AUTH_ROUTES",
    "PUBLIC_PREFIXES",
    "PUBLIC_ROUTES",
    "SESSION_COOKIE_NAME",
    "AuthRateLimiter",
    "authenticate",
    "authenticate_session_cookie",
    "canonical_origin",
    "is_db_free_public",
    "is_loopback_host",
    "is_loopback_peer",
    "is_open",
    "is_public",
    "make_csrf_token",
    "pepper_for",
    "request_auth_basis",
    "require_csrf",
    "require_same_origin",
    "uvicorn_proxy_config",
    "validate_web_auth_bind",
    "verify_csrf_token",
]

SESSION_COOKIE_NAME = "skm_session"
CSRF_COOKIE_NAME = "skm_csrf"
CSRF_HEADER_NAME = "x-skm-csrf"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_RE = re.compile(r"^skm_csrf_([A-Za-z0-9_-]{16,64})\.([0-9a-f]{64})\Z")
_MAX_RATE_LIMIT_BUCKETS = 4096

# Explicit public (method, path) admission table.
# Logout, session inspection, and session reload are intentionally excluded.
PUBLIC_AUTH_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/auth/csrf"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/pairing/exchange"),
    }
)
PUBLIC_ROUTES: frozenset[tuple[str, str]] = (
    frozenset(
        {
            ("GET", "/health/live"),
            ("HEAD", "/health/live"),
            ("GET", "/health/ready"),
            ("HEAD", "/health/ready"),
            ("GET", "/api/v1/openapi.json"),
            ("GET", "/"),
            ("HEAD", "/"),
        }
    )
    | PUBLIC_AUTH_ROUTES
)
PUBLIC_PREFIXES: tuple[tuple[str, str], ...] = (
    ("GET", "/assets/"),
    ("HEAD", "/assets/"),
)
DB_FREE_PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health/live"),
        ("HEAD", "/health/live"),
        ("GET", "/health/ready"),
        ("HEAD", "/health/ready"),
        ("GET", "/api/v1/openapi.json"),
        ("GET", "/"),
        ("HEAD", "/"),
    }
)


def is_public(method: str, path: str) -> bool:
    upper = method.upper()
    return (upper, path) in PUBLIC_ROUTES or any(
        upper == allowed_method and path.startswith(prefix) for allowed_method, prefix in PUBLIC_PREFIXES
    )


def is_db_free_public(method: str, path: str) -> bool:
    upper = method.upper()
    return (upper, path) in DB_FREE_PUBLIC_ROUTES or any(
        upper == allowed_method and path.startswith(prefix) for allowed_method, prefix in PUBLIC_PREFIXES
    )


def is_open(path: str, method: str = "GET") -> bool:
    """Compatibility helper backed by the explicit (method, path) public table."""
    return is_public(method, path)


def _is_loopback_ip(text: str) -> bool:
    try:
        addr = ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    return isinstance(addr, IPv6Address) and addr.ipv4_mapped is not None and addr.ipv4_mapped.is_loopback


def is_loopback_peer(client: tuple[str, int] | None) -> bool:
    """Require an explicit IPv4 or IPv6 loopback TCP peer."""
    if not client or not client[0]:
        return False
    return _is_loopback_ip(client[0])


def is_loopback_host(host_header: str) -> bool:
    """Accept only localhost or IPv4/IPv6 loopback hostnames (with optional port)."""
    value = host_header.strip()
    if not value:
        return False
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return False
        hostname = value[1:end]
        rest = value[end + 1 :]
        if rest and (not rest.startswith(":") or not rest[1:].isdigit()):
            return False
    elif ":" in value:
        hostname, _, port = value.rpartition(":")
        if not port.isdigit():
            return False
    else:
        hostname = value
    return hostname.lower() == "localhost" or _is_loopback_ip(hostname)


def validate_web_auth_bind(bind: str, web_auth: WebAuthConfig) -> None:
    """Refuse non-loopback listen addresses when ``web_auth.mode == 'none'``."""
    host, _port = parse_bind(bind)
    if web_auth.mode != "none":
        return
    if host.lower() != "localhost" and not _is_loopback_ip(host):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "web_auth.mode='none' requires a loopback bind address (127.0.0.1, [::1], or localhost)",
            details={"field": "web_auth.mode", "bind": bind},
        )


def uvicorn_proxy_config(
    web_auth: WebAuthConfig, settings: Mapping[str, JsonValue] | None = None
) -> tuple[bool, list[str] | None]:
    """Derive Uvicorn ``(proxy_headers, forwarded_allow_ips)`` strictly from pre-DB ``web_auth``."""
    del settings  # Never let DB-backed api.proxy.trusted widen proxy trust.
    if web_auth.mode == "none":
        return False, None
    if web_auth.forwarded_allow_ips:
        return True, list(web_auth.forwarded_allow_ips)
    return False, None


def canonical_origin(scheme: str, host: str) -> str:
    """Normalize ``scheme://host[:port]`` by lowercasing and omitting default ports."""
    normalized_scheme = scheme.lower()
    normalized_host = host.strip().lower()
    if normalized_scheme == "http" and normalized_host.endswith(":80"):
        normalized_host = normalized_host[:-3]
    elif normalized_scheme == "https" and normalized_host.endswith(":443"):
        normalized_host = normalized_host[:-4]
    return f"{normalized_scheme}://{normalized_host}"


def require_same_origin(request: Request) -> None:
    """Enforce strict same-origin against Uvicorn's normalized scheme and validated Host."""
    fetch_site = request.headers.getlist("sec-fetch-site")
    if len(fetch_site) > 1 or (fetch_site and fetch_site[0].lower() == "cross-site"):
        raise error_for(ErrorCode.ORIGIN_REJECTED, "Cross-site request is not allowed")
    hosts = request.headers.getlist("host")
    if len(hosts) != 1:
        raise error_for(ErrorCode.HOST_REJECTED, "The Host is not allowed")
    expected = canonical_origin(str(request.scope.get("scheme", "http")), hosts[0])
    origins = request.headers.getlist("origin")
    if origins:
        if len(origins) != 1 or origins[0] == "null":
            raise error_for(ErrorCode.ORIGIN_REJECTED, "Same-origin request is required")
        parsed = urlsplit(origins[0])
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or canonical_origin(parsed.scheme, parsed.netloc) != expected
        ):
            raise error_for(ErrorCode.ORIGIN_REJECTED, "Same-origin request is required")
        return
    referers = request.headers.getlist("referer")
    if len(referers) != 1:
        raise error_for(ErrorCode.ORIGIN_REJECTED, "Same-origin Origin or Referer header is required")
    parsed = urlsplit(referers[0])
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or canonical_origin(parsed.scheme, parsed.netloc) != expected
    ):
        raise error_for(ErrorCode.ORIGIN_REJECTED, "Same-origin request is required")


def make_csrf_token(
    pepper: bytes, *, subject: str = "anon", entropy: Callable[[int], bytes] = os.urandom
) -> str:
    nonce = base64.urlsafe_b64encode(entropy(24)).rstrip(b"=").decode("ascii")
    sig = hmac.new(pepper, f"csrf:{subject}:{nonce}".encode("ascii"), sha256).hexdigest()
    return f"skm_csrf_{nonce}.{sig}"


def verify_csrf_token(token: str, pepper: bytes, *, subjects: Sequence[str]) -> bool:
    match = _CSRF_RE.fullmatch(token)
    if match is None:
        return False
    nonce, signature = match.group(1), match.group(2)
    for subject in subjects:
        expected = hmac.new(pepper, f"csrf:{subject}:{nonce}".encode("ascii"), sha256).hexdigest()
        if hmac.compare_digest(signature, expected):
            return True
    return False


def require_csrf(request: Request, pepper: bytes, *, subjects: Sequence[str]) -> None:
    headers = request.headers.getlist(CSRF_HEADER_NAME)
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if (
        len(headers) != 1
        or not cookie
        or not hmac.compare_digest(headers[0], cookie)
        or not verify_csrf_token(headers[0], pepper, subjects=subjects)
    ):
        raise error_for(
            ErrorCode.FORBIDDEN,
            "Invalid or missing CSRF token",
            details={"reason": "csrf_invalid"},
        )


class AuthRateLimiter:
    """In-memory per-peer sliding-window limiter for login and pairing exchange."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = float(window_seconds)
        self._clock = clock
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, peer: str) -> None:
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            if len(self._buckets) >= _MAX_RATE_LIMIT_BUCKETS and peer not in self._buckets:
                stale = [key for key, times in self._buckets.items() if not times or times[-1] <= cutoff]
                for key in stale:
                    del self._buckets[key]
                if len(self._buckets) >= _MAX_RATE_LIMIT_BUCKETS:
                    oldest = min(self._buckets, key=lambda key: self._buckets[key][-1])
                    del self._buckets[oldest]
            bucket = self._buckets.setdefault(peer, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                retry_after = max(1, math.ceil(self._window - (now - bucket[0])))
                raise error_for(
                    ErrorCode.AUTH_RATE_LIMITED,
                    "Too many authentication attempts",
                    details={"retry_after": retry_after},
                    retryable=True,
                )
            bucket.append(now)


def pepper_for(app: App) -> bytes:
    return app.gateways.get(TokenPepperSource).pepper()


def authenticate_session_cookie(app: App, cookie_secret: str) -> tuple[Actor, WebSession]:
    meta = RequestMeta("api-session-auth", Surface.API, None, app.clock.now())
    with app.uow_factory(meta, readonly=True) as uow:
        return authenticate_web_session(uow, cookie_secret, pepper=pepper_for(app), now=app.clock.now())


def _resolve_none_actor(app: App) -> Actor:
    meta = RequestMeta("api-none-auth", Surface.API, None, app.clock.now())
    with app.uow_factory(meta, readonly=True) as uow:
        return resolve_local_owner(uow)


def _extract_bearer(request: Request) -> str | None:
    values = request.headers.getlist("authorization")
    if not values:
        return None
    if len(values) != 1:
        raise error_for(ErrorCode.UNAUTHENTICATED, "send Authorization: Bearer <token>")
    parts = values[0].split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise error_for(ErrorCode.UNAUTHENTICATED, "send Authorization: Bearer <token>")
    return parts[1]


def request_auth_basis(request: Request) -> AuthBasis:
    """Return the unified ``AuthBasis`` attached by HTTP admission (fallback: ``request.state.actor``)."""
    basis = getattr(request.state, "auth_basis", None)
    if isinstance(basis, AuthBasis):
        return basis
    actor = getattr(request.state, "actor", None)
    if isinstance(actor, Actor):
        return AuthBasis.from_actor(actor)
    raise error_for(ErrorCode.UNAUTHENTICATED, "invalid or expired token")


def _active_quarantine_guard(app: App) -> RecoveryGuard | None:
    guard = getattr(app.bus, "guard", None)
    if isinstance(guard, RecoveryGuard) and guard.receipt() is None:
        return guard
    return None


def _require_quarantine_recovery_actor(guard: RecoveryGuard, basis: AuthBasis | None) -> None:
    expected = guard.expected_recovery_token_id()
    if (
        expected is None
        or basis is None
        or basis.kind is not AuthBasisKind.BEARER
        or basis.actor.grant is None
        or basis.actor.grant.kind != "personal"
        or basis.token_id != expected
    ):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "Operation is blocked by restore recovery; exact recovery token is required",
            details={"reason": "restore_recovery_token_required"},
        )


async def _authenticate_bearer_with_precedence(
    request: Request, app: App, bearer_secret: str
) -> tuple[Actor, WebSession | None]:
    bearer_actor = await run_in_threadpool(app.authenticate, bearer_secret)
    session: WebSession | None = None
    cookie_secret = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_secret:
        try:
            cookie_actor, session = await run_in_threadpool(authenticate_session_cookie, app, cookie_secret)
        except Unauthenticated:
            session = None
        else:
            if cookie_actor.principal_id != bearer_actor.principal_id:
                raise error_for(
                    ErrorCode.AMBIGUOUS_CREDENTIALS,
                    "Bearer token and session cookie belong to different principals",
                )
    return bearer_actor, session


async def authenticate(request: Request, app: App, web_auth: WebAuthConfig | None = None) -> None:
    method, path = request.method.upper(), request.scope["path"]
    if is_public(method, path):
        if (method, path) in PUBLIC_AUTH_ROUTES and request.headers.getlist("authorization"):
            bearer_secret = _extract_bearer(request)
            assert bearer_secret is not None  # noqa: S101 -- authorization header is non-empty
            bearer_actor, session = await _authenticate_bearer_with_precedence(request, app, bearer_secret)
            basis = AuthBasis.bearer(
                bearer_actor,
                session_id=None if session is None else session.id,
                session_expires_at=None if session is None else session.expires_at,
            )
            request.state.auth_basis = basis
            request.state.actor = basis.actor
            request.state.auth_method = basis.auth_method
            request.state.web_session = session
        return

    effective = web_auth if web_auth is not None else app.web_auth
    quarantine_guard = await run_in_threadpool(_active_quarantine_guard, app)
    bearer_secret = _extract_bearer(request)
    cookie_secret = request.cookies.get(SESSION_COOKIE_NAME)

    if bearer_secret is not None:
        bearer_actor, session = await _authenticate_bearer_with_precedence(request, app, bearer_secret)
        basis = AuthBasis.bearer(
            bearer_actor,
            session_id=None if session is None else session.id,
            session_expires_at=None if session is None else session.expires_at,
        )
        if quarantine_guard is not None:
            await run_in_threadpool(_require_quarantine_recovery_actor, quarantine_guard, basis)
        # Same-subject Bearer + cookie always keeps the Bearer permission ceiling.
        request.state.auth_basis = basis
        request.state.actor = basis.actor
        request.state.auth_method = basis.auth_method
        request.state.web_session = session
        return

    if quarantine_guard is not None:
        # While quarantine is active, neither web sessions nor 'none'-mode local_owner may substitute
        # for the exact recovery token_id issued by _rotate.
        await run_in_threadpool(_require_quarantine_recovery_actor, quarantine_guard, None)

    if cookie_secret:
        cookie_actor, session = await run_in_threadpool(authenticate_session_cookie, app, cookie_secret)
        if method not in _SAFE_METHODS:
            require_same_origin(request)
            require_csrf(request, pepper_for(app), subjects=(str(session.id),))
        basis = AuthBasis.session(cookie_actor, session_id=session.id, expires_at=session.expires_at)
        request.state.auth_basis = basis
        request.state.actor = basis.actor
        request.state.auth_method = basis.auth_method
        request.state.web_session = session
        return

    if effective.mode == "none":
        local_actor = await run_in_threadpool(_resolve_none_actor, app)
        basis = AuthBasis.local_owner(local_actor)
        request.state.auth_basis = basis
        request.state.actor = basis.actor
        request.state.auth_method = basis.auth_method
        request.state.web_session = None
        return

    raise error_for(ErrorCode.UNAUTHENTICATED, "send Authorization: Bearer <token>")
