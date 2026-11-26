"""Factories for the implemented knowledge repository ports."""

from types import MappingProxyType

from skm.modules.knowledge.ports import GraphRepository, LessonRepository, MemoryRepository

from .graph import PostgresGraphRepository
from .repositories import PostgresLessonRepository, PostgresMemoryRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES = MappingProxyType(
    {
        GraphRepository: PostgresGraphRepository,
        MemoryRepository: PostgresMemoryRepository,
        LessonRepository: PostgresLessonRepository,
    }
)
