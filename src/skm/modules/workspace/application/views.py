"""Mapping of domain values to the generated views of the workspace module (workspace §8, §13).

The views never carry more than the spec lists: ``local_locator`` appears only when the caller passes
``locator=True`` (the actor holds ``checkout.read_locator``), and an event or a host view never holds it.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from skm.kernel.json_types import JsonObject
from skm.modules.workspace.domain.attach import (
    AttachOutcome,
    CreateRepository,
    Refuse,
    UseExistingRepository,
    UseMarker,
)
from skm.modules.workspace.domain.checkout_binding import CheckoutBinding, is_stale
from skm.modules.workspace.domain.host import Host, HostArch, HostOs, HostPlatform
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount
from skm.modules.workspace.domain.project import Project
from skm.modules.workspace.domain.repository import Repository
from skm.modules.workspace.domain.worker import Worker, WorkerCapabilities
from skm.modules.workspace.domain.workspace import Workspace
from skm.modules.workspace.generated import documents, views

__all__ = [
    "attach_decision_view",
    "binding_variant",
    "binding_view",
    "capabilities_document",
    "capabilities_from_document",
    "host_view",
    "location_view",
    "mount_view",
    "platform_from_document",
    "project_summary",
    "project_view",
    "repository_view",
    "worker_view",
    "workspace_summary",
    "workspace_view",
]


def capabilities_document(capabilities: WorkerCapabilities) -> documents.WorkerCapabilities:
    return documents.WorkerCapabilities(
        runtimes=capabilities.runtimes,
        isolation_profiles=capabilities.isolation_profiles,
        max_concurrency=capabilities.max_concurrency,
        labels=capabilities.labels,
        platform=documents.WorkerCapabilitiesDefsHostPlatform(
            os=documents.HostOs(capabilities.platform.os.value),
            arch=documents.HostArch(capabilities.platform.arch.value),
        ),
        skm_version=capabilities.skm_version,
    )


def platform_from_document(os: str, arch: str) -> HostPlatform:
    return HostPlatform(os=HostOs(os), arch=HostArch(arch))


def capabilities_from_document(document: documents.WorkerCapabilities) -> WorkerCapabilities:
    """Domain value of a validated document; the constructor re-checks every rule of the spec."""
    return WorkerCapabilities(
        runtimes=tuple(document.runtimes),
        isolation_profiles=tuple(document.isolation_profiles),
        max_concurrency=document.max_concurrency,
        labels=tuple(document.labels),
        platform=platform_from_document(document.platform.os.value, document.platform.arch.value),
        skm_version=document.skm_version,
    )


def workspace_summary(workspace: Workspace) -> views.WorkspaceSummaryView:
    return views.WorkspaceSummaryView(
        workspace_id=workspace.id,
        slug=workspace.slug.value,
        title=workspace.title,
        state=workspace.state.value,
    )


def workspace_view(workspace: Workspace, project_count: int) -> views.WorkspaceView:
    return views.WorkspaceView(
        workspace_id=workspace.id,
        slug=workspace.slug.value,
        title=workspace.title,
        state=workspace.state.value,
        project_count=project_count,
        row_version=workspace.row_version,
    )


def project_summary(project: Project) -> views.ProjectSummaryView:
    return views.ProjectSummaryView(
        project_id=project.id, slug=project.slug.value, title=project.title, state=project.state.value
    )


def repository_view(repository: Repository) -> views.RepositoryView:
    return views.RepositoryView(
        repository_id=repository.id,
        workspace_id=repository.workspace_id,
        title=repository.title,
        canonical_remote=None if repository.canonical_remote is None else repository.canonical_remote.value,
        provider=repository.provider.value,
        external_id=repository.external_id,
        row_version=repository.row_version,
        created_at=repository.created_at,
    )


def project_view(project: Project, mounts: Sequence[tuple[ProjectMount, Repository]]) -> views.ProjectView:
    return views.ProjectView(
        project_id=project.id,
        workspace_id=project.workspace_id,
        slug=project.slug.value,
        title=project.title,
        description=project.description,
        state=project.state.value,
        row_version=project.row_version,
        mounts=tuple(
            views.ProjectViewMountsItem(
                mount_name=mount.mount_name.value,
                role=mount.role.value,
                repository_id=repository.id,
                canonical_remote=None
                if repository.canonical_remote is None
                else repository.canonical_remote.value,
            )
            for mount, repository in sorted(mounts, key=lambda pair: pair[0].mount_name.value)
        ),
    )


def host_view(host: Host) -> views.HostView:
    return views.HostView(
        host_id=host.id,
        name=host.name,
        platform=views.HostViewDefsHostPlatform(
            os=views.HostOs(host.platform.os.value), arch=views.HostArch(host.platform.arch.value)
        ),
        state=host.state.value,
        registered_at=host.registered_at,
        last_seen_at=host.last_seen_at,
    )


def worker_view(worker: Worker) -> views.WorkerView:
    return views.WorkerView(
        worker_id=worker.id,
        workspace_id=worker.workspace_id,
        host_id=worker.host_id,
        display_name=worker.display_name,
        state=worker.state.value,
        capabilities=capabilities_document(worker.capabilities),
        last_heartbeat_at=worker.last_heartbeat_at,
        row_version=worker.row_version,
    )


def stale_after(days: int) -> timedelta:
    return timedelta(days=days)


def binding_variant(
    binding: CheckoutBinding, *, now: datetime, stale_days: int, locator: bool
) -> views.MountViewBindingVariant1:
    return views.MountViewBindingVariant1(
        binding_id=binding.id,
        state=binding.state.value,
        is_stale=is_stale(binding, now, stale_after(stale_days)),
        row_version=binding.row_version,
        local_locator=binding.local_locator if locator else None,
    )


def binding_view(
    binding: CheckoutBinding, *, now: datetime, stale_days: int, locator: bool
) -> views.CheckoutBindingView:
    return views.CheckoutBindingView(
        binding_id=binding.id,
        state=binding.state.value,
        is_stale=is_stale(binding, now, stale_after(stale_days)),
        row_version=binding.row_version,
        local_locator=binding.local_locator if locator else None,
    )


def mount_view(
    mount: ProjectMount, repository: Repository, binding: views.MountViewBindingVariant1 | None
) -> views.MountView:
    return views.MountView(
        mount_name=mount.mount_name.value,
        role=mount.role.value,
        repository=repository_view(repository),
        binding=binding,
    )


def location_view(binding: CheckoutBinding, *, now: datetime, stale_days: int) -> views.CheckoutLocationView:
    return views.CheckoutLocationView(
        binding_id=binding.id,
        repository_id=binding.repository_id,
        local_locator=binding.local_locator,
        state=binding.state.value,
        is_stale=is_stale(binding, now, stale_after(stale_days)),
    )


def attach_decision_view(
    outcome: AttachOutcome, *, mount_name: str, requested_project_id: UUID | None
) -> views.AttachDecisionView:
    diagnostics: tuple[JsonObject, ...] = tuple(
        {
            "code": item.code,
            "message": item.message,
            "severity": item.severity.value,
            "details": dict(item.details),
        }
        for item in outcome.diagnostics
    )
    decision = outcome.decision
    match decision:
        case UseMarker():
            return views.AttachDecisionView(
                kind="use_marker",
                project_id=decision.project_id,
                repository_id=decision.repository_id,
                mount_name=decision.mount_name.value,
                needs_confirmation=False,
                canonical_remote=None,
                refuse_code=None,
                refuse_details=None,
                diagnostics=diagnostics,
            )
        case UseExistingRepository():
            return views.AttachDecisionView(
                kind="use_existing_repository",
                project_id=decision.project_id,
                repository_id=decision.repository_id,
                mount_name=mount_name,
                needs_confirmation=decision.needs_confirmation,
                canonical_remote=None,
                refuse_code=None,
                refuse_details=None,
                diagnostics=diagnostics,
            )
        case CreateRepository():
            return views.AttachDecisionView(
                kind="create_repository",
                project_id=requested_project_id,
                repository_id=None,
                mount_name=mount_name,
                needs_confirmation=False,
                canonical_remote=None
                if decision.canonical_remote is None
                else decision.canonical_remote.value,
                refuse_code=None,
                refuse_details=None,
                diagnostics=diagnostics,
            )
        case Refuse():
            return views.AttachDecisionView(
                kind="refuse",
                project_id=None,
                repository_id=None,
                mount_name=None,
                needs_confirmation=False,
                canonical_remote=None,
                refuse_code=decision.code,
                refuse_details=decision.details,
                diagnostics=diagnostics,
            )
