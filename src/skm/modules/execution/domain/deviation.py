"""Deviation acceptance: a human decision with a reason (execution §4.14, §7.1 ``accept_deviation``).

Exactly one of ``criterion_id``/``finding_id`` for ``criterion``/``finding``; both ``None`` for
``attention_verdict`` (the attention verdict as a whole); ``criterion_id`` for ``coverage``. Only a trusted
human principal accepts a deviation; the reason is never empty. A deviation counts only for its own run
and task. A change outside the declared write scope is recorded as a finding of category
``WRITE_SCOPE_CATEGORY`` at that path; accepting that finding as a deviation is what clears A12.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Literal

    from skm.kernel.actor import Actor
    from skm.kernel.ids import EntityId, PrincipalId, RunId, TaskId
    from skm.modules.execution.domain.ids import DeviationId, FindingId
    from skm.modules.execution.domain.task import Task

__all__ = ["REASON_MAX_CHARS", "WRITE_SCOPE_CATEGORY", "DeviationAcceptance", "accept_deviation"]

REASON_MAX_CHARS: Final = 2000
WRITE_SCOPE_CATEGORY: Final = "scope/outside_write_set"
_SCOPES: Final = frozenset({"criterion", "finding", "attention_verdict", "coverage"})


@dataclass(frozen=True, slots=True)
class DeviationAcceptance:
    id: DeviationId
    run_id: RunId
    task_id: TaskId
    criterion_id: EntityId | None
    finding_id: FindingId | None
    reason: str
    approved_by: PrincipalId
    approved_at: datetime
    scope: Literal["criterion", "finding", "attention_verdict", "coverage"]

    def __post_init__(self) -> None:
        problems: list[str] = []
        shape = (self.criterion_id is not None, self.finding_id is not None)
        expected = {
            "criterion": (True, False),
            "finding": (False, True),
            "attention_verdict": (False, False),
            "coverage": (True, False),
        }.get(self.scope)
        if expected is None:
            problems.append(f"scope is one of {sorted(_SCOPES)}")
        elif shape != expected:
            problems.append(f"a {self.scope} deviation names criterion_id/finding_id as {expected}")
        if not self.reason.strip() or len(self.reason) > REASON_MAX_CHARS:
            problems.append(f"reason is 1..{REASON_MAX_CHARS} characters")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "deviation invariants violated: " + "; ".join(problems),
                details={"deviation_id": str(self.id), "violations": list(problems)},
            )


def accept_deviation(
    task: Task,
    *,
    actor: Actor,
    scope: Literal["criterion", "finding", "attention_verdict", "coverage"],
    criterion_id: EntityId | None,
    finding_id: FindingId | None,
    reason: str,
    deviation_id: DeviationId,
    now: datetime,
) -> DeviationAcceptance:
    """A new deviation of ``task`` approved by ``actor``; a non-human actor is ``FORBIDDEN``.

    The command ``execution.accept_deviation`` (§7.1) must authorize ``deviation.accept`` on the stored
    task's run scope before calling this rule. This keeps the human gate in the domain so a service,
    worker, advisor or policy path cannot become a deviation approver; it does not prove run permission.
    """
    if actor.kind is not PrincipalKind.HUMAN:
        raise error_for(
            ErrorCode.FORBIDDEN,
            "a deviation is accepted only by a human principal",
            details={"reason": "not_human", "principal_kind": actor.kind.value},
        )
    return DeviationAcceptance(
        id=deviation_id,
        run_id=task.run_id,
        task_id=task.id,
        criterion_id=criterion_id,
        finding_id=finding_id,
        reason=reason,
        approved_by=actor.principal_id,
        approved_at=now,
        scope=scope,
    )
