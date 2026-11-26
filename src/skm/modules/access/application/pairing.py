"""Pairing credentials use the caller's transaction and store only an HMAC and immutable intent."""

import hmac
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind, ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, Unauthenticated, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind
from skm.modules.access.application import authz, delegation, tokens
from skm.modules.access.application.facade import revoke_principal_tokens
from skm.modules.access.domain.pairing import PairingResult, PairingToken
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenKind,
    TokenSecret,
    generate_secret,
    grant_of,
    token_expiry,
)
from skm.modules.access.generated.settings import AccessSettings
from skm.modules.access.ports import PairingRepository, PrincipalRepository, TokenRepository

_PAIR_SECRET = re.compile(r"skm_pair_[A-Za-z0-9_-]{43}")
_MAX_TTL = timedelta(hours=1)


def _denied() -> Unauthenticated:
    return Unauthenticated(ErrorCode.UNAUTHENTICATED, "invalid or expired pairing credential")


def _hash(secret: str, pepper: bytes) -> bytes:
    return hmac.new(pepper, secret.encode("ascii"), sha256).digest()


def _worker_grant(uow: UnitOfWork, issuer: Actor, workspace_id: WorkspaceId) -> None:
    chain = authz.chain_of(uow, ScopeId(workspace_id))
    if chain[-1].kind is not ScopeKind.WORKSPACE:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "pairing requires a workspace")
    authz.require(uow, issuer, "worker.register", chain)


def _personal_grant(
    uow: UnitOfWork, issuer: Actor, principal_id: PrincipalId, grants: tuple[ScopeGrant, ...]
) -> None:
    chain = authz.chain_of(uow, None)
    authz.require(uow, issuer, "token.own", chain)
    if principal_id != issuer.principal_id:
        authz.require(uow, issuer, "token.any", chain)
    principal = uow.repo(PrincipalRepository).get(principal_id)
    if principal.kind is PrincipalKind.WORKER or principal.state is not PrincipalState.ACTIVE:
        raise Forbidden(ErrorCode.FORBIDDEN, "pairing requires an active human or service principal")
    delegation.validate_scope_grants(uow, issuer, grants)


def issue_pairing_token(  # noqa: PLR0913 -- explicit issuer, binding and credential dependencies
    uow: UnitOfWork,
    *,
    issuer: Actor,
    workspace_id: WorkspaceId,
    pairing_id: UUID,
    now: datetime,
    expires_at: datetime,
    entropy: Callable[[int], bytes],
    pepper: bytes,
    worker_registration: JsonObject | None = None,
    principal_id: PrincipalId | None = None,
    scope_grants: tuple[ScopeGrant, ...] = (),
    replaces: UUID | None = None,
) -> str:
    """Issue a one-use secret for a worker registration or a human/service credential.

    The caller owns the UoW and returns the secret once after commit. A replacement names a consumed
    worker pairing and preserves that registration. The exchange revokes the prior credentials.
    """
    if not now < expires_at <= now + _MAX_TTL:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "pairing validity must be at most one hour")
    issuer = authz.ensure_live(uow, issuer, now)
    if authz.chain_of(uow, ScopeId(workspace_id))[-1].kind is not ScopeKind.WORKSPACE:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "pairing requires a workspace")
    if replaces is not None:
        _worker_grant(uow, issuer, workspace_id)
        prior = uow.repo(PairingRepository).get_for_update(replaces)
        if (
            prior is None
            or prior.workspace_id != workspace_id
            or prior.revoked_at is not None
            or prior.result is None
            or prior.result.worker_id is None
        ):
            raise NotFound(ErrorCode.NOT_FOUND, "worker pairing not found")
        if worker_registration is not None or principal_id is not None or scope_grants:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "replacement inherits its worker binding")
        binding: JsonObject = {"replaces": str(replaces)}
    elif worker_registration is not None:
        if principal_id is not None or scope_grants:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "worker pairing uses fixed grants")
        _worker_grant(uow, issuer, workspace_id)
        binding = {"worker": worker_registration}
    else:
        if principal_id is None or not scope_grants:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "personal pairing requires a principal and grants"
            )
        _personal_grant(uow, issuer, principal_id, scope_grants)
        binding = {
            "principal_id": str(principal_id),
            "scope_grants": {
                str(pair.scope_id): list[JsonValue](sorted(pair.permissions)) for pair in scope_grants
            },
        }
    secret = "skm_pair_" + generate_secret(entropy).random
    uow.repo(PairingRepository).add(
        PairingToken(
            id=pairing_id,
            issuer_id=issuer.principal_id,
            issuer_token_id=None if issuer.grant is None else TokenId(issuer.grant.token_id),
            workspace_id=workspace_id,
            secret_hash=_hash(secret, pepper),
            binding=binding,
            created_at=now,
            expires_at=expires_at,
        )
    )
    return secret


