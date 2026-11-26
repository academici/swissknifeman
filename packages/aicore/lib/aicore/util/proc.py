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


# Default budgets (seconds) for the common kinds of child process.
GIT_TIMEOUT = 60
CLI_TIMEOUT = 120
TIMEOUT_RETURNCODE = 124   # the exit status of coreutils `timeout`


def run(argv, *, timeout, check=False, **kwargs):
    """``subprocess.run`` with a mandatory ``timeout`` that never raises ``TimeoutExpired``.

    A child that does not finish in ``timeout`` seconds is killed (the group, when ``start_new_session`` was asked
    for) and the result is a ``CompletedProcess`` with return code ``TIMEOUT_RETURNCODE`` and whatever output
    was read, so the return-code handling of the caller covers a hang too. With ``check=True`` that code raises
    ``CalledProcessError`` like any other failure.
    """
    import subprocess

    try:
        return subprocess.run(argv, timeout=timeout, check=check, **kwargs)
    except subprocess.TimeoutExpired as expired:
        text = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding")
                    or kwargs.get("errors"))

        def keep(value, empty):
            if value is None:
                return empty
            if text and isinstance(value, bytes):
                return value.decode("utf-8", "replace")
            return value

        empty = "" if text else b""
        stdout, stderr = keep(expired.stdout, empty), keep(expired.stderr, empty)
        note = f"timed out after {timeout}s: {argv[0] if argv else ''}"
        stderr = (stderr + ("\n" if stderr else "") + note) if text else stderr + note.encode("utf-8")
        result = subprocess.CompletedProcess(argv, TIMEOUT_RETURNCODE, stdout, stderr)
        if check:
            raise subprocess.CalledProcessError(TIMEOUT_RETURNCODE, argv, stdout, stderr) from expired
        return result
