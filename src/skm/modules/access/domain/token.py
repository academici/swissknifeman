"""API tokens (access §4.2, §5; ``examples/access/token-format.md``).

Pure functions over immutable values: secret generation and parsing, the peppered HMAC, token lifetime,
rotation and revocation. Plaintext secrets live only in ``TokenSecret``; its ``repr`` hides the random part.
"""

import base64
import dataclasses
import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Final, NewType, Protocol, override
from uuid import UUID
from zlib import crc32

from skm.kernel.actor import PrincipalKind, ScopeGrant, TokenGrant, ordered_scope_grants
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, Unauthenticated, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId

from .principal import Principal, PrincipalState
from .roles import ASSIGNMENT_TOKEN_DENIED, ROLE_PERMISSIONS, Role

__all__ = [
    "ASSIGNMENT_PERMISSION_CEILING",
    "PEPPER_MIN_BYTES",
    "ApiToken",
    "TokenGrant",
    "TokenId",
    "TokenKind",
    "TokenLifetimeSettings",
    "TokenSecret",
    "TokenState",
    "assignment_token_name",
    "ensure_assignment_binding",
    "ensure_binding_unchanged",
    "ensure_not_revived",
    "ensure_token_usable",
    "generate_secret",
    "grant_of",
    "hash_secret",
    "new_assignment_token",
    "parse_secret",
    "revoke",
    "rotate",
    "rotation_due",
    "token_expiry",
    "token_is_usable",
    "token_kind_allowed",
    "token_state",
    "verify_secret",
]


class TokenKind(StrEnum):
    PERSONAL = "personal"
    WORKER = "worker"
    ASSIGNMENT = "assignment"


class TokenState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


TokenId = NewType("TokenId", UUID)

PEPPER_MIN_BYTES: Final = 32
# What an assignment token may ever carry: the worker role without the worker protocol (§4.2).
ASSIGNMENT_PERMISSION_CEILING: Final = ROLE_PERMISSIONS[Role.WORKER] - ASSIGNMENT_TOKEN_DENIED

_PREFIX_RE: Final = re.compile(r"(?:live_)?[a-z2-7]{8}")
_RANDOM_RE: Final = re.compile(r"[A-Za-z0-9_-]{43}")
_SECRET_RE: Final = re.compile(r"skm_((?:live_)?[a-z2-7]{8})_([A-Za-z0-9_-]{43})(?:_([0-9a-f]{8}))?")
_HASH_BYTES: Final = 32
_NAME_MAX: Final = 100
_UNAUTHENTICATED_MESSAGE: Final = "invalid or expired token"
_WORKER_KINDS: Final = frozenset({TokenKind.WORKER, TokenKind.ASSIGNMENT})


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True, repr=False)
class TokenSecret:
    """Plaintext legacy or CRC32-protected live secret for issuance and authentication."""

    prefix: str
    random: str

    def __post_init__(self) -> None:
        if not _PREFIX_RE.fullmatch(self.prefix) or not _RANDOM_RE.fullmatch(self.random):
            raise ValueError("malformed token secret parts")

    @override
    def __str__(self) -> str:
        body = f"skm_{self.prefix}_{self.random}"
        if self.prefix.startswith("live_"):
            return f"{body}_{crc32(body.encode('ascii')):08x}"
        return body

    @override
    def __repr__(self) -> str:
        return f"TokenSecret(prefix={self.prefix!r}, random=***)"


