"""Creation of a logical file and of its next version inside the caller's unit of work (artifacts §7).

Shared by the ``add_file`` / ``add_file_version`` handlers and by the ``register_file_version`` facade, so the
rows and the events are the same whoever asks. The caller has already consumed the staged blob, scanned the
bytes and decided the classification; nothing here reads bytes or checks a permission.

Versions are immutable: a new version only appends a row and moves ``current_version_id`` of the file.
"""

from dataclasses import dataclass
from datetime import datetime

from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application.events import FileAdded, FileVersionAdded
from skm.modules.artifacts.application.staging import StagedBlobView, ensure_blob
from skm.modules.artifacts.domain import file as file_rules
from skm.modules.artifacts.domain.blob import Blob
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import File, FileId, FileOrigin
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource, new_version
from skm.modules.artifacts.ports import FileRepository, FileVersionRepository

__all__ = ["VersionDraft", "append_version", "create_file"]


@dataclass(frozen=True, slots=True)
class VersionDraft:
    """The admitted content of one new version."""

    staged: StagedBlobView
    original_filename: str
    declared_media_type: str | None
    description: str
    source: VersionSource
    safety: SafetyReport
    created_by: PrincipalId


def _store_version(
    uow: UnitOfWork, file: File, draft: VersionDraft, *, ids: IdGenerator, now: datetime
) -> tuple[File, FileVersion, Blob]:
    """Blob, version and the moved current pointer of ``file``; the file row is saved once."""
    versions = uow.repo(FileVersionRepository)
    blob = ensure_blob(uow, draft.staged, ids=ids, now=now)
    version = new_version(
        version_id=FileVersionId(ids.new_id()),
        file=file,
        previous_no=versions.last_no(file.id),
        blob=blob,
        original_filename=draft.original_filename,
        declared_media_type=draft.declared_media_type,
        description=draft.description,
        source=draft.source,
        safety=draft.safety,
        created_by=draft.created_by,
        now=now,
    )
    versions.add(version)
    return file_rules.set_current(file, version), version, blob


def _version_added(file: File, version: FileVersion, blob: Blob) -> FileVersionAdded:
    return FileVersionAdded(
        file_id=file.id,
        workspace_id=file.workspace_id,
        file_version_id=version.id,
        version_no=version.version_no,
        size_bytes=blob.size_bytes,
        digest=blob.digest,
        safety_verdict=version.safety.verdict(),
    )


def create_file(  # noqa: PLR0913 -- the fields of a new file and its first version
    uow: UnitOfWork,
    *,
    workspace_id: WorkspaceId,
    project_id: ProjectId | None,
    title: str,
    origin: FileOrigin,
    classification: Classification,
    draft: VersionDraft,
    ids: IdGenerator,
    now: datetime,
) -> tuple[File, FileVersion]:
    files = uow.repo(FileRepository)
    created = file_rules.new_file(
        file_id=FileId(ids.new_id()),
        workspace_id=workspace_id,
        project_id=project_id,
        title=title,
        origin=origin,
        classification=classification,
        created_by=draft.created_by,
        now=now,
    )
    files.add(created)
    current, version, blob = _store_version(uow, created, draft, ids=ids, now=now)
    files.save(current, expected_version=created.row_version)
    uow.record(
        FileAdded(
            file_id=current.id,
            workspace_id=current.workspace_id,
            project_id=current.project_id,
            title=current.title,
            origin=current.origin,
            classification=current.classification,
        )
    )
    uow.record(_version_added(current, version, blob))
    return current, version


def append_version(
    uow: UnitOfWork,
    file: File,
    *,
    classification: Classification,
    draft: VersionDraft,
    ids: IdGenerator,
    now: datetime,
) -> tuple[File, FileVersion]:
    """The next version of an active ``file``; its classification may rise to the given one, never fall."""
    raised = file_rules.reclassify(file, classification)
    current, version, blob = _store_version(uow, raised, draft, ids=ids, now=now)
    uow.repo(FileRepository).save(current, expected_version=file.row_version)
    uow.record(_version_added(current, version, blob))
    return current, version
