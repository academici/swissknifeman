"""Deterministic identifier source for tests (port: ``skm.kernel.id_generator``).

Ids are predictable on purpose, so they are NOT secrets: never use this fake as a source of tokens or keys
(that is ``skm.kernel.entropy.EntropySource``, see ``fakes.entropy``).
"""

from uuid import UUID

from skm.kernel.ids import UUID7_MAX_RAND_B, uuid7

__all__ = ["SequentialIds"]


class SequentialIds:
    """``IdGenerator`` that yields UUIDv7 values with a fixed timestamp and a growing counter."""

    def __init__(self, unix_ms: int = 1_767_268_800_000, start: int = 1) -> None:
        self._unix_ms = unix_ms
        self._next = start

    def new_id(self) -> UUID:
        if self._next > UUID7_MAX_RAND_B:
            raise OverflowError("SequentialIds counter exhausted")
        value = uuid7(self._unix_ms, 0, self._next)
        self._next += 1
        return value
