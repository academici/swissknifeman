"""Transaction-local tables cloned and published by the memory backend."""

from dataclasses import dataclass, field
from datetime import datetime

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.modules.knowledge.domain.lesson import Lesson, LessonId
from skm.modules.knowledge.domain.memory_entry import MemoryEntry, MemoryEntryId

__all__ = ["MemoryKnowledgeState", "knowledge_state"]


@dataclass
class MemoryKnowledgeState:
    entries: dict[MemoryEntryId, MemoryEntry] = field(default_factory=dict[MemoryEntryId, MemoryEntry])
    lessons: dict[LessonId, Lesson] = field(default_factory=dict[LessonId, Lesson])
    lesson_updates: dict[LessonId, datetime] = field(default_factory=dict[LessonId, datetime])


def knowledge_state(state: MemoryBackendState) -> MemoryKnowledgeState:
    found = state.modules.get("knowledge")
    if found is None:
        found = MemoryKnowledgeState()
        state.modules["knowledge"] = found
    if not isinstance(found, MemoryKnowledgeState):
        raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid knowledge backend state")
    return found