def lock_pairing_token(
    uow: UnitOfWork, pairing_id: UUID, secret: str, *, workspace_id: WorkspaceId, now: datetime, pepper: bytes
) -> tuple[PairingToken, Actor | None]:
    """Verify the proof and lock the pairing row until commit. Return a live issuer for new exchanges."""
    if _PAIR_SECRET.fullmatch(secret) is None:
        raise _denied()
    pairing = uow.repo(PairingRepository).get_for_update(pairing_id)
    if (
        pairing is None
        or pairing.workspace_id != workspace_id
        or pairing.revoked_at is not None
        or not hmac.compare_digest(pairing.secret_hash, _hash(secret, pepper))
    ):
        raise _denied()
    if pairing.result is not None:
        return pairing, None
    if pairing.expires_at <= now:
        raise _denied()
    try:
        principal = uow.repo(PrincipalRepository).get(pairing.issuer_id)
        token = (
            None
            if pairing.issuer_token_id is None
            else uow.repo(TokenRepository).get_for_update(pairing.issuer_token_id)
        )
    except NotFound:
        raise _denied() from None
    issuer = Actor(
        principal.id, principal.kind, principal.display_name, None if token is None else grant_of(token)
    )
    return pairing, authz.ensure_live(uow, issuer, now)


def prepare_worker_replacement(
    uow: UnitOfWork, pairing: PairingToken, issuer: Actor, now: datetime
) -> PairingResult:
    """Lock and revoke the prior pairing and its worker credentials in the exchange transaction."""
    _worker_grant(uow, issuer, pairing.workspace_id)
    repo = uow.repo(PairingRepository)
    prior = repo.get_for_update(UUID(cast("str", pairing.binding["replaces"])))
    if (
        prior is None
        or prior.workspace_id != pairing.workspace_id
        or prior.revoked_at is not None
        or prior.result is None
        or prior.result.worker_id is None
    ):
        raise _denied()
    repo.revoke(prior.id, now)
    revoke_principal_tokens(
        uow,
        prior.result.principal_id,
        by=issuer.principal_id,
        now=now,
        disable=False,
        include_expired=True,
    )
    return prior.result


def issue_paired_personal_token(
    uow: UnitOfWork,
    pairing: PairingToken,
    issuer: Actor,
    *,
    now: datetime,
    entropy: Callable[[int], bytes],
    pepper: bytes,
    token_id: TokenId,
    settings: AccessSettings,
) -> tuple[PairingResult, str]:
    """Recheck each stored pair and issue the human/service token in the exchange UoW."""
    principal_id = PrincipalId(UUID(cast("str", pairing.binding["principal_id"])))
    grants = tuple(
        ScopeGrant(ScopeId(UUID(scope)), frozenset(permissions))
        for scope, permissions in cast("dict[str, list[str]]", pairing.binding["scope_grants"]).items()
    )
    issuer = authz.ensure_live(uow, issuer, now)
    _personal_grant(uow, issuer, principal_id, grants)

    def build(secret: TokenSecret, digest: bytes) -> ApiToken:
        return ApiToken(
            id=token_id,
            principal_id=principal_id,
            kind=TokenKind.PERSONAL,
            name=f"pairing-{pairing.id}",
            prefix=secret.prefix,
            secret_hash=digest,
            scope_id=None,
            permissions=None,
            expires_at=token_expiry(TokenKind.PERSONAL, None, now, settings),
            created_at=now,
            created_by=issuer.principal_id,
            last_used_at=None,
            revoked_at=None,
            revoked_by=None,
            assignment_id=None,
            step_id=None,
            superseded_by=None,
            scope_grants=grants,
        )

    token, secret = tokens.add_with_fresh_secret(uow, entropy, pepper, build)
    tokens.record_created(uow, token)
    return PairingResult(principal_id, token.id, None), str(secret)


def consume_pairing_token(
    uow: UnitOfWork, pairing: PairingToken, result: PairingResult, now: datetime
) -> None:
    """Record only the exchange identifiers in the already locked pairing row."""
    uow.repo(PairingRepository).consume(pairing.id, result, now)


def revoke_all_pairing_tokens(uow: UnitOfWork, *, now: datetime) -> int:
    """Revoke every unrevoked pairing token inside the caller's writable UoW."""
    return uow.repo(PairingRepository).revoke_all(now)
