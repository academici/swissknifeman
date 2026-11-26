"""``workspace.add_repository_remote`` (workspace §7).

The DTO names a repository, which is not a scope: the bus checks the self right and this handler decides
``repo.manage`` on the workspace of the loaded repository (``guards`` module docstring). The module has no
event for a remote that was added, so none is recorded.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import RepositoryId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.guards import SELF_PERMISSION, require, require_active_workspace
from skm.modules.workspace.domain import repository as repository_rules
from skm.modules.workspace.generated.commands import AddRepositoryRemote
from skm.modules.workspace.generated.results import (
    AddRepositoryRemoteResult,
    AddRepositoryRemoteResultRemotesItem,
)
from skm.modules.workspace.ports import RepositoryRepository

__all__ = ["SPEC", "handle"]

PERMISSION = "repo.manage"


def handle(cmd: AddRepositoryRemote, ctx: CommandContext, uow: UnitOfWork) -> AddRepositoryRemoteResult:
    repositories = uow.repo(RepositoryRepository)
    repository = repositories.get(RepositoryId(cmd.repository_id))
    require(uow, ctx.clock, ctx.actor, PERMISSION, repository.workspace_id)
    require_active_workspace(uow, repository.workspace_id)
    outcome = repository_rules.add_remote(
        repository, repositories.remotes(repository.id), cmd.url, cmd.make_primary
    )
    if outcome.changed:
        if outcome.repository is not repository:
            repositories.save(outcome.repository, expected_version=repository.row_version)
        repositories.replace_remotes(repository.id, outcome.remotes)
    return AddRepositoryRemoteResult(
        repository_id=repository.id,
        remotes=tuple(
            AddRepositoryRemoteResultRemotesItem(
                normalized=item.normalized.value, display_url=item.display_url, is_primary=item.is_primary
            )
            for item in outcome.remotes
        ),
    )


SPEC = CommandSpec(
    name="workspace.add_repository_remote",
    dto=AddRepositoryRemote,
    result=AddRepositoryRemoteResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
