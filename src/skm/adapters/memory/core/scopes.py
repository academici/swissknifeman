"""``ScopeRegistry`` and ``ScopeTree`` over the memory scope table (kernel-platform §2.10)."""

from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.pagination import validate_page_limit
from skm.kernel.scopes import (
    ScopeKind,
    ScopeRecord,
    check_scope_parent,
    check_scope_workspace,
    scope_not_found,
)
from skm.platform.config.scope_tree import RegistryScopeTree

__all__ = ["MemoryScopeRegistry", "MemoryScopeTree"]


class MemoryScopeRegistry:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core

    def create(
        self,
        scope_id: ScopeId,
        kind: ScopeKind,
        *,
        parent: ScopeId | None,
        workspace_id: WorkspaceId | None,
    ) -> None:
        self._core.require_writable()
        if scope_id in self._core.scopes:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "scope already exists", details={"kind": "scope"})
        parent_record = None if parent is None else self.get(parent)
        check_scope_parent(kind, parent_record)
        if kind is ScopeKind.INSTANCE and any(
            r.kind is ScopeKind.INSTANCE for r in self._core.scopes.values()
        ):
            raise Conflict(ErrorCode.ALREADY_EXISTS, "the instance scope exists", details={"kind": "scope"})
        check_scope_workspace(scope_id, kind, parent_record, workspace_id)
        self._core.scopes[scope_id] = ScopeRecord(
            id=scope_id,
            kind=kind,
            parent_id=parent,
            workspace_id=workspace_id,
            created_at=self._core.clock.now(),
        )

    def get(self, scope_id: ScopeId) -> ScopeRecord:
        record = self._core.scopes.get(scope_id)
        if record is None:
            raise scope_not_found()
        return record

    def list_scopes(self, *, after: ScopeId | None = None, limit: int = 100) -> tuple[ScopeRecord, ...]:
        limit = validate_page_limit(limit)
        if after is not None and not isinstance(after, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("scope inventory after must be UUID or None")
        ordered = sorted(scope_id for scope_id in self._core.scopes if after is None or scope_id > after)
        return tuple(self._core.scopes[scope_id] for scope_id in ordered[:limit])

    def ancestors(self, scope_id: ScopeId) -> tuple[ScopeRecord, ...]:
        chain: list[ScopeRecord] = []
        record: ScopeRecord | None = self.get(scope_id)
        while record is not None:
            chain.append(record)
            record = None if record.parent_id is None else self.get(record.parent_id)
        chain.reverse()
        return tuple(chain)

    def instance(self) -> ScopeRecord:
        for record in self._core.scopes.values():
            if record.kind is ScopeKind.INSTANCE:
                return record
        raise scope_not_found()


class MemoryScopeTree(RegistryScopeTree):
    """The config scope tree over the memory scope table."""

    def __init__(self, state: MemoryBackendState) -> None:
        super().__init__(MemoryScopeRegistry(state))
