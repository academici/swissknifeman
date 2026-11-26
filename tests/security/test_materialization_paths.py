"""Security and portable-vector tests for artifact materialization paths, races, and retries."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast, override
from uuid import UUID

import pytest

from skm.adapters.blobs.local.materializer import READY_MANIFEST_NAME, LocalMaterialWriter
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.materialization import (
    MaterialEntry,
    MaterialSource,
    plan_materialization,
)
from skm.platform.fs.safe_paths import UnsafePathError

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = REPO_ROOT / "tests/fixtures/corpus/examples" / "artifacts" / "materialization-security.json"


@dataclass(frozen=True, slots=True)
class _Src:
    file_version_id: UUID
    original_filename: str
    size_bytes: int
    digest: ContentDigest


def _digest(data: bytes) -> ContentDigest:
    return ContentDigest(f"sha256:{hashlib.sha256(data).hexdigest()}")


def _entry(vid: str | UUID, rel_name: str, data: bytes) -> MaterialEntry:
    uid = FileVersionId(UUID(str(vid)))
    return MaterialEntry(
        file_version_id=uid, relative_path=f"{uid}/{rel_name}", size_bytes=len(data), digest=_digest(data)
    )


def _load_vectors() -> dict[str, dict[str, object]]:
    doc = cast("dict[str, object]", json.loads(VECTORS_PATH.read_text(encoding="utf-8")))
    cases = cast("list[dict[str, object]]", doc["cases"])
    return {str(case["id"]): case for case in cases}


def test_security_vector_catalog_is_complete() -> None:
    cases = _load_vectors()
    expected_ids = {
        "portable-reserved",
        "portable-trailing-dot",
        "same-version-retry",
        "same-version-metadata-mismatch",
        "distinct-case-and-unicode",
        "intermediate-symlink-race",
        "hardlink-existing",
        "preexisting-other-content",
        "archive-bytes",
        "partial-download",
    }
    assert set(cases) == expected_ids


def test_portable_reserved_and_trailing_dot_vectors(tmp_path: Path) -> None:
    cases = _load_vectors()
    v_res = cases["portable-reserved"]
    v_dot = cases["portable-trailing-dot"]
    id1 = FileVersionId(UUID("0192f5ca-5001-7a01-8000-f8091a2b3c4e"))
    id2 = FileVersionId(UUID("0192f5ca-5002-7a01-8000-f8091a2b3c4e"))
    b1, b2 = b"con-bytes", b"trailing-dot-bytes"

    plan = plan_materialization(
        (
            _Src(id1, str(v_res["original_filename"]), len(b1), _digest(b1)),
            _Src(id2, str(v_dot["original_filename"]), len(b2), _digest(b2)),
        )
    )
    assert plan[0].relative_path == f"{id1}/{v_res['safe_material_name']}"
    assert plan[1].relative_path == f"{id2}/{v_dot['safe_material_name']}"

    root = tmp_path / "portable"
    writer = LocalMaterialWriter()
    writer.write(root, plan[0], BytesIO(b1))
    writer.write(root, plan[1], BytesIO(b2))
    writer.seal(root)

    for entry, expected in ((plan[0], b1), (plan[1], b2)):
        target = root / entry.relative_path
        st = os.lstat(target)
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o444
        assert (st.st_mode & 0o111) == 0
        assert target.read_bytes() == expected
    assert (root / READY_MANIFEST_NAME).is_file()
    assert stat.S_IMODE(os.lstat(root).st_mode) == 0o555


@pytest.mark.parametrize(
    "bad_rel",
    [
        "../escape.txt",
        "0192f5ca-5001-7a01-8000-f8091a2b3c4e/../../escape.txt",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "0192f5ca-5001-7a01-8000-f8091a2b3c4e/sub/nested.txt",
        "not-a-uuid/file.txt",
        "0192f5ca-5002-7a01-8000-f8091a2b3c4e/wrong_uuid.txt",
        f"0192f5ca-5001-7a01-8000-f8091a2b3c4e/{READY_MANIFEST_NAME}",
        "0192f5ca-5001-7a01-8000-f8091a2b3c4e/bad\x00.txt",
    ],
)
def test_materialization_path_traversal_refused(tmp_path: Path, bad_rel: str) -> None:
    vid = FileVersionId(UUID("0192f5ca-5001-7a01-8000-f8091a2b3c4e"))
    payload = b"traversal-attempt"
    forged = MaterialEntry(
        file_version_id=vid, relative_path=bad_rel, size_bytes=len(payload), digest=_digest(payload)
    )
    root = tmp_path / "workspace" / "materials"
    writer = LocalMaterialWriter()
    with pytest.raises((UnsafePathError, ValidationFailed)):
        writer.write(root, forged, BytesIO(payload))
    assert not (tmp_path / "workspace" / "escape.txt").exists()
    assert not (root / READY_MANIFEST_NAME).exists()


def test_same_version_retry_and_metadata_mismatch_vectors(tmp_path: Path) -> None:
    cases = _load_vectors()
    retry_vec = cases["same-version-retry"]
    vids = [UUID(v) for v in cast("list[str]", retry_vec["version_ids"])]
    data = b"immutable-version-content"

    # 1. Plan deduplicates identical version id + metadata
    plan = plan_materialization(tuple(_Src(v, "report.txt", len(data), _digest(data)) for v in vids))
    assert len(plan) == 1

    # 2. Mismatched metadata for same version id in plan -> INVALID_REFERENCE
    mismatch_vid = UUID(str(cases["same-version-metadata-mismatch"]["version_id"]))
    with pytest.raises(ValidationFailed) as plan_err:
        plan_materialization(
            (
                _Src(mismatch_vid, "report.txt", len(data), _digest(data)),
                _Src(mismatch_vid, "report.txt", len(data), _digest(b"different-25-byte-payload")),
            )
        )
    assert plan_err.value.code is ErrorCode.INVALID_REFERENCE

    # 3. Initial materialization + own-manifest verified retry reuse
    root = tmp_path / "retry_root"
    w1 = LocalMaterialWriter()
    w1.write(root, plan[0], BytesIO(data))
    w1.seal(root)
    orig_ino = os.lstat(root / plan[0].relative_path).st_ino

    w2 = LocalMaterialWriter()
    w2.write(root, plan[0], BytesIO(data))
    w2.seal(root)
    assert os.lstat(root / plan[0].relative_path).st_ino == orig_ino

    # 4. Retry with mismatched digest against existing own manifest -> INVALID_REFERENCE
    bad_entry = MaterialEntry(
        file_version_id=plan[0].file_version_id,
        relative_path=plan[0].relative_path,
        size_bytes=len(data),
        digest=_digest(b"different-25-byte-payload"),
    )
    w3 = LocalMaterialWriter()
    with pytest.raises(ValidationFailed) as retry_err:
        w3.write(root, bad_entry, BytesIO(b"different-25-byte-payload"))
    assert retry_err.value.code is ErrorCode.INVALID_REFERENCE

    # 5. Tampering with sealed file (making it hardlink nlink=2) fails own-manifest retry re-verification
    os.chmod(root, 0o700)
    ver_dir = root / str(plan[0].file_version_id)
    os.chmod(ver_dir, 0o700)
    outside_link = tmp_path / "hardlinked_after_seal.txt"
    os.link(root / plan[0].relative_path, outside_link)
    os.chmod(ver_dir, 0o555)  # noqa: S103
    os.chmod(root, 0o555)  # noqa: S103

    w4 = LocalMaterialWriter()
    with pytest.raises(UnsafePathError):
        w4.write(root, plan[0], BytesIO(data))


def test_distinct_case_and_unicode_vector_and_alias_collision(tmp_path: Path) -> None:
    vec = _load_vectors()["distinct-case-and-unicode"]
    versions = cast("list[dict[str, str]]", vec["versions"])
    inputs: list[MaterialSource] = []
    payloads: dict[str, bytes] = {}
    for idx, item in enumerate(versions):
        vid = UUID(item["id"])
        raw = f"payload-{idx}-{item['name']}".encode()
        inputs.append(_Src(vid, item["name"], len(raw), _digest(raw)))
        payloads[str(vid)] = raw

    plan = plan_materialization(inputs)
    assert len(plan) == 4
    assert len({e.relative_path.split("/")[0] for e in plan}) == 4

    root = tmp_path / "unicode_case"
    writer = LocalMaterialWriter()
    for entry in plan:
        writer.write(root, entry, BytesIO(payloads[str(entry.file_version_id)]))
    writer.seal(root)

    for entry in plan:
        p = root / entry.relative_path
        assert p.read_bytes() == payloads[str(entry.file_version_id)]
        assert stat.S_IMODE(os.lstat(p).st_mode) == 0o444


@pytest.mark.parametrize("stage", ["before_open", "before_publish"])
def test_intermediate_symlink_race_barriers_refused(tmp_path: Path, stage: str) -> None:
    outside = tmp_path / "outside_secret"
    outside.mkdir()
    victim = outside / "target.txt"
    victim.write_bytes(b"OUTSIDE-UNTOUCHED")

    vid = UUID("0192f5ca-5001-7a01-8000-f8091a2b3c4e")
    entry = _entry(vid, "target.txt", b"attacker-overwrite")
    root = tmp_path / "race_root"

    def swap_version_dir_with_symlink(anchored: Path, cur_entry: MaterialEntry) -> None:
        vdir = anchored / str(cur_entry.file_version_id)
        if vdir.exists():
            shutil.rmtree(vdir)
        vdir.symlink_to(outside)

    writer = (
        LocalMaterialWriter(before_open=swap_version_dir_with_symlink)
        if stage == "before_open"
        else LocalMaterialWriter(before_publish=swap_version_dir_with_symlink)
    )
    with pytest.raises(UnsafePathError):
        writer.write(root, entry, BytesIO(b"attacker-overwrite"))

    assert victim.read_bytes() == b"OUTSIDE-UNTOUCHED"
    assert not (root / READY_MANIFEST_NAME).exists()

    # Symlinked root itself is also refused
    sym_root = tmp_path / "sym_root"
    sym_root.symlink_to(outside)
    with pytest.raises(UnsafePathError):
        LocalMaterialWriter().write(sym_root, entry, BytesIO(b"attacker-overwrite"))
    assert victim.read_bytes() == b"OUTSIDE-UNTOUCHED"


def test_preexisting_hardlink_fifo_symlink_dir_and_foreign_file_refused(tmp_path: Path) -> None:
    vid = UUID("0192f5ca-5001-7a01-8000-f8091a2b3c4e")
    new_bytes = b"materialized-replacement"
    entry = _entry(vid, "item.txt", new_bytes)

    # 1. Preexisting hardlink (nlink == 2) -> UnsafePathError, linked source untouched
    outside_src = tmp_path / "linked_source.txt"
    outside_src.write_bytes(b"ORIGINAL-LINKED-BYTES")
    hl_root = tmp_path / "hl_root"
    (hl_root / str(vid)).mkdir(parents=True)
    os.link(outside_src, hl_root / entry.relative_path)
    with pytest.raises(UnsafePathError) as hl_err:
        LocalMaterialWriter().write(hl_root, entry, BytesIO(new_bytes))
    assert hl_err.value.reason == "hard_link"
    assert outside_src.read_bytes() == b"ORIGINAL-LINKED-BYTES"

    # 2. Preexisting foreign regular file -> INVALID_REFERENCE, no overwrite
    foreign_root = tmp_path / "foreign_root"
    foreign_file = foreign_root / entry.relative_path
    foreign_file.parent.mkdir(parents=True)
    foreign_file.write_bytes(b"FOREIGN-BYTES")
    with pytest.raises(ValidationFailed) as f_err:
        LocalMaterialWriter().write(foreign_root, entry, BytesIO(new_bytes))
    assert f_err.value.code is ErrorCode.INVALID_REFERENCE
    assert foreign_file.read_bytes() == b"FOREIGN-BYTES"

    # 3. Preexisting FIFO -> UnsafePathError without blocking
    fifo_root = tmp_path / "fifo_root"
    fifo_path = fifo_root / entry.relative_path
    fifo_path.parent.mkdir(parents=True)
    os.mkfifo(fifo_path)
    with pytest.raises(UnsafePathError) as fifo_err:
        LocalMaterialWriter().write(fifo_root, entry, BytesIO(new_bytes))
    assert fifo_err.value.reason == "not_regular"

    # 4. Preexisting symlink at leaf -> UnsafePathError, target untouched
    sym_root = tmp_path / "sym_leaf_root"
    sym_leaf = sym_root / entry.relative_path
    sym_leaf.parent.mkdir(parents=True)
    sym_leaf.symlink_to(outside_src)
    with pytest.raises(UnsafePathError) as sl_err:
        LocalMaterialWriter().write(sym_root, entry, BytesIO(new_bytes))
    assert sl_err.value.reason == "symlink"
    assert outside_src.read_bytes() == b"ORIGINAL-LINKED-BYTES"

    # 5. Preexisting directory at leaf -> UnsafePathError
    dir_root = tmp_path / "dir_leaf_root"
    (dir_root / entry.relative_path).mkdir(parents=True)
    with pytest.raises(UnsafePathError):
        LocalMaterialWriter().write(dir_root, entry, BytesIO(new_bytes))


def test_archive_bytes_stored_and_materialized_without_extraction(tmp_path: Path) -> None:
    tar_buf = BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tf:
        esc = tarfile.TarInfo(name="../escape_from_tar.txt")
        esc_bytes = b"escaped?"
        esc.size = len(esc_bytes)
        tf.addfile(esc, BytesIO(esc_bytes))
        sym = tarfile.TarInfo(name="passwd_link")
        sym.type = tarfile.SYMTYPE
        sym.linkname = "/etc/passwd"
        tf.addfile(sym)
    tar_bytes = tar_buf.getvalue()

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w") as zf:
        zf.writestr("../escape_from_zip.txt", "escaped-zip")
    zip_bytes = zip_buf.getvalue()

    e_tar = _entry("0192f5ca-5001-7a01-8000-f8091a2b3c4e", "bundle.tar", tar_bytes)
    e_zip = _entry("0192f5ca-5002-7a01-8000-f8091a2b3c4e", "bundle.zip", zip_bytes)
    root = tmp_path / "nested" / "archives"
    writer = LocalMaterialWriter()
    writer.write(root, e_tar, BytesIO(tar_bytes))
    writer.write(root, e_zip, BytesIO(zip_bytes))
    writer.seal(root)

    assert (root / e_tar.relative_path).read_bytes() == tar_bytes
    assert (root / e_zip.relative_path).read_bytes() == zip_bytes
    assert not (tmp_path / "nested" / "escape_from_tar.txt").exists()
    assert not (tmp_path / "nested" / "escape_from_zip.txt").exists()


class _BrokenStream(io.RawIOBase):
    @override
    def read(self, _size: int = -1) -> bytes:
        raise OSError("simulated upstream disconnect")


def test_partial_download_and_corrupt_second_entry_leave_no_ready_manifest(tmp_path: Path) -> None:
    e1 = _entry("0192f5ca-5001-7a01-8000-f8091a2b3c4e", "first.sh", b"#!/bin/sh\necho hi\n")
    e2 = _entry("0192f5ca-5002-7a01-8000-f8091a2b3c4e", "second.txt", b"expected-second-payload")

    # Case A: Digest mismatch on second entry
    root_a = tmp_path / "partial_digest"
    writer_a = LocalMaterialWriter()
    writer_a.write(root_a, e1, BytesIO(b"#!/bin/sh\necho hi\n"))
    with pytest.raises(ValidationFailed) as dm_err:
        writer_a.write(root_a, e2, BytesIO(b"truncated"))
    assert dm_err.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
    with pytest.raises(PreconditionFailed):
        writer_a.seal(root_a)
    assert not (root_a / READY_MANIFEST_NAME).exists()
    # Even executable shebang script in entry 1 has zero execute bits (0444)
    assert (os.lstat(root_a / e1.relative_path).st_mode & 0o111) == 0

    # Case B: Producer IO error mid-stream on second entry
    root_b = tmp_path / "partial_io"
    writer_b = LocalMaterialWriter()
    writer_b.write(root_b, e1, BytesIO(b"#!/bin/sh\necho hi\n"))
    with pytest.raises(OSError, match="simulated upstream disconnect"):
        writer_b.write(root_b, e2, cast("BinaryIO", _BrokenStream()))
    with pytest.raises(PreconditionFailed):
        writer_b.seal(root_b)
    assert not (root_b / READY_MANIFEST_NAME).exists()
    # Temp files in version 2 directory were unlinked
    assert list((root_b / str(e2.file_version_id)).iterdir()) == []
