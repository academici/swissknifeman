"""``workspace.attach_repository`` (workspace §7): mount a repository of the project's workspace."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ProjectId, RepositoryId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.events import RepositoryAttached
from skm.modules.workspace.application.guards import require_active_project
from skm.modules.workspace.domain import mount as mount_rules
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.generated.commands import AttachRepository
from skm.modules.workspace.generated.results import AttachRepositoryResult
from skm.modules.workspace.ports import MountRepository, RepositoryRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: AttachRepository, ctx: CommandContext, uow: UnitOfWork) -> AttachRepositoryResult:
    project = require_active_project(uow, ProjectId(cmd.project_id))
    repository = uow.repo(RepositoryRepository).get(RepositoryId(cmd.repository_id))
    mounts = uow.repo(MountRepository)
    mount = mount_rules.attach(
        project,
        repository,
        MountName(cmd.mount_name),
        MountRole(cmd.role),
        mounts.for_project(project.id),
        now=ctx.clock.now(),
    )
    mounts.add(mount)
    uow.record(
        RepositoryAttached(project.id, project.workspace_id, repository.id, mount.mount_name, mount.role)
    )
    return AttachRepositoryResult(
        project_id=project.id, mount_name=mount.mount_name.value, repository_id=repository.id
    )


SPEC = CommandSpec(
    name="workspace.attach_repository",
    dto=AttachRepository,
    result=AttachRepositoryResult,
    permission="project.manage",
    scope_of=lambda cmd: ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
