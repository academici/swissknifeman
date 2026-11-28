"""An ownership fact is not readable until its JSON bytes are complete."""

from __future__ import annotations

import json
import multiprocessing
import os
import signal
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from skm.bootstrap.host_services import WorkerReaper, build_host_storage
from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership, SessionHandle


def _handle(tmp_path: Path) -> SessionHandle:
    unit = uuid4()
    ownership = ProcessOwnership(
        ProcessOwner(
            uuid4(), uuid4(), uuid4(), uuid4(), "step", unit, "n" * 32, str(tmp_path / "identities")
        ),
        "cgroup",
        "owned-test-unit",
    )
    started = datetime(2026, 11, 28, tzinfo=UTC)
    return SessionHandle("fake", str(unit), os.getpid(), 1, started, ownership)


def test_record_does_not_publish_an_empty_ownership_fact(tmp_path: Path, monkeypatch) -> None:
    handle = _handle(tmp_path)
    published_empty: list[str] = []
    real_write = os.write

    def write(fd: int, data: bytes) -> int:
        try:
            name = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            name = ""
        if "/ownership-facts/" in name and name.endswith(".json") and Path(name).stat().st_size == 0:
            published_empty.append(name)
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", write)
    WorkerReaper(tmp_path, build_host_storage(tmp_path), resolve=lambda _: None).record(handle)
    body = (tmp_path / "ownership-facts" / f"{handle.request_id}.json").read_bytes()
    assert json.loads(body)["pid"] == os.getpid()
    assert published_empty == []


@pytest.mark.parametrize("published", [False, True])
def test_record_recovers_interrupted_replacement(
    tmp_path: Path, published: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ownership-facts"
    handle = _handle(tmp_path)
    storage = build_host_storage(tmp_path)
    WorkerReaper(tmp_path, storage, resolve=lambda _: None).record(handle)
    target = root / f"{handle.request_id}.json"
    new_ticks = 123

    def interrupt() -> None:
        real_sync, real_replace = os.fsync, os.replace

        def sync(fd: int) -> None:
            if not published and Path(os.readlink(f"/proc/self/fd/{fd}")).parent == root:
                os.kill(os.getpid(), signal.SIGKILL)
            real_sync(fd)

        def rename(src, dst, **kwargs) -> None:
            real_replace(src, dst, **kwargs)
            if published and dst == target:
                os.kill(os.getpid(), signal.SIGKILL)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(os, "fsync", sync)
            patch.setattr(os, "replace", rename)
            WorkerReaper(tmp_path, storage, resolve=lambda _: None).record(
                replace(handle, process_start_ticks=new_ticks)
            )

    child = multiprocessing.get_context("fork").Process(target=interrupt)
    child.start()
    try:
        child.join(10)
        assert child.exitcode == -signal.SIGKILL
    finally:
        if child.is_alive():
            child.kill()
            child.join()
    assert list(root.glob("*.json")) == [target]
    assert json.loads(target.read_bytes())["start_ticks"] == (
        new_ticks if published else handle.process_start_ticks
    )
    assert storage.snapshot(root, min_free_bytes=0).reserved_bytes > 0
    directory_syncs = []
    real_sync = os.fsync

    def observe_recovery(fd: int) -> None:
        if os.path.samefile(f"/proc/self/fd/{fd}", root):
            directory_syncs.append(fd)
        real_sync(fd)

    monkeypatch.setattr(os, "fsync", observe_recovery)
    assert storage.reconcile(root).reserved_bytes == 0
    assert directory_syncs
    assert list(root.iterdir()) == [target]
    assert target.stat().st_mode & 0o777 == 0o600
