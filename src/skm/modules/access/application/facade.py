"""Functions of ``access.public`` that run inside the caller's unit of work (access §13).

They write through the repositories of the caller's UoW and record events there, so the caller's commit makes
membership, principal and token changes atomic with its own state. Secrets reach the caller once as a return
value (``create_worker_principal``) or come in from the host (``issue_assignment_token``) and are stored only
as peppered hashes; no event, receipt or audit record gets a plaintext secret.
"""

import dataclasses
import hmac
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind, ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, uuid7
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.application import authz, events, tokens
from skm.modules.access.application.views import token_summary
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import disable as disabled_copy
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.domain.roles import HOST_WORKER_PERMISSIONS, ROLE_PERMISSIONS, Role
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenKind,
    TokenSecret,
    ensure_assignment_binding,
    ensure_token_usable,
    grant_of,
    new_assignment_token,
    revoke,
    token_expiry,
    token_is_usable,
    verify_secret,
)
from skm.modules.access.generated.settings import AccessSettings
from skm.modules.access.generated.views import TokenSummaryView
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenRepository

__all__ = [
    "create_worker_principal",
    "extend_assignment_tokens",
    "grant_initial_membership",
    "issue_assignment_token",
    "revoke_assignment_tokens",
    "revoke_principal_tokens",
]

_PAGE = 200
_RAND_A_BITS = 12
_RAND_B_BITS = 62


def _new_id(entropy: Callable[[int], bytes], now: datetime) -> UUID:
    """UUIDv7 from the supplied clock and entropy (the facade is called without an ``IdGenerator``)."""
    rand_a = int.from_bytes(entropy(2), "big") & ((1 << _RAND_A_BITS) - 1)
    rand_b = int.from_bytes(entropy(8), "big") & ((1 << _RAND_B_BITS) - 1)
    return uuid7(int(now.timestamp() * 1000), rand_a, rand_b)


def _assignment_token_id(secret: TokenSecret, pepper: bytes, now: datetime) -> TokenId:
    """The caller supplies no id source: derive a UUIDv7 from the public prefix under the pepper.

    The prefix is unique per token, so the id is too, and a repeated issue of the same secret finds its token
    by prefix before an id is needed. Nothing of the secret or its stored hash is exposed by the id.
    """
    digest = hmac.new(pepper, b"assignment-token-id:" + secret.prefix.encode("ascii"), sha256).digest()
    return TokenId(_new_id(lambda n: digest[:n] if n == 2 else digest[2 : 2 + n], now))


def _principal_tokens(
    uow: UnitOfWork, principal_id: PrincipalId, *, include_inactive: bool = False
) -> list[ApiToken]:
    repo = uow.repo(TokenRepository)
    found: list[ApiToken] = []
    after: str | None = None
    while True:
        page = repo.list_for(principal_id, include_inactive=include_inactive, after=after, limit=_PAGE)
        found.extend(page.items)
        if page.next is None:
            return found
        after = page.next


def revoke_principal_tokens(
    uow: UnitOfWork,
    principal_id: PrincipalId,
    *,
    by: PrincipalId,
    now: datetime,
    disable: bool,
    reason: str = "retired",
    include_expired: bool = False,
) -> int:
    """Revoke usable tokens and optionally expired tokens that still reserve their name."""
    repo = uow.repo(TokenRepository)
    revoked = 0
    for token in _principal_tokens(uow, principal_id, include_inactive=include_expired):
        if token.revoked_at is not None:
            continue
        current = repo.get_for_update(token.id)
        holds_name = include_expired and current.superseded_by is None
        if current.revoked_at is not None or (not holds_name and not token_is_usable(current, now)):
            continue
        updated = revoke(current, by, now)
        repo.save(updated)
        tokens.record_revoked(uow, updated, by)
        revoked += 1
    if disable:
        principals = uow.repo(PrincipalRepository)
        principal = principals.get(principal_id)
        changed = disabled_copy(principal)
        if changed is not principal:
            principals.save(changed, expected_version=principal.row_version)
            uow.record(events.PrincipalDisabled(principal_id=principal_id, reason=reason))
    return revoked


def grant_initial_membership(
    uow: UnitOfWork, *, scope_id: ScopeId, principal_id: PrincipalId, role: Role, now: datetime
) -> None:
    """The creator of a scope gets ``role`` without ``can_grant`` (its handler is already authorized)."""
    scope = uow.repo(ScopeRegistry).get(scope_id)
    memberships = uow.repo(MembershipRepository)
    previous = memberships.get(scope_id, principal_id)
    memberships.upsert(
        Membership(
            scope_id=scope_id, principal_id=principal_id, role=role, granted_by=principal_id, granted_at=now
        )
    )
    uow.record(
        events.MembershipGranted(
            scope_id=scope_id,
            principal_id=principal_id,
            role=role,
            previous_role=None if previous is None else previous.role,
            workspace_id=scope.workspace_id,
        )
    )


