"""First local owner password and password verification inside the caller's UoW."""

import hmac
from collections.abc import Callable
from hashlib import scrypt

from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Unauthenticated, ValidationFailed
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.ports import IdentityRepository, PrincipalRepository

_SALT_SIZE = 16
_MAX_LENGTH = 1024
_MIN_LENGTH = 12


def _derive(password: str, salt: bytes) -> bytes:
    return scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8, p=1, maxmem=256 * 1024**2, dklen=32)


def set_first_password(
    uow: UnitOfWork, principal_id: PrincipalId, password: str | None, entropy: Callable[[int], bytes]
) -> None:
    principals = uow.repo(PrincipalRepository)
    if password is None or principals.password_hash(principal_id) is not None:
        return
    if not _MIN_LENGTH <= len(password) <= _MAX_LENGTH:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid first admin password length")
    salt = entropy(_SALT_SIZE)
    principals.set_first_password(principal_id, salt + _derive(password, salt))


def authenticate_local_owner_password(uow: UnitOfWork, password: str) -> Actor:
    """Verify the local owner's password and return its current active principal."""
    denied = Unauthenticated(ErrorCode.UNAUTHENTICATED, "invalid credentials")
    if not _MIN_LENGTH <= len(password) <= _MAX_LENGTH:
        raise denied
    known = uow.repo(IdentityRepository).find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT)
    principals = uow.repo(PrincipalRepository)
    digest = None if known is None else principals.password_hash(known.principal_id)
    salt = bytes(_SALT_SIZE) if digest is None else digest[:_SALT_SIZE]
    try:
        derived = _derive(password, salt)
    except UnicodeEncodeError:
        raise denied from None
    if known is None or digest is None or not hmac.compare_digest(digest[_SALT_SIZE:], derived):
        raise denied
    principal = principals.get(known.principal_id)
    if principal.state is not PrincipalState.ACTIVE:
        raise denied
    return Actor(principal.id, principal.kind, principal.display_name)
