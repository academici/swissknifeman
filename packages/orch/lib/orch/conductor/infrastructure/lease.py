"""Local ownership of runs, checkouts and question updates. Lock files are never unlinked."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl  # noqa: F401  (tests patch lease.fcntl.flock)
import hashlib
import json
import os
from pathlib import Path
import socket
import time  # noqa: F401  (tests patch lease.time.monotonic)
from typing import Optional

from aicore.util.lock import FileLock, probe_free  # FileLock is re-exported for the tests
from aicore.util.proc import GIT_TIMEOUT, run as run_with_timeout

from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import write_json


def _owner(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class RunLease:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.lock = FileLock(self.directory / "lease.lock")
        self.metadata = self.directory / "lease.json"

    @staticmethod
    def held(directory: Path) -> Optional[bool]:
        """``True`` held, ``False`` free, ``None`` unknown (the lock cannot be opened here)."""
        free = probe_free(Path(directory) / "lease.lock")
        return None if free is None else not free

    @staticmethod
    def owner(directory: Path) -> dict:
        return _owner(Path(directory) / "lease.json")

    def busy(self) -> Stop:
        owner = self.owner(self.directory)
        return Stop("RUN_BUSY", f"run {self.directory.name} is held by pid {owner.get('pid') or 'unknown'} "
                    f"on {owner.get('host') or 'unknown'} since {owner.get('started_at') or 'unknown'}; wait or stop it")

    def acquire(self, command: str):
        if not self.lock.acquire():
            raise self.busy()
        try:
            write_json(self.metadata, {"pid": os.getpid(), "host": socket.gethostname(),
                                      "started_at": clock.utc_now(), "command": command})
        except BaseException:
            self.release()
            raise
        return self

    def release(self) -> None:
        if self.lock.fd is not None:
            try:
                self.metadata.unlink(missing_ok=True)
            finally:
                self.lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def checkout_toplevel(project: Path) -> Path:
    """Git toplevel of ``project``, or ``project`` when git fails or exceeds ``GIT_TIMEOUT``."""
    result = run_with_timeout(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=GIT_TIMEOUT)
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else Path(project).resolve()


class CheckoutLock(RunLease):
    def __init__(self, runs_root: Path, toplevel: Path):
        self.toplevel = Path(toplevel).resolve()
        key = hashlib.sha256(os.fsencode(self.toplevel)).hexdigest()[:16]
        self.directory = Path(runs_root) / "checkouts"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = FileLock(self.directory / (key + ".lock"))
        self.metadata = self.directory / (key + ".json")

    def busy(self) -> Stop:
        owner = _owner(self.metadata)
        return Stop("WORKTREE_BUSY", f"checkout {self.toplevel} is driven by run {owner.get('run') or 'unknown'} "
                    f"(pid {owner.get('pid') or 'unknown'}); one conductor per checkout")

    def acquire(self, command: str, run_id: str = "unknown"):
        super().acquire(command)
        try:
            write_json(self.metadata, {**_owner(self.metadata), "run": run_id})
        except BaseException:
            self.release()
            raise
        return self


@contextmanager
def questions_lock(item_dir: Path):
    directory = Path(item_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock = FileLock(directory / "questions.lock")
    if not lock.acquire(blocking=True, timeout=10):
        raise Stop("QUESTIONS_LOCKED", f"{directory / 'questions.lock'} is held for more than 10 s")
    try:
        yield
    finally:
        lock.release()
