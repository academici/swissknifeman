"""The signals that end a conductor run like Ctrl-C (``application/loop.py`` installs them for the time of its loop)."""
from __future__ import annotations

import signal
import threading


def terminated(_signum, _frame) -> None:
    """SIGTERM/SIGHUP end the run like Ctrl-C: the role and check processes of the run are killed by the code that waits
    for them (a plain SIGTERM would leave the executor ``claude -p`` and its test workers running)."""
    raise KeyboardInterrupt


def interruptible() -> dict:
    """Install ``terminated`` for SIGTERM and SIGHUP, and for SIGINT when it is ignored, and return the handlers it replaced.
    A process started in the background of a shell inherits an ignored SIGINT and Python then installs no Ctrl-C handler:
    the SIGINT of ``autopilot stop`` and of the supervisor would be lost. A SIGINT handler of the caller is kept. Nothing
    outside the main thread."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    numbers = (signal.SIGTERM, signal.SIGHUP) + ((signal.SIGINT,) if signal.getsignal(signal.SIGINT) is signal.SIG_IGN else ())
    return {number: signal.signal(number, terminated) for number in numbers}
