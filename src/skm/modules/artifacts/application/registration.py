"""``register_file_version``: a file with version 1 recorded by another module's handler (artifacts §13).

The body of the facade function. Execution calls it for evidence, transcripts, patches and reports after its
fence check, inside its own unit of work, with the staged blob already consumed and scanned. What the caller
passes (``safety``, the conservative ``classification``) is taken as given; what is checked here is the
workspace boundary and the filename.
"""

from datetime import datetime

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import PrincipalId, ProjectId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application.staging import StagedBlobView
from skm.modules.artifacts.application.versions import VersionDraft, create_file
from skm.modules.artifacts.application.views import file_version_ref
from skm.modules.artifacts.domain.binding import FileVersionRef
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import FileOrigin
from skm.modules.artifacts.domain.file_version import VersionSource
from skm.modules.artifacts.domain.upload_rules import normalize_media_type, validate_filename
from skm.modules.workspace import public as workspace

__all__ = ["register"]


def register(  # noqa: PLR0913 -- the fields of the facade function
    uow: UnitOfWork,
    *,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    title: str,
    origin: FileOrigin,
    staged: StagedBlobView,
    original_filename: str,
    media_type: str | None,
    source: VersionSource,
    classification: Classification,
    safety: SafetyReport,
    created_by: PrincipalId,
    ids: IdGenerator,
    now: datetime,
) -> FileVersionRef:
    """The filename is checked first; the project and the staged bytes must belong to ``workspace_id``.

    No admission check of an active project is made: a recording that completes admitted work may follow an
    archive (workspace §5.4).
    """
    filename = validate_filename(original_filename)
    declared = normalize_media_type(media_type)
    if workspace.workspace_of_project(uow, project_id) != workspace_id or staged.workspace_id != workspace_id:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the reference belongs to another workspace",
            details={"reason": "other_workspace"},
        )
    draft = VersionDraft(
        staged=staged,
        original_filename=filename,
        declared_media_type=declared,
        description="",
        source=source,
        safety=safety,
        created_by=created_by,
    )
    _, version = create_file(
        uow,
        workspace_id=workspace_id,
        project_id=project_id,
        title=title,
        origin=origin,
        classification=classification,
        draft=draft,
        ids=ids,
        now=now,
    )
    return file_version_ref(version)
