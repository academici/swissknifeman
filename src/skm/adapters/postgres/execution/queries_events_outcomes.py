"""Event, budget, receipt, autopilot, and environment query helpers for ``PostgresExecutionQueries``."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    autopilot_from_row,
    budget_account_from_row,
    environment_from_row,
    finding_from_row,
    output_from_row,
    review_from_row,
    review_request_from_row,
    run_from_row,
)
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import run
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.ids import RunId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.autopilot import AutopilotStateKind
from skm.modules.execution.domain.environment import EnvironmentState
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.history import MAX_PAGE_EVENTS, build_history
from skm.modules.execution.domain.read_documents import (
    build_budget_view_doc,
    event_short_code,
    iso,
    parse_time_id_cursor,
    timeline_kind,
)
from skm.modules.execution.domain.review_request import CommitReviewTarget
from skm.modules.execution.domain.stored_payloads import not_found

if TYPE_CHECKING:
    from skm.kernel.ids import HostId, PlanId, ProjectId, RevisionId
    from skm.modules.execution.domain.contracts import (
        AutopilotStatusView,
        Cursor,
        EnvironmentView,
        HistoryPage,
        Page,
        ReviewReceipt,
        RunBudgetView,
        TimelineEntry,
    )

__all__: list[str] = []

_GET_RUN: Final = "SELECT * FROM skm_execution.runs WHERE id = %s"
_TIMELINE: Final = """
SELECT id, event_type, stream_seq, payload, occurred_at, recorded_at
  FROM skm_core.domain_events
 WHERE stream_kind = 'run' AND stream_id = %s AND stream_seq > %s
 ORDER BY stream_seq ASC
 LIMIT %s
"""
_HEAD_RUN_SEQ: Final = """
SELECT COALESCE(MAX(stream_seq), 0) AS head_seq
  FROM skm_core.domain_events
 WHERE stream_kind = 'run' AND stream_id = %s
"""
_RECONFIG_EVENTS: Final = """
SELECT payload
  FROM skm_core.domain_events
 WHERE stream_kind = 'run'
   AND stream_id = %s
   AND event_type = 'urn:skm:execution:event:run-reconfigured:v1'
 ORDER BY stream_seq ASC
"""
_HISTORY_EVENTS: Final = """
SELECT id, event_type, stream_seq, payload, occurred_at, recorded_at
  FROM skm_core.domain_events
 WHERE stream_kind = 'run'
   AND stream_id = %s
   AND stream_seq > %s
   AND stream_seq <= %s
 ORDER BY stream_seq ASC
 LIMIT %s
"""
_LATEST_RUN_ID: Final = """
SELECT r.id
  FROM skm_execution.runs r
  JOIN skm_planning.plans p ON p.id = r.plan_id
 WHERE r.project_id = %s
   AND r.kind = 'plan'
   AND p.purpose = 'standard'
   AND (%s::uuid IS NULL OR r.plan_id = %s::uuid)
   AND (%s::uuid IS NULL OR r.revision_id = %s::uuid)
 ORDER BY r.created_at DESC, r.id::text DESC
 LIMIT 1
"""
# The run's own accounts and its tasks' accounts, each reached through the partial index of its scope.
_BUDGET_ACCOUNTS_FOR_RUN: Final = """
SELECT * FROM (
    SELECT b.* FROM skm_execution.budget_accounts b WHERE b.scope = 'run' AND b.run_id = %s
    UNION ALL
    SELECT b.*
      FROM skm_execution.run_tasks t
      JOIN skm_execution.budget_accounts b ON b.scope = 'task' AND b.task_id = t.id AND b.run_id = t.run_id
     WHERE t.run_id = %s
) AS accounts
 ORDER BY CASE WHEN scope = 'run' THEN 0 ELSE 1 END ASC,
          COALESCE(task_id::text, '') ASC,
          dimension ASC,
          id::text ASC
"""
_UNKNOWN_USAGE_STEPS: Final = """
SELECT count(*) AS cnt
  FROM skm_execution.attempt_steps s
  JOIN skm_execution.attempts a ON a.id = s.attempt_id
 WHERE a.run_id = %s
   AND s.state <> 'started'
   AND (s.usage IS NULL OR s.usage->>'status' = 'unknown')
