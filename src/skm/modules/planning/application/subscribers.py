"""Subscribers of the planning module: none (planning §10).

The module reacts to no foreign event; what it needs from other modules it reads through their facades in its
own transaction.
"""

from __future__ import annotations

__all__ = ["SUBSCRIBERS"]

SUBSCRIBERS: tuple[object, ...] = ()
