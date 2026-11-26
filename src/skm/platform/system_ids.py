"""UUIDv7 generator (kernel-platform §3.1): RFC 9562 §6.2 counter, strictly increasing in a process."""

import threading
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from skm.kernel.clock import Clock
from skm.kernel.entropy import EntropySource
from skm.kernel.ids import UUID7_MAX_RAND_A, UUID7_MAX_RAND_B, uuid7
from skm.platform.system_entropy import SystemEntropy

__all__ = ["Uuid7Generator"]

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_MILLISECOND: Final = timedelta(milliseconds=1)
_RAND_B_BYTES: Final = 8
_RAND_A_BYTES: Final = 2
_COUNTER_SEED_MASK: Final = UUID7_MAX_RAND_A >> 1  # top counter bit stays zero: room for the increments


class Uuid7Generator:
    """``IdGenerator``: UUIDv7 with a 12-bit counter in ``rand_a``; the clock never makes ids go backwards.

    Randomness comes only from the injected ``entropy`` (``os.urandom``-backed ``SystemEntropy`` by default);
    the counter never replaces it.
    """

    def __init__(self, clock: Clock, entropy: EntropySource | None = None) -> None:
        self._clock = clock
        self._entropy: EntropySource = SystemEntropy() if entropy is None else entropy
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_rand_a = 0

    def new_id(self) -> UUID:
        with self._lock:
            now = self._clock.now()
            if now.tzinfo is None:
                raise ValueError("clock.now() must be timezone-aware")
            ms = (now - _EPOCH) // _MILLISECOND
            if ms > self._last_ms:
                rand_a = self._random_int(_RAND_A_BYTES) & _COUNTER_SEED_MASK
                self._last_ms = ms
            else:
                rand_a = self._last_rand_a + 1
                if rand_a > UUID7_MAX_RAND_A:
                    self._last_ms += 1
                    rand_a = self._random_int(_RAND_A_BYTES) & _COUNTER_SEED_MASK
            self._last_rand_a = rand_a
            rand_b = self._random_int(_RAND_B_BYTES) & UUID7_MAX_RAND_B
            return uuid7(self._last_ms, rand_a, rand_b)

    def _random_int(self, size: int) -> int:
        data = self._entropy.bytes(size)
        if len(data) != size:
            raise ValueError(f"entropy source returned {len(data)} bytes, expected {size}")
        return int.from_bytes(data, "big")
