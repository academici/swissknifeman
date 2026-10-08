"""Shared stdlib-only process helpers."""
import os


def pid_alive(pid):
    """Return process liveness, or ``None`` when no PID is supplied.

    Unreadable or malformed PIDs conservatively count as alive.
    """
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, ValueError, OverflowError):
        return True
