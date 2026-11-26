"""Shared persisted observations and read-only explanation of every autopilot guard."""

from dataclasses import asdict
from itertools import pairwise
from typing import Any
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._json_reads import integer, objects, optional_text
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._worker_dtos import WireRecord, parse_datetime
from skm.modules.execution.application.commands.start_autopilot import (
    load_state,
    owner_hold,
    policy_for,
    project_scope,
)
from skm.modules.execution.application.commands.stop_autopilot import project_runs
from skm.modules.execution.application.queries import get_autopilot_status
from skm.modules.execution.domain.autopilot import (
    AutopilotFacts,
    AutopilotStateKind,
    effective_policy,
    evaluate_conditions,
)
from skm.modules.execution.domain.decision_request import DecisionKind
from skm.modules.execution.domain.ids import OutputId
from skm.modules.execution.ports import (
    CheckRepository,
    ExecutionQueries,
    ReviewRepository,
    TaskRepository,
)
from skm.platform.config.explain import build_explain


class ExplainAutopilot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:query:explain-autopilot:v1"


class AutopilotExplainView(WireRecord):
    SCHEMA_URN = "urn:skm:execution:view:explain-autopilot:v1"


def run_events(uow: UnitOfWork, run_id: Any) -> list[Any]:
    queries = uow.repo(ExecutionQueries)
    head = queries.head_run_seq(run_id)
    after = 0
    rows: list[Any] = []
    while after < head:
        batch = queries.run_events(run_id, after, head, 200)
        if not batch:
            break
        rows.extend(batch)
        after = integer(batch[-1]["stream_seq"], "stream_seq")
    return rows


def requests_for(uow: UnitOfWork, scope_id: Any) -> list[Any]:
    after = None
    rows: list[Any] = []
    while True:
        page = uow.repo(ExecutionQueries).inbox_page((scope_id,), after, 200, frozenset(DecisionKind))
        rows.extend(objects(page.get("items"), "items"))
        after = optional_text(page.get("next_after"), "next_after")
        if after is None:
            return rows


def stagnant_rounds(counts: list[int]) -> int:
    streak = 0
    for previous, current in pairwise(counts):
        streak = streak + 1 if current > 0 and current >= previous else 0
    return streak


def no_improvement(uow: UnitOfWork, tasks: Any, events: Any) -> int:
    result = 0
    outputs: dict[str, list[str]] = {}
    for event in events:
        if ":check-completed:" not in event["event_type"]:
            continue
        payload = event["payload"]
        key, output = str(payload.get("task_id")), payload.get("output_id")
        if output and output not in outputs.setdefault(key, []):
            outputs[key].append(output)
    for task in tasks:
        reviews = sorted(uow.repo(ReviewRepository).for_task(task.id), key=lambda r: r.round_no)
        findings = uow.repo(ReviewRepository).findings_for_task(task.id)
        counts = [
            sum(
                f.review_id == review.id
                and f.severity.value in {"blocker", "major"}
                and f.state.value in {"confirmed", "resolved"}
                for f in findings
            )
            for review in reviews
            if review.state.value == "completed"
        ]
        result = max(result, stagnant_rounds(counts))
        red = [
            sum(
                c.required and c.state.value in {"failed", "error", "unknown"}
                for c in uow.repo(CheckRepository).for_output(OutputId(UUID(output)))
            )
            for output in outputs.get(str(task.id), [])
        ]
        result = max(result, stagnant_rounds(red))
    return result