def create_worker_principal(  # noqa: PLR0913 -- signature fixed by access §13
    uow: UnitOfWork,
    *,
    display_name: str,
    workspace_scope_id: ScopeId,
    issuer: Actor,
    worker_id: UUID,
    host_scope_id: ScopeId | None = None,
    token_name: str,
    pepper: bytes,
    entropy: Callable[[int], bytes],
    now: datetime,
    settings: AccessSettings | None = None,
) -> tuple[PrincipalId, TokenId, str]:
    """A ``worker`` principal, its ``worker`` membership on the workspace and a ``worker`` token."""
    scope = uow.repo(ScopeRegistry).get(workspace_scope_id)
    if scope.kind is not ScopeKind.WORKSPACE:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "a worker is registered on a workspace",
            details={"field": "workspace_scope_id", "actual": scope.kind.value},
        )
    issuer = authz.ensure_live(uow, issuer, now)
    authz.require(uow, issuer, "worker.register", authz.chain_of(uow, workspace_scope_id))
    created_by = issuer.principal_id
    principal = new_principal(
        principal_id=PrincipalId(_new_id(entropy, now)),
        kind=PrincipalKind.WORKER,
        display_name=display_name,
        created_by=created_by,
        now=now,
    )
    uow.repo(PrincipalRepository).add(principal)
    uow.record(
        events.PrincipalCreated(
            principal_id=principal.id, kind=principal.kind, display_name=principal.display_name
        )
    )
    uow.repo(MembershipRepository).upsert(
        Membership(
            scope_id=workspace_scope_id,
            principal_id=principal.id,
            role=Role.WORKER,
            granted_by=created_by,
            granted_at=now,
        )
    )
    uow.record(
        events.MembershipGranted(
            scope_id=workspace_scope_id,
            principal_id=principal.id,
            role=Role.WORKER,
            previous_role=None,
            workspace_id=scope.workspace_id,
        )
    )
    token, secret = issue_bound_worker_token(
        uow,
        principal_id=principal.id,
        issuer=issuer,
        worker_id=worker_id,
        workspace_scope_id=workspace_scope_id,
        host_scope_id=host_scope_id,
        token_name=token_name,
        pepper=pepper,
        entropy=entropy,
        now=now,
        settings=settings,
    )
    return principal.id, token.id, secret


def issue_bound_worker_token(  # noqa: PLR0913 -- worker and credential bindings
    uow: UnitOfWork,
    *,
    principal_id: PrincipalId,
    issuer: Actor,
    worker_id: UUID,
    workspace_scope_id: ScopeId,
    host_scope_id: ScopeId | None,
    token_name: str,
    pepper: bytes,
    entropy: Callable[[int], bytes],
    now: datetime,
    settings: AccessSettings | None,
) -> tuple[ApiToken, str]:
    """The fixed worker grant for one registration, authorized in the caller's UoW."""
    issuer = authz.ensure_live(uow, issuer, now)
    authz.require(uow, issuer, "worker.register", authz.chain_of(uow, workspace_scope_id))
    member = uow.repo(MembershipRepository).get(workspace_scope_id, principal_id)
    if member is None or member.role is not Role.WORKER:
        raise Forbidden(ErrorCode.FORBIDDEN, "worker credential requires its workspace membership")
    grants = [ScopeGrant(workspace_scope_id, ROLE_PERMISSIONS[Role.WORKER])]
    if host_scope_id is not None:
        host = uow.repo(ScopeRegistry).get(host_scope_id)
        if host.kind is not ScopeKind.HOST:
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "worker credential requires a host scope")
        grants.append(ScopeGrant(host_scope_id, HOST_WORKER_PERMISSIONS))
    effective = settings if settings is not None else tokens.default_settings()
    expires_at = token_expiry(TokenKind.WORKER, None, now, effective)

    def build(secret: TokenSecret, digest: bytes) -> ApiToken:
        return ApiToken(
            id=TokenId(_new_id(entropy, now)),
            principal_id=principal_id,
            kind=TokenKind.WORKER,
            name=token_name,
            prefix=secret.prefix,
            secret_hash=digest,
            scope_id=None,
            permissions=None,
            scope_grants=tuple(grants),
            worker_id=worker_id,
            expires_at=expires_at,
            created_at=now,
            created_by=issuer.principal_id,
            last_used_at=None,
            revoked_at=None,
            revoked_by=None,
            assignment_id=None,
            step_id=None,
            superseded_by=None,
        )

    token, secret = tokens.add_with_fresh_secret(uow, entropy, pepper, build)
    tokens.record_created(uow, token)
    return token, str(secret)


