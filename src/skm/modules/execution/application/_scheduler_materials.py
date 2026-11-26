"""Material availability guards before attempt creation, using pinned revision observations."""

from datetime import timedelta
from typing import Any

from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause
from skm.modules.execution.application._preview_facts import material_facts
from skm.modules.execution.application._primitives import move
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.task import Task, TaskStatus
from skm.modules.execution.ports import TaskRepository
from skm.modules.planning import public as planning


def refresh_material_waits(
    uow: UnitOfWork, ctx: Any, run: Any, values: Any, now: Any, *, initial_ready: Any = ()
) -> tuple[Task, ...]:
    if run.revision_id is None:
        return uow.repo(TaskRepository).list_for_run(run.id)
    facts = material_facts(uow, run.workspace_id, planning.revision_materials(uow, run.revision_id), now)
    tasks = list(uow.repo(TaskRepository).list_for_run(run.id))
    for index, task in enumerate(tasks):
        missing = [
            m
            for m in facts
            if not m["available"]
            and "execution" in m.get("required_for", ())
            and (
                m.get("is_global")
                or any(
                    task.display_key == key or task.display_key.startswith(key + "/")
                    for key in m.get("applies_to", ())
                )
            )
        ]
        prior = task.blocking_reason
        material_wait = prior is not None and prior.code is BlockingCode.BLOCKED_BY_MATERIAL
        if (
            material_wait
            and prior is not None
            and prior.next_check_at is not None
            and prior.next_check_at > now
        ):
            continue
        if material_wait and not missing:
            tasks[index] = move(uow, ctx, run, task, TaskStatus.READY, cause("wait_changed"))
        elif (
            missing
            and task.current_attempt_id is None
            and (task.status is TaskStatus.READY or task.id in initial_ready or material_wait)
        ):
            reason = blocking_reason(
                BlockingCode.BLOCKED_BY_MATERIAL,
                task_id=task.id,
                refs={
                    "material_ids": [m["material_id"] for m in missing],
                    "file_version_ids": [m["file_version_id"] for m in missing if m.get("file_version_id")],
                    "required_for": ["execution"],
                },
                now=now,
                next_check_at=now
                + timedelta(seconds=int(values.get("execution.materials.recheck_seconds", 300))),
                previous=prior,
                message="Pinned material is unavailable",
            )
            tasks[index] = move(
                uow,
                ctx,
                run,
                task,
                TaskStatus.BLOCKED,
                cause("wait_changed", codes=["BLOCKED_BY_MATERIAL"]),
                blocking=reason,
            )
    return tuple(tasks)
