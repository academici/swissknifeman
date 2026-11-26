"""Collect attempt-local signals after terminal task events."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import SubscriberContext
from skm.application_bus.registry import SubscriberSpec
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import AttemptId, ProjectId, TaskId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.public import (
    get_attempt_activity,
    get_attempt_summary,
    list_check_executions,
    list_task_attempts_for_learning,
)
from skm.modules.learning.domain.activity import ACTIVITY_SCHEMA, MAX_EXPOSURE_REFS, Outcome
from skm.modules.learning.generated.commands import extract_candidates_from_json
from skm.modules.learning.ports import ActivityRecordRepository
from skm.modules.workspace import public as workspace

from .commands.extract_candidates import extract, project_ref

_ACCEPTED = "urn:skm:execution:event:task-accepted:v1"
_FAILED = "urn:skm:execution:event:task-failed:v1"
_SUMS = (
    "tools_total",
    "reads_total",
    "retrieval_calls",
    "retrieval_result_chars",
    "retrieval_repeated_queries",
    "usage_input",
    "usage_cache_read",
    "usage_cache_write",
)
_ARRAYS = ("error_loops", "checks", "protected_writes", "workarounds")


def _summed_metrics(activity: JsonObject) -> JsonObject:
    steps = activity.get("activities")
    if activity.get("activity_complete") is not True or not isinstance(steps, list) or not steps:
        return {}
    valid = [step for step in steps if isinstance(step, dict)]
    if len(valid) != len(steps):
        return {}
    metrics: JsonObject = {}
    for name in _SUMS:
        numbers = [step.get(name) for step in valid]
        if all(type(value) is int and value >= 0 for value in numbers):
            metrics[name] = sum(cast("list[int]", numbers))
    for name in _ARRAYS:
        arrays = [step.get(name) for step in valid]
        if all(isinstance(value, list) for value in arrays):
            metrics[name] = [item for array in cast("list[list[JsonValue]]", arrays) for item in array]
    if len(valid) == 1:
        for name in ("reads_unique", "top_rereads", "cache_hit", "agents", "context_window_tokens"):
            if (value := valid[0].get(name)) is not None:
                metrics[name] = value
    return metrics


def _attempt_outcome(event: EventEnvelope, attempt: JsonObject, summary: JsonObject) -> Outcome:
    attempt_id = attempt["attempt_id"]
    if event.type == _ACCEPTED and event.payload.get("attempt_id") == attempt_id:
        output_id = event.payload.get("output_id")
        if (
            output_id is not None
            and output_id == summary.get("current_output_id")
            and attempt.get("accepted")
        ):
            return Outcome.SUCCESS
    if (
        attempt.get("state") in ("failed", "ownership_lost")
        or str(summary.get("end_reason")).casefold() in ("failed", "ownership_lost")
        or (event.type == _FAILED and event.payload.get("attempt_id") == attempt_id)
    ):
        return Outcome.FAILURE
    return Outcome.UNKNOWN


def _exposure(activity: JsonObject) -> tuple[str, list[JsonValue]]:
    coverage = activity.get("exposure_coverage")
    raw = activity.get("exposed_lesson_refs")
    if not isinstance(raw, list) or len(raw) > MAX_EXPOSURE_REFS:
        return "unknown", []
    refs: list[JsonValue] = []
    for value in raw:
        if not isinstance(value, dict):
            coverage = "unknown"
            continue
        try:
            lesson_id = str(UUID(str(value["id"]).rsplit(":", 1)[-1]))
            if not isinstance(value["version"], str) or not isinstance(value["content_digest"], str):
                raise ValueError("Invalid lesson provenance")
        except (KeyError, ValueError):
            coverage = "unknown"
            continue
        refs.append({**value, "id": lesson_id})
    return ("complete" if coverage == "complete" else "unknown"), refs


def _summary(
    event: EventEnvelope,
    attempt: JsonObject,
    facts: JsonObject,
    activity: JsonObject,
    observed: datetime,
    check_executions: tuple[JsonObject, ...],
) -> JsonObject:
    outcomes = _attempt_outcome(event, attempt, facts)
    exposure, exposed = _exposure(activity)
    summary = _summed_metrics(activity)
    executed: list[JsonValue] = [
        {
            "command": None,
            "ok": row["state"] == "passed",
            "origin": "check_execution",
            "check_key": row["check_key"],
        }
        for row in check_executions
        if row["state"] in ("failed", "passed")
    ]
    if executed:
        summary["checks"] = executed + cast("list[JsonValue]", summary.get("checks", []))
    if facts.get("latest_tree_digest") is not None:
        summary["files_changed"] = activity["changed_paths"]
    usage = activity.get("usage")
    if isinstance(usage, dict) and type(usage.get("input_tokens")) is int:
        summary.setdefault("usage_input", usage["input_tokens"])
    return {
        **summary,
        "schema": ACTIVITY_SCHEMA,
        "source_kind": "attempt",
        "source_key": attempt["attempt_id"],
        "outcome": outcomes.value,
        "task_outcome": "success" if event.type == _ACCEPTED else "failure",
        "exposure_coverage": exposure,
        "exposed_lesson_refs": exposed,
        "observed_at": observed.isoformat(),
    }


def task_outcome_signals(event: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    project_id = str(event.payload["project_id"])
    workspace_id = workspace.workspace_of_project(uow, ProjectId(UUID(project_id)))
    if workspace_id != event.workspace_id:
        return
    config = ctx.config_for(project_ref(project_id))
    if config.get("learning.signals.enabled") is False:
        return
    records = uow.repo(ActivityRecordRepository)
    task_id = TaskId(UUID(str(event.payload["task_id"])))
    attempts = list_task_attempts_for_learning(uow, task_id)
    for attempt in attempts:
        key = str(attempt["attempt_id"])
        if records.exists(workspace_id, key):
            continue
        attempt_id = AttemptId(UUID(key))
        facts = get_attempt_summary(uow, attempt_id)
        activity = get_attempt_activity(uow, attempt_id)
        finished = facts.get("finished_at")
        observed = datetime.fromisoformat(finished) if isinstance(finished, str) else event.occurred_at
        if event.type == _ACCEPTED and event.payload.get("attempt_id") == key:
            observed = event.occurred_at
        steps = cast("list[str]", activity.get("source_step_ids", []))
        extract(
            cast(
                "dict[str, Any]",
                extract_candidates_from_json(
                    {
                        "summary": _summary(
                            event, attempt, facts, activity, observed, list_check_executions(uow, attempt_id)
                        ),
                        "project_id": project_id,
                        "attempt_id": key,
                        "task_id": str(task_id),
                        "run_id": str(attempt["run_id"]),
                    }
                ),
            ),
            ctx,
            uow,
            config=config,
            source_refs=tuple({"kind": "step", "id": step} for step in steps),
        )


SUBSCRIBERS = (
    SubscriberSpec("learning.task_outcome_signals", frozenset({_ACCEPTED, _FAILED}), task_outcome_signals),
)
