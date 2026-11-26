"""``workspace.create_project`` (workspace §7): the golden slice -- a project with its own scope."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.workspace.application.events import ProjectCreated
from skm.modules.workspace.domain import project as project_rules
from skm.modules.workspace.domain import workspace as workspace_rules
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.generated.commands import CreateProject
from skm.modules.workspace.generated.results import CreateProjectResult
from skm.modules.workspace.ports import ProjectRepository, WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: CreateProject, ctx: CommandContext, uow: UnitOfWork) -> CreateProjectResult:
    workspace = uow.repo(WorkspaceRepository).get(WorkspaceId(cmd.workspace_id))
    projects = uow.repo(ProjectRepository)
    slug = Slug(cmd.slug)
    workspace_rules.require_active(workspace)
    if projects.find_by_slug(workspace.id, slug) is not None:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "project slug already used", details={"slug": slug.value})
    project = project_rules.new_project(
        project_id=ProjectId(ctx.ids.new_id()),
        workspace_id=workspace.id,
        slug=slug,
        title=cmd.title,
        description=cmd.description,
        now=ctx.clock.now(),
    )
    # The scope row first: projects.id references skm_core.scopes.id.
    uow.repo(ScopeRegistry).create(
        ScopeId(project.id), ScopeKind.PROJECT, parent=ScopeId(workspace.id), workspace_id=workspace.id
    )
    projects.add(project)
    uow.record(ProjectCreated(project.id, workspace.id, project.slug.value, project.title))
    return CreateProjectResult(
        project_id=project.id,
        workspace_id=workspace.id,
        slug=project.slug.value,
        row_version=project.row_version,
    )


SPEC = CommandSpec(
    name="workspace.create_project",
    dto=CreateProject,
    result=CreateProjectResult,
    permission="project.create",
    scope_of=lambda cmd: ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
