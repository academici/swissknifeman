"""PostgreSQL ``ExecutionQueries`` adapter (execution §6.2, §8; DDL ``0013``-``0016``, ``0026``-``0029``)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    attempt_from_row,
    bundle_from_row,
    check_from_row,
    decision_request_from_row,
    edge_from_row,
    effect_from_row,
    environment_from_row,
    finding_from_row,
    output_from_row,
    recovery_from_row,
    review_from_row,
    run_from_row,
    stage_from_row,
    step_from_row,
    task_from_row,
)
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import damaged, run, usage_to_json
from skm.adapters.postgres.execution.queries_events_outcomes import QueriesEventsOutcomesMixin
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.blocking_reason import blocking_reason_to_json
from skm.modules.execution.domain.execution_bundle import DEFAULT_POLICY_KEY, run_selection_to_json
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.read_documents import (
    AttemptDetailParts,
    build_attempt_detail_doc,
    build_attempt_summary_doc,
    build_step_view_doc,
    build_task_doc,
    iso,
    parse_time_id_cursor,
)
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stored_payloads import not_found
from skm.modules.execution.domain.work_policy import work_policy_to_json

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, ProjectId, RunId, ScopeId, TaskId
    from skm.modules.execution.domain.contracts import (
        AttemptView,
        Cursor,
        DecisionRequestView,
        Page,
        RunSummary,
        RunView,
        StepView,
        TaskView,
    )
    from skm.modules.execution.domain.decision_request import DecisionKind
    from skm.modules.execution.domain.ids import StepId
    from skm.modules.execution.domain.output import Output

__all__ = ["PostgresExecutionQueries"]

_GET_RUN: Final = "SELECT * FROM skm_execution.runs WHERE id = %s"
_GET_BUNDLE: Final = "SELECT * FROM skm_execution.execution_bundles WHERE run_id = %s"
_PLAN_ALIAS: Final = """
SELECT a.alias
  FROM skm_planning.plans p
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = p.workspace_id
   AND a.project_id = p.project_id
   AND a.plan_id = p.id
   AND a.alias_kind IN ('short', 'system')
 WHERE p.id = %s
 LIMIT 1
"""
_NOW: Final = "SELECT clock_timestamp() AS now"
_HEALTH_FACTS: Final = """
SELECT EXISTS(
           SELECT 1 FROM skm_execution.assignments a
             JOIN skm_execution.assignment_leases l ON l.assignment_id = a.id
            WHERE a.run_id = %s AND l.expires_at <= %s
       ) AS expired_leases,
       EXISTS(
           SELECT 1 FROM skm_execution.run_recoveries rr
            WHERE rr.run_id = %s AND rr.outcome IS NULL
       ) AS recovery_open,
       EXISTS(
           SELECT 1 FROM skm_execution.run_tasks t
            WHERE t.run_id = %s AND t.blocking_reason IS NOT NULL
       ) AS has_blocked
"""
_TASKS_FOR_RUN: Final = """
SELECT * FROM skm_execution.run_tasks WHERE run_id = %s ORDER BY position ASC, id::text ASC
"""
_EDGES_FOR_RUN: Final = "SELECT * FROM skm_execution.run_task_edges WHERE run_id = %s"
_GET_TASK: Final = "SELECT * FROM skm_execution.run_tasks WHERE id = %s"
_ATTEMPTS_FOR_TASK: Final = """
SELECT * FROM skm_execution.attempts WHERE task_id = %s ORDER BY attempt_no ASC
"""
_OUTPUTS_FOR_ATTEMPTS: Final = """
SELECT * FROM skm_execution.attempt_outputs WHERE attempt_id = ANY(%s::uuid[]) ORDER BY seq ASC
"""
_GET_ATTEMPT: Final = "SELECT * FROM skm_execution.attempts WHERE id = %s"
_ENV_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.execution_environments WHERE attempt_id = %s ORDER BY created_at ASC LIMIT 1
"""
_STAGES_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.attempt_stages
 WHERE attempt_id = %s ORDER BY seq ASC, started_at ASC, id::text ASC
"""
_STEPS_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.attempt_steps WHERE attempt_id = %s ORDER BY started_at ASC, id::text ASC
"""
# Checks, reviews and recoveries carry no attempt_id index: the task (run) of the attempt narrows them
# through ix_check_executions__task_id_round_no, uq_reviews__task_id_round_no and
# ix_run_recoveries__run_id_at.
_CHECKS_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.check_executions
 WHERE task_id = %s AND attempt_id = %s
 ORDER BY COALESCE(started_at, '1970-01-01T00:00:00Z'::timestamptz) ASC, id::text ASC
