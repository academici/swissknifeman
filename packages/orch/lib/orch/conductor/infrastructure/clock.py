"""The clocks of a run, one place each, so that a test can replace them (``mock.patch.object(clock, "sleep", ...)``).
Callers use them through the module (``clock.wall()``), never by importing the function."""
from __future__ import annotations

from datetime import datetime, timezone
import random
import secrets
import time

from aicore.util import timefmt


def mono() -> float:
    """The clock of the active run time."""
    return time.monotonic()


def sleep(seconds: float) -> None:
    """One second of a wait (a seam for the tests)."""
    time.sleep(seconds)


def wall() -> float:
    return time.time()


def unit_random() -> float:
    return random.random()


def utc_stamp(epoch: float) -> str:
    return timefmt.utc_stamp(epoch)


def utc_now() -> str:
    return timefmt.utc_stamp()


def new_run_id() -> str:
    return "cnd-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
