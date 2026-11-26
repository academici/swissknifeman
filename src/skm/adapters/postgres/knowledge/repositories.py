"""Knowledge repository bindings. Graph storage is owned by P13.02.a."""

from typing import Protocol

from skm.modules.knowledge.ports import GraphRepository

from .lessons import PostgresLessonRepository
from .memory import PostgresMemoryRepository

__all__ = ["PostgresGraphRepository", "PostgresLessonRepository", "PostgresMemoryRepository"]


class PostgresGraphRepository(GraphRepository, Protocol):
    """Unimplemented technology binding of GraphRepository."""
