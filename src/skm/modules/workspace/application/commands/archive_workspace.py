"""``workspace.archive_workspace`` (workspace §7, §5.4): close new admissions, keep the data."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.workspace.application.events import WorkspaceArchived
from skm.modules.workspace.domain import workspace as workspace_rules
from skm.modules.workspace.generated.commands import ArchiveWorkspace
from skm.modules.workspace.generated.results import ArchiveWorkspaceResult
from skm.modules.workspace.ports import WorkspaceRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: ArchiveWorkspace, ctx: CommandContext, uow: UnitOfWork) -> ArchiveWorkspaceResult:
    del ctx
    workspaces = uow.repo(WorkspaceRepository)
    workspace = workspaces.get(WorkspaceId(cmd.workspace_id))
    check_expected(workspace.row_version, ExpectedVersion(cmd.expected_row_version))
    archived = workspace_rules.archive(workspace)
    if archived is not workspace:  # a repeated archive changes nothing and records nothing
        workspaces.save(archived, expected_version=workspace.row_version)
        uow.record(WorkspaceArchived(archived.id, cmd.reason))
    return ArchiveWorkspaceResult(
        workspace_id=archived.id, state=archived.state.value, row_version=archived.row_version
    )


SPEC = CommandSpec(
    name="workspace.archive_workspace",
    dto=ArchiveWorkspace,
    result=ArchiveWorkspaceResult,
    permission="workspace.manage",
    scope_of=lambda cmd: ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
