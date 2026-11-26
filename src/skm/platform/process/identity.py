"""Diagnostic process facts by number; never a containment proof and never ownership.

These calls can observe a reused PID or PGID, and comparing an identity before ``kill_group`` is
check-then-kill. The authority to signal or reap a child lives in ``ownership.OwnedProcess``.
"""

import errno
import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ProcessIdentity", "group_alive", "identity_of", "is_same_process", "kill_group"]


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    start_ticks: int | None
    boot_id: str | None


def _read_stat_raw(pid: int) -> bytes:
    # Unbuffered FileIO reads the whole record without the Path wrapper overhead on hot group scans.
    with open(f"/proc/{pid}/stat", "rb", buffering=0) as stream:
        return stream.readall()


def _proc_pids() -> list[str]:
    with os.scandir("/proc") as entries:
        return [entry.name for entry in entries if entry.name.isdecimal()]


def _stat(pid: int) -> tuple[str, int, int]:
    # comm may contain spaces, newlines and closing parentheses. The last ')' closes it.
    raw = _read_stat_raw(pid)
    try:
        fields = raw.rsplit(b")", 1)[1].split()
        state = fields[0].decode("ascii")
        if len(state) != 1:
            raise ValueError("invalid process state")
        return state, int(fields[2]), int(fields[19])
    except (IndexError, ValueError) as error:
        raise OSError(errno.EIO, "malformed process identity") from error


def identity_of(pid: int) -> ProcessIdentity | None:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("pid must be a positive integer")
    try:
        if sys.platform == "linux":
            ticks = _stat(pid)[2]
            try:
                boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            except FileNotFoundError as error:
                raise OSError(errno.EIO, "boot identity unavailable") from error
            if not boot:
                raise OSError("boot identity unavailable")
            return ProcessIdentity(pid, ticks, boot)
        os.kill(pid, 0)
    except (FileNotFoundError, ProcessLookupError):
        return None
    return ProcessIdentity(pid, None, None)


def is_same_process(identity: ProcessIdentity) -> bool:
    current = identity_of(identity.pid)
    if current is None or current != identity:
        return False
    if sys.platform == "linux":
        try:
            return _stat(identity.pid)[0] not in ("Z", "X")
        except (FileNotFoundError, ProcessLookupError):
            return False
    return True


def kill_group(pgid: int, sig: int) -> None:
    if isinstance(pgid, bool) or not isinstance(pgid, int) or pgid <= 0:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("pgid must be a positive integer")
    with suppress(ProcessLookupError):
        os.killpg(pgid, sig)


def group_alive(pgid: int) -> bool:
    """Whether a group has runnable members. Permission/observation failures propagate.

    This checks only members still in the group, including those left after leader exit.
    It cannot detect descendants that have escaped with setsid().
    """
    if pgid <= 0:
        raise ValueError("pgid must be positive")
    if sys.platform == "linux":
        for name in _proc_pids():
            try:
                state, group, _ = _stat(int(name))
            except (FileNotFoundError, ProcessLookupError):
                continue
            if group == pgid and state not in ("Z", "X"):
                return True
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True
