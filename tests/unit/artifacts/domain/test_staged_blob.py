from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.staged_blob import (
    StagedBlob,
    StagedBlobId,
    consume,
    is_expired,
    staged_blob_ref,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WS = WorkspaceId(uuid4())
USER = PrincipalId(uuid4())
DIGEST = ContentDigest("sha256:" + "a" * 64)


def make_staged(**over: object) -> StagedBlob:
    fields: dict[str, object] = {
        "id": StagedBlobId(uuid4()),
        "workspace_id": WS,
        "digest": DIGEST,
        "size_bytes": 3,
        "media_type": "text/plain",
        "detected_media_type": "text/plain",
        "backend_id": "local-primary",
        "storage_key": "staging/x",
        "created_by": USER,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
        "consumed_at": None,
        "consumed_request_id": None,
    }
    fields.update(over)
    return StagedBlob(**fields)  # type: ignore[arg-type]


def test_ref_exposes_no_storage_location() -> None:
    ref = staged_blob_ref(make_staged())
    assert set(ref) == {"staged_blob_id", "workspace_id", "digest", "size", "media_type"}


def test_consume_marks_request() -> None:
    s = make_staged()
    out = consume(s, staged_blob_ref(s), WS, "req-1", NOW)
    assert (out.consumed_at, out.consumed_request_id) == (NOW, "req-1")


def test_consume_twice_conflicts() -> None:
    s = make_staged()
    done = consume(s, staged_blob_ref(s), WS, "r", NOW)
    with pytest.raises(Conflict) as e:
        consume(done, staged_blob_ref(done), WS, "r2", NOW)
    assert e.value.code is ErrorCode.STAGED_BLOB_CONSUMED


def test_consume_expired() -> None:
    s = make_staged()
    assert is_expired(s, NOW + timedelta(hours=1))
    with pytest.raises(PreconditionFailed) as e:
        consume(s, staged_blob_ref(s), WS, "r", NOW + timedelta(hours=2))
    assert e.value.code is ErrorCode.STAGED_BLOB_EXPIRED


def test_consumed_is_not_expired() -> None:
    s = make_staged(consumed_at=NOW)
    assert not is_expired(s, NOW + timedelta(days=9))


def test_other_workspace_forbidden() -> None:
    s = make_staged()
    with pytest.raises(Forbidden):
        consume(s, staged_blob_ref(s), WorkspaceId(uuid4()), "r", NOW)
    ref = {**staged_blob_ref(s), "workspace_id": str(uuid4())}
    with pytest.raises(Forbidden):
        consume(s, ref, WS, "r", NOW)


def test_digest_or_size_mismatch() -> None:
    s = make_staged()
    ref = staged_blob_ref(s)
    for bad in ({**ref, "size": 4}, {**ref, "digest": ContentDigest("sha256:" + "b" * 64).value}):
        with pytest.raises(ValidationFailed) as e:
            consume(s, bad, WS, "r", NOW)
        assert e.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
    assert replace(s).id == s.id