def issue_assignment_token(  # noqa: PLR0913 -- signature fixed by access §13
    uow: UnitOfWork,
    *,
    worker: Actor,
    secret: TokenSecret,
    run_scope_id: ScopeId,
    assignment_id: UUID,
    step_id: UUID,
    expires_at: datetime,
    permissions: frozenset[str],
    pepper: bytes,
    now: datetime,
) -> TokenSummaryView:
    """Token of one runtime step: scope = the run, one secret per step, immutable binding (access §13)."""
    grant = worker.grant
    if worker.kind is not PrincipalKind.WORKER or grant is None or grant.kind != TokenKind.WORKER.value:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "assignment tokens are issued only from a worker token",
            details={"reason": "not_worker_token"},
        )
    repo = uow.repo(TokenRepository)
    parent = repo.get(TokenId(grant.token_id))
    principal = uow.repo(PrincipalRepository).get(worker.principal_id)
    ensure_token_usable(parent, principal, now)  # a dead worker credential issues nothing
    run_chain = uow.repo(ScopeRegistry).ancestors(run_scope_id)
    if run_chain[-1].kind is not ScopeKind.RUN:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "an assignment token is bound to a run scope",
            details={"field": "run_scope_id", "actual": run_chain[-1].kind.value},
        )
    worker = authz.ensure_live(uow, worker, now)
    authz.require(uow, worker, "worker.claim", run_chain)  # the run lies in the worker's own workspace
    existing = repo.find_by_prefix(secret.prefix)
    if existing is not None:
        if not verify_secret(secret, existing, pepper):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "token prefix collision",
                details={"kind": "token", "field": "prefix"},
            )
        ensure_assignment_binding(
            existing,
            principal_id=worker.principal_id,
            run_scope_id=run_scope_id,
            assignment_id=assignment_id,
            step_id=step_id,
        )
        if not token_is_usable(existing, now):  # revoked and expired tokens are never revived
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "the assignment token is no longer active",
                details={"reason": "token_not_active"},
            )
        return token_summary(existing, now)
    if any(other.step_id == step_id for other in repo.for_assignment(assignment_id)):
        raise Conflict(
            ErrorCode.ALREADY_EXISTS,
            "this assignment step already has an active token",
            details={"kind": "token", "field": "step_id"},
        )
    parent_grant = grant_of(parent)
    token = new_assignment_token(
        token_id=_assignment_token_id(secret, pepper, now),
        worker_token=parent_grant,
        worker_expires_at=parent.expires_at,
        principal_id=worker.principal_id,
        secret=secret,
        run_scope_id=run_scope_id,
        assignment_id=assignment_id,
        step_id=step_id,
        expires_at=expires_at,
        permissions=permissions & authz.effective(uow, worker, run_chain),
        now=now,
        pepper=pepper,
    )
    repo.add(token)
    tokens.record_created(uow, token)
    return token_summary(token, now)


def extend_assignment_tokens(
    uow: UnitOfWork, *, assignment_id: UUID, expires_at: datetime, now: datetime
) -> int:
    """Lengthen usable assignment tokens to ``expires_at``, never past their worker's token; no revival."""
    repo = uow.repo(TokenRepository)
    extended = 0
    for token in repo.for_assignment(assignment_id):
        if not token_is_usable(token, now):
            continue
        ceiling = _worker_expiry(uow, token.principal_id, now)
        wanted = expires_at if ceiling is None else min(expires_at, ceiling)
        if token.expires_at is None or wanted > token.expires_at:
            repo.save(dataclasses.replace(repo.get_for_update(token.id), expires_at=wanted))
            extended += 1
    return extended


def _worker_expiry(uow: UnitOfWork, principal_id: PrincipalId, now: datetime) -> datetime | None:
    """The latest expiry among the usable ``worker`` tokens of the principal; ``now`` when there is none."""
    expiries = [
        token.expires_at
        for token in _principal_tokens(uow, principal_id)
        if token.kind is TokenKind.WORKER and token_is_usable(token, now) and token.expires_at is not None
    ]
    return max(expiries) if expiries else now


def revoke_assignment_tokens(
    uow: UnitOfWork, *, assignment_id: UUID, by: PrincipalId, now: datetime, step_id: UUID | None = None
) -> int:
    """Revoke the tokens of an assignment, or only those bound to ``step_id``; a repeat revokes nothing."""
    repo = uow.repo(TokenRepository)
    revoked = 0
    for token in repo.for_assignment(assignment_id):
        if step_id is not None and token.step_id != step_id:
            continue
        updated = revoke(repo.get_for_update(token.id), by, now)
        repo.save(updated)
        tokens.record_revoked(uow, updated, by)
        revoked += 1
    return revoked
