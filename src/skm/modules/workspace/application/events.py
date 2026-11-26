"""Domain events of the workspace module (workspace §9).

``workspace_id`` is the workspace the event belongs to (``None`` for ``HostRegistered``: hosts are instance
level). Payloads come from the generated event DTOs. ``local_locator`` is never part of a payload: it is not
portable and only readers with ``checkout.read_locator`` see it.
"""

from dataclasses import dataclass
from typing import ClassVar, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import HostId, PrincipalId, ProjectId, RepositoryId, WorkerId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.workspace.domain.checkout_binding import BindingState, CheckoutBindingId
from skm.modules.workspace.domain.host import HostPlatform
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.remote_url import NormalizedRemote, RepositoryProvider
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.domain.worker import WorkerCapabilities, WorkerState
from skm.modules.workspace.generated import events as generated

from .views import capabilities_document

__all__ = [
    "CheckoutBindingVerified",
    "CheckoutBound",
    "HostRegistered",
    "ProjectArchived",
    "ProjectCreated",
    "RepositoryAttached",
    "RepositoryDetached",
    "RepositoryRegistered",
    "WorkerRegistered",
    "WorkerStateChanged",
    "WorkspaceArchived",
    "WorkspaceCreated",
]

_PREFIX = "urn:skm:workspace:event:"


def _urn(name: str) -> str:
    return f"{_PREFIX}{name}:v1"


@dataclass(frozen=True, slots=True)
class WorkspaceCreated(DomainEvent):
    event_type: ClassVar[str] = _urn("workspace-created")
    stream_kind: ClassVar[str] = "workspace"

    workspace_id: WorkspaceId
    slug: Slug
    title: str

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.WorkspaceCreated(
            workspace_id=self.workspace_id, slug=self.slug.value, title=self.title
        ).to_json()


@dataclass(frozen=True, slots=True)
class WorkspaceArchived(DomainEvent):
    event_type: ClassVar[str] = _urn("workspace-archived")
    stream_kind: ClassVar[str] = "workspace"

    workspace_id: WorkspaceId
    reason: str

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.WorkspaceArchived(workspace_id=self.workspace_id, reason=self.reason).to_json()


@dataclass(frozen=True, slots=True)
class ProjectCreated(DomainEvent):
    event_type: ClassVar[str] = _urn("project-created")
    stream_kind: ClassVar[str] = "project"

    project_id: ProjectId
    workspace_id: WorkspaceId
    slug: str
    title: str

    @override
    def stream_id(self) -> UUID:
        return self.project_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ProjectCreated(
            project_id=self.project_id, workspace_id=self.workspace_id, slug=self.slug, title=self.title
        ).to_json()


@dataclass(frozen=True, slots=True)
class ProjectArchived(DomainEvent):
    event_type: ClassVar[str] = _urn("project-archived")
    stream_kind: ClassVar[str] = "project"

    project_id: ProjectId
    workspace_id: WorkspaceId
    reason: str

    @override
    def stream_id(self) -> UUID:
        return self.project_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ProjectArchived(
            project_id=self.project_id, workspace_id=self.workspace_id, reason=self.reason
        ).to_json()


@dataclass(frozen=True, slots=True)
class RepositoryRegistered(DomainEvent):
    event_type: ClassVar[str] = _urn("repository-registered")
    stream_kind: ClassVar[str] = "workspace"

    repository_id: RepositoryId
    workspace_id: WorkspaceId
    canonical_remote: NormalizedRemote | None
    provider: RepositoryProvider

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.RepositoryRegistered(
            repository_id=self.repository_id,
            workspace_id=self.workspace_id,
            canonical_remote=None if self.canonical_remote is None else self.canonical_remote.value,
            provider=self.provider.value,
        ).to_json()


@dataclass(frozen=True, slots=True)
class RepositoryAttached(DomainEvent):
    event_type: ClassVar[str] = _urn("repository-attached")
    stream_kind: ClassVar[str] = "project"

    project_id: ProjectId
    workspace_id: WorkspaceId
    repository_id: RepositoryId
    mount_name: MountName
    role: MountRole

    @override
    def stream_id(self) -> UUID:
        return self.project_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.RepositoryAttached(
            project_id=self.project_id,
            repository_id=self.repository_id,
            mount_name=self.mount_name.value,
            role=self.role.value,
        ).to_json()


@dataclass(frozen=True, slots=True)
class RepositoryDetached(DomainEvent):
    event_type: ClassVar[str] = _urn("repository-detached")
    stream_kind: ClassVar[str] = "project"

    project_id: ProjectId
    workspace_id: WorkspaceId
    repository_id: RepositoryId
    mount_name: MountName

    @override
    def stream_id(self) -> UUID:
        return self.project_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.RepositoryDetached(
            project_id=self.project_id, repository_id=self.repository_id, mount_name=self.mount_name.value
        ).to_json()


@dataclass(frozen=True, slots=True)
class HostRegistered(DomainEvent):
    event_type: ClassVar[str] = _urn("host-registered")
    stream_kind: ClassVar[str] = "host"

    host_id: HostId
    name: str
    platform: HostPlatform

    @override
    def stream_id(self) -> UUID:
        return self.host_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return generated.HostRegistered(
            host_id=self.host_id,
            name=self.name,
            platform=generated.HostRegisteredDefsHostPlatform(
                os=generated.HostOs(self.platform.os.value), arch=generated.HostArch(self.platform.arch.value)
            ),
        ).to_json()


@dataclass(frozen=True, slots=True)
class CheckoutBound(DomainEvent):
    event_type: ClassVar[str] = _urn("checkout-bound")
    stream_kind: ClassVar[str] = "workspace"

    binding_id: CheckoutBindingId
    workspace_id: WorkspaceId
    host_id: HostId
    repository_id: RepositoryId
    state: BindingState

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.CheckoutBound(
            binding_id=self.binding_id,
            host_id=self.host_id,
            repository_id=self.repository_id,
            state=self.state.value,
        ).to_json()


@dataclass(frozen=True, slots=True)
class CheckoutBindingVerified(DomainEvent):
    event_type: ClassVar[str] = _urn("checkout-binding-verified")
    stream_kind: ClassVar[str] = "workspace"

    binding_id: CheckoutBindingId
    workspace_id: WorkspaceId
    state: BindingState
    reason: str | None

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.CheckoutBindingVerified(
            binding_id=self.binding_id,
            state=self.state.value,
            reason=self.reason,
        ).to_json()


@dataclass(frozen=True, slots=True)
class WorkerRegistered(DomainEvent):
    event_type: ClassVar[str] = _urn("worker-registered")
    stream_kind: ClassVar[str] = "workspace"

    worker_id: WorkerId
    workspace_id: WorkspaceId
    host_id: HostId
    principal_id: PrincipalId
    capabilities: WorkerCapabilities

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.WorkerRegistered(
            worker_id=self.worker_id,
            workspace_id=self.workspace_id,
            host_id=self.host_id,
            principal_id=self.principal_id,
            capabilities=capabilities_document(self.capabilities),
        ).to_json()


@dataclass(frozen=True, slots=True)
class WorkerStateChanged(DomainEvent):
    event_type: ClassVar[str] = _urn("worker-state-changed")
    stream_kind: ClassVar[str] = "workspace"

    worker_id: WorkerId
    workspace_id: WorkspaceId
    from_state: WorkerState
    to_state: WorkerState

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.WorkerStateChanged(
            worker_id=self.worker_id,
            from_state=self.from_state.value,
            to_state=self.to_state.value,
        ).to_json()
