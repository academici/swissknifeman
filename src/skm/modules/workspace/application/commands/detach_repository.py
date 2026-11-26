"""``workspace.detach_repository`` (workspace §7): remove a mount; bindings belong to repo+host and stay."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.events import RepositoryDetached
from skm.modules.workspace.domain import mount as mount_rules
from skm.modules.workspace.domain.mount import MountName
from skm.modules.workspace.generated.commands import DetachRepository
from skm.modules.workspace.generated.results import DetachRepositoryResult
from skm.modules.workspace.ports import MountRepository, ProjectRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: DetachRepository, ctx: CommandContext, uow: UnitOfWork) -> DetachRepositoryResult:
    del ctx
    project = uow.repo(ProjectRepository).get(ProjectId(cmd.project_id))
    mounts = uow.repo(MountRepository)
    name = MountName(cmd.mount_name)
    found = mount_rules.detach(mounts.for_project(project.id), project.id, name)
    if found is None:  # nothing to remove: no event
        return DetachRepositoryResult(project_id=project.id, mount_name=name.value, removed=False)
    mounts.remove(project.id, name)
    uow.record(RepositoryDetached(project.id, project.workspace_id, found.repository_id, name))
    return DetachRepositoryResult(project_id=project.id, mount_name=name.value, removed=True)


SPEC = CommandSpec(
    name="workspace.detach_repository",
    dto=DetachRepository,
    result=DetachRepositoryResult,
    permission="project.manage",
    scope_of=lambda cmd: ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
