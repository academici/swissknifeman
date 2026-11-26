"""OPS-NEW-04: disk admission and durable evidence share one host ledger."""

import errno
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import httpx
import pytest

from contracts.artifacts.test_blob_store import MAX, WS, Disk, identity, local_env
from contracts.runtimes import conftest as runtime
from integration.http.test_client_blobs import _BYTES, _WS, _client, _no_network, _reference
from skm.adapters.runtimes._cli_session.session import SessionLimits
from skm.bootstrap import lifecycle
from skm.bootstrap.host_services import build_host_storage
from skm.kernel.errors import BackendUnavailable
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.fs import storage_budget
from skm.platform.fs.storage_budget import StorageBudget
from support.service_runner import Instance

ROOTS = ("logs", "temp", "spool", "worktree", "build", "model-cache", "artifacts", "journal", "uploads")


def budget_for(disk: Disk, *, alive: bool | None = True) -> StorageBudget:
    return StorageBudget(
        disk.root / "locks", free_bytes=disk.free, identity=identity, owner_alive=lambda _: alive
    )


def test_all_roots_share_one_floor_during_concurrent_writes(tmp_path: Path) -> None:
    disk = Disk(tmp_path, 1 << 22)
    roots = [tmp_path / name for name in ROOTS]
    for root in roots:
        root.mkdir()
    release = Event()
    ready = [Event() for _ in roots]
    floor = 16_384

    def write(root: Path, entered: Event) -> None:
        with budget_for(disk).reserve(root, owner_id=root.name, max_bytes=8192, min_free_bytes=floor) as hold:
            hold.open_file(root / "capture").write(root.name.encode())
            entered.set()
            assert release.wait(10)

    with ThreadPoolExecutor(len(roots)) as pool:
        writers = [pool.submit(write, root, entered) for root, entered in zip(roots, ready, strict=True)]
        try:
            assert all(entered.wait(10) for entered in ready)
            budget = budget_for(disk)
            expected = len(roots) * (8192 + 2 * max(4096, os.statvfs(tmp_path).f_frsize))
            for root in roots:
                snapshot = budget.snapshot(root, min_free_bytes=0)
                assert snapshot.reserved_bytes == expected
                assert snapshot.available_bytes == snapshot.free_bytes - expected - floor
            (roots[0] / "capture").unlink()
            filler = tmp_path / "external-fill"
            filler.write_bytes(b"x" * (disk.free(tmp_path) - expected - floor + 1))
            assert budget.reconcile(tmp_path).reserved_bytes == expected
            for root in roots:
                with pytest.raises(BackendUnavailable) as refusal:
                    budget.reserve(root, owner_id="late-writer", max_bytes=1, min_free_bytes=0)
                assert refusal.value.details == {"reason": "disk_low"}
                assert not (root / "late-writer").exists()
        finally:
            release.set()
        for writer in writers:
            writer.result(timeout=10)
    assert budget_for(disk).snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


def test_unfinished_upload_blocks_other_producers_and_failed_uploads_reclaim_capacity(
    tmp_path: Path,
) -> None:
    env = local_env(tmp_path)
    disk = Disk(tmp_path, 1 << 22)
    env.disk = disk
    store = env.make()
    budget = budget_for(disk)
    kept = store.promote(store.stage(WS, [b"referenced"]))
    reference_bytes = env.final(kept).read_bytes()
    spool = tmp_path / "spool"
    entered, resume = Event(), Event()

    def unfinished() -> Iterator[bytes]:
        yield _BYTES[:32]
        entered.set()
        assert resume.wait(10)
        yield _BYTES[32:]

    def broken() -> Iterator[bytes]:
        yield b"partial"
        raise RuntimeError("producer disconnected")

    def receive(request: httpx.Request) -> httpx.Response:
        assert request.read() == _BYTES
        return httpx.Response(201, json=_reference())

    with (
        httpx.Client(transport=httpx.MockTransport(receive)) as first_http,
        httpx.Client(transport=httpx.MockTransport(_no_network)) as refused_http,
        ThreadPoolExecutor(1) as pool,
    ):
        first = _client(spool, budget, first_http, min_free_bytes=4096)
        peer = _client(spool, budget_for(disk), refused_http)
        started = pool.submit(first.upload_blob, _WS, unfinished(), size=len(_BYTES))
        try:
            assert entered.wait(10)
            active = budget.snapshot(env.root, min_free_bytes=0)
            assert active.reserved_bytes >= len(_BYTES)
            # Limit physical headroom while both writers still see the same held upload ceiling.
            disk.capacity -= active.available_bytes
            with pytest.raises(BackendUnavailable) as denied:
                peer.upload_blob(_WS, [b"peer"], size=4)
            assert denied.value.details == {"reason": "disk_low"}
            with pytest.raises(BackendUnavailable) as denied_stage:
                store.stage(WS, [b"peer"])
            assert denied_stage.value.details == {"reason": "disk_low"}
            assert len(list(spool.iterdir())) == 1
            assert env.parts() == []
        finally:
            resume.set()
        assert started.result(timeout=10).size == len(_BYTES)
        assert not list(spool.iterdir())
        disk.capacity = 1 << 22
        for _ in range(3):
            with pytest.raises(RuntimeError, match="producer disconnected"):
                peer.upload_blob(_WS, broken(), size=len(_BYTES))
            with pytest.raises(RuntimeError, match="producer disconnected"):
                store.stage(WS, broken())
            assert not list(spool.iterdir())
            assert env.parts() == []
            assert budget.snapshot(spool, min_free_bytes=0).reserved_bytes == 0
    assert env.final(kept).read_bytes() == reference_bytes


