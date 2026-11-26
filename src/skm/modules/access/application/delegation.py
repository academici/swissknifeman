"""Permission ceilings for personal credentials (access §4.5).

``token.own`` lets a principal manage its own credentials, but not step outside the credential in hand. The
caller's *current* ``TokenGrant`` bounds the scope and the permissions of every token it creates or rotates;
live roles further narrow every permission. A missing scope denotes the instance.
"""

from collections.abc import Sequence

from skm.kernel.actor import Actor, ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRecord, ScopeRegistry
from skm.modules.access.application import authz
from skm.modules.access.domain.authorization import Denied, DenyReason
from skm.modules.access.domain.roles import KNOWN_PERMISSIONS, NON_GRANTABLE_BY_TOKEN
from skm.modules.access.domain.token import ApiToken

__all__ = [
    "ensure_scope_within_grant",
    "grant_permissions",
    "personal_rotation_permissions",
    "scope_within",
    "validate_scope_grants",
]


def scope_within(uow: UnitOfWork, ceiling: ScopeId, scope_id: ScopeId | None) -> bool:
    """Whether the scope is the ceiling or falls below it. A missing scope means the instance."""
    if scope_id is None:
        return uow.repo(ScopeRegistry).instance().id == ceiling
    try:
        chain: Sequence[ScopeRecord] = uow.repo(ScopeRegistry).ancestors(scope_id)
    except NotFound:
        return False
    return any(record.id == ceiling for record in chain)


def _refusal(reason: DenyReason, permission: str, **extra: str) -> Forbidden:
    details: JsonObject = {
        "permission": permission,
        "reason": reason.value,
        "reason_code": authz.BUS_REASON[reason],
    }
    details.update(extra)
    return Forbidden(
        ErrorCode.FORBIDDEN, "a token cannot exceed the credential that manages it", details=details
    )


def ensure_scope_within_grant(uow: UnitOfWork, actor: Actor, scope_id: ScopeId | None) -> None:
    """``FORBIDDEN(token_scope_mismatch)`` unless the scope lies inside the scope of ``actor.grant``."""
    grant = actor.grant
    if grant is None:
        return
    if grant.scope_grants is not None:
        if not any(scope_within(uow, pair.scope_id, scope_id) for pair in grant.scope_grants):
            raise _refusal(DenyReason.TOKEN_SCOPE_MISMATCH, "token.own")
        return
    if grant.scope_id is None:
        return
    if not scope_within(uow, grant.scope_id, scope_id):
        raise _refusal(DenyReason.TOKEN_SCOPE_MISMATCH, "token.own", scope_id=str(grant.scope_id))


def personal_rotation_permissions(uow: UnitOfWork, actor: Actor, target: ApiToken) -> frozenset[str] | None:
    """Check every issued grant against the rotating actor's live scope and permissions."""
    if target.scope_grants is not None:
        validate_scope_grants(uow, actor, target.scope_grants)
        return None

    ensure_scope_within_grant(uow, actor, target.scope_id)
    grant = actor.grant
    if (
        target.permissions is None
        and grant is not None
        and grant.token_id != target.id
        and grant.permissions is not None
    ):
        # A limited single-scope credential cannot rotate an unrestricted legacy token.
        raise _refusal(DenyReason.TOKEN_PERMISSION_MISSING, "token.own")
    return grant_permissions(uow, actor, authz.chain_of(uow, target.scope_id), target.permissions)


def grant_permissions(
    uow: UnitOfWork,
    actor: Actor,
    chain: tuple[ScopeRecord, ...],
    requested: frozenset[str] | None,
) -> frozenset[str]:
    """Freeze explicit or default permissions under the live role and credential ceilings."""
    owner = authz.is_instance_owner(uow, actor)
    if requested is None:
        held = frozenset(
            p for p in authz.effective(uow, actor, chain) if allows_delegation(uow, actor, p, chain[-1].id)
        )
        return held if owner else held - NON_GRANTABLE_BY_TOKEN
    unknown = requested - KNOWN_PERMISSIONS
    if unknown:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "unknown permission",
            details={"field": "permissions", "reason": "unknown_permission", "permission": min(unknown)},
        )
    for permission in sorted(requested):
        if permission in NON_GRANTABLE_BY_TOKEN and not owner:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                f"{permission} cannot be placed into a token by this principal",
                details={"permission": permission, "reason": "not_grantable_by_token"},
            )
        if not allows_delegation(uow, actor, permission, chain[-1].id):
            raise _refusal(DenyReason.TOKEN_PERMISSION_MISSING, permission)
        verdict = authz.decision(uow, actor, permission, chain)
        if isinstance(verdict, Denied):
            raise authz.refuse(permission, chain, verdict)
    return requested


def validate_scope_grants(
    uow: UnitOfWork, actor: Actor, grants: tuple[ScopeGrant, ...]
) -> tuple[ScopeGrant, ...]:
    """Check every pair against the issuer at its own scope."""
    if len({pair.scope_id for pair in grants}) != len(grants):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "scope grants repeat a scope")
    for pair in grants:
        chain = authz.chain_of(uow, pair.scope_id)
        ensure_scope_within_grant(uow, actor, pair.scope_id)
        grant_permissions(uow, actor, chain, pair.permissions)
    return grants


def allows_delegation(uow: UnitOfWork, actor: Actor, permission: str, scope_id: ScopeId) -> bool:
    """Require the matching credential pair for delegation, including self permissions."""
    grant = actor.grant
    if grant is None or grant.scope_grants is None:
        return True
    return any(
        permission in pair.permissions and scope_within(uow, pair.scope_id, scope_id)
        for pair in grant.scope_grants
    )
