"""``artifacts.add_file_version`` (artifacts §7): the next immutable version of an active file.

The bus resolves the stored file's own scope (``file_scope_of_file``: its project, else its workspace),
authorises ``file.write`` there and loads the configuration of that scope, so a token narrowed to
``file.write`` passes and the settings applied are the file's own, never those of a reference the caller
wrote. The handler binds itself to the authorised scope and decides ``file.write`` again. The expected row
version, the trashed state, the filename and the safety policy are all settled before the staged blob is
consumed (a staged blob of another workspace is refused there). The classification of the file may rise with
the admission and never falls. A worker never adds a version.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.artifacts.application import views
from skm.modules.artifacts.application.admission import admission_policy, scan_and_admit
from skm.modules.artifacts.application.guards import (
    file_scope_of_file,
    require_bound,
    require_file,
    require_not_worker,
)
from skm.modules.artifacts.application.staging import consume_staged
from skm.modules.artifacts.application.versions import VersionDraft, append_version
from skm.modules.artifacts.domain.file import FileId, FileState
from skm.modules.artifacts.domain.staged_blob import StagedBlobId
from skm.modules.artifacts.domain.upload_rules import normalize_media_type, validate_filename
from skm.modules.artifacts.generated.commands import AddFileVersion
from skm.modules.artifacts.generated.results import AddFileVersionResult
from skm.modules.artifacts.ports import BlobDigestLock, FileRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle"]


def handle(cmd: AddFileVersion, ctx: CommandContext, uow: UnitOfWork) -> AddFileVersionResult:
    require_not_worker(ctx.actor)
    filename = validate_filename(cmd.original_filename)
    declared = normalize_media_type(cmd.declared_media_type)
    file = uow.repo(FileRepository).get(FileId(cmd.file_id))
    require_bound(ctx, file)  # the settings in ``ctx.config`` are those of the authorised scope
    require_file(uow, ctx, "file.write", file)
    check_expected(file.row_version, ExpectedVersion(cmd.expected_row_version))
    if file.state is not FileState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.FILE_TRASHED,
            "cannot add a version to a trashed file",
            details={"file_id": str(file.id)},
        )
    if file.project_id is not None:
        workspace.require_active_project(uow, file.project_id)
    else:
        workspace.require_active_workspace(uow, file.workspace_id)
    now = ctx.clock.now()
    policy = admission_policy(ctx.config)  # the file's workspace settings, before the staged blob is touched
    uow.repo(BlobDigestLock).lock_staged(file.workspace_id, StagedBlobId(cmd.blob.staged_blob_id))
    staged = consume_staged(
        uow, ref=cmd.blob.to_json(), workspace_id=file.workspace_id, request_id=ctx.meta.request_id, now=now
    )
    admitted = scan_and_admit(
        ctx,
        staged,
        policy=policy,
        name=filename,
        declared_media_type=declared,
        origin=file.origin,
        classification=file.classification,
        acknowledge=tuple(cmd.acknowledge),
    )
    draft = VersionDraft(
        staged=staged,
        original_filename=filename,
        declared_media_type=declared,
        description=cmd.description,
        source=views.source_from_command(cmd.source),
        safety=admitted.report,
        created_by=ctx.actor.principal_id,
    )
    _, version = append_version(
        uow, file, classification=admitted.classification, draft=draft, ids=ctx.ids, now=now
    )
    return AddFileVersionResult(
        file_id=file.id,
        file_version_id=version.id,
        version_no=version.version_no,
        safety=views.add_version_safety(admitted.report),
    )


SPEC = CommandSpec(
    name="artifacts.add_file_version",
    dto=AddFileVersion,
    result=AddFileVersionResult,
    permission="file.write",
    scope_of=None,
    scope_resolver=file_scope_of_file,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),  # a worker never adds a version
)
