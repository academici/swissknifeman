"""Local ownership of runs, checkouts and question updates. Lock files are never unlinked."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import write_json


class FileLock:
    """A flock on the inode currently at ``path``, on a descriptor closed by exec."""

    def __init__(self, path: Path, *, create: bool = True):
        self.path, self.create, self.fd = Path(path), create, None

    def acquire(self, blocking: bool = False, timeout=None) -> bool:
        if self.fd is not None:
            raise RuntimeError("lock already acquired")
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
            fd = os.open(self.path, flags | (os.O_CREAT if self.create else 0), 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    current = os.path.samestat(os.fstat(fd), os.stat(self.path))
                except FileNotFoundError:
                    current = False
                if current:
                    self.fd = fd
                    return True
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if not blocking or (deadline is not None and time.monotonic() >= deadline):
                    return False
                time.sleep(0.02)
            finally:
                if self.fd != fd:
                    os.close(fd)
            # A replaced inode is retried even for a nonblocking acquisition.
            if deadline is not None and time.monotonic() >= deadline:
                return False

    def release(self) -> None:
        if self.fd is not None:
            fd, self.fd = self.fd, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def probe_free(path: Path) -> bool:
    """Probe on a separate fd without creating a file or changing owner metadata."""
    lock = FileLock(path, create=False)
    try:
        return lock.acquire()
    except FileNotFoundError:
        return True
    finally:
        lock.release()


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
    def held(directory: Path) -> bool:
        return not probe_free(Path(directory) / "lease.lock")

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
    result = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
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
