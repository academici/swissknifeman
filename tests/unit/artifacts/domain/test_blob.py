from datetime import UTC, datetime
from uuid import uuid4

import pytest

from skm.kernel.ids import WorkspaceId
from skm.modules.artifacts.domain.blob import Blob, BlobAvailability, BlobId, ContentDigest
from skm.modules.artifacts.domain.storage_backend import BackendKind, BackendState, StorageBackend

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WS = WorkspaceId(uuid4())
DIGEST = ContentDigest("sha256:" + "a" * 64)


def make_blob(ws: WorkspaceId = WS) -> Blob:
    return Blob(BlobId(uuid4()), ws, DIGEST, 3, "text/plain", BlobAvailability.AVAILABLE, NOW, None)


@pytest.mark.parametrize("value", ["", "sha256:abc", "sha256:" + "A" * 64, "md5:" + "a" * 64])
def test_digest_format_enforced(value: str) -> None:
    with pytest.raises(ValueError, match="digest"):
        ContentDigest(value)


def test_negative_size_rejected() -> None:
    with pytest.raises(ValueError, match="size_bytes"):
        Blob(BlobId(uuid4()), WS, make_blob().digest, -1, "x/y", BlobAvailability.AVAILABLE, NOW, None)


def test_equal_digest_in_two_workspaces_are_two_blobs() -> None:
    a, b = make_blob(), make_blob(WorkspaceId(uuid4()))
    assert a.digest == b.digest
    assert a.id != b.id
    assert a.workspace_id != b.workspace_id


def test_backend_id_pattern() -> None:
    StorageBackend("local-primary", BackendKind.LOCAL, "paths.blobs_root", BackendState.ACTIVE)
    for bad in ("L", "1a", "a", "a_b", "x" * 33):
        with pytest.raises(ValueError, match="backend id"):
            StorageBackend(bad, BackendKind.LOCAL, "k", BackendState.ACTIVE)
