"""Web session lifecycle and local-owner resolution inside the caller's UoW."""

import base64
import hmac
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, Unauthenticated, ValidationFailed
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application.authz import UNAUTHENTICATED_MESSAGE
from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.domain.session import WebSession
from skm.modules.access.ports import IdentityRepository, PrincipalRepository, WebSessionRepository

__all__ = [
    "SESSION_SECRET_PREFIX",
    "authenticate_web_session",
    "create_web_session",
    "resolve_local_owner",
    "revoke_all_web_sessions",
    "revoke_web_session",
]

SESSION_SECRET_PREFIX = "skm_sess_"
_SESSION_SECRET_RE = re.compile(r"^skm_sess_[A-Za-z0-9_-]{43}\Z")
_MIN_TTL_SECONDS = 60
_MAX_TTL_SECONDS = 2_592_000


def _unauthenticated() -> Unauthenticated:
    return Unauthenticated(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE)


def _hash(secret: str, pepper: bytes) -> bytes:
    return hmac.new(pepper, secret.encode("ascii"), sha256).digest()


def _generate_session_secret(entropy: Callable[[int], bytes]) -> str:
    raw = entropy(32)
    if len(raw) != 32:
        raise ValueError("entropy source must return 32 bytes")
    return SESSION_SECRET_PREFIX + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def create_web_session(
    uow: UnitOfWork,
    *,
    principal_id: PrincipalId,
    session_id: UUID,
    now: datetime,
    ttl_seconds: int,
    entropy: Callable[[int], bytes],
    pepper: bytes,
) -> tuple[WebSession, str]:
    """Create a new active human web session inside the caller's writable UoW."""
    if not _MIN_TTL_SECONDS <= ttl_seconds <= _MAX_TTL_SECONDS:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid web session TTL")
    principal = uow.repo(PrincipalRepository).get(principal_id)
    if principal.kind is not PrincipalKind.HUMAN or principal.state is not PrincipalState.ACTIVE:
        raise Forbidden(ErrorCode.FORBIDDEN, "web sessions require an active human principal")
    secret = _generate_session_secret(entropy)
    session = WebSession(
        id=session_id,
        principal_id=principal.id,
        secret_hash=_hash(secret, pepper),
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    uow.repo(WebSessionRepository).add(session)
    return session, secret


def authenticate_web_session(
    uow: UnitOfWork,
    secret_text: str,
    *,
    pepper: bytes,
    now: datetime,
) -> tuple[Actor, WebSession]:
    """Verify a session cookie secret against ``skm_access.web_sessions`` and the active human principal."""
    if _SESSION_SECRET_RE.fullmatch(secret_text) is None:
        raise _unauthenticated()
    digest = _hash(secret_text, pepper)
    session = uow.repo(WebSessionRepository).find_by_hash(digest)
    if session is None or not hmac.compare_digest(session.secret_hash, digest) or not session.is_active(now):
        raise _unauthenticated()
    try:
        principal = uow.repo(PrincipalRepository).get(session.principal_id)
    except NotFound:
        raise _unauthenticated() from None
    if principal.kind is not PrincipalKind.HUMAN or principal.state is not PrincipalState.ACTIVE:
        raise _unauthenticated()
    return Actor(principal.id, principal.kind, principal.display_name), session


def revoke_web_session(uow: UnitOfWork, session_id: UUID, *, now: datetime) -> bool:
    """Revoke one web session inside the caller's writable UoW."""
    return uow.repo(WebSessionRepository).revoke(session_id, now)


def revoke_all_web_sessions(uow: UnitOfWork, *, now: datetime) -> int:
    """Revoke every active web session inside the caller's writable UoW."""
    return uow.repo(WebSessionRepository).revoke_all(now)


def resolve_local_owner(uow: UnitOfWork) -> Actor:
    """Resolve the active local human owner from the database (used by loopback-only ``none`` mode)."""
    known = uow.repo(IdentityRepository).find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT)
    if known is None:
        raise _unauthenticated()
    try:
        principal = uow.repo(PrincipalRepository).get(known.principal_id)
    except NotFound:
        raise _unauthenticated() from None
    if principal.kind is not PrincipalKind.HUMAN or principal.state is not PrincipalState.ACTIVE:
        raise _unauthenticated()
    return Actor(principal.id, principal.kind, principal.display_name)