"""
_GET_REVIEW_REQ: Final = "SELECT * FROM skm_execution.review_requests WHERE id = %s"
# Through the run's tasks: reviews are indexed by task, not by run.
_LATEST_REVIEW_FOR_RUN: Final = """
SELECT v.*
  FROM skm_execution.run_tasks t
  JOIN skm_execution.reviews v ON v.task_id = t.id
 WHERE t.run_id = %s
 ORDER BY v.round_no DESC, v.id::text DESC
 LIMIT 1
"""
_LATEST_OUTPUT_FOR_RUN: Final = """
SELECT o.*
  FROM skm_execution.attempt_outputs o
  JOIN skm_execution.attempts a ON a.id = o.attempt_id
 WHERE a.run_id = %s
 ORDER BY o.sealed_at DESC, o.seq DESC
 LIMIT 1
"""
_FINDINGS_FOR_REVIEWS: Final = """
SELECT * FROM skm_execution.review_findings WHERE review_id = ANY(%s::uuid[]) ORDER BY id::text ASC
"""
_GET_AUTOPILOT: Final = "SELECT * FROM skm_execution.autopilot_states WHERE project_id = %s"
_ENVIRONMENTS_PAGE: Final = """
SELECT e.*, a.run_id, COALESCE(t.display_key, '') AS task_display_key
  FROM skm_execution.execution_environments e
  LEFT JOIN skm_execution.attempts a ON a.id = e.attempt_id
  LEFT JOIN skm_execution.run_tasks t ON t.id = a.task_id
 WHERE e.host_id = %s
   AND (NOT %s OR e.state = 'discarded')
   AND (%s::timestamptz IS NULL OR (e.created_at, e.id::text) > (%s::timestamptz, %s::text))
 ORDER BY e.created_at ASC, e.id::text ASC
 LIMIT %s
