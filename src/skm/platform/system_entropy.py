"""System CSPRNG (kernel-platform §8 "Энтропия"): ``os.urandom``, never clocks, ids or ``random``."""

import builtins
import os

__all__ = ["SystemEntropy"]


class SystemEntropy:
    """``EntropySource`` on ``os.urandom``."""

    def bytes(self, n: int) -> builtins.bytes:
        if isinstance(n, bool) or not isinstance(n, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"n must be int, got {type(n).__name__}")
        if n < 0:
            raise ValueError(f"n must be >= 0, got {n}")
        return os.urandom(n)
