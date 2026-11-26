"""Facade of the workspace module (workspace §13): the only surface other modules and entrypoints import.

Functions run inside the caller's unit of work and check no permission: the caller is a handler that was
already authorised. The DTOs, results and views are the generated contract of the commands and queries,
which the surfaces use through ``SkmClient``.

The facade has no clock and no configuration: ``resolve_checkout`` and ``get_checkout_binding`` take ``now``
(and ``stale_after_days``, default 30 days) from the calling handler, and no facade view carries a
``local_locator`` unless the function is ``resolve_checkout`` (whose caller is authorised for it).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from importlib import import_module
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import HostId, PrincipalId, ProjectId, RepositoryId, ScopeId, WorkerId, WorkspaceId

if TYPE_CHECKING:
    from skm.kernel.ports_uow import UnitOfWork
    from skm.kernel.scopes import ScopeRef
    from skm.modules.workspace.domain.checkout_binding import (
        CheckoutBindingId as CheckoutBindingId,
    )
    from skm.modules.workspace.domain.checkout_binding import (
        ObservedCheckout,
        checkout_id_from_locator,
        checkout_locator,
    )
    from skm.modules.workspace.domain.checkout_marker import CheckoutMarker, marker_from_document
    from skm.modules.workspace.domain.mount import MountName
    from skm.modules.workspace.domain.remote_url import NormalizedRemote, normalize_remote, redact_remote
    from skm.modules.workspace.domain.slug import Slug
    from skm.modules.workspace.domain.worker import WorkerCapabilities
    from skm.modules.workspace.generated.commands import (
        AddRepositoryRemote,
        ArchiveProject,
        ArchiveWorkspace,
        AttachRepository,
        BindCheckout,
        CreateProject,
        CreateWorkspace,
        DetachRepository,
        ExchangePairingToken,
        RecordCheckoutVerification,
        RecordWorkerHeartbeat,
        RegisterHost,
        RegisterHostDefsHostPlatform,
        RegisterRepository,
        RegisterWorker,
        SetWorkerState,
    )
    from skm.modules.workspace.generated.queries import (
        GetHost,
        GetProject,
        GetWorkspace,
        ListHosts,
        ListProjectRepositories,
        ListProjects,
        ListRepositories,
        ListWorkers,
        ListWorkspaces,
        MatchCheckout,
        ResolveCheckout,
    )
    from skm.modules.workspace.generated.results import (
        AddRepositoryRemoteResult,
        AddRepositoryRemoteResultRemotesItem,
        ArchiveProjectResult,
        ArchiveWorkspaceResult,
        AttachRepositoryResult,
        BindCheckoutResult,
        CreateProjectResult,
        CreateWorkspaceResult,
        DetachRepositoryResult,
        ExchangePairingTokenResult,
        RecordCheckoutVerificationResult,
        RecordWorkerHeartbeatResult,
        RegisterHostResult,
        RegisterRepositoryResult,
        RegisterWorkerResult,
        SetWorkerStateResult,
    )
    from skm.modules.workspace.generated.views import (
        AttachDecisionView,
        CheckoutBindingView,
        CheckoutLocationView,
        HostView,
        HostViewDefsHostPlatform,
        ListHostsView,
        ListProjectRepositoriesView,
        ListProjectsView,
        ListRepositoriesView,
        ListWorkersView,
        ListWorkspacesView,
        MountView,
        MountViewBindingVariant1,
        ProjectRepositoriesView,
        ProjectSummaryView,
        ProjectView,
        ProjectViewMountsItem,
        RepositoryView,
        WorkerView,
        WorkspaceSummaryView,
        WorkspaceView,
    )

_LAZY_EXPORTS: dict[str, str] = {
    **dict.fromkeys(
        (
            "AddRepositoryRemote",
            "ArchiveProject",
            "ArchiveWorkspace",
            "AttachRepository",
            "BindCheckout",
            "CreateProject",
            "CreateWorkspace",
            "DetachRepository",
            "RecordCheckoutVerification",
            "RecordWorkerHeartbeat",
            "RegisterHost",
            "RegisterHostDefsHostPlatform",
            "RegisterRepository",
            "ExchangePairingToken",
            "RegisterWorker",
            "SetWorkerState",
        ),
        ".generated.commands",
    ),
    **dict.fromkeys(
        (
            "GetHost",
            "GetProject",
            "GetWorkspace",
            "ListHosts",
            "ListProjectRepositories",
            "ListProjects",
            "ListRepositories",
            "ListWorkers",
            "ListWorkspaces",
            "MatchCheckout",
            "ResolveCheckout",
        ),
        ".generated.queries",
    ),
    **dict.fromkeys(
        (
            "AddRepositoryRemoteResult",
            "AddRepositoryRemoteResultRemotesItem",
            "ArchiveProjectResult",
            "ArchiveWorkspaceResult",
            "AttachRepositoryResult",
            "BindCheckoutResult",
            "CreateProjectResult",
            "CreateWorkspaceResult",
            "DetachRepositoryResult",
            "RecordCheckoutVerificationResult",
            "RecordWorkerHeartbeatResult",
            "RegisterHostResult",
            "RegisterRepositoryResult",
            "ExchangePairingTokenResult",
            "RegisterWorkerResult",
            "SetWorkerStateResult",
        ),
        ".generated.results",
    ),
    **dict.fromkeys(
        (
            "AttachDecisionView",
            "CheckoutBindingView",
            "CheckoutLocationView",
            "HostView",
            "HostViewDefsHostPlatform",
            "ListHostsView",
            "ListProjectRepositoriesView",
            "ListProjectsView",
            "ListRepositoriesView",
            "ListWorkersView",
            "ListWorkspacesView",
            "MountView",
            "MountViewBindingVariant1",
            "ProjectRepositoriesView",
            "ProjectSummaryView",
            "ProjectView",
            "ProjectViewMountsItem",
            "RepositoryView",
            "WorkerView",
            "WorkspaceSummaryView",
            "WorkspaceView",
        ),
        ".generated.views",
    ),
    "CheckoutBindingId": ".domain.checkout_binding",
    "checkout_id_from_locator": ".domain.checkout_binding",
    "checkout_locator": ".domain.checkout_binding",
    "ObservedCheckout": ".domain.checkout_binding",
    "CheckoutMarker": ".domain.checkout_marker",
    "marker_from_document": ".domain.checkout_marker",
    "MountName": ".domain.mount",
    "NormalizedRemote": ".domain.remote_url",
    "normalize_remote": ".domain.remote_url",
    "redact_remote": ".domain.remote_url",
    "Slug": ".domain.slug",
    "WorkerCapabilities": ".domain.worker",
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "AddRepositoryRemote",
    "AddRepositoryRemoteResult",
    "AddRepositoryRemoteResultRemotesItem",
    "ArchiveProject",
    "ArchiveProjectResult",
    "ArchiveWorkspace",
    "ArchiveWorkspaceResult",
    "AttachDecisionView",
    "AttachRepository",
    "AttachRepositoryResult",
    "BindCheckout",
    "BindCheckoutResult",
    "CheckoutBindingView",
    "CheckoutLocationView",
    "CheckoutMarker",
    "CreateProject",
    "CreateProjectResult",
    "CreateWorkspace",
    "CreateWorkspaceResult",
    "DetachRepository",
    "DetachRepositoryResult",
    "ExchangePairingToken",
    "ExchangePairingTokenResult",
    "GetHost",
    "GetProject",
    "GetWorkspace",
    "HostView",
    "HostViewDefsHostPlatform",
    "ListHosts",
    "ListHostsView",
    "ListProjectRepositories",
    "ListProjectRepositoriesView",
    "ListProjects",
    "ListProjectsView",
    "ListRepositories",
    "ListRepositoriesView",
    "ListWorkers",
    "ListWorkersView",
    "ListWorkspaces",
    "ListWorkspacesView",
    "MatchCheckout",
    "MountName",
    "MountView",
    "MountViewBindingVariant1",
    "NormalizedRemote",
    "ObservedCheckout",
    "ProjectRepositoriesView",
    "ProjectSummaryView",
    "ProjectView",
    "ProjectViewMountsItem",
    "RecordCheckoutVerification",
    "RecordCheckoutVerificationResult",
    "RecordWorkerHeartbeat",
    "RecordWorkerHeartbeatResult",
    "RegisterHost",
    "RegisterHostDefsHostPlatform",
    "RegisterHostResult",
    "RegisterRepository",
    "RegisterRepositoryResult",
    "RegisterWorker",
    "RegisterWorkerResult",
    "RepositoryView",
    "ResolveCheckout",
    "SetWorkerState",
    "SetWorkerStateResult",
    "Slug",
    "WorkerCapabilities",
    "WorkerView",
    "WorkspaceSummaryView",
    "WorkspaceView",
    "checkout_id_from_locator",
    "checkout_locator",
    "get_checkout_binding",
    "get_host",
    "get_project",
    "get_repository",
    "get_worker",
    "list_online_workers",
    "mark_workers_offline",
    "marker_from_document",
    "normalize_remote",
    "primary_remote",
    "project_mounts",
    "project_repositories",
    "redact_remote",
    "require_active_project",
    "require_active_workspace",
    "require_repository",
    "resolve_checkout",
    "scope_chain",
    "worker_for_principal",
    "workspace_of_project",
]


def _repository_view(uow: UnitOfWork, repository_id: RepositoryId) -> RepositoryView:
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import RepositoryRepository

    return views.repository_view(uow.repo(RepositoryRepository).get(repository_id))


def get_project(uow: UnitOfWork, project_id: ProjectId) -> ProjectView:
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import MountRepository, ProjectRepository, RepositoryRepository

    project = uow.repo(ProjectRepository).get(project_id)
    repositories = uow.repo(RepositoryRepository)
    mounts = tuple(
        (mount, repositories.get(mount.repository_id))
        for mount in uow.repo(MountRepository).for_project(project.id)
    )
    return views.project_view(project, mounts)


def require_active_project(uow: UnitOfWork, project_id: ProjectId) -> None:
    """``PROJECT_ARCHIVED`` when the project **or its workspace** is not active (workspace §5.4)."""
    from skm.modules.workspace.application import guards

    guards.require_active_project(uow, project_id)


def project_mounts(uow: UnitOfWork, project_id: ProjectId) -> frozenset[str]:
    from skm.modules.workspace.ports import MountRepository

    return frozenset(item.mount_name.value for item in uow.repo(MountRepository).for_project(project_id))


def project_repositories(uow: UnitOfWork, project_id: ProjectId) -> tuple[MountView, ...]:
    """The mounts of the project with their repositories; no binding (a binding belongs to one host)."""
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import MountRepository, RepositoryRepository

    repositories = uow.repo(RepositoryRepository)
    mounts = sorted(uow.repo(MountRepository).for_project(project_id), key=lambda item: item.mount_name.value)
    return tuple(views.mount_view(item, repositories.get(item.repository_id), None) for item in mounts)


def resolve_checkout(
    uow: UnitOfWork,
    project_id: ProjectId,
    mount_name: str,
    host_id: HostId,
    *,
    now: datetime,
    stale_after_days: int = 30,
) -> CheckoutLocationView:
    """No permission check: the caller is a handler already authorised for ``checkout.read_locator``."""
    from skm.modules.workspace.application import locations

    return locations.resolve_location(
        uow, project_id, mount_name, host_id, now=now, stale_days=stale_after_days
    )


def get_repository(uow: UnitOfWork, repository_id: RepositoryId) -> RepositoryView:
    return _repository_view(uow, repository_id)


def get_worker(uow: UnitOfWork, worker_id: WorkerId) -> WorkerView:
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import WorkerRepository

    return views.worker_view(uow.repo(WorkerRepository).get(worker_id))


def worker_for_principal(uow: UnitOfWork, principal_id: PrincipalId) -> WorkerView | None:
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import WorkerRepository

    found = uow.repo(WorkerRepository).for_principal(principal_id)
    return None if found is None else views.worker_view(found)


def mark_workers_offline(uow: UnitOfWork, cutoff: datetime) -> tuple[WorkerId, ...]:
    """``online|draining -> offline`` for workers without a heartbeat since ``cutoff``; one event each."""
    from skm.modules.workspace.application.events import WorkerStateChanged
    from skm.modules.workspace.ports import WorkerRepository

    workers = uow.repo(WorkerRepository)
    before = {item.id: item for item in workers.overdue(cutoff)}
    marked = workers.mark_offline_older_than(cutoff)
    for worker_id in marked:
        was = before[worker_id]
        uow.record(WorkerStateChanged(was.id, was.workspace_id, was.state, workers.get(worker_id).state))
    return marked


def scope_chain(uow: UnitOfWork, scope_id: ScopeId) -> tuple[ScopeRef, ...]:
    """The chain from the instance to ``scope_id`` (``NOT_FOUND`` for an unknown scope)."""
    from skm.kernel.scopes import ScopeRef, ScopeRegistry

    return tuple(ScopeRef(item.kind, item.id) for item in uow.repo(ScopeRegistry).ancestors(scope_id))


def workspace_of_project(uow: UnitOfWork, project_id: ProjectId) -> WorkspaceId:
    from skm.modules.workspace.ports import ProjectRepository

    return uow.repo(ProjectRepository).get(project_id).workspace_id


def require_active_workspace(uow: UnitOfWork, workspace_id: WorkspaceId) -> WorkspaceView:
    """``PROJECT_ARCHIVED`` (``details.kind="workspace"``) for a suspended or archived workspace."""
    from skm.modules.workspace.application import guards, views
    from skm.modules.workspace.ports import ProjectRepository

    workspace = guards.require_active_workspace(uow, workspace_id)
    return views.workspace_view(workspace, uow.repo(ProjectRepository).count(workspace.id))


def require_repository(
    uow: UnitOfWork, workspace_id: WorkspaceId, repository_id: RepositoryId
) -> RepositoryView:
    """The repository of that workspace; the id of another workspace is ``NOT_FOUND``."""
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import RepositoryRepository

    repository = uow.repo(RepositoryRepository).get(repository_id)
    if repository.workspace_id != workspace_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "repository not found",
            details={"kind": "repository", "ref": str(repository_id)},
        )
    return views.repository_view(repository)


def get_host(uow: UnitOfWork, host_id: HostId) -> HostView:
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import HostRepository

    return views.host_view(uow.repo(HostRepository).get(host_id))


def get_checkout_binding(
    uow: UnitOfWork, checkout_binding_id: CheckoutBindingId, *, now: datetime, stale_after_days: int = 30
) -> CheckoutBindingView:
    """The binding without its locator; ``resolve_checkout`` is the way to a locator."""
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import CheckoutBindingRepository

    binding = uow.repo(CheckoutBindingRepository).get(checkout_binding_id)
    return views.binding_view(binding, now=now, stale_days=stale_after_days, locator=False)


def primary_remote(uow: UnitOfWork, repository_id: RepositoryId) -> NormalizedRemote | None:
    from skm.modules.workspace.ports import RepositoryRepository

    for item in uow.repo(RepositoryRepository).remotes(repository_id):
        if item.is_primary:
            return item.normalized
    return None


def list_online_workers(uow: UnitOfWork, workspace_ids: Sequence[WorkspaceId]) -> tuple[WorkerView, ...]:
    """Only ``online`` workers of the named workspaces, ordered by ``(host_id, worker_id)``."""
    from skm.modules.workspace.application import views
    from skm.modules.workspace.ports import WorkerRepository

    return tuple(views.worker_view(item) for item in uow.repo(WorkerRepository).online(workspace_ids))
