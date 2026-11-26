"""``artifacts.restore_file`` (artifacts §7, §11.1): the logical un-hide of a trashed file; always possible.

Restore never needs an active project: it only moves ``files.state`` back. A repeated restore is a no-op
without a second event.

The bus resolves the stored file's own scope (``file_scope_of_file``) and authorises ``file.write`` there,
so a token narrowed to ``file.write`` passes; the handler binds itself to that scope and decides again.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.artifacts.application.events import FileRestored
from skm.modules.artifacts.application.guards import (
    file_scope_of_file,
    require_bound,
    require_file,
    require_not_worker,
)
from skm.modules.artifacts.domain import file as file_rules
from skm.modules.artifacts.domain.file import FileId
from skm.modules.artifacts.generated.commands import RestoreFile
from skm.modules.artifacts.generated.results import RestoreFileResult
from skm.modules.artifacts.ports import FileRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: RestoreFile, ctx: CommandContext, uow: UnitOfWork) -> RestoreFileResult:
    require_not_worker(ctx.actor)
    files = uow.repo(FileRepository)
    file = files.get(FileId(cmd.file_id))
    require_bound(ctx, file)
    require_file(uow, ctx, "file.write", file)
    check_expected(file.row_version, ExpectedVersion(cmd.expected_row_version))
    restored = file_rules.restore(file)
    if restored is not file:
        files.save(restored, expected_version=file.row_version)
        uow.record(FileRestored(file_id=restored.id, workspace_id=restored.workspace_id))
    return RestoreFileResult(
        file_id=restored.id, state=restored.state.value, row_version=restored.row_version
    )


SPEC = CommandSpec(
    name="artifacts.restore_file",
    dto=RestoreFile,
    result=RestoreFileResult,
    permission="file.write",
    scope_of=None,
    scope_resolver=file_scope_of_file,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),  # a worker never restores a file
)
