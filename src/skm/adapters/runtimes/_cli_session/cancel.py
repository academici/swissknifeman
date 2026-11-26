"""Bounded signal escalation using owned containment rather than diagnostic PID numbers."""

from __future__ import annotations

import signal
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol

from skm.kernel.clock import Monotonic
from skm.modules.runtimes.public import ProcessOwnership

from .identity import OwnedContainment

__all__: list[str] = []


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class TerminationOutcome:
    signal_reached: str | None
    ignored_cancel: bool
    stopped: bool
    reason: str | None = None


def _wait_empty(
    backend: OwnedContainment,
    seconds: float,
    clock: Monotonic,
    sleeper: Sleeper,
    drain: Callable[[], None] | None,
) -> bool:
    deadline = clock.monotonic() + seconds
    # The iteration ceiling also bounds a faulty/frozen injected clock.
    for _ in range(int(seconds / 0.05) + 2):
        if drain is not None:
            drain()
        if backend.empty() is True:
            return True
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            break
        sleeper.sleep(min(0.05, remaining))
    return backend.empty() is True


def terminate_group(  # noqa: PLR0913 - spec boundary plus injected containment/drain ports
    pgid: int | None,
    *,
    ownership: ProcessOwnership,
    mode: Literal["cancel", "reap"],
    sleeper: Sleeper,
    clock: Monotonic,
    backend: OwnedContainment | None = None,
    grace_int_seconds: float = 5.0,
    grace_term_seconds: float = 10.0,
    on_ignored: Callable[[Literal["SIGINT", "SIGTERM"]], None] | None = None,
    drain: Callable[[], None] | None = None,
) -> TerminationOutcome:
    del pgid  # Numeric group identity is diagnostic; only the backend may signal.
    if mode not in ("cancel", "reap") or any(
        not isfinite(value) or value < 0 for value in (grace_int_seconds, grace_term_seconds)
    ):
        raise ValueError("invalid termination policy")
    if backend is None:
        return TerminationOutcome(None, False, False, "ownership_unconfirmed")
    stages = (
        ((signal.SIGINT, grace_int_seconds), (signal.SIGTERM, grace_term_seconds))
        if mode == "cancel"
        else ((signal.SIGTERM, 5.0),)
    )
    reached = None
    try:
        if not backend.confirmed(ownership):
            return TerminationOutcome(None, False, False, "ownership_unconfirmed")
        if backend.empty() is True:
            return TerminationOutcome(None, False, True)
        for sig, grace in stages:
            reached = sig.name
            # Missing leader/group is not empty-containment proof.
            with suppress(ProcessLookupError):
                backend.signal(sig)
            if _wait_empty(backend, grace, clock, sleeper, drain):
                return TerminationOutcome(reached, False, True)
            if mode == "cancel" and on_ignored is not None:
                on_ignored("SIGINT" if sig == signal.SIGINT else "SIGTERM")
        reached = "SIGKILL"
        with suppress(ProcessLookupError):
            backend.signal(signal.SIGKILL)
        stopped = _wait_empty(backend, 1.0, clock, sleeper, drain)
        return TerminationOutcome(reached, True, stopped, None if stopped else "cleanup_unconfirmed")
    except PermissionError:
        return TerminationOutcome(reached, reached == "SIGKILL", False, "signal_permission_denied")
    except OSError:
        return TerminationOutcome(reached, reached == "SIGKILL", False, "cleanup_unconfirmed")
