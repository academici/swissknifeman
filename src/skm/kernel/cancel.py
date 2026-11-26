"""Thread-safe, cooperative cancellation of host operations (kernel-platform §2.11b)."""

import math
from threading import Event, Lock
from time import monotonic
from typing import Protocol
from weakref import WeakSet

__all__ = ["CancelSource", "CancelToken", "Cancelled"]


class CancelToken(Protocol):
    """Read-only view of a cancellation; thread-safe."""

    @property
    def cancelled(self) -> bool: ...

    @property
    def reason(self) -> str | None:
        """``"shutdown"``, ``"lease_lost"``, ``"user_cancel"`` or ``"timeout"``."""
        ...

    def raise_if_cancelled(self) -> None:
        """Raises ``Cancelled(reason)``."""
        ...

    def wait(self, timeout_seconds: float) -> bool:
        """``True`` when cancelled within the wait; used instead of ``sleep``."""
        ...


class Cancelled(Exception):
    """Flow control of a host operation, not an ``SkmError``.

    The worker maps it to a stage outcome, the ``skm`` CLI to exit 130.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _Token:
    def __init__(self, parent: CancelToken | None) -> None:
        self._event = Event()
        self._lock = Lock()
        self._reason: str | None = None
        self._children: WeakSet[_Token] = WeakSet()
        self._parent = parent
        # Native ancestors set this token's event when cancelled; a foreign one can only be polled.
        ancestor = parent
        while isinstance(ancestor, _Token):
            ancestor = ancestor._parent
        self._polls = ancestor is not None
        if isinstance(parent, _Token):
            with parent._lock:
                parent._children.add(self)
            self._refresh()

    def _set_cancelled(self, reason: str) -> None:
        # Iterate rather than recurse: cancellation also works for deep ownership trees.
        pending: list[_Token] = [self]
        while pending:
            token = pending.pop()
            with token._lock:
                if token._event.is_set():
                    continue
                token._reason = reason
                token._event.set()
                pending.extend(token._children)

    def _refresh(self) -> None:
        if self._event.is_set():
            return
        parent = self._parent
        while isinstance(parent, _Token) and not parent._event.is_set():
            parent = parent._parent
        if parent is not None and parent.cancelled:
            reason = parent.reason
            if reason is not None:
                self._set_cancelled(reason)

    @property
    def cancelled(self) -> bool:
        self._refresh()
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        self._refresh()
        with self._lock:
            return self._reason

    def raise_if_cancelled(self) -> None:
        reason = self.reason
        if reason is not None:
            raise Cancelled(reason)

    def wait(self, timeout_seconds: float) -> bool:
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("cancellation wait must be finite and non-negative")
        deadline = monotonic() + timeout_seconds
        while not self.cancelled:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            # A foreign Protocol implementation has no registration hook. Poll it without
            # creating a watcher thread per child; native children are woken by Event.set.
            self._event.wait(min(remaining, 0.05) if self._polls else remaining)
        return True


class CancelSource:
    """Owns cancellation; tokens expose no mutating operation. First reason wins."""

    def __init__(self, *, parent: CancelToken | None = None) -> None:
        self._token = _Token(parent)

    @property
    def token(self) -> CancelToken:
        return self._token

    def cancel(self, reason: str) -> None:
        self._token._refresh()  # pyright: ignore[reportPrivateUsage] - source owns the private token
        self._token._set_cancelled(reason)  # pyright: ignore[reportPrivateUsage]
