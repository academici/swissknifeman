"""Exercise no-clobber publication, local lock and fault boundaries on real descriptors."""

import errno
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from multiprocessing.synchronize import Event
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import HostId


def test_two_publishers_never_clobber(tmp_path: Path) -> None:
    fs = LocalVaultFs(tmp_path)
    start = Barrier(2)

    def publish(body: bytes) -> bool:
        start.wait(timeout=5)
        return fs.create_new("folder/out.md", body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        bodies = (b"left", b"right")
        results = tuple(pool.map(publish, bodies))
    assert sum(results) == 1
    assert fs.read_bounded("folder/out.md", max_bytes=20, durable=True) == bodies[results.index(True)]
    assert {path.name for path in (tmp_path / "folder").iterdir()} == {"out.md"}


@pytest.mark.parametrize(
    ("failure", "expected", "exists"),
    [
        ("file_fsync", "failed_without_effect", False),
        ("after_link", "outcome_unknown", True),
        ("directory_fsync", "outcome_unknown", True),
    ],
)
def test_publication_faults_report_the_effect_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected: str,
    exists: bool,
) -> None:
    fs = LocalVaultFs(tmp_path)
    fsync, link = os.fsync, os.link
    linked = False

    def fail_fsync(fd: int) -> None:
        if failure == "file_fsync" and stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "injected file fsync")
        if failure == "directory_fsync" and linked and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "injected directory fsync")
        fsync(fd)

    def fail_link(
        src: str,
        dst: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        nonlocal linked
        link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, follow_symlinks=follow_symlinks)
        linked = True
        if failure == "after_link":
            raise OSError(errno.EIO, "injected after link")

    with monkeypatch.context() as fault:
        fault.setattr(os, "fsync", fail_fsync)
        fault.setattr(os, "link", fail_link)
        with pytest.raises(SkmError) as err:
            fs.create_new("sub/out.md", b"expected")
        assert err.value.details["outcome"] == expected
    assert (tmp_path / "sub/out.md").exists() == exists
    assert fs.read_bounded("sub/out.md", max_bytes=10, durable=True) == (b"expected" if exists else None)


def test_binding_probes_required_backend_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    fs = LocalVaultFs(root, tmp_path)

    def no_hardlinks(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOTSUP, "hardlinks unavailable")

    monkeypatch.setattr(os, "link", no_hardlinks)
    with pytest.raises(SkmError, match="Unsupported vault filesystem") as err:
        fs.update_identity(HostId(uuid4()), fork=False, deadline_seconds=1)
    assert err.value.code == ErrorCode.BACKEND_UNAVAILABLE
    assert list(root.iterdir()) == []


def test_verified_existing_reflushes_file_and_parent_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fs = LocalVaultFs(tmp_path)
    assert fs.create_new("one/two/note.md", b"note")
    original = os.fsync
    synced: list[int] = []

    def record(fd: int) -> None:
        synced.append(os.fstat(fd).st_ino)
        original(fd)

    monkeypatch.setattr(os, "fsync", record)
    assert fs.read_bounded("one/two/note.md", max_bytes=4, durable=True) == b"note"
    assert synced == [(tmp_path / path).stat().st_ino for path in ("one/two/note.md", "one/two", "one", ".")]


def _hold_writer_lock(root: Path, state: Path, vault_id: UUID, entered: Event, release: Event) -> None:
    with LocalVaultFs(root, state).lock(vault_id, deadline_seconds=1):
        entered.set()
        if not release.wait(timeout=10):
            raise RuntimeError("test did not release the writer lock")


def test_writer_lock_serializes_distinct_processes(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    vault_id = uuid4()
    fs = LocalVaultFs(root, tmp_path)
    spawn = get_context("spawn")
    entered, release = spawn.Event(), spawn.Event()
    writer = spawn.Process(target=_hold_writer_lock, args=(root, tmp_path, vault_id, entered, release))
    writer.start()
    try:
        assert entered.wait(timeout=5)
        with pytest.raises(SkmError) as error, fs.lock(vault_id, deadline_seconds=0):
            pytest.fail("second process acquired the writer lock")
        assert error.value.code == ErrorCode.BACKEND_UNAVAILABLE
    finally:
        release.set()
        writer.join(timeout=10)
        if writer.is_alive():
            writer.terminate()
            writer.join(timeout=5)
    assert writer.exitcode == 0
    with fs.lock(vault_id, deadline_seconds=0):
        assert fs.create_new("note.md", b"new writer")


def test_explicit_writer_transfer_requires_the_new_local_state(tmp_path: Path) -> None:
    root, old_state, new_state = (tmp_path / folder for folder in ("vault", "old-state", "new-state"))
    for folder in (root, old_state, new_state):
        folder.mkdir()
    first, second = HostId(uuid4()), HostId(uuid4())
    old_fs, new_fs = LocalVaultFs(root, old_state), LocalVaultFs(root, new_state)
    original = old_fs.update_identity(first, fork=False, deadline_seconds=1)
    with pytest.raises(SkmError, match="writer binding"):
        new_fs.require_writer(second)
    transferred = new_fs.update_identity(second, fork=False, deadline_seconds=1)
    assert transferred.vault_id == original.vault_id
    assert new_fs.require_writer(second) == transferred
    with pytest.raises(SkmError, match="writer binding"):
        old_fs.require_writer(first)
