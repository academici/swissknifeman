"""Deterministic seed of the memory backend: the instance scope, two workspaces and one principal.

The ids are fixed so that assertions and golden values do not depend on generation order. The seed is written
through a real unit of work, so it exercises ``ScopeRegistry.create`` like production code would.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRegistry

__all__ = ["Seed", "seed_backend"]

_RECEIVED = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Seed:
    instance_id: ScopeId
    workspace_id: WorkspaceId
    other_workspace_id: WorkspaceId
    principal_id: PrincipalId

    def actor(self, kind: PrincipalKind = PrincipalKind.HUMAN) -> Actor:
        return Actor(principal_id=self.principal_id, kind=kind, display_name="tester")


SEED = Seed(
    instance_id=ScopeId(UUID("01900000-0000-7000-8000-000000000001")),
    workspace_id=WorkspaceId(UUID("01900000-0000-7000-8000-0000000000a1")),
    other_workspace_id=WorkspaceId(UUID("01900000-0000-7000-8000-0000000000a2")),
    principal_id=PrincipalId(UUID("01900000-0000-7000-8000-0000000000b1")),
)


def seed_backend(uow_factory: UnitOfWorkFactory) -> Seed:
    """Create the instance scope and both workspace scopes in one committed unit of work."""
    meta = RequestMeta(
        request_id="req_SEED", surface=Surface.TEST, idempotency_key=None, received_at=_RECEIVED
    )
    with uow_factory(meta) as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(SEED.instance_id, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        for workspace_id in (SEED.workspace_id, SEED.other_workspace_id):
            scopes.create(
                ScopeId(workspace_id), ScopeKind.WORKSPACE, parent=SEED.instance_id, workspace_id=workspace_id
            )
        uow.commit()
    return SEED