@dataclass(frozen=True, slots=True)
class ApiToken:
    id: TokenId
    principal_id: PrincipalId
    kind: TokenKind
    name: str
    prefix: str
    secret_hash: bytes
    scope_id: ScopeId | None
    permissions: frozenset[str] | None
    expires_at: datetime | None
    created_at: datetime
    created_by: PrincipalId
    last_used_at: datetime | None
    revoked_at: datetime | None
    revoked_by: PrincipalId | None
    assignment_id: UUID | None
    step_id: UUID | None
    superseded_by: TokenId | None
    scope_grants: tuple[ScopeGrant, ...] | None = None
    assignment_scope_id: ScopeId | None = None
    worker_id: UUID | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.name) <= _NAME_MAX:
            raise ValueError("token name must be 1..100 characters")
        if not _PREFIX_RE.fullmatch(self.prefix):
            raise ValueError("invalid legacy or live token prefix")
        if len(self.secret_hash) != _HASH_BYTES:
            raise ValueError("secret_hash must be a 32-byte HMAC-SHA256 digest")
        if self.permissions is not None and not isinstance(self.permissions, frozenset):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("ApiToken.permissions must be a frozenset or None")
        for field in ("expires_at", "created_at", "last_used_at", "revoked_at"):
            value: datetime | None = getattr(self, field)
            if value is not None:
                _require_aware(value, field)
        if self.kind in _WORKER_KINDS and self.expires_at is None:
            raise ValueError(f"a {self.kind.value} token needs expires_at")
        if (self.revoked_at is None) != (self.revoked_by is None):
            raise ValueError("revoked_at and revoked_by are set together")
        if self.superseded_by == self.id:
            raise ValueError("a token cannot supersede itself")
        if self.scope_grants is not None:
            if self.scope_id is not None or self.permissions is not None or self.kind is TokenKind.ASSIGNMENT:
                raise ValueError("paired grants require their own scope and permission fields")
            object.__setattr__(self, "scope_grants", ordered_scope_grants(self.scope_grants))
        if self.worker_id is not None and self.kind is not TokenKind.WORKER:
            raise ValueError("only worker credentials have a worker binding")
        self._validate_assignment_binding()

    def _validate_assignment_binding(self) -> None:
        if (self.kind is TokenKind.ASSIGNMENT) != (self.assignment_id is not None):
            raise ValueError("assignment_id is set exactly for an assignment token")
        if self.step_id is not None and self.kind is not TokenKind.ASSIGNMENT:
            raise ValueError("step_id is allowed only for an assignment token")
        if self.kind is not TokenKind.ASSIGNMENT and self.assignment_scope_id is not None:
            raise ValueError("only assignments have an assignment scope")
        if self.kind is TokenKind.ASSIGNMENT:
            if self.step_id is None or self.scope_id is None:
                raise ValueError("an assignment token needs step_id and scope_id")
            if self.assignment_scope_id not in (None, self.scope_id):
                raise ValueError("assignment scope must match the run scope")
            object.__setattr__(self, "assignment_scope_id", self.scope_id)
            if self.permissions is None or not self.permissions <= ASSIGNMENT_PERMISSION_CEILING:
                raise ValueError(
                    "assignment permissions must be a subset of the worker role without worker.claim"
                )


def token_kind_allowed(principal_kind: PrincipalKind, token_kind: TokenKind) -> bool:
    """A worker principal owns worker/assignment tokens; human and service principals only personal ones."""
    if principal_kind is PrincipalKind.WORKER:
        return token_kind in _WORKER_KINDS
    return token_kind is TokenKind.PERSONAL


def generate_secret(entropy: Callable[[int], bytes]) -> TokenSecret:
    prefix_bytes = entropy(5)
    random_bytes = entropy(32)
    if len(prefix_bytes) != 5 or len(random_bytes) != 32:
        raise ValueError("entropy source returned the wrong number of bytes")
    prefix = base64.b32encode(prefix_bytes).decode("ascii").lower()[:8]
    random = base64.urlsafe_b64encode(random_bytes).decode("ascii").rstrip("=")
    return TokenSecret(prefix=f"live_{prefix}", random=random)


def parse_secret(text: str) -> TokenSecret:
    match = _SECRET_RE.fullmatch(text) if isinstance(text, str) else None  # pyright: ignore[reportUnnecessaryIsInstance]
    if match is not None:
        secret = TokenSecret(prefix=match.group(1), random=match.group(2))
        if hmac.compare_digest(text, str(secret)):
            return secret
    # The surface turns this into UNAUTHENTICATED; the offending text is never echoed.
    raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "malformed token", details={"field": "token"})


def hash_secret(secret: TokenSecret, pepper: bytes) -> bytes:
    if len(pepper) < PEPPER_MIN_BYTES:
        raise ValueError("token pepper must be at least 32 bytes")
    return hmac.new(pepper, str(secret).encode("ascii"), sha256).digest()


def verify_secret(secret: TokenSecret, token: ApiToken, pepper: bytes) -> bool:
    return hmac.compare_digest(hash_secret(secret, pepper), token.secret_hash)


def token_is_usable(token: ApiToken, now: datetime) -> bool:
    _require_aware(now, "now")
    return token.revoked_at is None and (token.expires_at is None or token.expires_at > now)


def token_state(token: ApiToken, now: datetime) -> TokenState:
    _require_aware(now, "now")
    if token.revoked_at is not None:
        return TokenState.REVOKED
    if token.expires_at is not None and token.expires_at <= now:
        return TokenState.EXPIRED
    return TokenState.ACTIVE


def ensure_token_usable(token: ApiToken, principal: Principal, now: datetime) -> None:
    """Live credential check (§4.6): every unusable credential looks the same to the caller.

    Revoked, expired, foreign or owned by a disabled principal: one code, one message, no details.
    """
    if (
        principal.id != token.principal_id
        or principal.state is not PrincipalState.ACTIVE
        or not token_is_usable(token, now)
        or not token_kind_allowed(principal.kind, token.kind)
    ):
        raise Unauthenticated(ErrorCode.UNAUTHENTICATED, _UNAUTHENTICATED_MESSAGE)


