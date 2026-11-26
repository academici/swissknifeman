"""``workspace.archive_project`` (workspace §7, §5.4): close the project to new admissions, keep its data."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.workspace.application.events import ProjectArchived
from skm.modules.workspace.domain import project as project_rules
from skm.modules.workspace.generated.commands import ArchiveProject
from skm.modules.workspace.generated.results import ArchiveProjectResult
from skm.modules.workspace.ports import ProjectRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: ArchiveProject, ctx: CommandContext, uow: UnitOfWork) -> ArchiveProjectResult:
    del ctx
    projects = uow.repo(ProjectRepository)
    project = projects.get(ProjectId(cmd.project_id))
    check_expected(project.row_version, ExpectedVersion(cmd.expected_row_version))
    archived = project_rules.archive(project)
    if archived is not project:  # a repeated archive changes nothing and records nothing
        projects.save(archived, expected_version=project.row_version)
        uow.record(ProjectArchived(archived.id, archived.workspace_id, cmd.reason))
    return ArchiveProjectResult(
        project_id=archived.id, state=archived.state.value, row_version=archived.row_version
    )


SPEC = CommandSpec(
    name="workspace.archive_project",
    dto=ArchiveProject,
    result=ArchiveProjectResult,
    permission="project.manage",
    scope_of=lambda cmd: ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
