"""``scope_of`` for access DTOs that name a scope by its id only (access §7.3, §7.5, §8)."""

from uuid import UUID

from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef

__all__ = ["scope_by_id"]


def scope_by_id(scope_id: UUID | None) -> ScopeRef | None:
    """Bus scope of a bare ``scope_id``; ``None`` is the instance scope.

    A DTO carries no scope kind, so the kind of the returned ref is provisional (``instance``): the bus
    resolves the chain by id, and the handlers read the stored kind from ``CommandContext.scope_chain`` or
    the registry, never from this ref.
    """
    return None if scope_id is None else ScopeRef(ScopeKind.INSTANCE, ScopeId(scope_id))
