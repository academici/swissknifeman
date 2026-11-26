"""``workspace.create_workspace`` (workspace §7): a workspace with its scope and its first owner."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.public import Role, grant_initial_membership
from skm.modules.workspace.application.events import WorkspaceCreated
from skm.modules.workspace.domain import workspace as workspace_rules
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.generated.commands import CreateWorkspace
from skm.modules.workspace.generated.results import CreateWorkspaceResult
from skm.modules.workspace.ports import WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: CreateWorkspace, ctx: CommandContext, uow: UnitOfWork) -> CreateWorkspaceResult:
    workspaces = uow.repo(WorkspaceRepository)
    slug = Slug(cmd.slug)
    if workspaces.find_by_slug(slug) is not None:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "workspace slug already used", details={"slug": slug.value})
    now = ctx.clock.now()
    workspace = workspace_rules.new_workspace(
        workspace_id=WorkspaceId(ctx.ids.new_id()), slug=slug, title=cmd.title, now=now
    )
    uow.repo(ScopeRegistry).create(
        ScopeId(workspace.id), ScopeKind.WORKSPACE, parent=ctx.scope.id, workspace_id=workspace.id
    )
    workspaces.add(workspace)
    grant_initial_membership(
        uow, scope_id=ScopeId(workspace.id), principal_id=ctx.actor.principal_id, role=Role.OWNER, now=now
    )
    uow.record(WorkspaceCreated(workspace.id, workspace.slug, workspace.title))
    return CreateWorkspaceResult(
        workspace_id=workspace.id, slug=workspace.slug.value, row_version=workspace.row_version
    )


SPEC = CommandSpec(
    name="workspace.create_workspace",
    dto=CreateWorkspace,
    result=CreateWorkspaceResult,
    permission="workspace.create",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
