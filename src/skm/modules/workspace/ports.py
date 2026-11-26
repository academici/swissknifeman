"""Repository ports of the workspace module (workspace §6) and the host gateway ``RepositoryInspector``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from skm.kernel.gateways import host_gateway
from skm.kernel.ports_uow import repository_port

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import HostId, PrincipalId, ProjectId, RepositoryId, WorkerId, WorkspaceId
    from skm.kernel.pagination import Page

    from .domain.attach import RepositoryMatchView
    from .domain.checkout_binding import CheckoutBinding, CheckoutBindingId, ObservedCheckout
    from .domain.checkout_marker import CheckoutMarker
    from .domain.host import Host, HostState
    from .domain.mount import MountName
    from .domain.mount import ProjectRepository as ProjectMount
    from .domain.project import Project, ProjectState
    from .domain.remote_url import NormalizedRemote
    from .domain.repository import Repository, RepositoryRemote
    from .domain.slug import Slug
    from .domain.worker import Worker, WorkerCapabilities, WorkerState
    from .domain.workspace import Workspace, WorkspaceState

__all__ = [
    "MARKER_INVALID",
    "CheckoutBindingRepository",
    "HostRepository",
    "MountRepository",
    "ProjectRepository",
    "RepositoryInspector",
    "RepositoryRepository",
    "WorkerRepository",
    "WorkspaceRepository",
]

MARKER_INVALID = "MARKER_INVALID"


@repository_port
class WorkspaceRepository(Protocol):
    def get(self, workspace_id: WorkspaceId) -> Workspace: ...
    def find_by_slug(self, slug: Slug) -> Workspace | None: ...
    def add(self, workspace: Workspace) -> None: ...  # ALREADY_EXISTS (slug)
    def save(self, workspace: Workspace, *, expected_version: int) -> None: ...
    def list(self, *, state: WorkspaceState | None, after: str | None, limit: int) -> Page[Workspace]: ...


@repository_port
class ProjectRepository(Protocol):
    def get(self, project_id: ProjectId) -> Project: ...
    def find_by_slug(self, workspace_id: WorkspaceId, slug: Slug) -> Project | None: ...
    def add(self, project: Project) -> None: ...
    def save(self, project: Project, *, expected_version: int) -> None: ...
    def list(
        self, workspace_id: WorkspaceId, *, state: ProjectState | None, after: str | None, limit: int
    ) -> Page[Project]: ...
    def count(
        self, workspace_id: WorkspaceId
    ) -> int: ...  # projects of every state (WorkspaceView.project_count)


@repository_port
class RepositoryRepository(Protocol):
    def get(self, repository_id: RepositoryId) -> Repository: ...
    def add(self, repository: Repository) -> None: ...  # ALREADY_EXISTS (workspace, canonical_remote)
    def save(self, repository: Repository, *, expected_version: int) -> None: ...
    def remotes(self, repository_id: RepositoryId) -> tuple[RepositoryRemote, ...]: ...
    def replace_remotes(
        self, repository_id: RepositoryId, remotes: Sequence[RepositoryRemote]
    ) -> None: ...  # ALREADY_EXISTS (remote другого репо)
    def match_remotes(
        self, workspace_id: WorkspaceId, remotes: Sequence[NormalizedRemote]
    ) -> tuple[RepositoryMatchView, ...]: ...
    def list(
        self, workspace_id: WorkspaceId, *, id_prefix: str | None, after: str | None, limit: int
    ) -> Page[Repository]: ...  # keyset (created_at, id); id_prefix = lower-case hex of the id without dashes


@repository_port
class MountRepository(Protocol):
    def for_project(self, project_id: ProjectId) -> tuple[ProjectMount, ...]: ...
    def projects_of(self, repository_id: RepositoryId) -> tuple[ProjectId, ...]: ...
    def add(self, mount: ProjectMount) -> None: ...  # ALREADY_EXISTS (mount_name)
    def remove(self, project_id: ProjectId, mount_name: MountName) -> ProjectMount | None: ...


@repository_port
class HostRepository(Protocol):
    def get(self, host_id: HostId) -> Host: ...
    def find_by_name(self, name: str) -> Host | None: ...
    def add(self, host: Host) -> None: ...
    def save(self, host: Host, *, expected_version: int) -> None: ...
    def touch(self, host_id: HostId, at: datetime) -> None: ...
    def list(self, *, state: HostState | None, after: str | None, limit: int) -> Page[Host]: ...  # (name, id)


@repository_port
class CheckoutBindingRepository(Protocol):
    def get(self, binding_id: CheckoutBindingId) -> CheckoutBinding: ...
    def find(
        self, host_id: HostId, repository_id: RepositoryId
    ) -> CheckoutBinding | None: ...  # state ≠ removed
    def add(self, binding: CheckoutBinding) -> None: ...  # ALREADY_EXISTS (host, repo) среди не-removed
    def save(self, binding: CheckoutBinding, *, expected_version: int) -> None: ...


@repository_port
class WorkerRepository(Protocol):
    def get(self, worker_id: WorkerId) -> Worker: ...
    def add(self, worker: Worker) -> None: ...
    def save(self, worker: Worker, *, expected_version: int) -> None: ...
    def heartbeat(
        self, worker_id: WorkerId, at: datetime, capabilities: WorkerCapabilities | None
    ) -> Worker: ...  # без expected_version (последний побеждает)
    def list(
        self, workspace_id: WorkspaceId, *, state: WorkerState | None, after: str | None, limit: int
    ) -> Page[Worker]: ...
    def for_principal(self, principal_id: PrincipalId) -> Worker | None: ...  # UNIQUE (principal_id)
    def online(self, workspace_ids: Sequence[WorkspaceId]) -> tuple[Worker, ...]: ...  # (host_id, worker_id)
    def overdue(
        self, cutoff: datetime
    ) -> tuple[Worker, ...]: ...  # live workers whose heartbeat is before cutoff
    def mark_offline_older_than(
        self, cutoff: datetime
    ) -> tuple[WorkerId, ...]: ...  # для фоновой службы (execution.expire_leases вызывает через фасад)


@host_gateway
class RepositoryInspector(Protocol):
    def checkout_path(self, path: str) -> object: ...
    def resolve_commit(self, path: str, ref: str) -> str: ...
    def merge_base(self, path: str, base: str, head: str) -> str: ...  # adapters/git/repo_inspect.py
    def observe(
        self,
        path: str,
        *,
        marker_relpath: str = ".skm/project.json",
        timeout_seconds: float = 60.0,
    ) -> ObservedCheckout: ...
    # Observe Git facts and a schema-validated marker; invalid marker produces MARKER_INVALID.
    def observe_with_diagnostics(
        self,
        path: str,
        *,
        marker_relpath: str = ".skm/project.json",
        timeout_seconds: float = 60.0,
    ) -> tuple[ObservedCheckout, tuple[str, ...]]: ...
    def write_marker(
        self,
        path: str,
        *,
        marker_relpath: str = ".skm/project.json",
        marker: CheckoutMarker,
    ) -> None: ...

    # Validate the marker and publish relative to the verified root; reject symlinks and path escape.
