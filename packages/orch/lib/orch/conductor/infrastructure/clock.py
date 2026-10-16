"""The clocks of a run, one place each, so that a test can replace them (``mock.patch.object(clock, "sleep", ...)``).
Callers use them through the module (``clock.wall()``), never by importing the function."""
from __future__ import annotations

from datetime import datetime, timezone
import random
import secrets
import time


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
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return "cnd-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
