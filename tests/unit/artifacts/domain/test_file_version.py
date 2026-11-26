import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, WorkspaceId
from skm.modules.artifacts.domain.blob import Blob, BlobAvailability, BlobId, ContentDigest
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import File, FileId, FileOrigin, new_file, trash
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource, new_version

NOW = datetime(2026, 1, 1, tzinfo=UTC)
USER = PrincipalId(uuid4())


def make_file() -> File:
    return new_file(
        file_id=FileId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        project_id=None,
        title="spec",
        origin=FileOrigin.UPLOAD,
        classification=Classification.INTERNAL,
        created_by=USER,
        now=NOW,
    )


def make_blob(ws: WorkspaceId) -> Blob:
    return Blob(
        BlobId(uuid4()),
        ws,
        ContentDigest("sha256:" + "a" * 64),
        3,
        "text/plain",
        BlobAvailability.AVAILABLE,
        NOW,
        None,
    )


def make_version(
    file: File, blob: Blob | None = None, previous_no: int = 0, name: str = "a.txt"
) -> FileVersion:
    return new_version(
        version_id=FileVersionId(uuid4()),
        file=file,
        previous_no=previous_no,
        blob=blob or make_blob(file.workspace_id),
        original_filename=name,
        declared_media_type=None,
        description="",
        source=VersionSource("upload", None, None),
        safety=SafetyReport((), (), False),
        created_by=USER,
        now=NOW,
    )


def test_version_numbers_are_sequential_and_bound_to_file() -> None:
    f = make_file()
    v = make_version(f, previous_no=4)
    assert (v.version_no, v.file_id, v.workspace_id) == (5, f.id, f.workspace_id)


def test_trashed_file_rejects_new_version() -> None:
    with pytest.raises(PreconditionFailed) as e:
        make_version(trash(make_file()))
    assert e.value.code is ErrorCode.FILE_TRASHED


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("", "too_long"),
        ("x" * 256, "too_long"),
        ("ж" * 128, "too_long"),
        ("a/b", "not_basename"),
        ("a\\b", "not_basename"),
        ("a\0b", "control_char"),
        ("bell\x07.txt", "control_char"),
        ("x\N{RIGHT-TO-LEFT OVERRIDE}gpj.exe", "control_char"),
        ("\N{POP DIRECTIONAL ISOLATE}a.txt", "control_char"),
        ("a\x85b", "control_char"),
        (".", "dot_name"),
        ("..", "dot_name"),
    ],
)
def test_bad_filename_rejected_by_validate_filename(name: str, reason: str) -> None:
    with pytest.raises(ValidationFailed) as e:
        make_version(make_file(), name=name)
    assert e.value.code is ErrorCode.SCHEMA_INVALID
    assert e.value.details == {"field": "original_filename", "reason": reason}


def test_original_filename_is_stored_in_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "résumé.pdf")
    nfc = unicodedata.normalize("NFC", "résumé.pdf")
    assert nfd != nfc
    assert make_version(make_file(), name=nfd).original_filename == nfc


def test_blob_of_other_workspace_rejected() -> None:
    f = make_file()
    with pytest.raises(ValidationFailed):
        make_version(f, blob=make_blob(WorkspaceId(uuid4())))


def test_version_is_immutable() -> None:
    v = make_version(make_file())
    with pytest.raises(AttributeError):
        v.version_no = 9  # type: ignore[misc]
