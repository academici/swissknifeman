"""An ownership fact is not readable until its JSON bytes are complete."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from skm.bootstrap.host_services import WorkerReaper, build_host_storage
from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership, SessionHandle


def test_record_does_not_publish_an_empty_ownership_fact(tmp_path: Path, monkeypatch) -> None:
    unit = uuid4()
    ownership = ProcessOwnership(
        ProcessOwner(
            uuid4(), uuid4(), uuid4(), uuid4(), "step", unit, "n" * 32, str(tmp_path / "identities")
        ),
        "cgroup",
        "owned-test-unit",
    )
    started = datetime(2026, 11, 28, tzinfo=UTC)
    handle = SessionHandle("fake", str(unit), os.getpid(), 1, started, ownership)
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
    body = (tmp_path / "ownership-facts" / f"{unit}.json").read_bytes()
    assert json.loads(body)["pid"] == os.getpid()
    assert published_empty == []
