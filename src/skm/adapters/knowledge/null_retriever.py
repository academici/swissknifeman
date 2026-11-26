"""Prove empty SKM memory exposure when the optional knowledge module is disabled."""

from typing import override

from skm.kernel.actor import Actor
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.context.domain.contracts import MemoryHit
from skm.modules.context.ports import MemoryRetriever

__all__ = ["NullMemoryRetriever"]


class NullMemoryRetriever(MemoryRetriever):
    @override
    def search(
        self,
        uow: UnitOfWork | None = None,
        *,
        actor: Actor | None = None,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        query: str,
        top_k: int,
    ) -> tuple[MemoryHit, ...]:
        return ()
