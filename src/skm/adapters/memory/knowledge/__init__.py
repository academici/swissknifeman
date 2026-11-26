"""Factories for the implemented knowledge repository ports."""

from types import MappingProxyType

from skm.modules.knowledge.ports import GraphRepository, LessonRepository, MemoryRepository

from .graph import MemoryGraphRepository
from .repositories import MemoryLessonRepository, MemoryMemoryRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES = MappingProxyType(
    {
        GraphRepository: MemoryGraphRepository,
        MemoryRepository: MemoryMemoryRepository,
        LessonRepository: MemoryLessonRepository,
    }
)