"""


class QueriesEventsOutcomesMixin:
    _conn: psycopg.Connection[Any]

    def timeline(self, run_id: RunId, after_seq: int | None, limit: int) -> Page[TimelineEntry]:
        floor = 0 if after_seq is None else after_seq

        def _op() -> Page[TimelineEntry]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_TIMELINE, (run_id, floor, limit + 1))
                fetched = cur.fetchall()
                has_more = len(fetched) > limit
                sliced = fetched[:limit]
                items: list[JsonValue] = []
                for row in sliced:
                    ev_type = str(row["event_type"])
                    pl = thaw_json(row["payload"])
                    pl_dict = pl if isinstance(pl, dict) else {}
                    tid, aid = pl_dict.get("task_id"), pl_dict.get("attempt_id")
                    code = event_short_code(ev_type)
                    occ = cast("datetime", row["occurred_at"]).isoformat()
                    rec = cast("datetime", row["recorded_at"]).isoformat()
                    items.append(
                        {
                            "seq": int(row["stream_seq"]),
                            "event_id": str(row["id"]),
                            "event_type": ev_type,
                            "at": occ,
                            "occurred_at": occ,
                            "recorded_at": rec,
                            "kind": timeline_kind(ev_type),
                            "task_id": tid if isinstance(tid, str) else None,
                            "attempt_id": aid if isinstance(aid, str) else None,
                            "code": code,
                            "summary": str(pl_dict.get("summary", code)),
                            "refs": {
                                k: v for k, v in pl_dict.items() if k.endswith("_id") and isinstance(v, str)
                            },
                            "payload": pl_dict,
                        }
                    )
                nxt = None if not (has_more and sliced) else str(int(sliced[-1]["stream_seq"]))
                return {"items": items, "next_after": nxt}

        return run(_op)

    def head_run_seq(self, run_id: RunId) -> int:
        def _op() -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_HEAD_RUN_SEQ, (run_id,))
                row = cur.fetchone()
                return 0 if row is None else int(row["head_seq"])

        return run(_op)

    def run_reconfiguration_order(self, run_id: RunId) -> tuple[UUID, ...]:
        def _op() -> tuple[UUID, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_RECONFIG_EVENTS, (run_id,))
                out: list[UUID] = []
                for row in cur.fetchall():
                    pl = thaw_json(row["payload"])
                    if isinstance(pl, dict) and isinstance(raw_id := pl.get("reconfiguration_id"), str):
                        try:
                            out.append(UUID(raw_id))
                        except ValueError:
                            continue
                return tuple(out)

        return run(_op)

    def history(
        self, run_id: RunId, *, after: Cursor | None, through_seq: int | None, limit: int
    ) -> HistoryPage:
        bound = self.head_run_seq(run_id) if through_seq is None else through_seq
        after_seq = 0 if after is None else int(after)
        return build_history(
            self.run_events(run_id, after_seq, bound, limit),
            bound,
            run_id=str(run_id),
            after_seq=after_seq,
            limit=limit,
        )

    def run_events(
        self, run_id: RunId, after_seq: int, through_seq: int, limit: int
    ) -> tuple[JsonObject, ...]:
        def _op() -> tuple[JsonObject, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_HISTORY_EVENTS, (run_id, after_seq, through_seq, min(limit, MAX_PAGE_EVENTS)))
                return tuple(
                    {
                        "id": str(row["id"]),
                        "stream_kind": "run",
                        "stream_id": str(run_id),
                        "stream_seq": int(row["stream_seq"]),
                        "event_type": str(row["event_type"]),
                        "occurred_at": cast("datetime", row["occurred_at"]).isoformat(),
                        "recorded_at": cast("datetime", row["recorded_at"]).isoformat(),
                        "payload": cast("JsonObject", thaw_json(row["payload"])),
                    }
                    for row in cur.fetchall()
                )

        return run(_op)

    def latest_run_id(
        self,
        project_id: ProjectId,
        plan_id: PlanId | None = None,
        *,
        revision_id: RevisionId | None = None,
    ) -> RunId | None:
        def _op() -> RunId | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LATEST_RUN_ID, (project_id, plan_id, plan_id, revision_id, revision_id))
                row = cur.fetchone()
                return None if row is None else RunId(as_uuid(row["id"]))

        return run(_op)

    def budget_view(self, run_id: RunId) -> RunBudgetView:
        def _op() -> RunBudgetView:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_RUN, (run_id,))
                if cur.fetchone() is None:
                    raise not_found("run", run_id)
                cur.execute(_BUDGET_ACCOUNTS_FOR_RUN, (run_id, run_id))
                accs = [budget_account_from_row(r) for r in cur.fetchall()]
                cur.execute(_UNKNOWN_USAGE_STEPS, (run_id,))
                urow = cur.fetchone()
                unknown_steps = 0 if urow is None else int(urow["cnt"])
                return build_budget_view_doc(accs, unknown_steps)

        return run(_op)

    def review_receipt(self, run_id: RunId) -> ReviewReceipt:
        def _op() -> ReviewReceipt:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_RUN, (run_id,))
                rrow = cur.fetchone()
                if rrow is None:
                    raise not_found("review_receipt", run_id)
                r = run_from_row(rrow)
                if r.review_request_id is None:
                    raise not_found("review_receipt", run_id)
                cur.execute(_GET_REVIEW_REQ, (r.review_request_id,))
                reqrow = cur.fetchone()
                if reqrow is None:
                    raise not_found("review_request", r.review_request_id)
                req = review_request_from_row(reqrow)
                cur.execute(_LATEST_REVIEW_FOR_RUN, (run_id,))
                revrow = cur.fetchone()
                latest_rev = None if revrow is None else review_from_row(revrow)
                cur.execute(_LATEST_OUTPUT_FOR_RUN, (run_id,))
                outrow = cur.fetchone()
                if latest_rev is not None:
                    cur.execute(
                        "SELECT * FROM skm_execution.attempt_outputs WHERE id = %s", (latest_rev.output_id,)
                    )
                    outrow = cur.fetchone()
                latest_out = None if outrow is None else output_from_row(outrow)
                fnds: list[JsonValue] = []
                if latest_rev is not None:
                    cur.execute(_FINDINGS_FOR_REVIEWS, ([UUID(str(latest_rev.id))],))
                    fnds = [
                        {
                            "finding_id": str(f.id),
                            "finding_key": f.finding_key,
                            "location": dict(f.location),
                            "state": f.state.value,
                            "severity": f.severity.value,
                            "category": f.category,
                            "message": f.message,
                        }
                        for f in (finding_from_row(fr) for fr in cur.fetchall())
                    ]
                base_c = req.target.base_commit
                head_c = (
                    req.target.head_commit
                    if isinstance(req.target, CommitReviewTarget)
                    else (
                        next(
                            (m.head_commit for m in latest_out.manifest.mounts if m.mount == req.mount),
                            base_c,
                        )
                        if latest_out is not None
                        else base_c
                    )
                )
                return {
                    "request_id": str(req.id),
                    "run_id": str(r.id),
                    "status": r.status.value,
                    "verdict": (
                        None
                        if (latest_rev is None or latest_rev.verdict is None)
                        else latest_rev.verdict.value
                    ),
                    "findings": fnds,
                    "output_id": str(latest_out.id if latest_out is not None else UUID(int=0)),
                    "tree_digest": (
                        latest_out.manifest.tree_digest if latest_out is not None else ("sha256:" + "0" * 64)
                    ),
                    "base_commit": base_c,
                    "head_commit": head_c,
                }

        return run(_op)

    def autopilot_view(self, project_id: ProjectId) -> AutopilotStatusView:
        def _op() -> AutopilotStatusView:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_AUTOPILOT, (project_id,))
                row = cur.fetchone()
                if row is None:
                    return {
                        "effective_state": AutopilotStateKind.IDLE.value,
                        "state": AutopilotStateKind.IDLE.value,
                        "emergency": False,
                        "current_run_id": None,
                        "queue": [],
                        "counters": {},
                        "stop_code": None,
                        "stop_detail": None,
                        "session_started_at": None,
                    }
                st = autopilot_from_row(row)
                eff = AutopilotStateKind.STOPPED.value if st.emergency else st.state.value
                raw_c = thaw_json(st.counters)
                return {
                    "effective_state": eff,
                    "state": st.state.value,
                    "emergency": st.emergency,
                    "current_run_id": None if st.current_run_id is None else str(st.current_run_id),
                    "queue": [],
                    "counters": raw_c if isinstance(raw_c, dict) else {},
                    "stop_code": st.stop_code,
                    "stop_detail": st.stop_detail,
                    "session_started_at": iso(st.session_started_at),
                }

        return run(_op)

    def environments_page(
        self, host_id: HostId, removable_only: bool, after: Cursor | None, limit: int
    ) -> Page[EnvironmentView]:
        cur_pair = parse_time_id_cursor(after)
        cur_dt = None if cur_pair is None else require_aware(cur_pair[0])
        cur_id = None if cur_pair is None else cur_pair[1]

        def _op() -> Page[EnvironmentView]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _ENVIRONMENTS_PAGE,
                    (host_id, removable_only, cur_dt, cur_dt, cur_id, limit + 1),
                )
                fetched = cur.fetchall()
                has_more = len(fetched) > limit
                sliced = fetched[:limit]
                items: list[JsonValue] = []
                last_env = None
                for row in sliced:
                    env = environment_from_row(row)
                    last_env = env
                    removable = env.state is EnvironmentState.DISCARDED
                    run_id_val = row["run_id"]
                    items.append(
                        {
                            "environment_id": str(env.id),
                            "attempt_id": str(env.attempt_id),
                            "run_id": str(as_uuid(run_id_val) if run_id_val is not None else UUID(int=0)),
                            "task_display_key": str(row["task_display_key"] or ""),
                            "kind": env.kind.value,
                            "state": env.state.value,
                            "local_locator": env.local_locator,
                            "created_at": env.created_at.isoformat(),
                            "discarded_at": iso(env.discarded_at),
                            "removable": removable,
                            "reason": "discarded" if removable else env.state.value,
                        }
                    )
                nxt = (
                    None
                    if not (has_more and last_env)
                    else f"{last_env.created_at.isoformat()}|{last_env.id}"
                )
                return {"items": items, "next_after": nxt}

        return run(_op)