@pytest.mark.parametrize("flood", ["stderr", "unterminated-stdout"])
def test_runtime_stream_pressure_never_produces_completed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flood: str
) -> None:
    disk = Disk(tmp_path, 1 << 20)
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(runtime, "budget_for", lambda _: budget_for(disk))
    stdout, stderr = b'{"type":"fake_result","final_text":"done"}\n', b""
    if flood == "stderr":
        stderr = b"untrusted noise\n" * 4096
    else:
        stdout = b'{"type":"text_delta","text":"' + b"x" * 65_536
    harness = runtime.build(
        tmp_path, stdout=stdout, stderr=stderr, limits=SessionLimits(max_stream_bytes=4096)
    )
    assert harness.budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 4096
    result = harness.session.result()
    assert result.outcome == "failed"
    assert result.failure is not None
    assert result.failure.details == {"reason": "stream_too_large"}
    assert result.observation is not None
    assert result.observation.capture.truncated
    assert sum(p.stat().st_size for p in harness.writer.step_dir.iterdir()) <= 4096
    assert len(harness.session.tail.pending) <= 4096
    assert harness.budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


def test_dead_writer_keeps_reserve_until_ownership_can_be_proven(tmp_path: Path) -> None:
    disk = Disk(tmp_path, 1 << 20)
    child_code = """
import os
import sys
from pathlib import Path
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity

root = Path(sys.argv[1])
budget = StorageBudget(root / 'locks', free_bytes=lambda _: 1 << 20,
                       identity=lambda: StorageOwnerIdentity('test-boot', os.getpid(), 'child'),
                       owner_alive=lambda _: True)
held = budget.reserve(root, owner_id='crashed-upload', max_bytes=32768, min_free_bytes=4096)
held.open_file(root / 'unfinished').write(b'partial evidence')
os._exit(73)
"""
    dead = subprocess.run([sys.executable, "-c", child_code, str(tmp_path)], check=False, timeout=10)
    assert dead.returncode == 73
    evidence = tmp_path / "unfinished"
    unknown = budget_for(disk, alive=None).reconcile(tmp_path)
    assert unknown.reserved_bytes > 32_768
    assert unknown.unknown_owners == ("crashed-upload",)
    assert budget_for(disk).reconcile(tmp_path).reserved_bytes == unknown.reserved_bytes
    assert budget_for(disk, alive=False).reconcile(tmp_path).reserved_bytes == 0
    assert evidence.read_bytes() == b"partial evidence"


