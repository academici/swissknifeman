"""Memory read-model queries for ``ExecutionQueries`` (execution §6.2, §8)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.queries_helpers import (
    build_attempt_detail_doc,
    build_attempt_summary_doc,
    build_task_doc,
)
from skm.adapters.memory.execution.review_requests import build_review_receipt
from skm.adapters.memory.execution.state import execution_state, plan_info, usage_to_json
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.autopilot import AutopilotStateKind
from skm.modules.execution.domain.blocking_reason import blocking_reason_to_json
from skm.modules.execution.domain.environment import EnvironmentState
from skm.modules.execution.domain.execution_bundle import DEFAULT_POLICY_KEY, run_selection_to_json
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.history import MAX_PAGE_EVENTS, build_history
from skm.modules.execution.domain.read_documents import (
    build_budget_view_doc,
    build_step_view_doc,
    event_short_code,
    iso,
    parse_time_id_cursor,
    timeline_kind,
)
from skm.modules.execution.domain.run import Run, RunKind, RunStatus
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.stored_payloads import not_found
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.domain.work_policy import work_policy_to_json

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, HostId, PlanId, ProjectId, RevisionId, RunId, ScopeId, TaskId
    from skm.modules.execution.domain.contracts import (
        AttemptView,
        AutopilotStatusView,
        Cursor,
        DecisionRequestView,
        EnvironmentView,
        HistoryPage,
        Page,
        ReviewReceipt,
        RunBudgetView,
        RunSummary,
        RunView,
        StepView,
        TaskView,
        TimelineEntry,
    )
    from skm.modules.execution.domain.decision_request import DecisionKind
    from skm.modules.execution.domain.ids import StepId

__all__ = ["MemoryExecutionQueries"]


class MemoryExecutionQueries:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def run_health_view(self, run_id: RunId, *, now: datetime) -> JsonObject:
        run = self._state.runs.get(run_id)
        if run is None:
            raise not_found("run", run_id)
        reasons: list[JsonValue] = []
        if run.unmetered_at is not None:
            reasons.append("unmetered")
        if run.stop_code is not None:
            reasons.append(f"stop_code:{run.stop_code}")
        expired_leases = any(
            asg.run_id == run_id
            and (ls := self._state.leases.get(asg.id)) is not None
            and ls.expires_at <= now
            for asg in self._state.assignments.values()
        )
        if expired_leases:
            reasons.append("lease_expired")
        if any(r.run_id == run_id and r.outcome is None for r in self._state.recoveries.values()):
            reasons.append("recovery_open")
        blocked = sum(
            1 for t in self._state.tasks.values() if t.run_id == run_id and t.blocking_reason is not None
        )
        if blocked:
            reasons.append("tasks_blocked")
        if expired_leases or "recovery_open" in reasons:
            health = "stalled"
        elif blocked and run.status in {RunStatus.PAUSED, RunStatus.RUNNING}:
            health = "blocked"
        elif reasons:
            health = "degraded"
        else:
            health = "healthy"
        return {"health": health, "reasons": reasons}

    def run_view(self, run_id: RunId) -> RunView:
        run = self._state.runs.get(run_id)
        if run is None:
            raise not_found("run", run_id)
        bundle = self._state.bundles.get(run_id)
        alias = plan_info(self._backend, run.plan_id)[0] if run.plan_id is not None else ""
        counts = Counter(t.status.value for t in self._state.tasks.values() if t.run_id == run_id)
        clk = self._backend.core.clock.clock
        eff_now = clk.now() if clk is not None else (run.finished_at or run.started_at or run.created_at)
        wp_def = (
            bundle.work_policies.get(DEFAULT_POLICY_KEY)
            if (bundle is not None and bundle.work_policies is not None)
            else None
        )
        return {
            "run_id": str(run.id),
            "kind": run.kind.value,
            "plan_id": str(run.plan_id) if run.plan_id is not None else None,
            "plan_alias": alias,
            "revision_no": run.revision_no,
            "status": run.status.value,
            "stop_code": run.stop_code,
            "pause_source": run.pause_source,
            "unmetered": run.unmetered_at is not None,
            "selection": (
                None
                if (bundle is None or bundle.selection is None)
                else run_selection_to_json(bundle.selection)
            ),
            "health": self.run_health_view(run_id, now=eff_now),
            "counts_by_status": dict[str, JsonValue](sorted(counts.items())),
            "started_at": iso(run.started_at),
            "finished_at": iso(run.finished_at),
            "review_grouping": run.review_grouping.mode,
            "bundle_digest": "" if bundle is None else bundle.config_digest,
            "work_policy_default": None if wp_def is None else work_policy_to_json(wp_def),
            "autopilot": run.autopilot,
            "row_version": run.row_version,
        }

    def runs_page(
        self, project_id: ProjectId, after: Cursor | None, limit: int, statuses: frozenset[RunStatus]
    ) -> Page[RunSummary]:
        cur = parse_time_id_cursor(after)
        rows = sorted(
            (
                r
                for r in self._state.runs.values()
                if r.project_id == project_id and (not statuses or r.status in statuses)
            ),
            key=lambda r: (r.created_at, str(r.id)),
            reverse=True,
        )
        if cur is not None:
            rows = [r for r in rows if (r.created_at, str(r.id)) < cur]
        sliced = rows[:limit]
        has_more = len(rows) > limit
        items: list[JsonValue] = []
        for r in sliced:
            alias = plan_info(self._backend, r.plan_id)[0] if r.plan_id is not None else ""
            rtasks = [t for t in self._state.tasks.values() if t.run_id == r.id]
            bundle = self._state.bundles.get(r.id)
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
                    "plan_alias": alias,
                    "revision_id": str(r.revision_id) if r.revision_id is not None else None,
                    "revision_no": r.revision_no,
                    "status": r.status.value,
                    "stop_code": r.stop_code,
                    "created_at": r.created_at.isoformat(),
                    "started_at": iso(r.started_at),
                    "finished_at": iso(r.finished_at),
                    "tasks_total": len(rtasks),
                    "tasks_accepted": sum(1 for t in rtasks if t.status is TaskStatus.ACCEPTED),
                    "work_policy_default": None if wp_def is None else work_policy_to_json(wp_def),
                }
            )
        nxt = None if not (has_more and sliced) else f"{sliced[-1].created_at.isoformat()}|{sliced[-1].id}"
        return {"items": items, "next_after": nxt}

    def task_views(self, run_id: RunId) -> tuple[TaskView, ...]:
        tasks = sorted(
            (t for t in self._state.tasks.values() if t.run_id == run_id),
            key=lambda t: (t.position, str(t.id)),
        )
        return tuple(build_task_doc(self._state, t, summary_only=True) for t in tasks)

    def task_view(self, task_id: TaskId) -> TaskView:
        task = self._state.tasks.get(task_id)
        if task is None:
            raise not_found("task", task_id)
        return build_task_doc(self._state, task, summary_only=False)

    def task_attempts_view(self, task_id: TaskId) -> JsonObject:
        if task_id not in self._state.tasks:
            raise not_found("task", task_id)
        atts = sorted(
            (a for a in self._state.attempts.values() if a.task_id == task_id), key=lambda a: a.attempt_no
        )
        return {"attempts": [build_attempt_summary_doc(self._state, a) for a in atts]}

    def attempt_view(self, attempt_id: AttemptId) -> AttemptView:
        att = self._state.attempts.get(attempt_id)
        if att is None:
            raise not_found("attempt", attempt_id)
        return build_attempt_detail_doc(self._state, att)

    def step_view(self, step_id: StepId) -> StepView:
        step = self._state.steps.get(step_id)
        if step is None:
            raise not_found("step", step_id)
        return build_step_view_doc(step, usage_to_json(step.usage))

    def inbox_page(
        self, scope_ids: Sequence[ScopeId], after: Cursor | None, limit: int, kinds: frozenset[DecisionKind]
    ) -> Page[DecisionRequestView]:
        cur = parse_time_id_cursor(after)
        wanted = {UUID(str(sid)) for sid in scope_ids}
        rows = sorted(
            (
                req
                for req in self._state.decision_requests.values()
                if (not kinds or req.kind in kinds)
                and (
                    UUID(str(req.run_id)) in wanted
                    or (
                        (run := self._state.runs.get(req.run_id)) is not None
                        and UUID(str(run.project_id)) in wanted
                    )
                )
            ),
            key=lambda r: (r.created_at, str(r.id)),
            reverse=True,
        )
        if cur is not None:
            rows = [r for r in rows if (r.created_at, str(r.id)) < cur]
        sliced = rows[:limit]
        has_more = len(rows) > limit
        items: list[JsonValue] = []
        for req in sliced:
            task = None if req.task_id is None else self._state.tasks.get(req.task_id)
            rec = next((dr for dr in self._state.decision_records.values() if dr.request_id == req.id), None)
            item: dict[str, JsonValue] = {
                "request_id": str(req.id),
                "run_id": str(req.run_id),
                "task_id": None if req.task_id is None else str(req.task_id),
                "task_display_key": None if task is None else task.display_key,
                "kind": req.kind.value,
                "audience": req.audience.value,
                "category": None if req.category is None else req.category.value,
                "gate_categories": list[JsonValue](req.gate_categories),
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
            if rec is not None:
                item["decision_record"] = {"id": str(rec.id), "state": rec.status}
            items.append(item)
        nxt = None if not (has_more and sliced) else f"{sliced[-1].created_at.isoformat()}|{sliced[-1].id}"
        return {"items": items, "next_after": nxt}

    def timeline(self, run_id: RunId, after_seq: int | None, limit: int) -> Page[TimelineEntry]:
        floor = 0 if after_seq is None else after_seq
        rid_uuid = UUID(str(run_id))
        matched = sorted(
            (
                ev
                for ev in self._backend.core.events
                if ev.stream_kind == "run" and ev.stream_id == rid_uuid and ev.stream_seq > floor
            ),
            key=lambda ev: ev.stream_seq,
        )
        sliced = matched[:limit]
        has_more = len(matched) > limit
        items: list[JsonValue] = []
        for ev in sliced:
            pl = thaw_json(ev.payload)
            pl_dict = pl if isinstance(pl, dict) else {}
            tid, aid = pl_dict.get("task_id"), pl_dict.get("attempt_id")
            code = event_short_code(ev.type)
            items.append(
                {
                    "seq": ev.stream_seq,
                    "event_id": str(ev.id),
                    "event_type": ev.type,
                    "at": ev.occurred_at.isoformat(),
                    "occurred_at": ev.occurred_at.isoformat(),
                    "recorded_at": ev.recorded_at.isoformat(),
                    "kind": timeline_kind(ev.type),
                    "task_id": tid if isinstance(tid, str) else None,
                    "attempt_id": aid if isinstance(aid, str) else None,
                    "code": code,
                    "summary": str(pl_dict.get("summary", code)),
                    "refs": {k: v for k, v in pl_dict.items() if k.endswith("_id") and isinstance(v, str)},
                    "payload": pl_dict,
                }
            )
        nxt = None if not (has_more and sliced) else str(sliced[-1].stream_seq)
        return {"items": items, "next_after": nxt}

    def head_run_seq(self, run_id: RunId) -> int:
        rid_uuid = UUID(str(run_id))
        seqs = [
            ev.stream_seq
            for ev in self._backend.core.events
            if ev.stream_kind == "run" and ev.stream_id == rid_uuid
        ]
        return max(seqs, default=0)

    def run_reconfiguration_order(self, run_id: RunId) -> tuple[UUID, ...]:
        rid_uuid = UUID(str(run_id))
        reconf_urn = "urn:skm:execution:event:run-reconfigured:v1"
        evs = sorted(
            (
                ev
                for ev in self._backend.core.events
                if ev.stream_kind == "run" and ev.stream_id == rid_uuid and ev.type == reconf_urn
            ),
            key=lambda ev: ev.stream_seq,
        )
        out: list[UUID] = []
        for ev in evs:
            raw_id = ev.payload.get("reconfiguration_id")
            if isinstance(raw_id, str):
                try:
                    out.append(UUID(raw_id))
                except ValueError:
                    continue
        return tuple(out)

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
        evs = sorted(
            (
                ev
                for ev in self._backend.core.events
                if ev.stream_kind == "run"
                and ev.stream_id == run_id
                and after_seq < ev.stream_seq <= through_seq
            ),
            key=lambda ev: ev.stream_seq,
        )[: min(limit, MAX_PAGE_EVENTS)]
        return tuple(
            {
                "id": str(ev.id),
                "stream_kind": "run",
                "stream_id": str(run_id),
                "stream_seq": ev.stream_seq,
                "event_type": ev.type,
                "occurred_at": ev.occurred_at.isoformat(),
                "recorded_at": ev.recorded_at.isoformat(),
                "payload": cast("JsonObject", thaw_json(ev.payload)),
            }
            for ev in evs
        )

    def latest_run_id(
        self,
        project_id: ProjectId,
        plan_id: PlanId | None = None,
        *,
        revision_id: RevisionId | None = None,
    ) -> RunId | None:
        candidates: list[Run] = []
        for run in self._state.runs.values():
            if run.project_id != project_id or run.kind is not RunKind.PLAN:
                continue
            if (plan_id is not None and run.plan_id != plan_id) or (
                revision_id is not None and run.revision_id != revision_id
            ):
                continue
            if plan_info(self._backend, run.require_plan())[1] != "standard":
                continue
            candidates.append(run)
        if not candidates:
            return None
        return max(candidates, key=lambda r: (r.created_at, str(r.id))).id

    def budget_view(self, run_id: RunId) -> RunBudgetView:
        if run_id not in self._state.runs:
            raise not_found("run", run_id)
        accs = sorted(
            (a for a in self._state.budget_accounts.values() if a.run_id == run_id),
            key=lambda a: (0 if a.scope == "run" else 1, str(a.task_id or ""), a.dimension.value, str(a.id)),
        )
        stage_run_attempts = {s.attempt_id for s in self._state.stages.values() if s.run_id == run_id} | {
            a.id for a in self._state.attempts.values() if a.run_id == run_id
        }
        unknown_steps = sum(
            1
            for s in self._state.steps.values()
            if s.attempt_id in stage_run_attempts
            and s.state is not StepState.STARTED
            and (s.usage is None or s.usage.status.value == "unknown")
        )
        return build_budget_view_doc(accs, unknown_steps)

    def review_receipt(self, run_id: RunId) -> ReviewReceipt:
        return build_review_receipt(self._state, run_id)

    def autopilot_view(self, project_id: ProjectId) -> AutopilotStatusView:
        st = self._state.autopilot_states.get(project_id)
        if st is None:
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

    def environments_page(
        self, host_id: HostId, removable_only: bool, after: Cursor | None, limit: int
    ) -> Page[EnvironmentView]:
        cur = parse_time_id_cursor(after)
        rows = sorted(
            (e for e in self._state.environments.values() if e.host_id == host_id),
            key=lambda e: (e.created_at, str(e.id)),
        )
        enriched: list[tuple[datetime, str, JsonObject]] = []
        for env in rows:
            att = self._state.attempts.get(env.attempt_id)
            task = None if att is None else self._state.tasks.get(att.task_id)
            removable = env.state is EnvironmentState.DISCARDED
            if removable_only and not removable:
                continue
            if cur is not None and (env.created_at, str(env.id)) <= cur:
                continue
            enriched.append(
                (
                    env.created_at,
                    str(env.id),
                    {
                        "environment_id": str(env.id),
                        "attempt_id": str(env.attempt_id),
                        "run_id": str(att.run_id if att is not None else UUID(int=0)),
                        "task_display_key": "" if task is None else task.display_key,
                        "kind": env.kind.value,
                        "state": env.state.value,
                        "local_locator": env.local_locator,
                        "created_at": env.created_at.isoformat(),
                        "discarded_at": iso(env.discarded_at),
                        "removable": removable,
                        "reason": "discarded" if removable else env.state.value,
                    },
                )
            )
        sliced = enriched[:limit]
        has_more = len(enriched) > limit
        nxt = None if not (has_more and sliced) else f"{sliced[-1][0].isoformat()}|{sliced[-1][1]}"
        return {"items": [it[2] for it in sliced], "next_after": nxt}
