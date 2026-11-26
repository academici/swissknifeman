"""Execution event envelopes and material wait boundaries, in the caller's UoW."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cache
from typing import Any, ClassVar, cast, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import TaskId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.domain.events import EVENT_TYPES
from skm.modules.execution.ports import TaskRepository


@dataclass(frozen=True, slots=True)
class _Event(DomainEvent):
    stream: UUID
    workspace: Any
    data: JsonObject
    event_type: ClassVar[str] = ""
    stream_kind: ClassVar[str] = "run"

    @override
    def stream_id(self) -> UUID:
        return self.stream

    @override
    def scope_workspace_id(self) -> Any:
        return self.workspace

    @override
    def payload(self) -> JsonObject:
        return self.data


@cache
def event_class(urn: str) -> type[_Event]:
    return type(
        "".join(part.title() for part in urn.split(":")[-2].split("-")),
        (_Event,),
        {
            "event_type": urn,
            "stream_kind": (
                "project"
                if "autopilot-state-changed" in urn
                else "plan"
                if "readiness-reported" in urn
                else "run"
            ),
        },
    )


EVENTS = tuple(event_class(urn) for urn in EVENT_TYPES)


def cause(
    kind: str,
    *,
    event_id: UUID | None = None,
    refs: list[JsonObject] | None = None,
    rule: str | None = None,
    codes: list[str] | None = None,
) -> JsonObject:
    result: JsonObject = {
        "trigger_kind": kind,
        "advance_rule": rule,
        "reason_codes": cast("Any", codes or []),
        "refs": cast("Any", refs or []),
    }
    if event_id is not None:
        result["source_event_id"] = str(event_id)
    return result


def emit(uow: UnitOfWork, run: Any, short: str, data: JsonObject, why: JsonObject) -> None:
    if short == "task-ready" and "display_key" not in data:
        data = {
            **data,
            "display_key": uow.repo(TaskRepository).get(TaskId(UUID(str(data["task_id"])))).display_key,
        }
    payload: JsonObject = {
        "workspace_id": str(run.workspace_id),
        "project_id": str(run.project_id),
        "run_id": str(run.id),
        **data,
        "cause": why,
    }
    uow.record(event_class(f"urn:skm:execution:event:{short}:v1")(run.id, run.workspace_id, payload))


def task_created(uow: UnitOfWork, run: Any, task: Any, why: JsonObject) -> None:
    emit(
        uow,
        run,
        "task-created",
        {
            "task_id": str(task.id),
            "kind": task.kind.value,
            "revision_id": None if run.revision_id is None else str(run.revision_id),
            "entity_id": None if task.spec_entity_id is None else str(task.spec_entity_id),
            "initial_state": task.status.value,
            "position": task.position,
            "parent_task_id": None
            if task.origin is None or task.origin.source_task_id is None
            else str(task.origin.source_task_id),
            "origin": None
            if task.origin is None
            else {
                "source_task_id": None
                if task.origin.source_task_id is None
                else str(task.origin.source_task_id),
                "finding_ids": [str(i) for i in task.origin.finding_ids],
                "reason_code": task.origin.reason.upper()
                if task.origin.reason in {"checks_failed", "review_findings"}
                else "SYNTHETIC_TASK",
            },
        },
        why,
    )


def _wait_material(task: Any) -> object:
    wait = task.blocking_reason
    if wait is None:
        return None
    return (
        wait.code,
        dict(wait.refs),
        wait.message,
        wait.resolver_role,
        wait.allowed_actions,
    )


def save_task(uow: UnitOfWork, run: Any, old: Any, new: Any, why: JsonObject, now: Any) -> None:
    if old == new:
        return
    changed = _wait_material(old) != _wait_material(new)
    if changed and new.blocking_reason is not None:
        new = replace(new, blocking_reason=replace(new.blocking_reason, since=now))
    uow.repo(TaskRepository).save(new, expected_version=old.row_version)
    if not changed:
        return
    before, after = old.blocking_reason, new.blocking_reason
    emit(
        uow,
        run,
        "task-wait-changed",
        {
            "task_id": str(new.id),
            "attempt_id": None if new.current_attempt_id is None else str(new.current_attempt_id),
            "previous_code": None if before is None else before.code.value,
            "code": None if after is None else after.code.value,
            "started_at": None if after is None else after.since.isoformat(),
            "finished_at": None if before is None else now.isoformat(),
        },
        why,
    )
