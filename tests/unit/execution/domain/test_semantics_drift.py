"""Meaning of a role result and the drift between two readings (execution §5.7)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.semantics import (
    NO_IMPACT,
    SEVERITY_RANK,
    STATUS_RANK,
    VERDICT_RANK,
    drift,
    outcome_key,
)

REPORT = "stage-report"
REVIEW = "review-findings"
TRIAGE = "triage-result"


def key_of(kind: str, doc: Any) -> Any:
    return outcome_key(kind, doc)


def issue(kind: str, text: str = "x", **more: Any) -> dict[str, Any]:
    return {"kind": kind, "text": text, **more}


def report(status: str = "done", issues: Any = (), checks: Any = (), questions: Any = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "status": status,
        "summary": "s",
        "open_issues": list(issues),
        "checks_run": list(checks),
    }
    if questions is not None:
        doc["questions"] = questions
    return doc


def finding(
    fid: str = "F1",
    severity: str = "major",
    path: str = "src/a.py",
    scenario: str = "token is replayed",
    **more: Any,
) -> dict[str, Any]:
    return {
        "id": fid,
        "severity": severity,
        "location": {"mount": "api", "path": path},
        "failure_scenario": scenario,
        **more,
    }


def review(verdict: str = "attention", *findings: dict[str, Any]) -> dict[str, Any]:
    return {"verdict": verdict, "findings": list(findings)}


# ---------------------------------------------------------------- orders


def test_orders_put_the_cautious_value_higher() -> None:
    assert list(STATUS_RANK) == ["done", "done_with_deviations", "done_pending_checks", "blocked"]
    assert list(VERDICT_RANK) == ["green", "attention", "red"]
    assert list(SEVERITY_RANK) == ["nit", "minor", "major", "blocker"]
    assert [STATUS_RANK[name] for name in STATUS_RANK] == [0, 1, 2, 3]


# ---------------------------------------------------------------- outcome_key


def test_stage_report_key_keeps_only_the_meaning() -> None:
    doc = report(
        "Done-With Deviations",
        [
            issue("blocker"),
            issue("Escalation"),
            issue("pending"),
            issue("deviation", "d1", impact="i", **{"class": "docs"}, outcome="accepted"),
            issue("deviation", "d2", outcome="follow_up"),
            issue("note"),
        ],
        [
            {"id": "V1", "cmd": "pytest", "exit": 0},
            {"id": "V2", "procedure": "look", "verdict": "pass"},
            {"id": "V3", "cmd": "ruff", "exit": "1"},
            {"id": "tests", "cmd": "ls", "exit": 0},  # not a V<n> acceptance check
        ],
        [{"id": "Q1", "blocking": True}, {"id": "Q2", "blocking": False}],
    )
    key = key_of(REPORT, doc)
    assert isinstance(key, dict)
    assert (key["status"], key["status_rank"]) == ("done_with_deviations", 1)
    assert key["issue_counts"] == {"escalation": 1, "blocker": 1, "pending": 1, "deviation": 2}
    assert key["deviations_accepted"] == 1
    assert key["questions"] == {"Q1": True, "Q2": False}
    assert key["check_rows"] == {"V1": [0], "V2": [0], "V3": [1]}


def test_wording_ids_and_order_are_not_meaning() -> None:
    first = report(
        "done",
        [issue("blocker", "a"), issue("pending", "b")],
        [{"id": "V2", "cmd": "b", "exit": 0}, {"id": "V1", "cmd": "a", "exit": 0}],
    )
    second = report(
        "done",
        [issue("pending", "other words"), issue("blocker", "zzz")],
        [{"id": "V1", "cmd": "A!", "exit": 0}, {"id": "V2", "cmd": "B!", "exit": 0}],
    )
    assert outcome_key(REPORT, first) == outcome_key(REPORT, second)


def test_review_key_ignores_ids_and_keeps_severities_per_identity() -> None:
    doc = review(
        "attention",
        finding("F1", "minor"),
        finding("F2", "blocker"),  # same place and scenario as F1: one identity with two severities
        finding("F3", "major", path="./src\\b.py ", scenario="  Other   Scenario "),
    )
    renumbered = review(
        "ATTENTION",
        finding("F9", "blocker"),
        finding("F8", "major", path="src/b.py", scenario="other scenario"),
        finding("F7", "Minor"),
    )
    key = key_of(REVIEW, doc)
    assert isinstance(key, dict)
    assert key["verdict_rank"] == 1
    assert sorted(len(ranks) for ranks in key["findings"].values()) == [1, 2]
    assert key == key_of(REVIEW, renumbered)
    two = next(ranks for ranks in key["findings"].values() if len(ranks) == 2)
    assert two == [3, 1]  # from the highest down


def test_review_places_distinguish_mounts() -> None:
    api = review("red", finding(path="a.py"))
    web = review("red", {**finding(path="a.py"), "location": {"mount": "web", "path": "a.py"}})
    assert outcome_key(REVIEW, api) != outcome_key(REVIEW, web)
    bare = review("red", {**finding(), "location": "./a.py"})
    assert isinstance(outcome_key(REVIEW, bare), dict)


def test_triage_key_is_the_two_id_sets() -> None:
    doc = {
        "confirmed": [{"finding_id": "F2"}, {"finding_id": "F1"}, {"finding_id": "F1"}],
        "rejected": [{"finding_id": "F3"}],
    }
    assert key_of(TRIAGE, doc) == {"confirmed": ["F1", "F2"], "rejected": ["F3"]}


@pytest.mark.parametrize("doc", [None, 5, "x", [1], [], {}])
def test_garbage_has_a_key_and_never_raises(doc: Any) -> None:
    for kind in (REPORT, REVIEW, TRIAGE):
        outcome_key(kind, doc)
    assert outcome_key("scout-result", {"status": "done"}) == {}
    assert outcome_key(REPORT, doc) in ({}, outcome_key(REPORT, {}))


def test_one_object_is_a_list_of_one_before_and_after() -> None:
    """A blocker written as `open_issues: {...}` is counted, so heal cannot lose it unseen."""
    raw = {"status": "blocked", "summary": "s", "open_issues": issue("blocker")}
    key = key_of(REPORT, raw)
    assert isinstance(key, dict)
    assert key["issue_counts"]["blocker"] == 1
    lost = {"status": "blocked", "summary": "s", "open_issues": []}
    assert drift(REPORT, raw, lost) == ("/open_issues: blocker 1 -> 0",)


# ---------------------------------------------------------------- drift: stage-report


def check(before: dict[str, Any], after: dict[str, Any], *lines: str, kind: str = REPORT) -> None:
    assert drift(kind, before, after) == lines


def test_no_change_and_more_caution_are_not_drift() -> None:
    base = report(
        "done_with_deviations",
        [issue("deviation", "d", outcome="follow_up")],
        [{"id": "V1", "cmd": "c", "exit": 0}],
    )
    check(base, copy.deepcopy(base))
    more = report(
        "blocked",
        [
            issue("deviation", "d", outcome="follow_up"),
            issue("escalation", "e"),
            issue("blocker", "b"),
            issue("pending", "p"),
        ],
        [{"id": "V1", "cmd": "c", "exit": 0}, {"id": "V9", "cmd": "new", "exit": 3}],
        [{"id": "Q1", "blocking": True}],
    )
    check(base, more)


@pytest.mark.parametrize(
    ("before", "after", "line"),
    [
        ("blocked", "done", "/status: blocked -> done"),
        (
            "done_pending_checks",
            "done_with_deviations",
            "/status: done_pending_checks -> done_with_deviations",
        ),
        ("done_with_deviations", "done", "/status: done_with_deviations -> done"),
    ],
)
def test_lowered_status_is_drift(before: str, after: str, line: str) -> None:
    check(report(before), report(after), line)
    check(report(before), {"summary": "s"}, f"/status: {before} -> None")  # the status vanished


def test_unstated_before_has_nothing_to_compare() -> None:
    check(report("finished"), report("done"))


@pytest.mark.parametrize("kind", ["escalation", "blocker", "pending", "deviation"])
def test_a_fewer_issue_of_each_kind_is_drift(kind: str) -> None:
    before = report("blocked", [issue(kind, "one"), issue(kind, "two")])
    after = report("blocked", [issue(kind, "one")])
    check(before, after, f"/open_issues: {kind} 2 -> 1")
    check(
        before,
        report("blocked", [issue("note", "one"), issue("note", "two")]),
        f"/open_issues: {kind} 2 -> 0",
    )


def test_accepting_a_deviation_is_drift() -> None:
    follow_up = report("done_with_deviations", [issue("deviation", "d", outcome="follow_up")])
    accepted = report("done_with_deviations", [issue("deviation", "d", outcome="accepted")])
    check(follow_up, accepted, "/open_issues: deviations accepted 0 -> 1")
    check(accepted, follow_up)  # the opposite is caution


def test_swapping_which_deviation_is_accepted_is_drift() -> None:
    before = report(
        "done_with_deviations",
        [
            issue("deviation", "a", outcome="accepted", impact="i1"),
            issue("deviation", "b", outcome="follow_up", impact="i2"),
        ],
    )
    after = report(
        "done_with_deviations",
        [
            issue("deviation", "a", outcome="follow_up", impact="i1"),
            issue("deviation", "b", outcome="accepted", impact="i2"),
        ],
    )
    check(before, after, "/open_issues: deviation accepted: b (impact: i2, class: -)")


def test_same_text_deviations_are_told_apart_by_impact_and_class() -> None:
    before = report(
        "done_with_deviations",
        [
            issue("deviation", "t", outcome="accepted", impact="one"),
            issue("deviation", "t", outcome="follow_up", impact="two"),
        ],
    )
    after = report(
        "done_with_deviations",
        [
            issue("deviation", "t", outcome="follow_up", impact="one"),
            issue("deviation", "t", outcome="accepted", impact="two"),
        ],
    )
    assert drift(REPORT, before, after) == ("/open_issues: deviation accepted: t (impact: two, class: -)",)


def test_the_defaults_heal_fills_into_a_deviation_are_not_a_new_deviation() -> None:
    bare = report("done_with_deviations", [{"kind": "deviation", "text": "t", "outcome": "accepted"}])
    filled = report(
        "done_with_deviations",
        [{"kind": "deviation", "text": "t", "outcome": "accepted", "class": "other", "impact": NO_IMPACT}],
    )
    check(bare, filled)
    check(filled, bare)


def test_questions_may_not_vanish_or_stop_blocking() -> None:
    before = report("blocked", questions=[{"id": "Q1", "blocking": True}, {"id": "Q2", "blocking": False}])
    check(
        before,
        report("blocked", questions=[{"id": "Q1", "blocking": False}, {"id": "Q2", "blocking": True}]),
        "/questions: Q1 blocking true -> false",
    )
    check(before, report("blocked", questions=[{"id": "Q1", "blocking": True}]), "/questions: Q2 lost")
    check(before, report("blocked", questions=[]), "/questions: Q1 lost", "/questions: Q2 lost")
    check(
        before, report("blocked", questions=[{"id": "Q1", "blocking": True}, {"id": "Q2", "blocking": True}])
    )


def test_check_rows_may_not_vanish_or_change_their_result() -> None:
    before = report(
        "done",
        checks=[{"id": "V1", "cmd": "c", "exit": 0}, {"id": "V2", "procedure": "p", "verdict": "pass"}],
    )
    check(before, report("done", checks=[{"id": "V1", "cmd": "c", "exit": 0}]), "/checks_run: V2 lost")
    check(
        before,
        report(
            "done",
            checks=[{"id": "V1", "cmd": "c", "exit": 1}, {"id": "V2", "procedure": "p", "verdict": "pass"}],
        ),
        "/checks_run: V1 result 0 -> 1",
    )
    # the same result spelled differently is the same result
    check(
        before,
        report("done", checks=[{"id": "V1", "cmd": "c", "exit": "0"}, {"id": "V2", "cmd": "p", "exit": 0}]),
    )
    check(
        report("done", checks=[{"id": "V2", "procedure": "p", "verdict": "pass"}]),
        report("done", checks=[{"id": "V2", "procedure": "p", "verdict": "fail"}]),
        "/checks_run: V2 result 0 -> 1",
    )


# ---------------------------------------------------------------- drift: review and triage


def test_a_lower_verdict_is_drift() -> None:
    finds = [finding("F1", "minor")]
    check(review("red", *finds), review("attention", *finds), "/verdict: red -> attention", kind=REVIEW)
    check(review("attention", *finds), review("green", *finds), "/verdict: attention -> green", kind=REVIEW)
    check(review("attention", *finds), review("red", *finds), kind=REVIEW)
    check(
        review("attention", *finds),
        {"findings": []},
        "/verdict: attention -> None",
        "finding lost at api:src/a.py",
        kind=REVIEW,
    )


def test_a_removed_finding_is_drift() -> None:
    before = review("red", finding("F1", "blocker"), finding("F2", "major", path="src/b.py"))
    after = review("red", finding("F1", "blocker"))
    check(before, after, "finding lost at api:src/b.py", kind=REVIEW)
    twice = review("red", finding("F1", "major"), finding("F2", "major"))  # two findings with one identity
    check(twice, review("red", finding("F1", "major")), "finding lost at api:src/a.py", kind=REVIEW)


def test_a_lowered_severity_is_drift() -> None:
    before = review("red", finding("F1", "blocker"))
    check(
        before,
        review("red", finding("F1", "major")),
        "severity lowered at api:src/a.py: blocker -> major",
        kind=REVIEW,
    )
    check(
        before,
        review("red", finding("F1", "nit")),
        "severity lowered at api:src/a.py: blocker -> nit",
        kind=REVIEW,
    )
    check(review("red", finding("F1", "minor")), review("red", finding("F1", "blocker")), kind=REVIEW)
    both = review("red", finding("F1", "blocker"), finding("F2", "minor"))
    check(
        both,
        review("red", finding("F1", "major"), finding("F2", "minor")),
        "severity lowered at api:src/a.py: blocker -> major",
        kind=REVIEW,
    )


def test_renumbering_and_rewording_the_message_is_not_drift() -> None:
    before = review("red", finding("F1", "blocker", message="old words"))
    after = review("red", finding("F4", "blocker", message="new words", confidence="low"))
    check(before, after, kind=REVIEW)


def test_a_triage_may_not_turn_confirmed_into_rejected_or_lose_it() -> None:
    before = {"confirmed": [{"finding_id": "F1"}, {"finding_id": "F2"}], "rejected": [{"finding_id": "F3"}]}
    check(
        before,
        {"confirmed": [{"finding_id": "F2"}], "rejected": [{"finding_id": "F3"}, {"finding_id": "F1"}]},
        "finding F1 confirmed -> rejected",
        kind=TRIAGE,
    )
    check(
        before,
        {"confirmed": [{"finding_id": "F1"}], "rejected": [{"finding_id": "F3"}]},
        "finding F2 confirmed -> lost",
        kind=TRIAGE,
    )
    check(
        before,
        {"confirmed": [{"finding_id": "F1"}, {"finding_id": "F2"}, {"finding_id": "F3"}], "rejected": []},
        kind=TRIAGE,
    )


def test_a_repair_that_improves_the_meaning_is_refused() -> None:
    """Negative examples of the closed-world law: each 'improvement' below must be caught."""
    original = report(
        "blocked",
        [issue("escalation", "need owner"), issue("blocker", "cannot proceed")],
        [{"id": "V1", "cmd": "pytest", "exit": 1}],
        [{"id": "Q1", "blocking": True}],
    )
    improved = [
        {**original, "status": "done"},
        {**original, "open_issues": [issue("note", "fine")]},
        {**original, "checks_run": [{"id": "V1", "cmd": "pytest", "exit": 0}]},
        {**original, "checks_run": []},
        {**original, "questions": [{"id": "Q1", "blocking": False}]},
    ]
    for result in improved:
        assert drift(REPORT, original, result), result


def test_unreadable_after_loses_everything() -> None:
    assert drift(REPORT, report("blocked"), None) != ()  # type: ignore[arg-type]
    assert drift(REPORT, {}, report("done")) == ()
    assert drift("scout-result", report("blocked"), report("done")) == ()
    assert drift(REVIEW, None, review()) == ()  # type: ignore[arg-type]


# ---------------------------------------------------------------- properties

SCALARS = st.none() | st.booleans() | st.integers() | st.text(max_size=12)
JSON = st.recursive(
    SCALARS,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=25,
)
ISSUES = st.lists(
    st.fixed_dictionaries(
        {
            "kind": st.sampled_from(["escalation", "blocker", "pending", "deviation", "note", "junk"]),
            "text": st.text(max_size=6),
        },
        optional={
            "outcome": st.sampled_from(["accepted", "follow_up", "owner_decision"]),
            "impact": st.text(max_size=4),
        },
    ),
    max_size=6,
)
REPORTS = st.fixed_dictionaries(
    {"status": st.sampled_from([*STATUS_RANK, "junk"]), "summary": st.text(max_size=5), "open_issues": ISSUES}
)


@given(JSON, JSON)
def test_drift_is_total_on_any_json(before: Any, after: Any) -> None:
    for kind in (REPORT, REVIEW, TRIAGE):
        result = drift(kind, before, after)
        assert isinstance(result, tuple)
        assert all(isinstance(line, str) for line in result)


@given(REPORTS)
def test_a_document_never_drifts_from_itself(doc: JsonObject) -> None:
    assert drift(REPORT, doc, copy.deepcopy(doc)) == ()
