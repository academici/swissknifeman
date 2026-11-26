"""``authenticate_token`` (access §13): a bearer secret -> the trusted ``Actor``.

Every failure -- malformed text, unknown prefix, wrong hash, revoked/expired token, disabled principal, a
credential whose scope vanished -- is one ``UNAUTHENTICATED`` with one message, so a caller learns nothing
about which part was wrong. The secret itself is never logged or put into an error.
"""

from datetime import datetime

from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, Unauthenticated, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.application.authz import UNAUTHENTICATED_MESSAGE
from skm.modules.access.domain.token import ensure_token_usable, grant_of, parse_secret, verify_secret
from skm.modules.access.ports import PrincipalRepository, TokenRepository

__all__ = ["authenticate_token"]


def _unauthenticated() -> Unauthenticated:
    return Unauthenticated(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE)


def authenticate_token(uow: UnitOfWork, secret_text: str, *, pepper: bytes, now: datetime) -> Actor:
    try:
        secret = parse_secret(secret_text)
    except ValidationFailed:
        raise _unauthenticated() from None
    token = uow.repo(TokenRepository).find_by_prefix(secret.prefix)
    if token is None or not verify_secret(secret, token, pepper):
        raise _unauthenticated()
    try:
        principal = uow.repo(PrincipalRepository).get(token.principal_id)
    except NotFound:
        raise _unauthenticated() from None
    ensure_token_usable(token, principal, now)  # the same UNAUTHENTICATED for every unusable credential
    ancestors: tuple[ScopeId, ...] = ()
    if token.scope_id is not None:
        try:
            chain = uow.repo(ScopeRegistry).ancestors(token.scope_id)
        except NotFound:
            raise _unauthenticated() from None
        ancestors = tuple(record.id for record in chain if record.id != token.scope_id)
    return Actor(
        principal_id=principal.id,
        kind=principal.kind,
        display_name=principal.display_name,
        grant=grant_of(token, scope_ancestors=ancestors),
    )
