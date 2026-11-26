"""How a stage record is started: its mode and the feedback references it carries (execution §5.1).

Low-level records (attempt, session, stage record) store these values, and the advance engine in
``actions`` produces them; keeping them in their own module lets those records avoid importing the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.modules.execution.domain.ids import DecisionRequestId, FixBriefId, StageRecordId, StepId

__all__ = ["FeedbackRefs", "StageMode"]


class StageMode(StrEnum):
    NORMAL = "normal"
    RETRY = "retry"
    REWORK = "rework"
    FINAL_CORRECTION = "final_correction"
    CONTINUE_WITH_ANSWER = "continue_with_answer"
    RESUME_INTERRUPTED = "resume_interrupted"
    RETRIAGE_WITH_ADVICE = "retriage_with_advice"
    RECONCILE = "reconcile"


@dataclass(frozen=True, slots=True)
class FeedbackRefs:
    fix_brief_id: FixBriefId | None = None
    schema_errors_step_id: StepId | None = None
    answer_request_ids: tuple[DecisionRequestId, ...] = ()
    advice_step_id: StepId | None = None
    interrupted_stage_record_id: StageRecordId | None = None
