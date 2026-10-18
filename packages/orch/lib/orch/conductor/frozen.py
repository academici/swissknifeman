"""``run --frozen`` / ``resume --frozen``: the conductor runs from a snapshot of the orchestrator, not from the checkout it works on.

A piece that rewrites ``orch`` itself (a refactor of the conductor) changes the code of the process that conducts it. The snapshot
is the committed state (``git archive HEAD``) of the orchestrator checkout the command was started from: its ``packages`` and ``bridges``, in a folder under ``~/.cache/skm-frozen-runs`` that is removed when the run ends. The run itself
is the same command started again from the snapshot with the project it works on named by ``--project`` and every environment
variable that names a path inside the checkout (the install roots) pointing into the snapshot; the check commands
of the pieces do not inherit those roots (``checks.check_env``), so they test the project's own code. The work-source plugin
stays the one the configuration registers (its code is the project's, not part of the snapshot). ``resume --frozen`` takes a new
snapshot, which is how a mechanism fix reaches a run that was stopped on purpose."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import io
import time
from typing import Optional

from orch.settings import ORCH_ROOT
from aicore.util.proc import run as run_with_timeout

SNAPSHOT_PATHS = ("packages", "bridges")
CACHE = Path.home() / ".cache" / "skm-frozen-runs"


class FrozenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def hub_root() -> Path:
    """The git checkout the running orchestrator belongs to (the orchestrator lies under its ``packages``)."""
    found = run_with_timeout(["git", "-C", str(ORCH_ROOT), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=60)
    top = Path(found.stdout.strip()) if found.returncode == 0 and found.stdout.strip() else None
    if top is None or not (top / SNAPSHOT_PATHS[0]).is_dir() or top.resolve() not in ORCH_ROOT.resolve().parents:
        raise FrozenError("FROZEN_UNAVAILABLE", f"the orchestrator at {ORCH_ROOT} is not in a git checkout with a "
                          f"{SNAPSHOT_PATHS[0]} folder: --frozen needs one (run without it)")
    return top


def freeze(hub: Path, destination: Path) -> Path:
    """Unpack the committed state of ``SNAPSHOT_PATHS`` of ``hub`` into ``destination``."""
    present = [path for path in SNAPSHOT_PATHS if (hub / path).is_dir()]
    done = run_with_timeout(["git", "-C", str(hub), "archive", "--format=tar", "HEAD", *present], capture_output=True, timeout=300)
    if done.returncode:
        raise FrozenError("FROZEN_FAILED", f"git archive failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as archive:
        # the archive is our own committed HEAD; the "data" filter (refuse links out, absolute names) where Python has it
        archive.extractall(destination, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return destination


def strip(argv: list) -> list:
    """The command line without ``--frozen`` and without a ``--project`` (the relaunch names the project itself)."""
    kept, skip = [], False
    for token in argv:
        if skip:
            skip = False
        elif token == "--frozen":
            continue
        elif token == "--project":
            skip = True
        elif token.startswith("--project="):
            continue
        else:
            kept.append(token)
    return kept


def environment(snapshot: Path, hub: Path, base: Optional[dict] = None) -> dict:
    """The environment of the relaunch: every variable whose value is a path inside the checkout (the install roots of the
    orchestrator and its partners) points to the same place in the snapshot; ``PYTHONPATH`` is dropped (a path of the
    checkout would win over the snapshot's lib)."""
    env = dict(os.environ if base is None else base)
    env.pop("PYTHONPATH", None)
    hub = hub.resolve()
    for name, value in list(env.items()):
        if not value.startswith("/"):
            continue
        try:
            inside = Path(value).resolve().relative_to(hub)
        except (OSError, ValueError):
            continue
        env[name] = str(snapshot / inside)
    return env


def relaunch(argv: list, project: Path) -> int:
    """Take a snapshot, run the same command from it, remove the snapshot; the exit code is the command's."""
    hub = hub_root()
    CACHE.mkdir(parents=True, exist_ok=True)
    snapshot = CACHE / f"run-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    try:
        freeze(hub, snapshot)
        entry = snapshot / "packages/orch/scripts/conduct.py"
        command = [sys.executable, str(entry), "--project", str(project), *strip(argv)]
        print(f"frozen: running from a snapshot of {hub} at HEAD ({snapshot})", file=sys.stderr, flush=True)
        return subprocess.run(command, env=environment(snapshot, hub), cwd=str(project)).returncode  # no-timeout: this is the conductor run itself
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)
