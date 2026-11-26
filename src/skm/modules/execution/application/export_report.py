"""Load structural run metrics without following artifacts or session references."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.finding import FindingState
from skm.modules.execution.domain.ids import CheckExecutionId
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    CheckRepository,
    ExecutionQueries,
    ReviewRepository,
    StageRepository,
    TaskRepository,
)

if TYPE_CHECKING:
    from skm.kernel.ids import RunId
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.execution.domain.step import AttemptStep
    from skm.modules.execution.domain.task import Task

_GROUP = {
    RoleId.EXECUTOR: "executor",
    RoleId.REVIEWER: "review",
    RoleId.TRIAGER: "triage",
    RoleId.SCOUT: "scout",
    RoleId.ADVISOR: "advice",
    RoleId.RESEARCHER: "scout",
    RoleId.REGISTRAR: "executor",
}
_REQUESTED = "urn:skm:execution:event:decision-requested:v1"
_ANSWERED = "urn:skm:execution:event:decision-answered:v1"
_DEVIATION = "urn:skm:execution:event:deviation-accepted:v1"
_EVENTS = frozenset({_REQUESTED, _ANSWERED, _DEVIATION})


def _step_metrics(step: AttemptStep) -> JsonObject:
    usage = step.usage
    return {
        "group": _GROUP[step.role],
        "seconds": (step.finished_at - step.started_at).total_seconds() if step.finished_at else None,
        "input_tokens": usage.input_tokens if usage else None,
        "cached_tokens": usage.cache_read_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "cost_usd_micros": usage.cost_usd_micros if usage else None,
    }


def _task_metrics(uow: UnitOfWork, task: Task) -> JsonObject:
    attempts = uow.repo(AttemptRepository).list_for_task(task.id)
    histories = [uow.repo(StageRepository).history(attempt.id) for attempt in attempts]
    entries = [entry for history in histories for entry in history.entries]
    checks: list[JsonValue] = []
    queries, check_repo = uow.repo(ExecutionQueries), uow.repo(CheckRepository)
    for attempt in attempts:
        detail = queries.attempt_view(attempt.id)
        for row in cast("list[JsonObject]", detail["checks"]):
            check = check_repo.get(CheckExecutionId(UUID(cast("str", row["check_execution_id"]))))
            checks.append(
                {
                    "check_key": check.check_key,
                    "failed": check.state in {CheckState.FAILED, CheckState.ERROR},
                    "reused": check.reused_from_id is not None,
                    "seconds": (
                        (check.finished_at - check.started_at).total_seconds()
                        if check.started_at and check.finished_at
                        else 0.0
                    ),
                }
            )
    accepted_no = next((item.attempt_no for item in attempts if item.id == task.accepted_attempt_id), None)
    decisions = uow.repo(AcceptanceRepository).decisions_for_task(task.id)
    accepted_deviations = task.status.value == "accepted" and any(
        item.decision == "accepted" and item.output_id == task.accepted_output_id and item.basis.deviation_ids
        for item in decisions
    )
    return {
        "task_id": str(task.id),
        "display_key": task.display_key,
        "status": "accepted with deviations" if accepted_deviations else task.status.value,
        "attempts_count": len(attempts),
        "accepted_attempt_no": accepted_no,
        "check_fix_rounds": task.check_fix_rounds,
        "review_rounds": task.review_rounds,
        "rework_rounds": sum(
            entry.record.mode in {StageMode.REWORK, StageMode.FINAL_CORRECTION} for entry in entries
        ),
        "checks": checks,
        "steps": [_step_metrics(step) for entry in entries for step in entry.steps],
    }


def _event_counts(queries: ExecutionQueries, run_id: RunId) -> Counter[str]:
    counts: Counter[str] = Counter()
    after, head = 0, queries.head_run_seq(run_id)
    while after < head:
        batch = queries.run_events(run_id, after, head, 200)
        if not batch:
            break
        counts.update(kind for row in batch if (kind := str(row["event_type"])) in _EVENTS)
        after = cast("int", batch[-1]["stream_seq"])
    return counts


def load_run_export_metrics(uow: UnitOfWork, run_id: RunId) -> JsonObject:
    tasks = uow.repo(TaskRepository).list_for_run(run_id)
    reviews = uow.repo(ReviewRepository)
    counts = _event_counts(uow.repo(ExecutionQueries), run_id)
    return {
        "tasks": [_task_metrics(uow, task) for task in tasks],
        "findings": [
            {"severity": finding.severity.value, "state": finding.state.value}
            for task in tasks
            for finding in reviews.findings_for_task(task.id)
            if finding.state in {FindingState.CONFIRMED, FindingState.REJECTED}
        ],
        "deviations_accepted": counts[_DEVIATION],
        "decisions_asked": counts[_REQUESTED],
        "decisions_answered": counts[_ANSWERED],
    }
