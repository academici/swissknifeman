"""Tables of ``skm_workspace`` in the memory backend state (workspace §11).

The tables live in ``MemoryBackendState.modules["workspace"]``; a unit of work works on a deep copy, so a
rollback drops them. The rows are the immutable domain values themselves.
"""

from dataclasses import dataclass, field
from typing import Final

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import HostId, ProjectId, RepositoryId, WorkerId, WorkspaceId
from skm.modules.workspace.domain.checkout_binding import CheckoutBinding, CheckoutBindingId
from skm.modules.workspace.domain.host import Host
from skm.modules.workspace.domain.mount import ProjectRepository
from skm.modules.workspace.domain.project import Project
from skm.modules.workspace.domain.repository import Repository, RepositoryRemote
from skm.modules.workspace.domain.worker import Worker
from skm.modules.workspace.domain.workspace import Workspace

__all__ = ["STATE_KEY", "MemoryWorkspaceState", "workspace_state"]

STATE_KEY: Final = "workspace"


@dataclass
class MemoryWorkspaceState:
    workspaces: dict[WorkspaceId, Workspace] = field(default_factory=dict[WorkspaceId, Workspace])
    projects: dict[ProjectId, Project] = field(default_factory=dict[ProjectId, Project])
    repositories: dict[RepositoryId, Repository] = field(default_factory=dict[RepositoryId, Repository])
    remotes: dict[RepositoryId, tuple[RepositoryRemote, ...]] = field(
        default_factory=dict[RepositoryId, tuple[RepositoryRemote, ...]]
    )
    mounts: dict[tuple[ProjectId, str], ProjectRepository] = field(
        default_factory=dict[tuple[ProjectId, str], ProjectRepository]
    )
    hosts: dict[HostId, Host] = field(default_factory=dict[HostId, Host])
    bindings: dict[CheckoutBindingId, CheckoutBinding] = field(
        default_factory=dict[CheckoutBindingId, CheckoutBinding]
    )
    workers: dict[WorkerId, Worker] = field(default_factory=dict[WorkerId, Worker])


def workspace_state(state: MemoryBackendState) -> MemoryWorkspaceState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryWorkspaceState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryWorkspaceState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "workspace memory state is malformed", details={"module": STATE_KEY}
        )
    return found
