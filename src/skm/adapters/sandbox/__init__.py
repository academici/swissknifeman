"""Command isolation profiles and their registry, including Linux Bubblewrap and macOS Seatbelt.

The registry fails closed: a command that a profile cannot cover is refused rather than run unconfined.
"""

from skm.adapters.sandbox.seatbelt import SeatbeltSandbox

__all__ = ["SeatbeltSandbox"]
