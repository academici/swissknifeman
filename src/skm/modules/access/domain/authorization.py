"""The authorization decision (access §4.4, K17): can this actor use a permission in a scope?

``decide`` is a pure function over values the authorizer has just read (principal, memberships on the scope
chain, host facts). It never reads storage and never trusts a request field: ``Actor.kind`` must agree
with the principal record, and ``SYSTEM_PERMISSIONS`` belong to the canonical system actor alone.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind, ScopeRef

from .membership import Membership
from .principal import Principal, PrincipalState
from .roles import (
    ASSIGNMENT_TOKEN_DENIED,
    HOST_MEMBER_PERMISSIONS,
    HOST_WORKER_PERMISSIONS,
    KNOWN_PERMISSIONS,
    MEMBER_CONFIG_LEVELS,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    SELF_PERMISSIONS,
    SYSTEM_PERMISSIONS,
    WORKER_SCOPE_KINDS,
    Role,
)

__all__ = [
    "Allowed",
    "AuthzDecision",
    "Denied",
    "DenyReason",
    "decide",
    "effective_permissions",
    "is_system_actor",
]

_ASSIGNMENT: Final = "assignment"
_READ_SUFFIX: Final = ".read"
_CONFIG_WRITE: Final = "config.write"


class DenyReason(StrEnum):
    PRINCIPAL_DISABLED = "principal_disabled"
    NO_MEMBERSHIP = "no_membership"
    PERMISSION_MISSING = "permission_missing"
    ROLE_LEVEL_RESTRICTED = "role_level_restricted"
    TOKEN_SCOPE_MISMATCH = "token_scope_mismatch"
    TOKEN_PERMISSION_MISSING = "token_permission_missing"
    SYSTEM_ONLY = "system_only"


@dataclass(frozen=True, slots=True)
class Allowed:
    """``details['via']`` is ``system``, ``self``, ``host_worker``, ``host_member`` or ``role``.

    For ``role``, ``via_role`` and ``via_scope`` name the granting membership."""

    details: JsonObject


@dataclass(frozen=True, slots=True)
class Denied:
    """``details`` always carries ``permission``, ``scope_id`` and ``scope_kind`` of the request."""

    reason: DenyReason
    details: JsonObject


type AuthzDecision = Allowed | Denied


def is_system_actor(actor: Actor) -> bool:
    """The canonical ``SYSTEM_ACTOR`` only: its id, kind ``service`` and no token (none is issued).

    Any other service principal, and any actor claiming the system id with another kind or a token, is not it.
    """
    return (
        actor.principal_id == SYSTEM_PRINCIPAL_ID
        and actor.kind is PrincipalKind.SERVICE
        and actor.grant is None
    )


def _deny(code: DenyReason, permission: str, target: ScopeRef, /, **extra: str) -> Denied:
    details: JsonObject = {
        "permission": permission,
        "scope_id": str(target.id),
        "scope_kind": target.kind.value,
    }
    details.update(extra)
    return Denied(code, details)


def _checked_chain(target_chain: Sequence[ScopeRef]) -> tuple[ScopeRef, ...]:
    chain = tuple(target_chain)
    if not chain or chain[0].kind is not ScopeKind.INSTANCE:
        raise ValueError("target_chain starts at the instance scope")
    return chain


def _pick(granted: frozenset[str], permission: str, target: ScopeRef, via: str) -> AuthzDecision:
    if permission in granted:
        return Allowed({"via": via, "via_scope": str(target.id)})
    return _deny(DenyReason.PERMISSION_MISSING, permission, target)


def _token_gate(actor: Actor, permission: str, chain: tuple[ScopeRef, ...]) -> Denied | None:
    """Rows 4a, 4b, 5 and 5a: what the authenticating token itself allows. ``None`` means "go on"."""
    grant = actor.grant
    if grant is None:
        return None
    target = chain[-1]
    chain_ids = {ref.id for ref in chain}
    if grant.scope_grants is not None:
        matching = [pair for pair in grant.scope_grants if pair.scope_id in chain_ids]
        # Self-management asks at instance level and still requires an explicit self permission.
        if permission in SELF_PERMISSIONS and target.kind is ScopeKind.INSTANCE:
            matching = list(grant.scope_grants)
        if not matching:
            return _deny(DenyReason.TOKEN_SCOPE_MISMATCH, permission, target)
        if not any(permission in pair.permissions for pair in matching):
            return _deny(DenyReason.TOKEN_PERMISSION_MISSING, permission, target)
        return None
    credential_scope = grant.assignment_scope_id if grant.kind == _ASSIGNMENT else grant.scope_id
    if credential_scope is not None and credential_scope not in chain_ids:
        # 4a: an assignment token may still read the ancestors of its run
        reads_run_ancestor = (
            grant.kind == _ASSIGNMENT
            and target.id in grant.scope_ancestors
            and permission.endswith(_READ_SUFFIX)
        )
        # 4b: otherwise the token acts only in its scope and below (own tokens stay manageable)
        if not reads_run_ancestor and permission not in SELF_PERMISSIONS:
            return _deny(DenyReason.TOKEN_SCOPE_MISMATCH, permission, target)
    if grant.permissions is not None and permission not in grant.permissions:  # 5
        return _deny(DenyReason.TOKEN_PERMISSION_MISSING, permission, target)
    if grant.kind == _ASSIGNMENT and permission in ASSIGNMENT_TOKEN_DENIED:  # 5a
        return _deny(DenyReason.TOKEN_PERMISSION_MISSING, permission, target)
    return None


def _without_membership(
    permission: str,
    target: ScopeRef,
    principal: Principal,
    worker_host_ids: frozenset[ScopeId],
    has_workspace_membership: bool,
) -> AuthzDecision:
    """Rows 6a, 6b and 6: no membership on the chain; only a host scope can still grant something."""
    if target.kind is ScopeKind.HOST:
        if principal.kind is PrincipalKind.WORKER and target.id in worker_host_ids:
            return _pick(
                HOST_WORKER_PERMISSIONS & ROLE_PERMISSIONS[Role.WORKER], permission, target, "host_worker"
            )
        if principal.kind is not PrincipalKind.WORKER and has_workspace_membership:
            return _pick(HOST_MEMBER_PERMISSIONS, permission, target, "host_member")
    return _deny(DenyReason.NO_MEMBERSHIP, permission, target)


def _usable_permissions(role: Role, membership_scope: ScopeRef, target: ScopeRef) -> frozenset[str]:
    """Permissions of one membership after the level restrictions of access §4.3."""
    permissions = ROLE_PERMISSIONS[role]
    if role is Role.WORKER and membership_scope.kind not in WORKER_SCOPE_KINDS:
        return frozenset()
    if role is Role.MEMBER and target.kind not in MEMBER_CONFIG_LEVELS:
        return permissions - {_CONFIG_WRITE}
    return permissions


def _by_role(
    permission: str, chain: tuple[ScopeRef, ...], by_id: dict[ScopeId, int], relevant: list[Membership]
) -> AuthzDecision:
    """Rows 7-9: union of the roles on the chain; the highest rank, then the deepest scope, is cited."""
    target = chain[-1]
    best: tuple[tuple[int, int], Membership] | None = None
    restricted = False
    for membership in relevant:
        role = Role(membership.role)
        index = by_id[membership.scope_id]
        if permission in _usable_permissions(role, chain[index], target):
            rank = (ROLE_RANK[role], index)
            if best is None or rank > best[0]:
                best = (rank, membership)
        elif permission in ROLE_PERMISSIONS[role]:
            restricted = True
    if best is not None:
        granting = best[1]
        return Allowed(
            {"via": "role", "via_role": Role(granting.role).value, "via_scope": str(granting.scope_id)}
        )
    if restricted:
        return _deny(DenyReason.ROLE_LEVEL_RESTRICTED, permission, target)
    return _deny(DenyReason.PERMISSION_MISSING, permission, target)


def decide(
    actor: Actor,
    permission: str,
    target_chain: Sequence[ScopeRef],
    principal: Principal,
    memberships: Iterable[Membership],
    *,
    worker_host_ids: frozenset[ScopeId] = frozenset(),
    has_workspace_membership: bool = False,
) -> AuthzDecision:
    """Table access §4.4 in order; ``target_chain`` is ``[instance, ..., target]`` (``[instance, host:H]``).

    ``memberships`` may be broader than needed: only the principal's own memberships on the chain count.
    """
    chain = _checked_chain(target_chain)
    target = chain[-1]

    # 1-2: system permissions belong to the canonical system actor alone
    if permission in SYSTEM_PERMISSIONS:
        if is_system_actor(actor):
            return Allowed({"via": "system"})
        return _deny(DenyReason.SYSTEM_ONLY, permission, target)

    # The Actor must be the principal record read for this request (ACCESS-01): kind comes from the record.
    if actor.principal_id != principal.id or actor.kind is not principal.kind:
        return _deny(DenyReason.PERMISSION_MISSING, permission, target, reason="actor_principal_mismatch")

    if principal.state is PrincipalState.DISABLED:  # 3
        return _deny(DenyReason.PRINCIPAL_DISABLED, permission, target)

    denied = _token_gate(actor, permission, chain)
    if denied is not None:
        return denied

    # 5c: own tokens need no membership (the handler checks ownership of the concrete token)
    if permission in SELF_PERMISSIONS:
        return Allowed({"via": "self"})

    by_id = {ref.id: index for index, ref in enumerate(chain)}
    relevant = [m for m in memberships if m.principal_id == principal.id and m.scope_id in by_id]
    if not relevant:
        return _without_membership(permission, target, principal, worker_host_ids, has_workspace_membership)
    return _by_role(permission, chain, by_id, relevant)


def effective_permissions(
    actor: Actor,
    target_chain: Sequence[ScopeRef],
    principal: Principal,
    memberships: Iterable[Membership],
    *,
    worker_host_ids: frozenset[ScopeId] = frozenset(),
    has_workspace_membership: bool = False,
) -> frozenset[str]:
    """Every catalogue permission ``decide`` allows for this actor in the target scope (token ceiling too)."""
    chain = _checked_chain(target_chain)
    held = tuple(memberships)
    return frozenset(
        permission
        for permission in KNOWN_PERMISSIONS
        if isinstance(
            decide(
                actor,
                permission,
                chain,
                principal,
                held,
                worker_host_ids=worker_host_ids,
                has_workspace_membership=has_workspace_membership,
            ),
            Allowed,
        )
    )
