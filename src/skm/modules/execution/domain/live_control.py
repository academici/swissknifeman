"""Immutable observations and operator interventions for a task."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from skm.kernel.ids import PrincipalId, TaskId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.budget import BudgetAccount
from skm.modules.execution.domain.ids import StepId

type ObservedCoverage = Literal["complete", "partial"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    tool: str | None
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class ToolCallObservation:
    step_id: StepId
    call: ToolCall
    coverage: ObservedCoverage
    fencing_token: int
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class IncidentGate:
    id: UUID
    task_id: TaskId
    stop_after: StepId | None
    fencing_token: int | None
    kind: str
    actor_id: PrincipalId
    reason: str
    details: JsonObject
    created_at: datetime


def crossed_percent(account: BudgetAccount, spent: Decimal) -> tuple[int, ...]:
    """Report each spent threshold once, including a batch that crosses several thresholds."""
    limit = account.limit_value
    if limit is None or limit <= 0:
        return ()
    return tuple(percent for percent in (80, 100) if account.spent * 100 < limit * percent <= spent * 100)
