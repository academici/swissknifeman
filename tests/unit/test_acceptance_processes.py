import json
import os
import signal
import sys
from pathlib import Path

import pytest

from support import processes


def test_forced_acceptance_teardown_reaps_separate_process_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = """
import json, os, signal, subprocess, sys
from pathlib import Path

grandchild = subprocess.Popen(
    [sys.executable, "-c", "import signal; signal.pause()"], start_new_session=True
)
path = Path("ready.json.tmp")
path.write_text(json.dumps([os.getppid(), os.getpid(), grandchild.pid]))
path.replace("ready.json")
signal.pause()
"""
    worker = """
import os, signal, sys
from pathlib import Path

from skm.platform.process.ownership import launch

signal.signal(signal.SIGTERM, signal.SIG_IGN)
pipes, owned = launch((sys.executable, "-c", sys.argv[1]), cwd=Path.cwd(), env=os.environ)
signal.pause()
"""
    monkeypatch.setattr(processes, "_STOP_GRACE", 0.05)
    process = processes.ManagedProcess.launch(
        (sys.executable, "-c", worker, runtime),
        tmp_path,
        os.environ,
        tmp_path / "stdout",
        tmp_path / "stderr",
    )
    ready = tmp_path / "ready.json"
    try:
        processes._wait_until(ready.is_file, 5, "worker runtime and its child")
        pids = json.loads(ready.read_text())
        assert len({os.getpgid(pid) for pid in pids}) == len(pids)
        assert process.stop() == 128 + signal.SIGKILL
        for pid in pids:
            assert not Path(f"/proc/{pid}").exists(), f"process {pid} survived teardown"
    finally:
        process.stop(signal.SIGKILL)
