"""PostgreSQL repository for run tasks and task edges (DDL ``0013``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import edge_from_row, task_from_row
from skm.adapters.postgres.execution.mapping import opt_aware, opt_jsonb, require_unchanged, run
from skm.kernel.ids import RunId, TaskId
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason_to_json
from skm.modules.execution.domain.stored_payloads import (
    invalid_ref,
    not_found,
    schema_invalid,
    version_conflict,
)
from skm.modules.execution.domain.task import Task, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import TaskEdge

__all__ = ["PostgresTaskRepository"]

_TASK_OWNED: Final = (
    "run_id",
    "workspace_id",
    "kind",
    "spec_entity_id",
    "display_key",
    "position",
    "work_kind",
    "review_mode",
)


def _spec_entity_kind(kind: TaskKind) -> str | None:
    if kind is TaskKind.UNIT:
        return "unit"
    if kind in {TaskKind.ITEM, TaskKind.ITEM_GATE}:
        return "item"
    if kind is TaskKind.PHASE_GATE:
        return "phase"
    return None


# Batched with executemany: a run of N tasks and E edges is a pipeline, not N + E round trips.
_INSERT_TASK: Final = """
INSERT INTO skm_execution.run_tasks (
    id, run_id, workspace_id, plan_id, revision_id, run_kind, kind,
    spec_entity_id, spec_entity_kind, display_key, origin, position,
    status, work_kind, review_mode, review_profile, declared_write_scope,
    required_host_id, current_attempt_id, accepted_attempt_id, accepted_output_id,
    check_fix_rounds, review_rounds, attempt_count,
    blocking_reason, blocking_code, blocking_next_check_at,
    row_version, created_at, updated_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s,
    %s, clock_timestamp(), clock_timestamp()
)
"""
_INSERT_EDGE: Final = """
INSERT INTO skm_execution.run_task_edges (
    run_id, dependent_task_id, prerequisite_task_id, kind, reasons
) VALUES (%s, %s, %s, %s, %s)
"""


class PostgresTaskRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def _insert_tasks_and_edges(self, tasks: Sequence[Task], edges: Sequence[TaskEdge]) -> None:
        with self._conn.cursor() as cur:
            run_meta: dict[UUID, tuple[UUID | None, UUID | None, str]] = {}
            task_rows: list[tuple[object, ...]] = []
            for t in tasks:
                rid = UUID(str(t.run_id))
                if rid not in run_meta:
                    cur.execute(
                        "SELECT plan_id, revision_id, kind FROM skm_execution.runs WHERE id = %s", (rid,)
                    )
                    rrow = cur.fetchone()
                    if rrow is None:
                        raise invalid_ref("fk_run_tasks__runs", run_id=str(t.run_id))
                    run_meta[rid] = (rrow[0], rrow[1], rrow[2])
                plan_id, rev_id, run_kind = run_meta[rid]
                orig_doc = (
                    None
                    if t.origin is None
                    else {
                        "source_task_id": (
                            None if t.origin.source_task_id is None else str(t.origin.source_task_id)
                        ),
                        "finding_ids": [str(fid) for fid in t.origin.finding_ids],
                        "reason": t.origin.reason,
                    }
                )
                ws_doc = (
                    None
                    if t.declared_write_scope is None
                    else [{"mount": p.mount, "pattern": p.pattern} for p in t.declared_write_scope]
                )
                br_doc = None if t.blocking_reason is None else blocking_reason_to_json(t.blocking_reason)
                b_code = None if t.blocking_reason is None else t.blocking_reason.code.value
                b_next = None if t.blocking_reason is None else opt_aware(t.blocking_reason.next_check_at)
                task_rows.append(
                    (
                        UUID(str(t.id)),
                        rid,
                        UUID(str(t.workspace_id)),
                        plan_id,
                        rev_id,
                        run_kind,
                        t.kind.value,
                        None if t.spec_entity_id is None else UUID(str(t.spec_entity_id)),
                        _spec_entity_kind(t.kind),
                        t.display_key,
                        opt_jsonb(orig_doc),
                        t.position,
                        t.status.value,
                        t.work_kind,
                        t.review_mode.value,
                        t.review_profile,
                        opt_jsonb(ws_doc),
                        None if t.required_host_id is None else UUID(str(t.required_host_id)),
                        None if t.current_attempt_id is None else UUID(str(t.current_attempt_id)),
                        None if t.accepted_attempt_id is None else UUID(str(t.accepted_attempt_id)),
                        None if t.accepted_output_id is None else UUID(str(t.accepted_output_id)),
                        t.check_fix_rounds,
                        t.review_rounds,
                        t.attempt_count,
                        opt_jsonb(br_doc),
                        b_code,
                        b_next,
                        t.row_version,
                    ),
                )
            if task_rows:
                cur.executemany(_INSERT_TASK, task_rows)
            if edges:
                cur.executemany(
                    _INSERT_EDGE,
                    [
                        (
                            UUID(str(e.run_id)),
                            UUID(str(e.dependent_task_id)),
                            UUID(str(e.prerequisite_task_id)),
                            e.kind.value,
                            list(e.reasons),
                        )
                        for e in edges
                    ],
                )

    def add_many(self, tasks: Sequence[Task], edges: Sequence[TaskEdge]) -> None:
        run(lambda: self._insert_tasks_and_edges(tasks, edges))

    def add_synthetic(self, task: Task, edges: Sequence[TaskEdge]) -> None:
        if task.kind not in {TaskKind.INTEGRATION, TaskKind.FOLLOWUP, TaskKind.GROUP_REVIEW}:
            raise schema_invalid("add_synthetic accepts only integration, followup or group_review")
        run(lambda: self._insert_tasks_and_edges((task,), edges))

    def get(self, task_id: TaskId, *, for_update: bool = False) -> Task:
        def _q() -> Task:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(
                        "SELECT * FROM skm_execution.run_tasks WHERE id = %s FOR UPDATE",
                        (UUID(str(task_id)),),
                    )
                else:
                    cur.execute("SELECT * FROM skm_execution.run_tasks WHERE id = %s", (UUID(str(task_id)),))
                row = cur.fetchone()
            if row is None:
                raise not_found("task", task_id)
            return task_from_row(row)

        return run(_q)

    def list_for_run(self, run_id: RunId, *, blocking_code: BlockingCode | None = None) -> tuple[Task, ...]:
        def _q() -> tuple[Task, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if blocking_code is None:
                    cur.execute(
                        "SELECT * FROM skm_execution.run_tasks WHERE run_id = %s ORDER BY position, id",
                        (run_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM skm_execution.run_tasks
                         WHERE run_id = %s AND blocking_code = %s
                         ORDER BY position ASC, id ASC
                        """,
                        (run_id, blocking_code.value),
                    )
                return tuple(task_from_row(r) for r in cur.fetchall())

        return run(_q)

    def statuses_for_run(self, run_id: RunId) -> frozenset[TaskStatus]:
        def _q() -> frozenset[TaskStatus]:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT status FROM skm_execution.run_tasks WHERE run_id = %s", (run_id,)
                )
                return frozenset(TaskStatus(status) for (status,) in cur.fetchall())

        return run(_q)

    def edges_for_run(self, run_id: RunId) -> tuple[TaskEdge, ...]:
        def _q() -> tuple[TaskEdge, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.run_task_edges
                     WHERE run_id = %s
                     ORDER BY dependent_task_id ASC, prerequisite_task_id ASC
                    """,
                    (UUID(str(run_id)),),
                )
                return tuple(edge_from_row(r) for r in cur.fetchall())

        return run(_q)

    def save(self, task: Task, *, expected_version: int) -> None:
        current = self.get(task.id, for_update=True)
        if current.row_version != expected_version:
            raise version_conflict("task", task.id, expected_version, current.row_version)
        require_unchanged("task", current, task, _TASK_OWNED)
        new_ver = task.row_version if task.row_version > expected_version else expected_version + 1
        ws_doc = (
            None
            if task.declared_write_scope is None
            else [{"mount": p.mount, "pattern": p.pattern} for p in task.declared_write_scope]
        )
        br_doc = None if task.blocking_reason is None else blocking_reason_to_json(task.blocking_reason)
        b_code = None if task.blocking_reason is None else task.blocking_reason.code.value
        b_next = None if task.blocking_reason is None else opt_aware(task.blocking_reason.next_check_at)

        def _upd() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE skm_execution.run_tasks
                       SET status = %s, review_profile = %s, declared_write_scope = %s,
                           required_host_id = %s, current_attempt_id = %s,
                           accepted_attempt_id = %s, accepted_output_id = %s,
                           check_fix_rounds = %s, review_rounds = %s, attempt_count = %s,
                           blocking_reason = %s, blocking_code = %s, blocking_next_check_at = %s,
                           row_version = %s, updated_at = clock_timestamp()
                     WHERE id = %s AND row_version = %s
                    """,
                    (
                        task.status.value,
                        task.review_profile,
                        opt_jsonb(ws_doc),
                        None if task.required_host_id is None else UUID(str(task.required_host_id)),
                        None if task.current_attempt_id is None else UUID(str(task.current_attempt_id)),
                        None if task.accepted_attempt_id is None else UUID(str(task.accepted_attempt_id)),
                        None if task.accepted_output_id is None else UUID(str(task.accepted_output_id)),
                        task.check_fix_rounds,
                        task.review_rounds,
                        task.attempt_count,
                        opt_jsonb(br_doc),
                        b_code,
                        b_next,
                        new_ver,
                        UUID(str(task.id)),
                        expected_version,
                    ),
                )
                if cur.rowcount != 1:
                    raise version_conflict("task", task.id, expected_version, None)

        run(_upd)
