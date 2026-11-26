"""Real process death around the replace boundary, without a simulated success."""

import multiprocessing
import os
from pathlib import Path

import pytest

from skm.platform.fs import atomic_write as io


@pytest.mark.parametrize("after_replace", [False, True])
def test_crash_before_or_after_replace_leaves_complete_file(tmp_path: Path, after_replace: bool) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"old")
    ctx = multiprocessing.get_context("fork")

    def crash() -> None:
        replace = os.replace

        def crash_replace(src: Path, dst: Path) -> None:
            if after_replace:
                replace(src, dst)
            os._exit(32)

        os.replace = crash_replace
        io.atomic_write(target, b"new" * 4096)

    process = ctx.Process(target=crash)
    process.start()
    process.join(timeout=3)
    assert process.exitcode == 32
    assert target.read_bytes() == (b"new" * 4096 if after_replace else b"old")
    orphans = list(tmp_path.glob(".*.tmp"))
    assert len(orphans) == (0 if after_replace else 1)
    if orphans:
        assert orphans[0].read_bytes() == b"new" * 4096
