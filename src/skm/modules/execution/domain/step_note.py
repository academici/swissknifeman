"""Step notes: progress, questions, assumptions and risks recorded against a step."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.modules.execution.domain.ids import StepId


class NoteKind(StrEnum):
    PROGRESS = "progress"
    QUESTION = "question"
    ASSUMPTION = "assumption"
    RISK = "risk"


class Urgency(StrEnum):
    NORMAL = "normal"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class StepNote:
    id: UUID
    step_id: StepId
    kind: NoteKind
    text: str
    options: tuple[JsonObject, ...]
    why_blocked: str | None
    urgency: Urgency
    recorded_at: datetime
