"""Entropy source (kernel-platform §8 "Энтропия").

``platform/system_entropy.py`` reads ``os.urandom``; ``CommandContext.entropy`` and ``Uuid7Generator``
receive the source explicitly. Secret generators never use ``Clock``/``IdGenerator``/``random`` as a CSPRNG.
"""

import builtins
from typing import Protocol

__all__ = ["EntropySource"]


class EntropySource(Protocol):
    def bytes(self, n: int) -> builtins.bytes:
        """``n`` cryptographically secure random bytes."""
        ...
