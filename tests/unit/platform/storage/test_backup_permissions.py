"""Backup archives are private to their owner and a failed run leaves nothing behind."""

import os
import stat
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from skm.adapters.postgres.migrations.runner import packaged_baseline
from skm.kernel.errors import PreconditionFailed
from skm.platform.storage import backup


@pytest.fixture
def default_umask() -> Iterator[None]:
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def _write_like_pg_dump(path: Path) -> None:
    # pg_dump --file opens the path with fopen("wb"): the process umask decides a new file's mode.
    with path.open("wb") as stream:
        stream.write(b"PGDMP")


@contextmanager
def _export() -> Generator[backup.ExportedSnapshot]:
    snapshot = backup.Snapshot(uuid4(), 1, 180000, {}, (), [], packaged_baseline())
    yield backup.ExportedSnapshot(snapshot, _write_like_pg_dump)


@pytest.mark.usefixtures("default_umask")
def test_backup_files_are_owner_only(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    backup.create_backup(archive, tmp_path / "blobs", _export)

    modes = {item.name: stat.S_IMODE(item.stat().st_mode) for item in archive.iterdir()}
    assert modes[backup.DUMP] == 0o600
    assert set(modes.values()) == {0o600}


def test_failed_backup_leaves_no_partial_archive_and_can_be_retried(tmp_path: Path) -> None:
    def failing_dump(path: Path) -> None:
        _write_like_pg_dump(path)
        raise backup.invalid("pg_dump_failed")

    @contextmanager
    def failing_export() -> Generator[backup.ExportedSnapshot]:
        with _export() as exported:
            yield backup.ExportedSnapshot(exported.snapshot, failing_dump)

    archive = tmp_path / "archive"
    with pytest.raises(PreconditionFailed) as failed:
        backup.create_backup(archive, tmp_path / "blobs", failing_export)
    assert failed.value.details["reason"] == "pg_dump_failed"
    assert not archive.exists()

    backup.create_backup(archive, tmp_path / "blobs", _export)
    assert (archive / backup.MANIFEST).is_file()


def test_existing_output_is_refused_and_kept(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "keep").write_text("operator data")
    with pytest.raises(PreconditionFailed) as refused:
        backup.create_backup(archive, tmp_path / "blobs", _export)
    assert refused.value.details["reason"] == "backup_path_already_exists"
    assert (archive / "keep").read_text() == "operator data"


def test_termination_during_output_creation_removes_only_the_new_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import signal

    from skm.entrypoints.cli.errors import Terminated, sigterm_unwinds

    output = tmp_path / "archive"
    mkdir = Path.mkdir

    def interrupt(path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        mkdir(path, mode, parents, exist_ok)
        if path == output:
            signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(Path, "mkdir", interrupt)
    with sigterm_unwinds(), pytest.raises(Terminated):
        backup.create_backup(output, tmp_path, _export)
    assert not output.exists()