def grant_of(token: ApiToken, *, scope_ancestors: tuple[ScopeId, ...] = ()) -> TokenGrant:
    """The narrowing an authenticated token puts into ``Actor.grant``."""
    return TokenGrant(
        token_id=token.id,
        kind=token.kind.value,
        scope_id=token.scope_id,
        permissions=token.permissions,
        assignment_id=token.assignment_id,
        step_id=token.step_id,
        scope_ancestors=scope_ancestors,
        scope_grants=token.scope_grants,
        assignment_scope_id=token.assignment_scope_id,
        worker_id=token.worker_id,
    )


def _fail_expiry(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "invalid token expiry",
        details={"field": "expires_at", "reason": reason},
    )


class _TokenTtls(Protocol):
    @property
    def default_ttl_days(self) -> int: ...
    @property
    def max_ttl_days(self) -> int: ...
    @property
    def worker_ttl_hours(self) -> int: ...
    @property
    def worker_rotate_before_hours(self) -> int: ...


class TokenLifetimeSettings(Protocol):
    """The part of ``AccessSettings`` the lifetime rules read (domain cannot import generated)."""

    @property
    def tokens(self) -> _TokenTtls: ...


def token_expiry(
    kind: TokenKind, requested: datetime | None, now: datetime, settings: TokenLifetimeSettings
) -> datetime | None:
    """Expiry of a new token; ``None`` means the token never expires (only personal tokens, ttl 0)."""
    _require_aware(now, "now")
    tokens = settings.tokens
    ceiling = now + timedelta(days=tokens.max_ttl_days) if tokens.max_ttl_days else None
    if kind is TokenKind.WORKER:
        expiry = now + timedelta(hours=tokens.worker_ttl_hours)
        return expiry if ceiling is None else min(expiry, ceiling)
    if requested is None:
        if kind is TokenKind.ASSIGNMENT:
            raise _fail_expiry("required")
        if tokens.default_ttl_days:
            expiry = now + timedelta(days=tokens.default_ttl_days)
            return expiry if ceiling is None else min(expiry, ceiling)
        if ceiling is not None:
            raise _fail_expiry("exceeds_max_ttl")
        return None
    _require_aware(requested, "expires_at")
    if requested <= now:
        raise _fail_expiry("not_in_future")
    if kind is TokenKind.PERSONAL and ceiling is not None and requested > ceiling:
        raise _fail_expiry("exceeds_max_ttl")
    return requested


def rotation_due(token: ApiToken, now: datetime, settings: TokenLifetimeSettings) -> bool:
    _require_aware(now, "now")
    if token.kind is not TokenKind.WORKER or token.expires_at is None:
        return False
    tokens = settings.tokens
    window = timedelta(hours=min(tokens.worker_rotate_before_hours, tokens.worker_ttl_hours / 2))
    return token.expires_at - now <= window


def revoke(token: ApiToken, by: PrincipalId, now: datetime) -> ApiToken:
    """Idempotent: an already revoked token is returned unchanged, keeping the first revocation."""
    _require_aware(now, "now")
    if token.revoked_at is not None:
        return token
    return dataclasses.replace(token, revoked_at=now, revoked_by=by)


def rotate(
    old: ApiToken,
    *,
    new_id: TokenId,
    new_secret_hash: bytes,
    new_prefix: str,
    now: datetime,
    settings: TokenLifetimeSettings,
    grace: timedelta,
    created_by: PrincipalId | None = None,
) -> tuple[ApiToken, ApiToken]:
    """Return ``(superseded old, new)``; the old token stays usable until ``now + grace`` at most.

    The new token keeps principal, kind, name, scope and permissions: rotation never widens a credential.
    ``created_by`` names the rotating principal; it defaults to the creator of the old token.
    """
    _require_aware(now, "now")
    if grace < timedelta(0):
        raise ValueError("grace must not be negative")
    if (
        old.kind is TokenKind.ASSIGNMENT
        or old.superseded_by is not None
        or not token_is_usable(old, now)
        or new_id == old.id
    ):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "token cannot be rotated",
            details={"reason": "token_not_rotatable"},
        )
    grace_end = now + grace
    old_expiry = grace_end if old.expires_at is None else min(old.expires_at, grace_end)
    superseded = dataclasses.replace(old, superseded_by=new_id, expires_at=old_expiry)
    successor = ApiToken(
        id=new_id,
        principal_id=old.principal_id,
        kind=old.kind,
        name=old.name,
        prefix=new_prefix,
        secret_hash=new_secret_hash,
        scope_id=old.scope_id,
        permissions=old.permissions,
        expires_at=token_expiry(old.kind, None, now, settings),
        created_at=now,
        created_by=old.created_by if created_by is None else created_by,
        last_used_at=None,
        revoked_at=None,
        revoked_by=None,
        assignment_id=None,
        step_id=None,
        superseded_by=None,
        scope_grants=old.scope_grants,
        worker_id=old.worker_id,
    )
    return superseded, successor


