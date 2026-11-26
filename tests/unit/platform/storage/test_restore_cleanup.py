"""A restore that fails before staging removes its directory, which holds a full copy of the blobs."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from skm.adapters.postgres.migrations.runner import packaged_baseline
from skm.kernel.errors import PreconditionFailed
from skm.platform.storage import backup, restore

_WORKSPACE = str(uuid4())
_CONTENT = b"blob bytes " * 1000


def _dump(path: Path) -> None:
    path.write_bytes(b"PGDMP")


def _archive(tmp_path: Path) -> restore.VerifiedBackup:
    blob = backup.Blob(_WORKSPACE, "sha256:" + sha256(_CONTENT).hexdigest(), len(_CONTENT))
    source = tmp_path / "blobs" / blob.key
    source.parent.mkdir(parents=True)
    source.write_bytes(_CONTENT)

    @contextmanager
    def export() -> Generator[backup.ExportedSnapshot]:
        snapshot = backup.Snapshot(uuid4(), 1, 180000, {}, (blob,), [], packaged_baseline())
        yield backup.ExportedSnapshot(snapshot, _dump)

    directory = tmp_path / "archive"
    backup.create_backup(directory, tmp_path / "blobs", export)
    manifest = json.loads((directory / backup.MANIFEST).read_text())
    closure = json.loads((directory / backup.CLOSURE).read_text())
    return restore.VerifiedBackup(directory, manifest, "sha256:" + "0" * 64, closure, (blob,))


def test_failure_before_staging_removes_the_copied_blobs(tmp_path: Path) -> None:
    archive, parent = _archive(tmp_path), tmp_path / "restores"
    (archive.directory / backup.DUMP).write_bytes(b"PGDMP tampered")

    def stage(*_: object) -> None:
        raise AssertionError("a dump with the wrong digest must not be staged")

    with pytest.raises(PreconditionFailed) as failed:
        restore.restore_backup(archive, parent, stage)
    assert failed.value.details["reason"] == "dump_checksum_mismatch"
    assert list(parent.iterdir()) == []


def test_failure_while_staging_keeps_the_quarantine_directory(tmp_path: Path) -> None:
    # A staging database may already record this directory (test_lost_token_commit_remains_quarantined).
    archive, parent = _archive(tmp_path), tmp_path / "restores"

    def stage(*_: object) -> None:
        raise backup.invalid("staging_database_failed")

    with pytest.raises(PreconditionFailed):
        restore.restore_backup(archive, parent, stage)
    (staging,) = parent.iterdir()
    assert (staging / restore.MARKER).is_file()


def test_successful_stage_keeps_its_profile(tmp_path: Path) -> None:
    archive, parent = _archive(tmp_path), tmp_path / "restores"

    def stage(_: restore.VerifiedBackup, paths: restore.RestorePaths, *__: object) -> None:
        paths.profile.write_text("profile")

    result = restore.restore_backup(archive, parent, stage)
    assert Path(str(result["profile"])).read_text() == "profile"


def test_incomplete_staging_records_ignore_a_finished_profile(tmp_path: Path) -> None:
    parent = tmp_path / "restores"
    leftover = parent / "left"
    leftover.mkdir(parents=True)
    restore.write_staging_record(leftover, "postgresql://u:p@127.0.0.1:1/skm_left", 32)
    done = parent / "done"
    done.mkdir()
    restore.write_staging_record(done, "postgresql://u:p@127.0.0.1:1/skm_done", 33)
    (done / "bootstrap.toml").write_text("ok", encoding="utf-8")
    assert "postgresql" not in (leftover / restore.STAGING_RECORD).read_text()
    found = restore.incomplete_staging_records(parent)
    assert [item[1].name for item in found] == ["skm_left"]
    assert restore.is_incomplete_restore(leftover)
    assert not restore.is_incomplete_restore(done)


def test_old_name_only_journals_do_not_authorize_cleanup(tmp_path: Path) -> None:
    (tmp_path / restore.STAGING_RECORD).write_text(
        json.dumps({"name": "stage", "url": "postgresql://u@localhost/stage"})
    )
    assert restore.read_staging_record(tmp_path) is None
