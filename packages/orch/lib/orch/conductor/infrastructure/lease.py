"""Local ownership of runs, checkouts and question updates. Lock files are never unlinked."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl  # noqa: F401  (tests patch lease.fcntl.flock)
import hashlib
import os
from pathlib import Path
import socket
import time  # noqa: F401  (tests patch lease.time.monotonic)
from typing import Optional

from aicore.util.lock import FileLock, probe_free  # FileLock is re-exported for the tests
from aicore.util.proc import GIT_TIMEOUT, run as run_with_timeout

from orch.conductor import process, records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock


LAUNCHERS = ("terminal", "detached", "gui", "supervisor", "autopilot")


def launcher() -> str:
    """What started this conductor: ``SKM_ORCH_LAUNCHER`` when it names one of ``LAUNCHERS``, else ``terminal``."""
    found = os.environ.get("SKM_ORCH_LAUNCHER", "").strip()
    return found if found in LAUNCHERS else "terminal"


def _owner(path: Path) -> dict:
    """The owner recorded beside a lock, ``{}`` when it is unknown: none is recorded, or the record cannot be read or
    does not match records/v1 lease (it only names the owner in a busy message)."""
    try:
        found = records.read(path, "lease") or {}
    except (OSError, Stop):
        return {}
    return {key: value for key, value in found.items() if key != "$schema"}


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
            # the identity of the owner is (pid, start_ticks, boot_id): a pid alone is never a reason to signal (I13)
            records.write(self.metadata, {"pid": os.getpid(), "host": socket.gethostname(),
                                          "started_at": clock.utc_now(), "command": command,
                                          "start_ticks": process.start_ticks(os.getpid()), "boot_id": process.boot_id(),
                                          "launcher": launcher()}, "lease")
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
            records.write(self.metadata, {**_owner(self.metadata), "run": run_id}, "lease")
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
