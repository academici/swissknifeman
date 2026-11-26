"""Manifest of the workspace module (workspace §3)."""

from skm.kernel.module_manifest import ModuleManifest

from .application import events
from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .host.registry import HOST_OPERATIONS
from .permissions import PERMISSIONS
from .ports import (
    CheckoutBindingRepository,
    HostRepository,
    MountRepository,
    ProjectRepository,
    RepositoryInspector,
    RepositoryRepository,
    WorkerRepository,
    WorkspaceRepository,
)

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="workspace",
    depends_on=("access",),
    optional=False,
    db_schema="skm_workspace",
    settings_sections=("workspace",),
    permissions=PERMISSIONS,
    repository_ports=(
        WorkspaceRepository,
        ProjectRepository,
        RepositoryRepository,
        MountRepository,
        HostRepository,
        CheckoutBindingRepository,
        WorkerRepository,
    ),
    gateway_ports=(RepositoryInspector,),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=HOST_OPERATIONS,
    events=(
        events.WorkspaceCreated,
        events.WorkspaceArchived,
        events.ProjectCreated,
        events.ProjectArchived,
        events.RepositoryRegistered,
        events.RepositoryAttached,
        events.RepositoryDetached,
        events.HostRegistered,
        events.CheckoutBound,
        events.CheckoutBindingVerified,
        events.WorkerRegistered,
        events.WorkerStateChanged,
    ),
)
