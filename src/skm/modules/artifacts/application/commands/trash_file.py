"""``artifacts.trash_file`` (artifacts §7, §11.1): the logical hide of a file; versions and bytes stay.

Trash touches only ``files.state``: no version, blob, object, grant or binding is changed, so published
revisions keep reading their pinned versions. A repeated trash is a no-op without a second event.

The bus resolves the stored file's own scope (``file_scope_of_file``) and authorises ``file.write`` there,
so a token narrowed to ``file.write`` passes; the handler binds itself to that scope and decides again.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.artifacts.application.events import FileTrashed
from skm.modules.artifacts.application.guards import (
    file_scope_of_file,
    require_bound,
    require_file,
    require_not_worker,
)
from skm.modules.artifacts.domain import file as file_rules
from skm.modules.artifacts.domain.file import FileId
from skm.modules.artifacts.generated.commands import TrashFile
from skm.modules.artifacts.generated.results import TrashFileResult
from skm.modules.artifacts.ports import FileRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: TrashFile, ctx: CommandContext, uow: UnitOfWork) -> TrashFileResult:
    require_not_worker(ctx.actor)
    files = uow.repo(FileRepository)
    file = files.get(FileId(cmd.file_id))
    require_bound(ctx, file)
    require_file(uow, ctx, "file.write", file)
    check_expected(file.row_version, ExpectedVersion(cmd.expected_row_version))
    trashed = file_rules.trash(file)
    if trashed is not file:  # a repeated trash changes nothing and records nothing
        files.save(trashed, expected_version=file.row_version)
        uow.record(FileTrashed(file_id=trashed.id, workspace_id=trashed.workspace_id, reason=cmd.reason))
    return TrashFileResult(file_id=trashed.id, state=trashed.state.value, row_version=trashed.row_version)


SPEC = CommandSpec(
    name="artifacts.trash_file",
    dto=TrashFile,
    result=TrashFileResult,
    permission="file.write",
    scope_of=None,
    scope_resolver=file_scope_of_file,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),  # a worker never trashes a file
)
