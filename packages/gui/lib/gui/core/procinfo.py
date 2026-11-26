"""Start time of a process, to tell a PID from a reused one (I11); stdlib.

Linux: field 22 of ``/proc/<pid>/stat`` (clock ticks since boot). macOS: ``ps -o lstart= -p <pid>``. ``None``
when the process does not exist or the time cannot be read.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional


def start_time(pid: int) -> Optional[str]:
    if pid <= 0:
        return None
    if sys.platform.startswith("linux"):
        try:
            with open(f"/proc/{pid}/stat", "rb") as handle:
                raw = handle.read().decode("ascii", "replace")
        except OSError:
            return None
        # The command name (field 2) is in parentheses and may contain spaces: split after the last ')'.
        fields = raw[raw.rfind(")") + 2:].split()
        return fields[19] if len(fields) > 19 else None
    try:
        result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
                                env={"LC_ALL": "C", "PATH": os.environ.get("PATH", "/bin:/usr/bin")})
    except (OSError, subprocess.SubprocessError):
        return None
    text = result.stdout.strip()
    return text or None


def same_process(pid: int, started: Optional[str]) -> bool:
    """Whether ``pid`` is alive and is the process that had ``started``."""
    return started is not None and start_time(pid) == started
