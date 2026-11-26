"""Rights of an actor inside a command's unit of work (access §4.4-§4.6).

The handlers that act on credentials and memberships must not trust the bus decision alone: ``token.own`` is
a self right, the owner of the concrete token is checked here, and delegation (create/rotate) is
bounded by the *current* ``TokenGrant`` of the caller. ``decision`` reads the principal, the
memberships on the target chain and the host facts afresh from the repositories of the unit of work and
applies the pure ``decide`` table; an ``Actor`` is never a cache of rights. ``RbacAuthorizer``
builds on the same function.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, InternalError, NotFound, Unauthenticated
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef, ScopeRegistry
from skm.modules.access.domain.authorization import (
    Allowed,
    AuthzDecision,
    Denied,
    DenyReason,
    decide,
    effective_permissions,
)
from skm.modules.access.domain.principal import Principal, PrincipalState
from skm.modules.access.domain.roles import SYSTEM_PERMISSIONS, Role
from skm.modules.access.domain.token import TokenId, ensure_token_usable, grant_of
from skm.modules.access.ports import (
    MembershipRepository,
    PrincipalRepository,
    TokenRepository,
    WorkerHostLookup,
)

__all__ = [
    "BUS_REASON",
    "chain_of",
    "decision",
    "effective",
    "ensure_live",
    "is_instance_owner",
    "refuse",
    "require",
    "workspace_id_of",
]

UNAUTHENTICATED_MESSAGE: Final = "invalid or expired token"
# reason_code vocabulary of ``application_bus.ports.AuthzDecision`` for each domain reason
BUS_REASON: Final = {
    DenyReason.PRINCIPAL_DISABLED: "PRINCIPAL_DISABLED",
    DenyReason.NO_MEMBERSHIP: "NO_MEMBERSHIP",
    DenyReason.PERMISSION_MISSING: "ROLE_LACKS_PERMISSION",
    DenyReason.ROLE_LEVEL_RESTRICTED: "ROLE_LACKS_PERMISSION",
    DenyReason.SYSTEM_ONLY: "ROLE_LACKS_PERMISSION",
    DenyReason.TOKEN_SCOPE_MISMATCH: "TOKEN_SCOPE",
    DenyReason.TOKEN_PERMISSION_MISSING: "TOKEN_NARROWED",
}


def chain_of(uow: UnitOfWork, scope_id: ScopeId | None) -> tuple[ScopeRecord, ...]:
    """Scope records from the instance to ``scope_id`` (``None`` is the instance); ``NotFound`` if unknown."""
    scopes = uow.repo(ScopeRegistry)
    return (scopes.instance(),) if scope_id is None else scopes.ancestors(scope_id)


def workspace_id_of(chain: Sequence[ScopeRecord]) -> WorkspaceId | None:
    """Workspace the last scope of ``chain`` belongs to; ``None`` for instance and host scopes."""
    return next((record.workspace_id for record in reversed(chain) if record.workspace_id is not None), None)


def _principal(uow: UnitOfWork, actor: Actor, permission: str | None = None) -> Principal:
    """The principal record of ``actor``, read now.

    An actor without a record is no actor (``UNAUTHENTICATED``). The one exception is a system permission:
    rows 1-2 of the table decide it from the actor alone, so the instance can be initialised by
    ``SYSTEM_ACTOR`` before the ``system`` principal row exists; the record then stands in for rows that
    never read it.
    """
    try:
        return uow.repo(PrincipalRepository).get(actor.principal_id)
    except NotFound:
        if permission in SYSTEM_PERMISSIONS:
            return Principal(
                id=actor.principal_id,
                kind=actor.kind,
                display_name=actor.display_name,
                state=PrincipalState.ACTIVE,
                row_version=1,
                created_at=datetime.fromtimestamp(0, tz=UTC),
                created_by=None,
            )
        raise Unauthenticated(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE) from None


def _worker_hosts(uow: UnitOfWork, actor: Actor, target: ScopeRecord) -> frozenset[ScopeId]:
    if actor.kind is not PrincipalKind.WORKER or target.kind is not ScopeKind.HOST:
        return frozenset()
    try:
        return uow.repo(WorkerHostLookup).host_ids(actor.principal_id)
    except InternalError:  # no workspace adapter registered yet (access §6): an empty set
        return frozenset()


def decision(
    uow: UnitOfWork,
    actor: Actor,
    permission: str,
    chain: Sequence[ScopeRecord],
    *,
    principal: Principal | None = None,
) -> AuthzDecision:
    """``decide`` over facts read now: principal, own memberships on the chain, host facts of row 6a/6b.

    ``principal`` is the record of ``actor`` the caller already read in this unit of work, if any.
    """
    refs = tuple(ScopeRef(record.kind, record.id) for record in chain)
    if principal is None or principal.id != actor.principal_id:
        principal = _principal(uow, actor, permission)
    memberships = uow.repo(MembershipRepository)
    target = chain[-1]
    return decide(
        actor,
        permission,
        refs,
        principal,
        memberships.for_principal(principal.id, [record.id for record in chain]),
        worker_host_ids=_worker_hosts(uow, actor, target),
        has_workspace_membership=(
            target.kind is ScopeKind.HOST
            and actor.kind is not PrincipalKind.WORKER
            and memberships.has_workspace_membership(principal.id)
        ),
    )


def effective(uow: UnitOfWork, actor: Actor, chain: Sequence[ScopeRecord]) -> frozenset[str]:
    """Every permission ``decision`` allows for ``actor`` on the target of ``chain`` (grant ceiling too)."""
    refs = tuple(ScopeRef(record.kind, record.id) for record in chain)
    principal = _principal(uow, actor)
    memberships = uow.repo(MembershipRepository)
    target = chain[-1]
    return effective_permissions(
        actor,
        refs,
        principal,
        memberships.for_principal(principal.id, [record.id for record in chain]),
        worker_host_ids=_worker_hosts(uow, actor, target),
        has_workspace_membership=(
            target.kind is ScopeKind.HOST
            and actor.kind is not PrincipalKind.WORKER
            and memberships.has_workspace_membership(principal.id)
        ),
    )


def refuse(permission: str, chain: Sequence[ScopeRecord], denied: Denied) -> Forbidden:
    """``FORBIDDEN`` of a denied decision: ``reason`` is the access reason, ``reason_code`` the audit one."""
    details: JsonObject = {
        "permission": permission,
        "scope_id": str(chain[-1].id),
        "reason": denied.reason.value,
        "reason_code": BUS_REASON[denied.reason],
    }
    return Forbidden(ErrorCode.FORBIDDEN, f"this operation requires {permission}", details=details)


def require(uow: UnitOfWork, actor: Actor, permission: str, chain: Sequence[ScopeRecord]) -> None:
    """``FORBIDDEN`` unless ``actor`` holds ``permission`` on the target of ``chain`` right now."""
    result = decision(uow, actor, permission, chain)
    if isinstance(result, Allowed):
        return
    assert isinstance(result, Denied)  # noqa: S101 -- AuthzDecision is Allowed | Denied
    raise refuse(permission, chain, result)


def ensure_live(uow: UnitOfWork, actor: Actor, now: datetime) -> Actor:
    """Access §4.6: the principal is active and the authenticating token row is still usable.

    Revoked, expired, foreign or disabled-owner credentials are all ``UNAUTHENTICATED``.
    """
    principal = _principal(uow, actor)
    if actor.kind is not principal.kind:
        raise Unauthenticated(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE)
    if actor.grant is None:
        if principal.state is not PrincipalState.ACTIVE:
            raise Unauthenticated(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE)
        return actor
    try:
        token = uow.repo(TokenRepository).get(TokenId(actor.grant.token_id))
    except NotFound:
        raise Unauthenticated(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE) from None
    ensure_token_usable(token, principal, now)
    return replace(actor, grant=grant_of(token, scope_ancestors=actor.grant.scope_ancestors))


def is_instance_owner(uow: UnitOfWork, actor: Actor) -> bool:
    """The actor holds the ``owner`` role on the instance itself (access §4.3 ``NON_GRANTABLE_BY_TOKEN``)."""
    instance = uow.repo(ScopeRegistry).instance()
    membership = uow.repo(MembershipRepository).get(instance.id, actor.principal_id)
    return membership is not None and membership.role is Role.OWNER
