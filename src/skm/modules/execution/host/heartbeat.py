"""One renewal thread per active assignment, with a latched stop mode."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from skm.kernel.cancel import Cancelled
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError

if TYPE_CHECKING:
    from skm.kernel.cancel import CancelSource
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.host.stage_client import BoundStageClient


class EventFlag(Protocol):
    def set(self) -> None: ...
    def is_set(self) -> bool: ...
    def wait(self, timeout: float | None = None) -> bool: ...


class BackgroundTask(Protocol):
    def start(self) -> None: ...
    def join(self, timeout: float | None = None) -> None: ...
    def is_alive(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class HostConcurrency:
    event: Callable[[], EventFlag]
    thread: Callable[[Callable[[], None], str], BackgroundTask]
    lock: Callable[[], AbstractContextManager[object]]
    pool: Callable[[int], Any]


class Heartbeat:
    def __init__(
        self,
        worker: BoundStageClient,
        cancel: CancelSource,
        *,
        every_seconds: float,
        concurrency: HostConcurrency,
        tick_hook: Callable[[], None] = lambda: None,
    ) -> None:
        if every_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self.worker, self.cancel, self.every_seconds = worker, cancel, every_seconds
        self._concurrency = concurrency
        self._tick_hook = tick_hook
        self.snapshot_requested = concurrency.event()
        self.stopped = concurrency.event()
        self._failures = 0
        self._thread: BackgroundTask | None = None

    def observe(self, signal: JsonObject) -> None:
        if signal.get("snapshot_requested"):
            self.snapshot_requested.set()
        if signal.get("cancel_requested"):
            self.cancel.cancel("user_cancel")

    def tick(self) -> None:
        if self.cancel.token.cancelled or self.stopped.is_set():
            return
        try:
            self._tick_hook()
            self.observe(self.worker.heartbeat())
        except Cancelled:
            return
        except Exception as error:  # noqa: BLE001 - network errors carry no safe loggable detail
            self._failures += 1
            if (isinstance(error, SkmError) and error.code is ErrorCode.LEASE_LOST) or self._failures >= 2:
                self.cancel.cancel("lease_lost")
        else:
            self._failures = 0

    def _run(self) -> None:
        while not self.stopped.wait(self.every_seconds):
            self.tick()
            if self.cancel.token.cancelled:
                return

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("heartbeat already started")
        self._thread = self._concurrency.thread(self._run, "skm-assignment-heartbeat")
        self._thread.start()

    def stop(self) -> None:
        self.stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                self.cancel.cancel("lease_lost")
                raise RuntimeError("heartbeat request did not drain")
