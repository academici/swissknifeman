"""Key and reference-count stateless work that is currently in flight."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from threading import Lock

__all__ = ["DedupKey", "Inflight", "dedup_key"]

type DedupKey = tuple[str, str, str, str, str, bool, str]


def dedup_key(
    client_id: str,
    method: str,
    path: str,
    model: str,
    body: dict[str, object],
    headers: Mapping[str, str],
    *,
    hot_pool: bool = False,
) -> DedupKey | None:
    if hot_pool or "x-conversation-id" in headers or model.startswith("claude-code:"):
        return None
    canonical = dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    response_format = dumps(body.get("response_format", body.get("text")), sort_keys=True)
    return (
        client_id,
        method,
        path,
        model,
        sha256(canonical.encode()).hexdigest(),
        body.get("stream") is True,
        response_format,
    )


@dataclass(eq=False, slots=True)
class _Flight[T]:
    value: T
    subscribers: int = 0


class Inflight[T]:
    """The owner cancels work when its last subscriber leaves."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._flights: dict[DedupKey, _Flight[T]] = {}

    def acquire(
        self,
        key: DedupKey | None,
        create: Callable[[], T],
        joinable: Callable[[T], bool],
    ) -> tuple[T, Callable[[], bool]]:
        with self._lock:
            flight = self._flights.get(key) if key is not None else None
            if flight is None or not joinable(flight.value):
                flight = _Flight(create())
                if key is not None:
                    self._flights[key] = flight
            flight.subscribers += 1

        def release() -> bool:
            with self._lock:
                flight.subscribers -= 1
                if flight.subscribers:
                    return False
                if key is not None and self._flights.get(key) is flight:
                    del self._flights[key]
                return True

        return flight.value, release
