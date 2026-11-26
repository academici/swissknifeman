"""Memberships: a principal's role in a scope (access §4.2, §5).

Rights only accumulate down the tree; granting is limited to what the granter holds, and the last active
owner of the instance can never be removed.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef

from .roles import ROLE_PERMISSIONS, WORKER_SCOPE_KINDS, Role

__all__ = ["Membership", "can_grant", "last_owner_guard"]

_MANAGE: Final = "membership.manage"
_OWNER_GRANT: Final = "principal.manage"
# Rights held by the worker role alone. No human role carries them, so they cannot be part of the "granter
# holds every right of the role" test for ``worker``; the scope-kind limit and ``membership.manage`` apply.
_WORKER_ONLY: Final = ROLE_PERMISSIONS[Role.WORKER].difference(
    *(permissions for role, permissions in ROLE_PERMISSIONS.items() if role is not Role.WORKER)
)


@dataclass(frozen=True, slots=True)
class Membership:
    scope_id: ScopeId
    principal_id: PrincipalId
    role: Role
    granted_by: PrincipalId | None
    granted_at: datetime

    def __post_init__(self) -> None:
        if self.granted_at.tzinfo is None or self.granted_at.utcoffset() is None:
            raise ValueError("granted_at must be timezone-aware")


def can_grant(granter_perms: frozenset[str], role: Role, target_kind: ScopeKind) -> bool:
    """No escalation: the granter manages memberships and holds every right of the granted role.

    ``granter_perms`` are the granter's effective permissions in the target scope (token ceiling included).
    ``owner`` is granted only by a holder of ``principal.manage``; ``worker`` only from workspace level down.
    """
    role = Role(role)
    if _MANAGE not in granter_perms:
        return False
    if role is Role.OWNER and _OWNER_GRANT not in granter_perms:
        return False
    if role is Role.WORKER and ScopeKind(target_kind) not in WORKER_SCOPE_KINDS:
        return False
    required = ROLE_PERMISSIONS[role] - _WORKER_ONLY if role is Role.WORKER else ROLE_PERMISSIONS[role]
    return required <= granter_perms


def last_owner_guard(scope: ScopeRef, owners_left: int) -> None:
    """After the operation at least one active owner must remain on the instance."""
    if scope.kind is ScopeKind.INSTANCE and owners_left < 1:
        raise PreconditionFailed(
            ErrorCode.LAST_OWNER_REQUIRED,
            "the last active owner of the instance cannot be removed",
            details={"scope_id": str(scope.id)},
        )