def observe(
    uow: UnitOfWork, ctx: Any, state: Any, queue: Any, runs: Any
) -> tuple[AutopilotFacts, Any, list[Any]]:
    policy = effective_policy(policy_for(ctx), state.session_limits)
    run = next((r for r in runs if r.id == state.current_run_id), None)
    active = [r for r in runs if r.autopilot and r.status.value not in {"succeeded", "failed", "cancelled"}]
    tasks: Any = [] if run is None else uow.repo(TaskRepository).list_for_run(run.id)
    events = [] if run is None else run_events(uow, run.id)
    requests = requests_for(uow, state.project_id)
    owner_needed = any(
        r["state"] == "open" and r["audience"] == "owner" and r["kind"] in {"escalation", "question"}
        for r in requests
    )
    codes: set[Any] = {run.stop_code} if run is not None else set()
    resets: list[Any] = []
    blocker: Any = None
    for task in tasks:
        wait = task.blocking_reason
        if wait is not None:
            code = str(wait.refs.get("stop_code", wait.code.value))
            codes.add(code)
            if blocker is None:
                blocker = {"task_key": task.display_key, "code": code}
            raw_reset = wait.refs.get("reset_at")
            if raw_reset:
                try:
                    reset = parse_datetime(raw_reset)
                    if reset.tzinfo is not None:
                        resets.append(reset)
                except ValueError:
                    pass
        if task.kind.value == "followup" and task.status.value not in {"accepted", "cancelled", "skipped"}:
            source = task.origin.source_task_id if task.origin is not None else None
            sources = (task.id,) if source is None else (task.id, source)
            owner_needed = owner_needed or any(
                f.severity.value in {"major", "blocker"}
                and f.state.value in {"open", "confirmed", "deferred"}
                for source_id in sources
                for f in uow.repo(ReviewRepository).findings_for_task(source_id)
                if source_id == task.id or (task.origin is not None and f.id in task.origin.finding_ids)
            )
    current_active = run is not None and run in active
    next_plan = next((row for row in queue if row["status"] != "complete"), None)
    ready = {"ready", "ready_with_advisories"} if policy.accept_advisories else {"ready"}
    state_invalid = (
        state.current_run_id is not None and (run is None or not run.autopilot or run.kind.value != "plan")
    ) or any(row["status"] == "archived" for row in queue)
    state_invalid = state_invalid or any(
        ":external-effect-outcome-unknown:" in e["event_type"]
        and not any(
            ":external-effect-recorded:" in later["event_type"]
            and later["payload"].get("effect_id") == e["payload"].get("effect_id")
            and later["payload"].get("state") in {"succeeded", "failed"}
            for later in events
            if later["stream_seq"] > e["stream_seq"]
        )
        for e in events
    )
    previous = state.counters.get("last_blocker")
    repeated = bool(
        blocker
        and blocker == previous
        and state.counters.get("last_blocker_run_id") != str(state.current_run_id)
    )
    repeated = repeated or state.counters.get("repeated_blocker") is True
    selected = set(policy.stop_on)
    owner_needed = (
        owner_needed
        or ("task_failed" in selected and any(t.status.value == "failed" for t in tasks))
        or (
            "attention_verdict" in selected
            and any(
                r.verdict is not None and r.verdict.value == "attention"
                for t in tasks
                for r in uow.repo(ReviewRepository).for_task(t.id)
            )
        )
        or (
            "deviation_accepted" in selected
            and any(":deviation-accepted:" in e["event_type"] for e in events)
        )
    )
    readiness_stop = (
        "readiness_advisories" in selected
        and next_plan is not None
        and next_plan["status"] == "ready_with_advisories"
    )
    facts = AutopilotFacts(
        has_work=next_plan is not None or current_active,
        active=bool(active),
        busy=not current_active
        and sum(not r.autopilot and r.status.value not in {"succeeded", "failed", "cancelled"} for r in runs)
        >= int(value(ctx.config, "execution.parallel.max_runs_per_project", 1)),
        not_ready=not current_active
        and next_plan is not None
        and ((next_plan["status"] not in ready and next_plan["status"] != "archived") or readiness_stop),
        owner_needed=owner_needed or "RESULT_INVALID" in codes,
        waiting_runs=sum(r.status.value in {"paused", "waiting"} for r in active),
        budget_exhausted="BUDGET_EXHAUSTED" in codes,
        quota_exhausted="QUOTA_EXHAUSTED" in codes,
        quota_reset_at=max(resets) if resets and "quota_wait" not in selected else None,
        repeated_blocker=repeated,
        state_invalid=state_invalid,
        checkout_lost=bool(codes & {"CHECKOUT_UNBOUND", "CHECKOUT_MISMATCH", "EMERGENCY_STOPPED"}),
        no_improvement_rounds=no_improvement(uow, tasks, events),
        recovery_open="RECOVERY_CIRCUIT_OPEN" in codes,
        run_stopped=run is not None and run.status.value in {"failed", "cancelled"},
    )
    return facts, blocker, events


def handle(query: ExplainAutopilot, ctx: Any, uow: UnitOfWork) -> AutopilotExplainView:
    state = load_state(query, ctx, uow)
    status = get_autopilot_status.handle(get_autopilot_status.GetAutopilotStatus(query), ctx, uow)
    facts, _, _ = observe(uow, ctx, state, status["queue"], project_runs(uow, state.project_id))
    conditions = evaluate_conditions(state, policy_for(ctx), ctx.clock.now(), facts)
    keys = [key for key in ctx.config.resolved_keys() if key.startswith("execution.autopilot.")]
    explanation: Any = build_explain(ctx.config, keys=keys)
    result = AutopilotExplainView(
        status=status,
        keys=[
            {
                "key": row["key"],
                "value": row.get("value"),
                "provenance": ctx.config.provenance(row["key"]).to_json(),
            }
            for row in explanation["keys"]
        ],
        stop_conditions=[asdict(c) for c in conditions],
    )
    next_plan = next((row for row in status["queue"] if row["status"] != "complete"), None)
    if next_plan is not None:
        result["next_plan"] = next_plan
    # Closest numeric limit is first in the display without disturbing the normative AP order.
    status["nearest_limit"] = min(
        (asdict(c) for c in conditions if c.id in {"AP4", "AP5", "AP17", "AP18"}),
        key=lambda c: (c["limit"] - c["value"]) / max(1, c["limit"]),
    )
    if state.state is AutopilotStateKind.PAUSED:
        status["waiting_for"] = "owner_start" if owner_hold(state) else "coordinator_start"
    return result


SPEC = QuerySpec(
    name="execution.explain_autopilot",
    dto=ExplainAutopilot,
    result=AutopilotExplainView,
    permission="run.read",
    scope_of=project_scope,
    handler=handle,
)