"""
_REVIEWS_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.reviews
 WHERE task_id = %s AND attempt_id = %s ORDER BY round_no ASC, id::text ASC
"""
_FINDINGS_FOR_REVIEWS: Final = """
SELECT * FROM skm_execution.review_findings WHERE review_id = ANY(%s::uuid[]) ORDER BY id::text ASC
"""
_EFFECTS_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.external_effects WHERE attempt_id = %s ORDER BY created_at ASC, id::text ASC
"""
_RECOVERIES_FOR_ATTEMPT: Final = """
SELECT * FROM skm_execution.run_recoveries
 WHERE run_id = %s AND attempt_id = %s ORDER BY at ASC, id::text ASC
"""
_GET_STEP: Final = "SELECT * FROM skm_execution.attempt_steps WHERE id = %s"

_LIST_RUNS: Final = """
SELECT r.*,
       (
           SELECT a.alias FROM skm_planning.plan_aliases a
            WHERE a.workspace_id = r.workspace_id
              AND a.project_id = r.project_id
              AND a.plan_id = r.plan_id
              AND a.alias_kind IN ('short', 'system')
            LIMIT 1
       ) AS plan_alias,
       (SELECT count(*) FROM skm_execution.run_tasks t WHERE t.run_id = r.id) AS tasks_total,
       (
           SELECT count(*) FROM skm_execution.run_tasks t
            WHERE t.run_id = r.id AND t.status = 'accepted'
       ) AS tasks_accepted
  FROM skm_execution.runs r
 WHERE r.project_id = %s
   AND (%s::text[] IS NULL OR r.status = ANY(%s::text[]))
   AND (%s::timestamptz IS NULL OR (r.created_at, r.id::text) < (%s::timestamptz, %s::text))
 ORDER BY r.created_at DESC, r.id::text DESC
 LIMIT %s
"""
_BUNDLES_FOR_RUNS: Final = """
SELECT * FROM skm_execution.execution_bundles WHERE run_id = ANY(%s::uuid[])
"""
_INBOX_PAGE: Final = """
SELECT dr.*, da.id AS answer_id,
       drec.id AS rec_id, drec.status AS rec_status
  FROM skm_execution.decision_requests dr
  JOIN skm_execution.runs r ON r.id = dr.run_id
  LEFT JOIN skm_execution.decision_answers da
    ON da.request_id = dr.id AND da.request_revision = dr.revision
  LEFT JOIN LATERAL (
      SELECT id, status FROM skm_execution.decision_records
       WHERE request_id = dr.id
       ORDER BY created_at DESC, id DESC
       LIMIT 1
  ) drec ON TRUE
 WHERE (%s::text[] IS NULL OR dr.kind = ANY(%s::text[]))
   AND (dr.run_id = ANY(%s::uuid[]) OR r.project_id = ANY(%s::uuid[]))
   AND (%s::timestamptz IS NULL OR (dr.created_at, dr.id::text) < (%s::timestamptz, %s::text))
 ORDER BY dr.created_at DESC, dr.id::text DESC
 LIMIT %s
