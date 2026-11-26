"""Pure facts the advance engine reads from a task state (execution §5.1).

Findings, checks, integrated commits, budgets, retries, question routing and history causes: every helper
reads a ``TaskState`` or a stage entry and returns a value; none decides the next action. The condition
language of workflow stages lives in ``predicates``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final, cast
from uuid import UUID

from skm.kernel.languages import DEBT_FREE_GLOBS
from skm.modules.execution.domain.autonomy import decide_audience, gate_categories
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.domain.decision_record import classify_question
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionState,
    question_digest,
    question_key,
)
from skm.modules.execution.domain.finding import (
    OPEN_FINDING_STATES,
    SEVERITY_RANK,
    FindingState,
    Severity,
    logical_findings,
)
from skm.modules.execution.domain.retry import (
    STOP_CODES,
    RetryAction,
    RetryDecision,
    RetryInputs,
    class_for_code,
    decide_retry,
)
from skm.modules.execution.domain.risk import matching
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
from skm.modules.execution.domain.step import RoleId

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.execution.domain.autonomy import AudienceRoute, Denied, PolicyDefault, Reused
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.contracts import ExecutionPolicy, HistoryCause
    from skm.modules.execution.domain.decision_request import DecisionRequest
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.ids import DecisionRequestId
    from skm.modules.execution.domain.review import Review
    from skm.modules.execution.domain.session import RouteRef
    from skm.modules.execution.domain.step import AttemptStep
    from skm.modules.execution.domain.task import PathPattern
    from skm.modules.execution.domain.workflow.actions import TaskState
    from skm.modules.execution.domain.workflow.history import StageEntry


RULE_ID_PATTERN: Final = re.compile(r"[A-Z][A-Za-z0-9_]{0,31}")


_REASON_CODE: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


MAX_REASON_CODES: Final = 32


MAX_CAUSE_REFS: Final = 200


MAJOR: Final = SEVERITY_RANK[Severity.MAJOR]


REPEATS: Final = frozenset({RetryAction.RETRY, RetryAction.RETRY_AFTER, RetryAction.FALLBACK_ROUTE})


_EXECUTE_ROLES: Final = frozenset({RoleId.EXECUTOR, RoleId.RESEARCHER})


_CHECK_RETRY_KINDS: Final = frozenset(
    {StageOutcomeKind.CHECKS_UNKNOWN, StageOutcomeKind.CHECKS_ERROR, StageOutcomeKind.TREE_CHANGED}
)


_DEBT_FREE_PATTERNS: Final = DEBT_FREE_GLOBS


def latest_task_review(state: TaskState) -> Review | None:
    return max(state.reviews, key=lambda r: r.round_no, default=None)


def triaged_findings(state: TaskState, wanted: FindingState) -> list[Finding]:
    review = latest_task_review(state)
    if review is None:
        return []
    if wanted is FindingState.CONFIRMED:
        rounds = {r.id: r.round_no for r in state.reviews}
        found = [f for f in logical_findings(state.findings, rounds) if f.state is wanted]
    else:
        found = [f for f in state.findings if f.review_id == review.id and f.state is wanted]
    return sorted(found, key=lambda f: (-SEVERITY_RANK[f.severity], f.finding_key))


def loop_progress(state: TaskState, last: StageEntry) -> tuple[str, ...]:
    codes: list[str] = []
    if any(f.first_seen_review_id != f.review_id for f in triaged_findings(state, FindingState.CONFIRMED)):
        codes.append("FINDING_REPEATED")
    record = last.record
    if any(
        e.record.id != record.id and e.record.input_digest == record.input_digest
        for e in state.history.of_stage(record.stage_id)
    ):
        codes.append("INPUT_REPEATED")
    return tuple(codes)


def count_outcomes(state: TaskState, last: StageEntry, wanted: StageOutcomeKind) -> int:
    count = 0
    for item in reversed(state.history.of_stage(last.record.stage_id)):
        if item.record.round_no != last.record.round_no:
            break
        item_kind = kind_of(item.record)
        if item_kind is wanted:
            count += 1
        elif item_kind not in _CHECK_RETRY_KINDS:
            break
    return count


def failed_required(state: TaskState) -> list[CheckExecution]:
    return [c for c in state.checks if c.required and c.state is CheckState.FAILED]


def erred_checks_info(state: TaskState) -> tuple[str, list[tuple[str, UUID]]]:
    erred = [c for c in state.checks if c.required and c.state is CheckState.ERROR]
    code = next((c.error_code for c in erred if c.error_code), None) or "CHECKS_ERROR"
    return code, [("check", c.id) for c in erred]


def effective_check_state(state: TaskState, check: CheckExecution) -> CheckState:
    verdict = state.manual.get(check.id)
    if check.kind is CheckKind.MANUAL and check.state is CheckState.MANUAL_PENDING and verdict is not None:
        return CheckState.PASSED if verdict.verdict == "pass" else CheckState.FAILED
    return check.state


def manual_check_status(state: TaskState) -> tuple[list[CheckExecution], list[CheckExecution], bool]:
    states = {c.id: effective_check_state(state, c) for c in state.checks if c.required}
    pending = [c for c in state.checks if c.required and states[c.id] is CheckState.MANUAL_PENDING]
    failed = [c for c in state.checks if c.required and states[c.id] is CheckState.FAILED]
    return pending, failed, any(item in {CheckState.ERROR, CheckState.UNKNOWN} for item in states.values())


def review_debt_extra(wide: Sequence[tuple[str, str]]) -> dict[str, JsonValue]:
    ordered = sorted(wide)[:50]
    return {
        "review_debt": {
            "paths_outside_findings": [path for _, path in ordered],
            "changes_outside_findings": [{"mount": m, "path": p} for m, p in ordered],
            "count": len(wide),
        }
    }


def _place(mount: JsonValue, path: JsonValue) -> tuple[str, str]:
    return (mount if isinstance(mount, str) else "", str(path))


def changes_outside_findings(state: TaskState, confirmed: Sequence[Finding]) -> list[tuple[str, str]]:
    locations = {_place(f.location.get("mount"), f.location.get("path")) for f in confirmed}
    scope = state.task.declared_write_scope
    patterns: tuple[PathPattern, ...] = () if scope is None else tuple(scope)
    changed = [] if state.output is None else [(p.mount, p.path) for p in state.output.manifest.changed_paths]
    return [
        (mount, path)
        for mount, path in changed
        if (mount, path) not in locations
        and not (
            matching([path], _DEBT_FREE_PATTERNS)
            and matching([path], [p.pattern for p in patterns if p.mount == mount])
        )
    ]


def integrated_commits(state: TaskState, out: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    output = state.output
    if output is None or not output.manifest.mounts:
        return {}
    mounts = [m.mount for m in output.manifest.mounts]
    changed = {m.mount for m in output.manifest.mounts if m.base_commit != m.head_commit} | {
        c.mount for c in output.manifest.changed_paths
    }
    required = changed or set(mounts)
    if state.integration_receipts_by_mount is not None:
        return _commits_from_bound_receipts(
            state.integration_receipts_by_mount, mounts, required, str(output.id), out
        )
    if state.recheck_commits is not None:
        return _commits_from_bound_shas(state.recheck_commits, mounts, required, str(output.id), out)
    if len(mounts) != 1:
        return {}
    mount = mounts[0]
    receipts = out.get("integration_receipts")
    if receipts is not None and receipts != []:
        if not isinstance(receipts, list) or len(receipts) != 1:
            return {}
        tip = _tip(receipts[0], str(output.id))
        return {} if tip is None else {mount: tip}
    shas = out.get("commit_shas")
    return {mount: shas[-1]} if isinstance(shas, list) and shas and isinstance(shas[-1], str) else {}


def _commits_from_bound_receipts(
    by_mount: Mapping[str, Mapping[str, JsonValue]],
    mounts: Sequence[str],
    required: set[str],
    output_id: str,
    out: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    if not by_mount or not set(by_mount) <= set(mounts) or not required <= set(by_mount):
        return {}
    shas = {m: _tip(by_mount[m], output_id) for m in mounts if m in by_mount}
    if any(tip is None for tip in shas.values()):
        return {}
    return _commits_from_bound_shas(cast("dict[str, str]", shas), mounts, required, output_id, out)


def _commits_from_bound_shas(
    commits: Mapping[str, str],
    mounts: Sequence[str],
    required: set[str],
    output_id: str,
    out: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    if not commits or not set(commits) <= set(mounts) or not required <= set(commits):
        return {}
    if any(not sha for sha in commits.values()):
        return {}
    receipts = out.get("integration_receipts")
    if receipts is not None and receipts != []:
        if not isinstance(receipts, list) or len(receipts) != len(commits):
            return {}
        tips = [_tip(r, output_id) for r in receipts]
        if any(t is None for t in tips) or sorted(cast("list[str]", tips)) != sorted(commits.values()):
            return {}
    return {mount: commits[mount] for mount in mounts if mount in commits}


def _tip(receipt: JsonValue | Mapping[str, JsonValue], output_id: str) -> str | None:
    if not isinstance(receipt, Mapping):
        return None
    named = receipt.get("output_ids")
    if not isinstance(named, list) or output_id not in named:
        return None
    shas = receipt.get("commit_shas")
    if isinstance(shas, list) and shas and isinstance(shas[-1], str) and shas[-1]:
        return shas[-1]
    after = receipt.get("after_sha")
    return after if isinstance(after, str) and after else None


def open_owner_requests(
    state: TaskState, blocking_map: Mapping[DecisionKind, BlockingCode]
) -> list[DecisionRequest]:
    reqs = (
        r
        for r in state.open_requests
        if r.state is DecisionState.OPEN
        and r.task_id == state.task.id
        and r.kind in blocking_map
        and r.audience is Audience.OWNER
    )
    return sorted(reqs, key=lambda r: (r.created_at, str(r.id)))


def request_blocking_refs(request: DecisionRequest, code: BlockingCode) -> dict[str, JsonValue]:
    payload, request_id = request.payload, str(request.id)
    if code is BlockingCode.WAITING_ANSWER:
        return {"decision_request_id": request_id, "question_key": request.question_key or request_id}
    if code is BlockingCode.WAITING_APPROVAL:
        refs = payload.get("refs")
        source = refs if isinstance(refs, Mapping) else payload
        return {"intent_id": str(source.get("intent_id") or request_id), "decision_request_id": request_id}
    if code is BlockingCode.BLOCKED_BY_BUDGET:
        return {
            "decision_request_id": request_id,
            "dimension": payload.get("dimension", "unknown"),
            "scope": payload.get("scope", "run"),
            "limit": payload.get("limit", 0),
            "spent": payload.get("spent", 0),
        }
    stop = payload.get("code")
    stop_code = stop if isinstance(stop, str) and stop else "OWNER_DECISION_REQUIRED"
    return {"decision_request_id": request_id, "stop_code": stop_code}


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def budget_block(state: TaskState, stage_type_val: str, reserving: bool) -> JsonObject | None:
    if state.run.unmetered_at is not None or state.budget.get("unmetered") is True:
        return {"reason": "unmetered"}
    estimates, accounts = state.budget.get("estimate"), state.budget.get("accounts")
    for account in accounts if isinstance(accounts, list) else ():
        if not isinstance(account, Mapping):
            continue
        dim, limit = account.get("dimension"), _decimal(account.get("limit"))
        if limit is None or limit <= 0:
            continue
        spent = _decimal(account.get("spent")) or Decimal(0)
        used = spent + (_decimal(account.get("reserved")) or Decimal(0))
        if dim in {"tokens", "usd"} and reserving:
            est = estimates.get(dim) if isinstance(estimates, Mapping) else None
            need = _decimal(est) or Decimal(0)
            fits = used + need <= limit if need > 0 else used < limit
        elif dim in {"wall_seconds", "tool_calls"}:
            fits = spent < limit
        elif dim == "review_rounds" and stage_type_val == "agent_review":
            fits = used < limit
        else:
            continue
        if not fits:
            return {
                "reason": "limit",
                "dimension": dim,
                "scope": account.get("scope", "run"),
                "limit": str(limit),
                "spent": str(spent),
            }
    return None


def open_major_findings(state: TaskState) -> list[Finding]:
    return [
        f for f in state.findings if f.state in OPEN_FINDING_STATES and SEVERITY_RANK[f.severity] >= MAJOR
    ]


def gate_reasons(last: StageEntry) -> list[Mapping[str, JsonValue]]:
    raw = outcome_of(last).get("reasons")
    return [r for r in raw if isinstance(r, Mapping)] if isinstance(raw, list) else []


def advice_origin(entries: Sequence[StageEntry], last: StageEntry) -> StageEntry | None:
    earlier = [e for e in entries if e.record.seq < last.record.seq]
    return next((e for e in reversed(earlier) if e.record.stage_type != "advisor_consult"), None)


def advice_problem(last: StageEntry, previous: StageEntry | None, role: RoleId | None) -> str:
    named = outcome_of(last).get("problem_ref")
    if isinstance(named, str) and ":" in named:
        return named.split(":", 1)[0]
    if previous is None:
        return "readiness"
    if previous.record.stage_type == "run_checks":
        return "checks"
    if role is RoleId.TRIAGER:
        return "findings"
    return "question" if role in _EXECUTE_ROLES else "readiness"


def kind_of(record: object) -> StageOutcomeKind | None:
    outcome_kind = getattr(record, "outcome_kind", None)
    if outcome_kind is not None:
        return cast("StageOutcomeKind", outcome_kind)
    return StageOutcomeKind.RUNTIME_ERROR if getattr(record, "state", None) is StageState.FAILED else None


def outcome_of(entry: StageEntry) -> Mapping[str, JsonValue]:
    return entry.record.outcome or {}


def stage_failures(state: TaskState, stage_id: str) -> int:
    used = 0
    for e in state.history.of_stage(stage_id):
        if e.record.state is StageState.COMPLETED:
            used = 0
        elif e.record.state is StageState.FAILED and kind_of(e.record) is StageOutcomeKind.RUNTIME_ERROR:
            used += 1
    return used


def retry_decision(  # noqa: PLR0913
    state: TaskState,
    policy: ExecutionPolicy,
    entries: Sequence[StageEntry],
    last: StageEntry,
    *,
    role: RoleId | None,
    role_writes: bool,
    stage_retries_cap: int | None,
    route: RouteRef | None,
    max_infra_retries: int,
    retry_budget: int,
    max_wait_s: int,
) -> tuple[RetryDecision, str]:
    record, outcome = last.record, outcome_of(last)
    error_class = class_for_code(record.error_code or "")
    seconds = outcome.get("retry_after_seconds")
    max_r = max_infra_retries if stage_retries_cap is None else min(max_infra_retries, stage_retries_cap)
    own_repeats = sum(1 for e in entries if e.record.mode == "retry")
    run_wide = state.run_retries_used
    inputs = RetryInputs(
        error_class=error_class,
        stage_writes=record.stage_type == "integrate" or role_writes,
        worktree_dirty=outcome.get("worktree_dirty") is True,
        receipt_unresolved=outcome.get("receipt_unresolved") is True,
        attempts_used=stage_failures(state, record.stage_id),
        stage_retries_max=max_r,
        budget_left=retry_budget - (own_repeats if run_wide is None else max(own_repeats, run_wide)),
        retry_after_seconds=seconds if isinstance(seconds, int) and not isinstance(seconds, bool) else None,
        current_route=route,
        max_wait_seconds=max_wait_s,
        role=None if role is None else role.value,
    )
    config = policy.get("retry")
    decision = decide_retry(inputs, config if isinstance(config, dict) else {})
    if run_wide is None and decision.action in REPEATS:
        return RetryDecision(RetryAction.STOP, (*decision.reason_codes, "RUN_RETRIES_UNKNOWN")), error_class
    return decision, error_class


def retry_stop_outcome(
    decision: RetryDecision, error_class: str, last: StageEntry, stop_code: str | None
) -> tuple[str, BlockingCode]:
    code = stop_code or STOP_CODES.get(error_class, "RUNTIME_FAILURE_UNCLASSIFIED")
    quota_reset = (
        error_class == "quota"
        and decision.action is RetryAction.STOP
        and "RUN_RETRIES_UNKNOWN" not in decision.reason_codes
        and outcome_of(last).get("retry_after_seconds") is not None
    )
    return code, (BlockingCode.WAITING_BUDGET_RESET if quota_reset else BlockingCode.WAITING_OWNER)


def retry_not_before(now: datetime, wait_seconds: int | None) -> datetime | None:
    return now + timedelta(seconds=wait_seconds) if wait_seconds else None


type QuestionRoute = AudienceRoute | PolicyDefault | Reused | Denied


def _question_paths(
    state: TaskState, last: StageEntry, q: Mapping[str, JsonValue]
) -> tuple[list[str], list[str] | None]:
    extra: list[str] = []
    out = outcome_of(last)
    for raw in (q.get("paths"), out.get("changed_paths"), out.get("changed_paths_by_mount")):
        if isinstance(raw, list):
            extra.extend(p for p in raw if isinstance(p, str))
        elif isinstance(raw, Mapping):
            extra.extend(p for v in raw.values() if isinstance(v, list) for p in v if isinstance(p, str))
    m = None if state.output is None else state.output.manifest
    changed = () if m is None else (*m.changed_paths, *m.outside_write_scope)
    raw_scope = state.task.declared_write_scope
    scope_paths = [] if raw_scope is None else [p.pattern for p in raw_scope]
    paths = list(dict.fromkeys([*extra, *(c.path for c in changed), *scope_paths]))
    if raw_scope is not None:
        return paths, scope_paths
    if m is not None and not extra:
        outside = {c.path for c in m.outside_write_scope}
        return paths, [c.path for c in m.changed_paths if c.path not in outside]
    return paths, None


def evaluate_question_route(
    state: TaskState,
    policy: ExecutionPolicy,
    entries: Sequence[StageEntry],
    last: StageEntry,
) -> tuple[QuestionRoute, dict[str, JsonValue], frozenset[str], str, list[tuple[str, UUID]], JsonValue]:
    items = outcome_of(last).get("questions")
    q: dict[str, JsonValue] = {}
    if isinstance(items, list) and items and isinstance(items[0], Mapping):
        q = dict(cast("Mapping[str, JsonValue]", items[0]))
    key = question_key(state.task.display_key, q)
    q_id = str(q.get("id") or key)
    facts = q.get("facts")
    category = classify_question(
        cast("JsonObject", facts) if isinstance(facts, dict) else {}, str(q.get("kind")), (), (), {}
    )
    patterns = policy.get("risk_patterns")
    paths, scope = _question_paths(state, last, q)
    gates = gate_categories(
        cast("Mapping[str, JsonValue]", facts if isinstance(facts, dict) else {}),
        paths,
        scope,
        patterns if isinstance(patterns, dict) else None,
    )
    asked_before = sum(
        len(cast("list[JsonValue]", outcome_of(e).get("questions") or []))
        for e in entries[:-1]
        if kind_of(e.record) is StageOutcomeKind.QUESTION
    )
    route = decide_audience(
        q,
        category,
        gates,
        policy,
        state.reusable.get(key),
        state.advisor_rounds_used,
        asked_before,
        task_key=state.task.display_key,
        answered_by_policy_before=key in state.policy_answered,
    )
    info: dict[str, JsonValue] = {"question_id": q_id, "question_key": key, "category": category.value}
    digest = question_digest(state.task.display_key, q)
    refs = [("decision_request", UUID(q_id))] if _is_uuid(q_id) else []
    return route, info, gates, digest, refs, q.get("revision", 1)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def wrap_j7_cause(inner_cause: HistoryCause, refs: Sequence[tuple[str, UUID]]) -> HistoryCause:
    fired = inner_cause.get("advance_rule")
    codes = [str(c) for c in cast("list[str]", inner_cause["reason_codes"])]
    if isinstance(fired, str):
        codes.insert(0, f"VIA_{fired.upper()}")
    raw_refs = cast("list[dict[str, str]]", inner_cause["refs"])
    kept = [(str(r["kind"]), UUID(str(r["id"]))) for r in raw_refs]
    return make_cause("decision_answered", "J7", codes, [*refs, *kept])


type _RefList = list[tuple[str, UUID]]


def triage_facts(
    state: TaskState, last: StageEntry, gate: bool, reasons: Sequence[str]
) -> tuple[list[Finding], list[Finding], _RefList, tuple[str, ...], list[Finding], _RefList]:
    confirmed = triaged_findings(state, FindingState.CONFIRMED)
    rejected = triaged_findings(state, FindingState.REJECTED)
    review = latest_task_review(state)
    base: _RefList = [] if review is None else [("review", review.id)]
    codes = (*loop_progress(state, last), *reasons)
    blocking = [f for f in confirmed if SEVERITY_RANK[f.severity] >= MAJOR] if gate else confirmed
    refs = [*base, *(("finding", f.id) for f in confirmed)]
    return confirmed, rejected, base, codes, blocking, refs


def advice_facts(
    state: TaskState, last: StageEntry, previous: StageEntry | None, prev_role: RoleId | None
) -> tuple[str, AttemptStep | None, _RefList, tuple[DecisionRequestId, ...]]:
    problem = advice_problem(last, previous, prev_role)
    step = max(last.steps, key=lambda s: s.seq, default=None)
    refs: _RefList = [] if step is None else [("step", step.id)]
    ids = tuple(
        r.id
        for r in state.open_requests
        if r.kind is DecisionKind.QUESTION and r.audience is not Audience.OWNER
    )
    return problem, step, refs, ids


def make_cause(
    trigger_kind: str,
    advance_rule: str | None,
    reason_codes: Iterable[str] = (),
    refs: Iterable[tuple[str, UUID]] = (),
) -> HistoryCause:
    if advance_rule is not None and not RULE_ID_PATTERN.fullmatch(advance_rule):
        raise ValueError(f"advance_rule {advance_rule!r} is not a rule id")
    codes = list(dict.fromkeys(reason_codes))
    if len(codes) > MAX_REASON_CODES or not all(_REASON_CODE.fullmatch(code) for code in codes):
        raise ValueError("reason codes are at most 32 UPPER_SNAKE codes")
    unique = list(dict.fromkeys(refs))
    if len(unique) > MAX_CAUSE_REFS:
        raise ValueError("a cause holds at most 200 refs")
    return {
        "trigger_kind": trigger_kind,
        "advance_rule": advance_rule,
        "reason_codes": list(codes),
        "refs": [{"kind": kind, "id": str(ref_id)} for kind, ref_id in unique],
    }
