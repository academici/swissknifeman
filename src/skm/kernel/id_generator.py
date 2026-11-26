"""Identifier source (kernel-platform §2.8); ``platform/system_ids.py: Uuid7Generator`` implements it."""

from typing import Protocol
from uuid import UUID

__all__ = ["IdGenerator"]


class IdGenerator(Protocol):
    def new_id(self) -> UUID:
        """UUIDv7, strictly increasing within the process."""
        ...
