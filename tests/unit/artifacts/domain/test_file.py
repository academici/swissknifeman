from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, WorkspaceId
from skm.modules.artifacts.domain.blob import Blob, BlobAvailability, BlobId, ContentDigest
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import (
    File,
    FileId,
    FileOrigin,
    FileState,
    new_file,
    reclassify,
    restore,
    set_current,
    trash,
)
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource, new_version

NOW = datetime(2026, 1, 1, tzinfo=UTC)
USER = PrincipalId(uuid4())


def make_file(classification: Classification = Classification.INTERNAL) -> File:
    return new_file(
        file_id=FileId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        project_id=None,
        title="  spec  ",
        origin=FileOrigin.UPLOAD,
        classification=classification,
        created_by=USER,
        now=NOW,
    )


def make_version(file: File) -> FileVersion:
    blob = Blob(
        BlobId(uuid4()),
        file.workspace_id,
        ContentDigest("sha256:" + "a" * 64),
        3,
        "text/plain",
        BlobAvailability.AVAILABLE,
        NOW,
        None,
    )
    return new_version(
        version_id=FileVersionId(uuid4()),
        file=file,
        previous_no=0,
        blob=blob,
        original_filename="a.txt",
        declared_media_type=None,
        description="",
        source=VersionSource("upload", None, None),
        safety=SafetyReport((), (), False),
        created_by=USER,
        now=NOW,
    )


def test_new_file_trims_title_and_starts_without_version() -> None:
    f = make_file()
    assert (f.title, f.state, f.current_version_id, f.row_version) == ("spec", FileState.ACTIVE, None, 1)


def test_set_current_bumps_row_version() -> None:
    f = make_file()
    v = make_version(f)
    assert set_current(f, v).current_version_id == v.id
    assert set_current(f, v).row_version == 2


def test_set_current_rejects_version_of_another_file() -> None:
    with pytest.raises(InternalError):
        set_current(make_file(), make_version(make_file()))


def test_trash_restore_are_idempotent() -> None:
    f = make_file()
    t = trash(f)
    assert (t.state, t.row_version) == (FileState.TRASHED, 2)
    assert trash(t) is t
    assert restore(t).state is FileState.ACTIVE
    assert restore(f) is f


def test_empty_or_long_title_rejected() -> None:
    f = make_file()
    for title in ("   ", "x" * 301):
        with pytest.raises(ValidationFailed):
            new_file(
                file_id=f.id,
                workspace_id=f.workspace_id,
                project_id=None,
                title=title,
                origin=f.origin,
                classification=f.classification,
                created_by=f.created_by,
                now=f.created_at,
            )
    assert replace(f).title == f.title


def test_reclassify_cannot_lower() -> None:
    f = make_file(Classification.CONFIDENTIAL)
    with pytest.raises(ValidationFailed):
        reclassify(f, Classification.INTERNAL)
    assert reclassify(f, Classification.CONFIDENTIAL) is f
    assert reclassify(f, Classification.RESTRICTED).classification is Classification.RESTRICTED