def assignment_token_name(assignment_id: UUID, step_id: UUID) -> str:
    return f"assignment-{assignment_id}-step-{step_id}"


def new_assignment_token(  # noqa: PLR0913 -- owner contract access §5, plus worker_expires_at
    *,
    token_id: TokenId,
    worker_token: TokenGrant,
    worker_expires_at: datetime | None,
    principal_id: PrincipalId,
    secret: TokenSecret,
    run_scope_id: ScopeId,
    assignment_id: UUID,
    step_id: UUID,
    expires_at: datetime,
    permissions: frozenset[str],
    now: datetime,
    pepper: bytes,
) -> ApiToken:
    """Token handed to the runtime of one step: scope = the run, a fresh secret per step, immutable binding.

    ``worker_token`` must be the issuing worker's own ``worker`` grant; an assignment or personal grant never
    issues tokens. The lifetime is capped by ``worker_expires_at`` (a grant does not carry it) and the
    permissions by the worker role, the issuing grant and ``ASSIGNMENT_TOKEN_DENIED``.
    """
    _require_aware(now, "now")
    _require_aware(expires_at, "expires_at")
    if worker_token.kind != TokenKind.WORKER.value:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "assignment tokens are issued only from a worker token",
            details={"reason": "not_worker_token"},
        )
    capped = expires_at if worker_expires_at is None else min(expires_at, worker_expires_at)
    if capped <= now:
        raise _fail_expiry("not_in_future")
    granted = frozenset(permissions) & ASSIGNMENT_PERMISSION_CEILING
    if worker_token.permissions is not None:
        granted &= worker_token.permissions
    return ApiToken(
        id=token_id,
        principal_id=principal_id,
        kind=TokenKind.ASSIGNMENT,
        name=assignment_token_name(assignment_id, step_id),
        prefix=secret.prefix,
        secret_hash=hash_secret(secret, pepper),
        scope_id=run_scope_id,
        permissions=granted,
        expires_at=capped,
        created_at=now,
        created_by=principal_id,
        last_used_at=None,
        revoked_at=None,
        revoked_by=None,
        assignment_id=assignment_id,
        step_id=step_id,
        superseded_by=None,
    )


def ensure_assignment_binding(
    existing: ApiToken,
    *,
    principal_id: PrincipalId,
    run_scope_id: ScopeId,
    assignment_id: UUID,
    step_id: UUID,
) -> None:
    """An old secret never moves to another principal, run, assignment or step (access §13)."""
    if (
        existing.kind is not TokenKind.ASSIGNMENT
        or existing.principal_id != principal_id
        or existing.scope_id != run_scope_id
        or existing.assignment_id != assignment_id
        or existing.step_id != step_id
    ):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "token is bound to another assignment step",
            details={"reason": "assignment_binding_mismatch"},
        )


def ensure_binding_unchanged(before: ApiToken, after: ApiToken) -> None:
    """Repository ``save`` guard: identity, ownership, secret and assignment binding never change in place."""
    if (
        before.id != after.id
        or before.principal_id != after.principal_id
        or before.kind is not after.kind
        or before.prefix != after.prefix
        or before.secret_hash != after.secret_hash
        or before.scope_id != after.scope_id
        or before.permissions != after.permissions
        or before.assignment_id != after.assignment_id
        or before.step_id != after.step_id
        or before.scope_grants != after.scope_grants
        or before.assignment_scope_id != after.assignment_scope_id
        or before.worker_id != after.worker_id
        or before.created_at != after.created_at
        or before.created_by != after.created_by
    ):
        raise ValueError(
            "an issued token keeps its identity, secret, scope, permissions and assignment binding"
        )


def ensure_not_revived(current: ApiToken, after: ApiToken, *, successor_exists: bool) -> None:
    """Store ``save`` guard: a revocation is kept as first written; a successor that exists is never replaced.

    A rotation that lost its successor insert to a prefix collision rewrites ``superseded_by`` with the next
    successor id in the same unit of work: only a successor that was really stored is final.
    """
    if current.revoked_at is not None and (
        after.revoked_at != current.revoked_at or after.revoked_by != current.revoked_by
    ):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "a revoked token stays revoked",
            details={"kind": "token", "reason": "token_revoked"},
        )
    if current.superseded_by not in (None, after.superseded_by) and successor_exists:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "a rotated token keeps its successor",
            details={"kind": "token", "reason": "token_superseded"},
        )
