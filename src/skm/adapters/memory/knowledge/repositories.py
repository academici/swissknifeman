"""Knowledge repository bindings. Graph storage is owned by P13.02.a."""

from typing import Protocol

from skm.modules.knowledge.ports import GraphRepository

from .lessons import MemoryLessonRepository
from .memory import MemoryMemoryRepository

__all__ = ["MemoryGraphRepository", "MemoryLessonRepository", "MemoryMemoryRepository"]


class MemoryGraphRepository(GraphRepository, Protocol):
    """Unimplemented technology binding of GraphRepository."""