"""
_TASKS_BY_IDS: Final = "SELECT * FROM skm_execution.run_tasks WHERE id = ANY(%s::uuid[])"


class PostgresExecutionQueries(QueriesEventsOutcomesMixin):
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def run_health_view(self, run_id: RunId, *, now: datetime) -> JsonObject:
        now_aw = require_aware(now)

        def _op() -> JsonObject:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_RUN, (run_id,))
                rrow = cur.fetchone()
                if rrow is None:
                    raise not_found("run", run_id)
                r = run_from_row(rrow)
                cur.execute(_HEALTH_FACTS, (run_id, now_aw, run_id, run_id))
                facts = cur.fetchone()
                if facts is None:
                    raise damaged("runs", run_id)
                reasons: list[JsonValue] = []
                if r.unmetered_at is not None:
                    reasons.append("unmetered")
                if r.stop_code is not None:
                    reasons.append(f"stop_code:{r.stop_code}")
                expired = bool(facts["expired_leases"])
                rec_open = bool(facts["recovery_open"])
                has_blocked = bool(facts["has_blocked"])
                if expired:
                    reasons.append("lease_expired")
                if rec_open:
                    reasons.append("recovery_open")
                if has_blocked:
                    reasons.append("tasks_blocked")
                if expired or rec_open:
                    health = "stalled"
                elif has_blocked and r.status in {RunStatus.PAUSED, RunStatus.RUNNING}:
                    health = "blocked"
                elif reasons:
                    health = "degraded"
                else:
                    health = "healthy"
                return {"health": health, "reasons": reasons}

        return run(_op)

    def run_view(self, run_id: RunId) -> RunView:
        def _op() -> RunView:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_RUN, (run_id,))
                rrow = cur.fetchone()
                if rrow is None:
                    raise not_found("run", run_id)
                r = run_from_row(rrow)
                cur.execute(_GET_BUNDLE, (run_id,))
                brow = cur.fetchone()
                bundle = None if brow is None else bundle_from_row(brow)
                cur.execute(_PLAN_ALIAS, (r.plan_id,))
                arow = cur.fetchone()
                alias = "" if arow is None else str(arow["alias"])
                cur.execute(_TASKS_FOR_RUN, (run_id,))
                counts = Counter(str(tr["status"]) for tr in cur.fetchall())
                cur.execute(_NOW)
                nrow = cur.fetchone()
                if nrow is None:
                    raise damaged("runs", run_id)
                eff_now = cast("datetime", nrow["now"])
                wp_def = (
                    bundle.work_policies.get(DEFAULT_POLICY_KEY)
                    if (bundle is not None and bundle.work_policies is not None)
                    else None
                )
            return {
                "run_id": str(r.id),
                "kind": r.kind.value,
                "plan_id": str(r.plan_id) if r.plan_id is not None else None,
                "plan_alias": alias,
                "revision_no": r.revision_no,
                "status": r.status.value,
                "stop_code": r.stop_code,
                "pause_source": r.pause_source,
                "unmetered": r.unmetered_at is not None,
                "selection": (
                    None
                    if (bundle is None or bundle.selection is None)
                    else run_selection_to_json(bundle.selection)
                ),
                "health": self.run_health_view(run_id, now=eff_now),
                "counts_by_status": dict[str, JsonValue](sorted(counts.items())),
                "started_at": iso(r.started_at),
                "finished_at": iso(r.finished_at),
                "review_grouping": r.review_grouping.mode,
                "bundle_digest": "" if bundle is None else bundle.config_digest,
                "work_policy_default": None if wp_def is None else work_policy_to_json(wp_def),
                "autopilot": r.autopilot,
                "row_version": r.row_version,
            }

        return run(_op)

    def runs_page(
        self, project_id: ProjectId, after: Cursor | None, limit: int, statuses: frozenset[RunStatus]
    ) -> Page[RunSummary]:
        cur_pair = parse_time_id_cursor(after)
        cur_dt = None if cur_pair is None else require_aware(cur_pair[0])
        cur_id = None if cur_pair is None else cur_pair[1]
        st_arr = None if not statuses else sorted(s.value for s in statuses)

        def _op() -> Page[RunSummary]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LIST_RUNS, (project_id, st_arr, st_arr, cur_dt, cur_dt, cur_id, limit + 1))
                fetched = cur.fetchall()
                has_more = len(fetched) > limit
                sliced = fetched[:limit]
                run_uuids = [as_uuid(row["id"]) for row in sliced]
                bundles = {}
                if run_uuids:
                    cur.execute(_BUNDLES_FOR_RUNS, (run_uuids,))
                    bundles = {as_uuid(br["run_id"]): bundle_from_row(br) for br in cur.fetchall()}
                items: list[JsonValue] = []
                last_r = None
                for row in sliced:
                    r = run_from_row(row)
                    last_r = r
                    bundle = bundles.get(UUID(str(r.id)))
                    wp_def = (
                        bundle.work_policies.get(DEFAULT_POLICY_KEY)
                        if (bundle is not None and bundle.work_policies is not None)
                        else None
                    )
                    items.append(
                        {
                            "run_id": str(r.id),
                            "project_id": str(r.project_id),
                            "kind": r.kind.value,
                            "plan_id": str(r.plan_id) if r.plan_id is not None else None,
                            "plan_alias": str(row["plan_alias"] or ""),
                            "revision_id": str(r.revision_id) if r.revision_id is not None else None,
                            "revision_no": r.revision_no,
                            "status": r.status.value,
                            "stop_code": r.stop_code,
                            "created_at": r.created_at.isoformat(),
                            "started_at": iso(r.started_at),
                            "finished_at": iso(r.finished_at),
                            "tasks_total": int(row["tasks_total"]),
                            "tasks_accepted": int(row["tasks_accepted"]),
                            "work_policy_default": None if wp_def is None else work_policy_to_json(wp_def),
                        }
                    )
                nxt = None if not (has_more and last_r) else f"{last_r.created_at.isoformat()}|{last_r.id}"
                return {"items": items, "next_after": nxt}

        return run(_op)

    def task_views(self, run_id: RunId) -> tuple[TaskView, ...]:
        def _op() -> tuple[TaskView, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_BUNDLE, (run_id,))
                brow = cur.fetchone()
                bundle = None if brow is None else bundle_from_row(brow)
                cur.execute(_TASKS_FOR_RUN, (run_id,))
                tasks = [task_from_row(r) for r in cur.fetchall()]
                tasks_by_id = {t.id: t for t in tasks}
                cur.execute(_EDGES_FOR_RUN, (run_id,))
                edges = [edge_from_row(r) for r in cur.fetchall()]
                return tuple(
                    build_task_doc(
                        t,
                        bundle=bundle,
                        tasks_by_id=tasks_by_id,
                        edges=edges,
                        attempts=(),
                        outputs_by_attempt={},
                        summary_only=True,
                    )
                    for t in tasks
                )

        return run(_op)

    def task_view(self, task_id: TaskId) -> TaskView:
        def _op() -> TaskView:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_TASK, (task_id,))
                trow = cur.fetchone()
                if trow is None:
                    raise not_found("task", task_id)
                task = task_from_row(trow)
                cur.execute(_GET_BUNDLE, (task.run_id,))
                brow = cur.fetchone()
                bundle = None if brow is None else bundle_from_row(brow)
                cur.execute(_TASKS_FOR_RUN, (task.run_id,))
                tasks_by_id = {t.id: t for t in (task_from_row(r) for r in cur.fetchall())}
                cur.execute(_EDGES_FOR_RUN, (task.run_id,))
                edges = [edge_from_row(r) for r in cur.fetchall()]
                cur.execute(_ATTEMPTS_FOR_TASK, (task.id,))
                atts = [attempt_from_row(r) for r in cur.fetchall()]
                outs_by_att: dict[AttemptId, list[Output]] = defaultdict(list)
                if atts:
                    cur.execute(_OUTPUTS_FOR_ATTEMPTS, ([UUID(str(a.id)) for a in atts],))
                    for orow in cur.fetchall():
                        o = output_from_row(orow)
                        outs_by_att[o.attempt_id].append(o)
                return build_task_doc(
                    task,
                    bundle=bundle,
                    tasks_by_id=tasks_by_id,
                    edges=edges,
                    attempts=atts,
                    outputs_by_attempt=outs_by_att,
                    summary_only=False,
                )

        return run(_op)

    def task_attempts_view(self, task_id: TaskId) -> JsonObject:
        def _op() -> JsonObject:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_TASK, (task_id,))
                if cur.fetchone() is None:
                    raise not_found("task", task_id)
                cur.execute(_ATTEMPTS_FOR_TASK, (task_id,))
                atts = [attempt_from_row(r) for r in cur.fetchall()]
                outs_by_att: dict[AttemptId, list[Output]] = defaultdict(list)
                if atts:
                    cur.execute(_OUTPUTS_FOR_ATTEMPTS, ([UUID(str(a.id)) for a in atts],))
                    for orow in cur.fetchall():
                        o = output_from_row(orow)
                        outs_by_att[o.attempt_id].append(o)
                return {"attempts": [build_attempt_summary_doc(a, outs_by_att.get(a.id, ())) for a in atts]}

        return run(_op)

    def attempt_view(self, attempt_id: AttemptId) -> AttemptView:
        def _op() -> AttemptView:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_ATTEMPT, (attempt_id,))
                arow = cur.fetchone()
                if arow is None:
                    raise not_found("attempt", attempt_id)
                att = attempt_from_row(arow)
                cur.execute(_ENV_FOR_ATTEMPT, (attempt_id,))
                erow = cur.fetchone()
                env = None if erow is None else environment_from_row(erow)
                cur.execute(_STAGES_FOR_ATTEMPT, (attempt_id,))
                stages = [stage_from_row(r) for r in cur.fetchall()]
                cur.execute(_STEPS_FOR_ATTEMPT, (attempt_id,))
                steps = [step_from_row(r) for r in cur.fetchall()]
                cur.execute(_OUTPUTS_FOR_ATTEMPTS, ([UUID(str(attempt_id))],))
                outs = [output_from_row(r) for r in cur.fetchall()]
                cur.execute(_CHECKS_FOR_ATTEMPT, (att.task_id, attempt_id))
                checks = [check_from_row(r) for r in cur.fetchall()]
                cur.execute(_REVIEWS_FOR_ATTEMPT, (att.task_id, attempt_id))
                revs = [review_from_row(r) for r in cur.fetchall()]
                fnds = []
                if revs:
                    cur.execute(_FINDINGS_FOR_REVIEWS, ([UUID(str(rv.id)) for rv in revs],))
                    fnds = [finding_from_row(r) for r in cur.fetchall()]
                cur.execute(_EFFECTS_FOR_ATTEMPT, (attempt_id,))
                effs = [effect_from_row(r) for r in cur.fetchall()]
                cur.execute(_RECOVERIES_FOR_ATTEMPT, (att.run_id, attempt_id))
                recs = [recovery_from_row(r) for r in cur.fetchall()]
                return build_attempt_detail_doc(
                    att,
                    AttemptDetailParts(
                        env=env,
                        stages=stages,
                        steps=steps,
                        outs=outs,
                        checks=checks,
                        revs=revs,
                        fnds=fnds,
                        effs=effs,
                        recs=recs,
                    ),
                )

        return run(_op)

    def step_view(self, step_id: StepId) -> StepView:
        def _op() -> StepView:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_STEP, (step_id,))
                srow = cur.fetchone()
                if srow is None:
                    raise not_found("step", step_id)
                step = step_from_row(srow)
                return build_step_view_doc(step, usage_to_json(step.usage))

        return run(_op)

    def inbox_page(
        self, scope_ids: Sequence[ScopeId], after: Cursor | None, limit: int, kinds: frozenset[DecisionKind]
    ) -> Page[DecisionRequestView]:
        cur_pair = parse_time_id_cursor(after)
        if not scope_ids:
            return {"items": [], "next_after": None}
        cur_dt = None if cur_pair is None else require_aware(cur_pair[0])
        cur_id = None if cur_pair is None else cur_pair[1]
        kinds_arr = None if not kinds else sorted(k.value for k in kinds)
        scope_uuids = [UUID(str(sid)) for sid in scope_ids]

        def _op() -> Page[DecisionRequestView]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _INBOX_PAGE,
                    (kinds_arr, kinds_arr, scope_uuids, scope_uuids, cur_dt, cur_dt, cur_id, limit + 1),
                )
                fetched = cur.fetchall()
                has_more = len(fetched) > limit
                sliced = fetched[:limit]
                tids = [as_uuid(r["task_id"]) for r in sliced if r["task_id"] is not None]
                tasks_map = {}
                if tids:
                    cur.execute(_TASKS_BY_IDS, (tids,))
                    tasks_map = {as_uuid(tr["id"]): task_from_row(tr) for tr in cur.fetchall()}
                items: list[JsonValue] = []
                last_req = None
                for row in sliced:
                    req = decision_request_from_row(row)
                    last_req = req
                    task = None if req.task_id is None else tasks_map.get(UUID(str(req.task_id)))
                    item: dict[str, JsonValue] = {
                        "request_id": str(req.id),
                        "run_id": str(req.run_id),
                        "task_id": None if req.task_id is None else str(req.task_id),
                        "task_display_key": None if task is None else task.display_key,
                        "kind": req.kind.value,
                        "audience": req.audience.value,
                        "category": None if req.category is None else req.category.value,
                        "gate_categories": list[JsonValue](sorted(req.gate_categories)),
                        "payload": thaw_json(req.payload),
                        "state": req.state.value,
                        "revision": req.revision,
                        "created_at": req.created_at.isoformat(),
                        "deadline_at": iso(req.deadline_at),
                        "blocking_reason": (
                            None
                            if (task is None or task.blocking_reason is None)
                            else blocking_reason_to_json(task.blocking_reason)
                        ),
                    }
                    if row["rec_id"] is not None:
                        item["decision_record"] = {"id": str(row["rec_id"]), "state": str(row["rec_status"])}
                    items.append(item)
                nxt = (
                    None
                    if not (has_more and last_req)
                    else f"{last_req.created_at.isoformat()}|{last_req.id}"
                )
                return {"items": items, "next_after": nxt}

        return run(_op)
