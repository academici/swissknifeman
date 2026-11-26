"""Process-wide wakeups for the durable workspace event feed."""

from collections.abc import Callable
from threading import Event, Thread
from uuid import UUID

import psycopg

from skm.adapters.postgres.connection import PgSettings, connect_single
from skm.kernel.errors import BackendUnavailable
from skm.kernel.ids import WorkspaceId
from skm.platform.logging.logger import get_logger

__all__ = ["EventListener"]

_log = get_logger("adapters.postgres.events")


class EventListener:
    """One dedicated reader thread and autocommit connection, both owned by the API lifespan."""

    def __init__(self, settings: PgSettings) -> None:
        self._settings = settings
        self._stopped = Event()
        self._thread: Thread | None = None
        self._on_access_change: Callable[[], None] | None = None

    def set_access_change_callback(self, callback: Callable[[], None] | None) -> None:
        """Register a non-blocking wakeup callback for PostgreSQL ``skm_access_changed`` notifications."""
        self._on_access_change = callback

    def start(self, wake: Callable[[WorkspaceId], None]) -> None:
        """Start listening. ``wake`` runs on the reader thread and must hand off without blocking."""
        if self._thread is not None:
            raise RuntimeError("event listener already started")
        self._stopped.clear()
        self._thread = Thread(target=self._listen, args=(wake,), name="skm-events-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._stopped.set()
            self._thread.join()
            self._thread = None

    def _listen(self, wake: Callable[[WorkspaceId], None]) -> None:
        delay = 1
        while not self._stopped.is_set():
            try:
                with connect_single(self._settings, autocommit=True) as conn:
                    # Execute skm_access_changed first so pg_stat_activity.query remains "LISTEN skm_events".
                    conn.execute("LISTEN skm_access_changed")
                    conn.execute("LISTEN skm_events")
                    while not self._stopped.is_set():
                        # Keep the idle read shorter than the server's shutdown cleanup budget.
                        for notice in conn.notifies(timeout=0.1):
                            if self._stopped.is_set():
                                return
                            if notice.channel == "skm_access_changed":
                                callback = self._on_access_change
                                if callback is not None:
                                    callback()
                                continue
                            workspace = _workspace(notice.payload)
                            if workspace is not None:
                                wake(workspace)
                        delay = 1
            except (psycopg.Error, BackendUnavailable):
                _log.warning("events.listener.disconnected", retry_seconds=delay)
                self._stopped.wait(delay)
                delay = min(2 * delay, 30)


def _workspace(payload: str) -> WorkspaceId | None:
    workspace, separator, seq = payload.partition(":")
    if not separator or not seq.isascii() or not seq.isdecimal():
        return None
    try:
        return WorkspaceId(UUID(workspace))
    except ValueError:
        return None
