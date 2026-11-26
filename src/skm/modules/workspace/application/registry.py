"""Bus operations of the workspace module (workspace §7, §8)."""

from skm.modules.workspace.application.commands import (
    add_repository_remote,
    archive_project,
    archive_workspace,
    attach_repository,
    bind_checkout,
    create_project,
    create_workspace,
    detach_repository,
    exchange_pairing_token,
    record_checkout_verification,
    record_worker_heartbeat,
    register_host,
    register_repository,
    register_worker,
    set_worker_state,
)
from skm.modules.workspace.application.queries import (
    get_host,
    get_project,
    get_workspace,
    list_hosts,
    list_project_repositories,
    list_projects,
    list_repositories,
    list_workers,
    list_workspaces,
    match_checkout,
    resolve_checkout,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    create_workspace.SPEC,
    archive_workspace.SPEC,
    create_project.SPEC,
    archive_project.SPEC,
    register_repository.SPEC,
    add_repository_remote.SPEC,
    attach_repository.SPEC,
    detach_repository.SPEC,
    register_host.SPEC,
    bind_checkout.SPEC,
    record_checkout_verification.SPEC,
    register_worker.SPEC,
    exchange_pairing_token.SPEC,
    set_worker_state.SPEC,
    record_worker_heartbeat.SPEC,
)
QUERIES = (
    list_workspaces.SPEC,
    get_workspace.SPEC,
    list_projects.SPEC,
    get_project.SPEC,
    list_repositories.SPEC,
    list_project_repositories.SPEC,
    list_hosts.SPEC,
    get_host.SPEC,
    resolve_checkout.SPEC,
    list_workers.SPEC,
    match_checkout.SPEC,
)
