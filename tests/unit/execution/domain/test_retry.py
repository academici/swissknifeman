"""Retry decision table (execution §5.5; port of ``orch/retry.py``)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from skm.modules.execution.domain.repair import result_retry_allowed
from skm.modules.execution.domain.retry import (
    CODE_CLASSES,
    DEFAULT_ACTIONS,
    ERROR_CLASSES,
    RATE_LIMIT_DEFAULT_WAIT_S,
    STOP_CODES,
    UNKNOWN_OUTCOME,
    RetryAction,
    RetryDecision,
    RetryInputs,
    class_for_code,
    decide_retry,
)
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.workflow.actions import NewAttempt
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.runtimes.public import ErrorClass

CLAUDE = RouteRef(runtime_id="claude_code", model="claude-sonnet", effort="high")
CODEX_ROUTE = {"role": "executor", "runtime": "codex", "model_class": "implementation", "effort": "high"}
SECOND_CLAUDE = {"role": "executor", "runtime": "claude_code", "model_class": "frontier"}


def inputs(error_class: str, **changes: Any) -> RetryInputs:
    values: dict[str, Any] = {
        "error_class": error_class,
        "stage_writes": False,
        "worktree_dirty": False,
        "receipt_unresolved": False,
        "attempts_used": 1,
        "stage_retries_max": 2,
        "budget_left": 5,
    }
    return RetryInputs(**{**values, **changes})


def decide(error_class: str, policy: dict[str, Any] | None = None, /, **changes: Any) -> RetryDecision:
    return decide_retry(inputs(error_class, **changes), policy or {})


# ---------------------------------------------------------------- the table


def test_error_classes_follow_the_runtimes_classes() -> None:
    runtimes = {item.value for item in ErrorClass}
    assert set(ERROR_CLASSES) <= runtimes
    # outcomes of the process that the table has no row for: they reach execution as unknown (fail closed)
    assert runtimes - set(ERROR_CLASSES) == {"crash", "cancelled"}
    assert set(DEFAULT_ACTIONS) == {*ERROR_CLASSES, UNKNOWN_OUTCOME}


@pytest.mark.parametrize(
    ("error_class", "action", "code"),
    [
        ("authentication", RetryAction.STOP, "RUNTIME_AUTH_EXPIRED"),
        ("authorization", RetryAction.STOP, "RUNTIME_FORBIDDEN"),
        ("invalid_request", RetryAction.STOP, "RUNTIME_INVALID_REQUEST"),
        ("content_policy", RetryAction.STOP, "CONTENT_REFUSED"),
        ("quota", RetryAction.RETRY_AFTER, "QUOTA_EXHAUSTED"),
        ("rate_limit", RetryAction.RETRY_AFTER, "RATE_LIMITED"),
        ("model_unavailable", RetryAction.RETRY, "MODEL_UNAVAILABLE"),
        ("provider_internal", RetryAction.RETRY, "RUNTIME_OVERLOADED"),
        ("transport", RetryAction.RETRY, "RUNTIME_TRANSPORT"),
        ("timeout", RetryAction.RETRY, "RUNTIME_TIMEOUT"),
        ("context_limit", RetryAction.REPLAN, "CONTEXT_OVERFLOW"),
        ("unknown", RetryAction.STOP, "RUNTIME_FAILURE_UNCLASSIFIED"),
        (UNKNOWN_OUTCOME, RetryAction.RECONCILE, "OUTCOME_UNKNOWN"),
    ],
)
def test_default_table(error_class: str, action: RetryAction, code: str) -> None:
    assert DEFAULT_ACTIONS[error_class] is action
    assert STOP_CODES[error_class] == code
    assert class_for_code(code) == error_class
    # a read-only stage: the default action as the decision (quota needs a known reset, see below)
    decision = decide(error_class, retry_after_seconds=60)
    if action is RetryAction.STOP:
        assert decision == RetryDecision(RetryAction.STOP, ("ACTION_DEFAULT",))
    elif action is RetryAction.RETRY_AFTER:
        assert (decision.action, decision.wait_seconds) == (RetryAction.RETRY_AFTER, 60)
    else:
        assert decision.action in (action, RetryAction.RETRY)  # unknown_outcome of a read-only stage repeats


def test_stream_incomplete_is_a_transport_failure() -> None:
    """A session without a native terminal event is transport even at exit 0 with valid JSON in the text."""
    error_class = class_for_code("RUNTIME_STREAM_INCOMPLETE")
    assert error_class == "transport"
    assert CODE_CLASSES["RUNTIME_STREAM_INCOMPLETE"] == "transport"
    assert decide(error_class).action is RetryAction.RETRY
    # a writing stage with a dirty worktree is reconciled, not repeated
    dirty = decide(error_class, stage_writes=True, worktree_dirty=True)
    assert (dirty.action, dirty.reason_codes) == (
        RetryAction.RECONCILE,
        ("ACTION_DEFAULT", "PARTIAL_CHANGES"),
    )
    assert class_for_code("SOMETHING_NEW") == "unknown"
    assert (
        decide(class_for_code("RUNTIME_CRASHED")).action is RetryAction.STOP
    )  # fail closed until the table has a row


def test_policy_overrides_the_default_and_the_reason_says_so() -> None:
    policy = {"on_error": {"authentication": {"action": "retry", "max": 3}, "timeout": {"action": "stop"}}}
    assert decide("authentication", policy).reason_codes == ("ACTION_FROM_POLICY",)
    assert decide("authentication", policy).action is RetryAction.RETRY
    assert decide("timeout", policy) == RetryDecision(RetryAction.STOP, ("ACTION_FROM_POLICY",))


def test_unknown_class_and_bad_policy_are_programming_errors() -> None:
    with pytest.raises(ValueError, match="unknown failure class"):
        decide("result_invalid")  # a result form is repaired by §5.8, not retried here
    with pytest.raises(ValueError, match="not a retry action"):
        decide("timeout", {"on_error": {"timeout": {"action": "sleep"}}})
    with pytest.raises(ValueError, match="must be an object"):
        decide("timeout", {"on_error": {"timeout": "retry"}})


# ---------------------------------------------------------------- writes, unknown outcome, partial changes


def test_unknown_outcome_of_a_writing_stage_is_reconciled_never_repeated() -> None:
    decision = decide(UNKNOWN_OUTCOME, stage_writes=True)
    assert decision == RetryDecision(RetryAction.RECONCILE, ("ACTION_DEFAULT", "UNKNOWN_OUTCOME_WRITE"))
    # not even a policy that says retry (and a clean worktree, plenty of budget) bypasses reconcile
    policy = {"on_error": {UNKNOWN_OUTCOME: {"action": "retry"}}, "fallback_routes": [CODEX_ROUTE]}
    forced = decide(UNKNOWN_OUTCOME, policy, stage_writes=True, current_route=CLAUDE)
    assert forced.action is RetryAction.RECONCILE
    assert forced.route is None
    assert forced.reason_codes == ("ACTION_FROM_POLICY", "UNKNOWN_OUTCOME_WRITE")


def test_unknown_outcome_of_a_read_only_stage_is_repeated() -> None:
    decision = decide(UNKNOWN_OUTCOME)
    assert decision == RetryDecision(RetryAction.RETRY, ("ACTION_DEFAULT", "UNKNOWN_OUTCOME_READ_ONLY"))


@pytest.mark.parametrize(
    "cls", ["transport", "timeout", "provider_internal", "model_unavailable", "rate_limit"]
)
@pytest.mark.parametrize("dirty", [{"worktree_dirty": True}, {"receipt_unresolved": True}])
def test_partial_changes_of_a_writing_stage_are_reconciled(cls: str, dirty: dict[str, bool]) -> None:
    decision = decide(cls, stage_writes=True, **dirty)
    assert decision.action is RetryAction.RECONCILE
    assert decision.reason_codes[-1] == "PARTIAL_CHANGES"
    assert decision.wait_seconds is None
    assert decision.route is None
    # the same failure on a read-only stage, or on a clean writing stage, is a plain repeat
    assert decide(cls, **dirty).action is not RetryAction.RECONCILE
    assert decide(cls, stage_writes=True).action is not RetryAction.RECONCILE


def test_content_refusal_has_no_retry_and_no_fallback() -> None:
    """A refusal is final: declared fallbacks, spare budget and a dirty or clean tree change nothing."""
    policy = {"fallback_routes": [CODEX_ROUTE, SECOND_CLAUDE]}
    for stage in ({}, {"stage_writes": True}, {"stage_writes": True, "worktree_dirty": True}):
        decision = decide("content_policy", policy, current_route=CLAUDE, budget_left=100, **stage)
        assert decision == RetryDecision(RetryAction.STOP, ("ACTION_DEFAULT",))
        assert decision.route is None
        assert decision.wait_seconds is None


@pytest.mark.parametrize(
    "override",
    [
        {"action": "retry"},
        {"action": "retry_after"},
        {"action": "fallback_route"},
        {"action": "replan"},
        {"action": "reconcile"},
    ],
)
def test_content_refusal_stays_final_under_a_policy_override(override: dict[str, Any]) -> None:
    """Regression: ``on_error.content_policy`` of retry/fallback must not turn a refusal into a repeat."""
    policy = {"on_error": {"content_policy": override}, "fallback_routes": [CODEX_ROUTE, SECOND_CLAUDE]}
    for stage in ({}, {"stage_writes": True}, {"stage_writes": True, "worktree_dirty": True}):
        decision = decide(
            "content_policy", policy, current_route=CLAUDE, role="executor", budget_left=100, **stage
        )
        assert decision.action is RetryAction.STOP
        assert decision.route is None
        assert decision.wait_seconds is None
        assert decision.reason_codes == ("ACTION_DEFAULT", "CONTENT_POLICY_OVERRIDE_IGNORED")
    explicit_stop = decide("content_policy", {"on_error": {"content_policy": {"action": "stop"}}})
    assert explicit_stop == RetryDecision(RetryAction.STOP, ("ACTION_FROM_POLICY",))


def test_an_unknown_role_never_selects_a_role_bound_fallback() -> None:
    """Regression: a missing role matched every entry, so an executor route could serve an unknown stage."""
    bound = {"fallback_routes": [CODEX_ROUTE, SECOND_CLAUDE]}
    for cls, extra in (("model_unavailable", {}), ("quota", {"max_wait_seconds": 21_600})):
        policy = (
            {**bound, "on_error": {cls: {"action": "fallback_route"}}}
            if cls == "model_unavailable"
            else bound
        )
        missing = decide(cls, policy, current_route=CLAUDE, **extra)
        assert missing.action is RetryAction.STOP
        assert missing.route is None
        assert missing.reason_codes[-1] in {"FALLBACK_UNDECLARED", "RETRY_AFTER_UNKNOWN"}
    named = decide(
        "model_unavailable",
        {**bound, "on_error": {"model_unavailable": {"action": "fallback_route"}}},
        current_route=CLAUDE,
        role="executor",
    )
    assert named.action is RetryAction.FALLBACK_ROUTE
    unbound = {"runtime": "codex", "model_class": "implementation"}
    free = decide(
        "model_unavailable",
        {
            "on_error": {"model_unavailable": {"action": "fallback_route"}},
            "fallback_routes": [CODEX_ROUTE, unbound],
        },
        current_route=CLAUDE,
    )
    assert free.action is RetryAction.FALLBACK_ROUTE
    assert free.route == RouteRef(runtime_id="codex", model="", effort=None)


# ---------------------------------------------------------------- limits


def test_repeat_stops_when_any_limit_of_this_level_is_reached() -> None:
    assert decide("transport", attempts_used=2).action is RetryAction.RETRY  # 2 <= stage_retries_max
    for exhausted in ({"attempts_used": 3}, {"budget_left": 0}, {"budget_left": -1}):
        decision = decide("transport", **exhausted)
        assert decision == RetryDecision(RetryAction.STOP, ("ACTION_DEFAULT", "BUDGET_EXHAUSTED"))
    capped = {"on_error": {"transport": {"action": "retry", "max": 1}}}
    assert decide("transport", capped, attempts_used=1).action is RetryAction.RETRY
    assert decide("transport", capped, attempts_used=2).reason_codes == (
        "ACTION_FROM_POLICY",
        "BUDGET_EXHAUSTED",
    )
    assert decide("transport", {"on_error": {"transport": {"action": "retry"}}}, attempts_used=2).action is (
        RetryAction.RETRY
    )


def test_stop_and_replan_do_not_spend_the_retry_budget() -> None:
    assert decide("context_limit", budget_left=0, attempts_used=9) == RetryDecision(
        RetryAction.REPLAN, ("ACTION_DEFAULT", "CONTEXT_LIMIT")
    )
    assert decide("authentication", budget_left=0).reason_codes == ("ACTION_DEFAULT",)


# ---------------------------------------------------------------- waits and routes


def test_retry_after_waits_for_the_reset() -> None:
    decision = decide("rate_limit", retry_after_seconds=120)
    assert decision == RetryDecision(RetryAction.RETRY_AFTER, ("ACTION_DEFAULT",), wait_seconds=120)
    assert decide("rate_limit").wait_seconds == RATE_LIMIT_DEFAULT_WAIT_S
    assert (
        decide("rate_limit", retry_after_seconds=0).wait_seconds == RATE_LIMIT_DEFAULT_WAIT_S
    )  # §5.5 rule 5: or 30
    assert decide("quota", retry_after_seconds=7200, max_wait_seconds=21600).wait_seconds == 7200


def test_unknown_quota_reset_is_not_waited_for() -> None:
    assert decide("quota", max_wait_seconds=21600) == RetryDecision(
        RetryAction.STOP, ("ACTION_DEFAULT", "RETRY_AFTER_UNKNOWN")
    )
    with_route = decide(
        "quota",
        {"fallback_routes": [CODEX_ROUTE]},
        max_wait_seconds=21600,
        current_route=CLAUDE,
        role="executor",
    )
    assert with_route.action is RetryAction.FALLBACK_ROUTE
    assert with_route.reason_codes == ("ACTION_DEFAULT", "RETRY_AFTER_UNKNOWN", "FALLBACK_ROUTE")
    assert with_route.route == RouteRef(runtime_id="codex", model="", effort="high")
    assert (
        with_route.route_model_class == "implementation"
    )  # the model is chosen by routing, not invented here
    # no declared maximum wait: the donor behaviour is a stop, a route is not guessed
    assert (
        decide("quota", {"fallback_routes": [CODEX_ROUTE]}, current_route=CLAUDE).action is RetryAction.STOP
    )


def test_too_long_a_wait_leaves_for_another_route_or_stops() -> None:
    policy = {"fallback_routes": [CODEX_ROUTE]}
    leave = decide(
        "rate_limit",
        policy,
        retry_after_seconds=90_000,
        max_wait_seconds=21_600,
        current_route=CLAUDE,
        role="executor",
    )
    assert (leave.action, leave.reason_codes) == (
        RetryAction.FALLBACK_ROUTE,
        ("ACTION_DEFAULT", "WAIT_TOO_LONG", "FALLBACK_ROUTE"),
    )
    stay = decide("rate_limit", retry_after_seconds=90_000, max_wait_seconds=21_600)
    assert (stay.action, stay.reason_codes) == (RetryAction.STOP, ("ACTION_DEFAULT", "WAIT_TOO_LONG"))
    no_limit = decide("rate_limit", retry_after_seconds=90_000)
    assert no_limit.action is RetryAction.RETRY_AFTER
    assert no_limit.wait_seconds == 90_000


def test_a_fallback_route_is_another_runtime_or_model_class_of_the_role() -> None:
    policy = {
        "on_error": {"model_unavailable": {"action": "fallback_route"}},
        "fallback_routes": [
            {"role": "reviewer", "runtime": "codex"},  # another role
            {
                "role": "executor",
                "runtime": "claude_code",
                "model_class": "implementation",
            },  # the current route
            SECOND_CLAUDE,
            CODEX_ROUTE,
        ],
    }
    decision = decide(
        "model_unavailable",
        policy,
        current_route=CLAUDE,
        current_model_class="implementation",
        role="executor",
    )
    assert decision.action is RetryAction.FALLBACK_ROUTE
    assert decision.route == RouteRef(runtime_id="claude_code", model="", effort=None)
    assert decision.route_model_class == "frontier"
    assert decision.reason_codes == ("ACTION_FROM_POLICY", "FALLBACK_ROUTE")
    only_current = {"fallback_routes": [policy["fallback_routes"][1]]}
    stuck = decide(
        "model_unavailable",
        {"on_error": policy["on_error"], **only_current},
        current_route=CLAUDE,
        current_model_class="implementation",
        role="executor",
    )
    assert (stuck.action, stuck.reason_codes) == (
        RetryAction.STOP,
        ("ACTION_FROM_POLICY", "FALLBACK_UNDECLARED"),
    )
    nothing = decide("model_unavailable", {"on_error": policy["on_error"]}, current_route=CLAUDE)
    assert nothing.reason_codes == ("ACTION_FROM_POLICY", "FALLBACK_UNDECLARED")


def test_a_concrete_model_in_the_policy_entry_becomes_the_route_model() -> None:
    entry = {"role": "executor", "runtime": "codex", "model": "gpt-x", "effort": "low"}
    decision = decide(
        "model_unavailable",
        {"on_error": {"model_unavailable": {"action": "fallback_route"}}, "fallback_routes": [entry]},
        role="executor",
    )
    assert decision.route == RouteRef(runtime_id="codex", model="gpt-x", effort="low")


def test_policy_noise_does_not_change_the_decision() -> None:
    """Pins and the work policy digest are not inputs of a retry decision."""
    base = decide("transport", {"on_error": {}, "fallback_routes": []})
    noisy = {
        "on_error": {},
        "fallback_routes": [],
        "effective_work_policy_digest": "sha256:x",
        "pins": {"a": 1},
    }
    assert decide("transport", noisy) == base
    assert decide("transport", {}) == base


# ---------------------------------------------------------------- levels do not multiply and do not reset


def launches_until_stop(
    error_class: str, policy: dict[str, Any], *, stage_retries_max: int, budget_total: int
) -> int:
    """Run a stage that always fails; count the runtime processes that were really started."""
    launches, repeats = 0, 0
    route = CLAUDE
    while True:
        launches += 1
        decision = decide_retry(
            inputs(
                error_class,
                attempts_used=launches,
                stage_retries_max=stage_retries_max,
                budget_left=budget_total - repeats,
                current_route=route,
                role="executor",
            ),
            policy,
        )
        if decision.action not in (RetryAction.RETRY, RetryAction.RETRY_AFTER, RetryAction.FALLBACK_ROUTE):
            return launches
        repeats += 1
        route = decision.route or route
        assert launches < 100, "the retry loop does not end"


@pytest.mark.parametrize(
    ("stage_retries_max", "budget_total", "expected"), [(1, 6, 2), (2, 6, 3), (0, 6, 1), (5, 2, 3)]
)
def test_launches_are_bounded_by_the_tighter_infra_limit(
    stage_retries_max: int, budget_total: int, expected: int
) -> None:
    assert (
        launches_until_stop("transport", {}, stage_retries_max=stage_retries_max, budget_total=budget_total)
        == expected
    )


def test_changing_the_route_does_not_reset_the_counters() -> None:
    """fallback_route between two runtimes ping-pongs, but attempts and the run budget keep counting."""
    policy = {
        "on_error": {"transport": {"action": "fallback_route"}},
        "fallback_routes": [
            {"role": "executor", "runtime": "claude_code", "model_class": "implementation"},
            {"role": "executor", "runtime": "codex", "model_class": "implementation"},
        ],
    }
    assert launches_until_stop("transport", policy, stage_retries_max=2, budget_total=6) == 3
    assert launches_until_stop("transport", policy, stage_retries_max=9, budget_total=2) == 3


def test_every_level_has_its_own_counter_and_the_limits_do_not_multiply() -> None:
    """Infra repeats (decide_retry) and result-form repeats (§5.8) are separate counters: launches add up."""
    infra_max, result_max, budget = 2, 1, 6
    script = [
        "transport",
        "invalid",
        "transport",
        "invalid",
        "transport",
        "invalid",
        "transport",
        "invalid",
    ] * 2
    launches = infra_attempts = result_retries = 0
    for event in script:
        launches += 1
        if event == "transport":
            infra_attempts += 1
            decision = decide_retry(
                inputs(
                    "transport", attempts_used=infra_attempts, stage_retries_max=infra_max, budget_left=budget
                ),
                {},
            )
            if decision.action is not RetryAction.RETRY:
                break
        else:
            if not result_retry_allowed(result_retries, result_max):
                break
            result_retries += 1
    assert launches == 1 + infra_max + result_max  # additive: the first launch plus each level's own repeats
    assert launches < (1 + infra_max) * (1 + result_max)  # never the product of the two limits
    assert result_retry_allowed(0, 0) is False
    assert result_retry_allowed(1, 2) is True
    assert result_retry_allowed(2, 2) is False


def test_exhausting_one_level_leaves_the_others_decisions_unchanged() -> None:
    """decide_retry has no result-form input; the result-form rule has no infra input."""
    names = {field.name for field in dataclasses.fields(RetryInputs)}
    assert not {name for name in names if "result" in name or "schema" in name or "rework" in name}
    assert decide("transport", attempts_used=1) == decide("transport", attempts_used=1)
    assert result_retry_allowed(0, 1) is True  # an exhausted infra budget does not touch it


# ---------------------------------------------------------------- distinct causes, modes and refs


def test_retry_rework_new_attempt_and_reconcile_are_different_things() -> None:
    modes = {
        "infra/provider retry": StageMode.RETRY,
        "semantic rework": StageMode.REWORK,
        "final correction": StageMode.FINAL_CORRECTION,
        "resume after interruption": StageMode.RESUME_INTERRUPTED,
        "reconcile": StageMode.RECONCILE,
    }
    assert len(set(modes.values())) == len(modes)
    # the reconcile action of the table is the reconcile mode, not a retry
    assert decide(UNKNOWN_OUTCOME, stage_writes=True).action.value == StageMode.RECONCILE.value
    # each level keeps its history ref in its own field: schema errors, fix brief, interrupted stage
    refs = {field.name for field in dataclasses.fields(FeedbackRefs)}
    assert {"schema_errors_step_id", "fix_brief_id", "interrupted_stage_record_id"} <= refs
    assert NewAttempt(reason_code="RUNTIME_TRANSPORT").reason_code != StageMode.RETRY.value
    # reason codes of the infra table never name a result form or a semantic loop
    reasons = {
        reason
        for cls in (*ERROR_CLASSES, UNKNOWN_OUTCOME)
        for writes in (False, True)
        for dirty in (False, True)
        for reason in decide(
            cls, stage_writes=writes, worktree_dirty=dirty, retry_after_seconds=10
        ).reason_codes
    }
    assert reasons.isdisjoint({"RESULT_INVALID", "REPAIR_SEMANTIC_DRIFT", "REWORK", "NEW_ATTEMPT"})