@pytest.mark.parametrize("operation", ["enospc", "fsync"])
def test_upload_io_failure_never_issues_a_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    env = local_env(tmp_path)
    store = env.make()
    good = store.promote(store.stage(WS, [b"keep"]))
    failure = errno.ENOSPC if operation == "enospc" else errno.EIO
    original_write, original_sync = os.write, os.fsync

    def is_staging(fd: int) -> bool:
        return os.readlink(f"/proc/self/fd/{fd}").endswith(".part")

    def write(fd: int, data: bytes) -> int:
        if is_staging(fd):
            raise OSError(failure, "injected write failure")
        return original_write(fd, data)

    def sync(fd: int) -> None:
        if is_staging(fd):
            raise OSError(failure, "injected sync failure")
        original_sync(fd)

    with monkeypatch.context() as fault:
        if operation == "enospc":
            fault.setattr(os, "write", write)
        else:
            fault.setattr(os, "fsync", sync)
        with pytest.raises(OSError, match=r"injected .* failure") as refused:
            store.stage(WS, [b"must not be accepted"])
        assert refused.value.errno == failure
    assert env.parts() == []
    assert env.final(good).read_bytes() == b"keep"
    held = env.budget().snapshot(env.root, min_free_bytes=0).reserved_bytes
    if operation == "fsync":
        assert held >= MAX
    else:
        # The failed write was followed by a successful close and removal of its partial file.
        assert held == 0
    assert env.budget(alive=False).reconcile(env.root).reserved_bytes == 0


def test_cross_filesystem_promote_refuses_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = local_env(tmp_path)
    store = env.make()
    reference = store.promote(store.stage(WS, [b"keep"]))
    staged = store.stage(WS, [b"not published"])

    def cross_device(*_args, **_kwargs):
        raise OSError(errno.EXDEV, "injected cross-filesystem link")

    monkeypatch.setattr(os, "link", cross_device)
    with pytest.raises(OSError, match="cross-filesystem link") as refusal:
        store.promote(staged)
    assert refusal.value.errno == errno.EXDEV
    assert env.parts() == []
    assert set(env.root.glob("*/objects/*/*")) == {env.final(reference)}
    assert env.final(reference).read_bytes() == b"keep"


def test_ledger_write_failure_and_corruption_prevent_ingress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = local_env(tmp_path)
    store = env.make()
    good = store.promote(store.stage(WS, [b"keep"]))
    ledger = env.ledger / "storage-budget.json"

    def cannot_write(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "ledger is full")

    with monkeypatch.context() as fault:
        fault.setattr(storage_budget, "atomic_write", cannot_write)
        with pytest.raises(OSError, match="ledger is full") as unavailable:
            store.stage(WS, [b"no ledger admission"])
        assert unavailable.value.errno == errno.ENOSPC
    ledger.write_text('{"version":1,"reservations":[],"checksum":"damaged"}')
    with pytest.raises(BackendUnavailable) as corrupt:
        store.stage(WS, [b"no trustworthy ledger"])
    assert corrupt.value.details == {"reason": "storage_ledger_corrupt"}
    assert env.parts() == []
    assert env.final(good).read_bytes() == b"keep"


def local_service(root: Path) -> lifecycle.LocalProcesses:
    config = load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://127.0.0.1:5432/unused"}, root)
    return lifecycle.LocalProcesses(replace(config, state_dir=root / "state"))


def test_low_disk_refuses_local_log_writer_before_spawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import shutil
    from types import SimpleNamespace

    service = local_service(tmp_path)
    state = service.config.state_dir
    disk = Disk(tmp_path, 65_536)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=disk.free(Path(path))))
    monkeypatch.setattr(lifecycle, "_LOCAL_LOG_BYTES", 4096)
    budget = build_host_storage(state)

    def unexpected_spawn(*_args, **_kwargs):
        pytest.fail("local worker spawned with no durable reserve for its log")

    monkeypatch.setattr(lifecycle.subprocess, "Popen", unexpected_spawn)
    with budget.reserve(state, owner_id="in-flight-upload", max_bytes=8192, min_free_bytes=4096):
        snapshot = budget.snapshot(state, min_free_bytes=0)
        (tmp_path / "external").write_bytes(b"x" * (snapshot.available_bytes + 1))
        with service.lock().hold(timeout_seconds=1), pytest.raises(BackendUnavailable) as refused:
            lifecycle._run_local_service(
                state, state / "pids/worker.pid", {"role": "worker"}, [sys.executable, "-c", "pass"]
            )
        assert refused.value.details == {"reason": "disk_low"}
        assert not (state / "logs/worker.log").exists()


