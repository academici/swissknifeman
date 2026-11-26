"""Deterministic entropy for tests (port: ``skm.kernel.entropy``).

Reproducible bytes for tests only; production code must use ``skm.platform.system_entropy``.
"""

import builtins
import hashlib

__all__ = ["DeterministicEntropy"]


class DeterministicEntropy:
    """``EntropySource`` that expands a seed with SHA-256 in counter mode; every call gets fresh bytes."""

    def __init__(self, seed: builtins.bytes = b"skm-test-entropy") -> None:
        self._seed = seed
        self._block = 0
        self.requested: list[int] = []

    def bytes(self, n: int) -> builtins.bytes:
        if n < 0:
            raise ValueError(f"n must be >= 0, got {n}")
        self.requested.append(n)
        out = bytearray()
        while len(out) < n:
            out += hashlib.sha256(self._seed + self._block.to_bytes(8, "big")).digest()
            self._block += 1
        return builtins.bytes(out[:n])
