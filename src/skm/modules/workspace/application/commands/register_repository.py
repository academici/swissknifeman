"""``workspace.register_repository`` (workspace §7): the logical identity of code and its first remote."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import RepositoryId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.events import RepositoryRegistered
from skm.modules.workspace.application.guards import require_active_workspace
from skm.modules.workspace.domain import repository as repository_rules
from skm.modules.workspace.domain.remote_url import redact_remote
from skm.modules.workspace.domain.repository import RepositoryRemote
from skm.modules.workspace.generated.commands import RegisterRepository
from skm.modules.workspace.generated.results import RegisterRepositoryResult
from skm.modules.workspace.ports import RepositoryRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: RegisterRepository, ctx: CommandContext, uow: UnitOfWork) -> RegisterRepositoryResult:
    workspace = require_active_workspace(uow, WorkspaceId(cmd.workspace_id))
    repository = repository_rules.new_repository(
        repository_id=RepositoryId(ctx.ids.new_id()),
        workspace_id=workspace.id,
        title=cmd.title,
        remote_url=cmd.remote_url,
        external_id=cmd.external_id,
        now=ctx.clock.now(),
    )
    repositories = uow.repo(RepositoryRepository)
    canonical = repository.canonical_remote
    if canonical is not None:
        known = repositories.match_remotes(workspace.id, [canonical])
        if known:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a repository of this workspace already has this remote",
                details={"kind": "repository", "repository_id": str(known[0].repository_id)},
            )
    repositories.add(repository)
    if canonical is not None and cmd.remote_url is not None:
        repositories.replace_remotes(
            repository.id,
            [
                RepositoryRemote(
                    repository_id=repository.id,
                    normalized=canonical,
                    display_url=redact_remote(cmd.remote_url),
                    is_primary=True,
                )
            ],
        )
    uow.record(RepositoryRegistered(repository.id, workspace.id, canonical, repository.provider))
    return RegisterRepositoryResult(
        repository_id=repository.id,
        canonical_remote=None if canonical is None else canonical.value,
        provider=repository.provider.value,
    )


SPEC = CommandSpec(
    name="workspace.register_repository",
    dto=RegisterRepository,
    result=RegisterRepositoryResult,
    permission="repo.manage",
    scope_of=lambda cmd: ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