@pytest.mark.parametrize("fault", ["cap", "enospc", "fsync"])
def test_local_child_log_reservation_lives_through_writes_and_close(tmp_path: Path, fault: str) -> None:
    service = local_service(tmp_path)
    state = service.config.state_dir
    log = service.logs / "worker.log"
    budget = build_host_storage(state)
    gate, drained = tmp_path / "write", tmp_path / "drained"
    # Python loads this fixture in the detached owner so the actual pipe and ledger stay in use.
    (tmp_path / "sitecustomize.py").write_text(
        "import errno, os\n"
        "write, sync = os.write, os.fsync\n"
        "def fail_write(fd, data):\n"
        f"    if data and data[0] == 88 and os.readlink(f'/proc/self/fd/{{fd}}') == {str(log)!r}:\n"
        "        raise OSError(errno.ENOSPC, 'log full')\n"
        "    return write(fd, data)\n"
        "def fail_sync(fd):\n"
        f"    if os.readlink(f'/proc/self/fd/{{fd}}') == {str(log)!r}:\n"
        "        raise OSError(errno.EIO, 'log sync failed')\n"
        "    sync(fd)\n"
        + {"cap": "", "enospc": "os.write = fail_write\n", "fsync": "os.fsync = fail_sync\n"}[fault]
    )
    child = (
        "import pathlib, sys, time\n"
        "gate, drained = map(pathlib.Path, sys.argv[1:])\n"
        "print('out', flush=True); print('err', file=sys.stderr, flush=True)\n"
        "while not gate.exists(): time.sleep(0.01)\n"
        f"sys.stdout.buffer.write(b'X' * {2 * lifecycle._LOCAL_LOG_BYTES})\n"
        "sys.stdout.flush(); drained.touch()\n"
    )

    def read_reserved() -> int:
        return budget.snapshot(state, min_free_bytes=0).reserved_bytes

    with service.lock().hold(timeout_seconds=1):
        proc = service.start(
            "worker",
            [sys.executable, "-c", child, str(gate), str(drained)],
            {**os.environ, "PYTHONPATH": str(tmp_path)},
        )
        try:
            Instance.wait_until(lambda: log.stat().st_size >= 8, timeout=10, description="child log output")
            assert service.lookup("worker") == proc
            assert log.read_bytes() == b"out\nerr\n"
            assert read_reserved() > lifecycle._LOCAL_LOG_BYTES
            ledger = json.loads((state / "locks/storage-budget.json").read_text())
            (entry,) = ledger["reservations"]
            assert entry["identity"]["pid"] not in {os.getpid(), proc.identity.pid}
            assert entry["paths"] == [{"path": str(log), "dev": log.stat().st_dev, "ino": log.stat().st_ino}]
            gate.touch()
            if fault == "enospc":
                Instance.wait_until(
                    lambda: service.lookup("worker") is None,
                    timeout=10,
                    description="write failure stops child",
                )
                assert log.read_bytes() == b"out\nerr\n"
                assert not drained.exists()
            else:
                Instance.wait_until(drained.exists, timeout=10, description="child finished writing past cap")
                assert log.read_bytes() == b"out\nerr\n" + b"X" * (lifecycle._LOCAL_LOG_BYTES - 8)
            if fault == "fsync":
                with lifecycle.FileLock(state / "pids/worker.log.lock").hold(timeout_seconds=10):
                    assert read_reserved() > lifecycle._LOCAL_LOG_BYTES
                Instance.wait_until(
                    lambda: budget.reconcile(state).reserved_bytes == 0,
                    timeout=10,
                    description="reconcile after log owner exits",
                )
            else:
                Instance.wait_until(lambda: read_reserved() == 0, timeout=10, description="durable log close")
        finally:
            service.stop("worker", grace=0)


@pytest.mark.parametrize("operation", ["enospc", "fsync"])
def test_runtime_success_is_suppressed_when_transcript_cannot_be_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    harness = runtime.build(tmp_path, limits=SessionLimits(max_stream_bytes=4096))
    capture = harness.writer.step_dir / "stream.jsonl"
    original_write, original_sync = os.write, os.fsync

    def write(fd: int, data: bytes) -> int:
        if os.readlink(f"/proc/self/fd/{fd}") == str(capture):
            raise OSError(errno.ENOSPC, "output device filled")
        return original_write(fd, data)

    def sync(fd: int) -> None:
        if os.readlink(f"/proc/self/fd/{fd}") == str(capture):
            raise OSError(errno.EIO, "output fsync failed")
        original_sync(fd)

    with monkeypatch.context() as fault:
        if operation == "enospc":
            fault.setattr(os, "write", write)
        else:
            fault.setattr(os, "fsync", sync)
        result = harness.session.result()
    assert result.outcome == "failed"
    assert result.failure is not None
    assert not result.final_text
    assert harness.writer.failed
    assert result.observation is not None
    assert "capture_gap" in result.observation.capture.gaps
