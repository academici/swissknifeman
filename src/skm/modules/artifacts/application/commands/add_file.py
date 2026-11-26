"""``artifacts.add_file`` (artifacts §7): a logical file and its version 1 from a staged blob.

The filename is validated before anything else is touched (§4.5). The safety policy and the default
classification are read from the configuration of the file's scope (its project, else its workspace)
before the staged blob is consumed. The staged blob is consumed in this unit of work, its start is
scanned through the read-only gateway and the admission decides the classification; any refusal rolls
the whole unit back, so the staged row stays unconsumed. A worker never creates a file.

A request that omits ``classification`` takes the scoped ``artifacts.default_classification``; one that
names a value, ``internal`` included, keeps it: the absent field and the explicit value are different
requests.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts.application import views
from skm.modules.artifacts.application.admission import admission_policy, scan_and_admit
from skm.modules.artifacts.application.guards import require_not_worker
from skm.modules.artifacts.application.staging import consume_staged
from skm.modules.artifacts.application.versions import VersionDraft, create_file
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.file import FileOrigin
from skm.modules.artifacts.domain.staged_blob import StagedBlobId
from skm.modules.artifacts.domain.upload_rules import normalize_media_type, validate_filename
from skm.modules.artifacts.generated.commands import AddFile
from skm.modules.artifacts.generated.results import AddFileResult
from skm.modules.artifacts.generated.results import Classification as ResultClassification
from skm.modules.artifacts.ports import BlobDigestLock
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: AddFile) -> ScopeRef:
    """The project when named, else the workspace (a workspace-level file)."""
    if cmd.project_id is not None:
        return ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id))
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id))


def handle(cmd: AddFile, ctx: CommandContext, uow: UnitOfWork) -> AddFileResult:
    require_not_worker(ctx.actor)
    filename = validate_filename(cmd.original_filename)
    declared = normalize_media_type(cmd.declared_media_type)
    workspace_id = WorkspaceId(cmd.workspace_id)
    project_id = None if cmd.project_id is None else ProjectId(cmd.project_id)
    if project_id is not None:
        workspace.require_active_project(uow, project_id)
        if workspace.workspace_of_project(uow, project_id) != workspace_id:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "the project belongs to another workspace",
                details={"reason": "other_workspace"},
            )
    else:
        workspace.require_active_workspace(uow, workspace_id)
    now = ctx.clock.now()
    origin = FileOrigin(cmd.origin)
    policy = admission_policy(ctx.config)  # the scope's own settings, before the staged blob is touched
    requested = (
        policy.default_classification if cmd.classification is None else Classification(cmd.classification)
    )
    uow.repo(BlobDigestLock).lock_staged(workspace_id, StagedBlobId(cmd.blob.staged_blob_id))
    staged = consume_staged(
        uow, ref=cmd.blob.to_json(), workspace_id=workspace_id, request_id=ctx.meta.request_id, now=now
    )
    admitted = scan_and_admit(
        ctx,
        staged,
        policy=policy,
        name=filename,
        declared_media_type=declared,
        origin=origin,
        classification=requested,
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
    file, version = create_file(
        uow,
        workspace_id=workspace_id,
        project_id=project_id,
        title=cmd.title,
        origin=origin,
        classification=admitted.classification,
        draft=draft,
        ids=ctx.ids,
        now=now,
    )
    return AddFileResult(
        file_id=file.id,
        file_version_id=version.id,
        version_no=1,
        classification=ResultClassification(file.classification.value),
        safety=views.add_file_safety(admitted.report),
    )


SPEC = CommandSpec(
    name="artifacts.add_file",
    dto=AddFile,
    result=AddFileResult,
    permission="file.write",
    scope_of=scope_of,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),  # a worker never creates a file
)
