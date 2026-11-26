"""Stage history of one attempt in ``attempt_stages.seq`` order (execution §5.1) and its pure reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.modules.execution.domain.stage_record import StageOutcomeKind

if TYPE_CHECKING:
    from skm.modules.execution.domain.stage_record import StageRecord
    from skm.modules.execution.domain.step import AttemptStep

# Outcomes of an agent stage whose role result passed its schema (§5.2).
VALID_RESULT_OUTCOMES = frozenset(
    {
        StageOutcomeKind.SUCCESS,
        StageOutcomeKind.QUESTION,
        StageOutcomeKind.BLOCKED,
        StageOutcomeKind.WRITE_SCOPE_VIOLATION,
        StageOutcomeKind.VERDICT_GREEN,
        StageOutcomeKind.VERDICT_ATTENTION,
        StageOutcomeKind.VERDICT_RED,
        StageOutcomeKind.HELD,
    }
)


@dataclass(frozen=True, slots=True)
class StageEntry:
    record: StageRecord
    steps: tuple[AttemptStep, ...]


@dataclass(frozen=True, slots=True)
class StageHistory:
    entries: tuple[StageEntry, ...]

    def last(self) -> StageEntry | None:
        """The latest stage record (the row the decision table of §5.1 reads)."""
        return max(self.entries, key=lambda entry: entry.record.seq, default=None)

    def of_stage(self, stage_id: str) -> tuple[StageEntry, ...]:
        """Records of one workflow stage id, oldest first."""
        return tuple(
            sorted(
                (entry for entry in self.entries if entry.record.stage_id == stage_id),
                key=lambda entry: entry.record.seq,
            )
        )

    def result_retries_used(self, stage_id: str) -> int:
        """``result_invalid`` records of the stage since it last returned a valid result (C10/F5/H0, §5.8).

        Each one is answered by a retry of the same role with its schema errors; no other role repairs it.
        Runtime errors and interrupted records neither count nor reset.
        """
        used = 0
        for entry in self.of_stage(stage_id):
            if entry.record.outcome_kind in VALID_RESULT_OUTCOMES:
                used = 0
            elif entry.record.outcome_kind is StageOutcomeKind.RESULT_INVALID:
                used += 1
        return used
