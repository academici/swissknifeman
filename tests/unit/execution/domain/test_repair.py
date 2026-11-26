"""Repair of a role result's form: heal, the meaning law, schema hints (execution §5.8)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.repair import (
    MAX_SCHEMA_ERRORS,
    NO_IMPACT,
    NO_SUMMARY,
    heal,
    repair_form,
    result_retry_allowed,
    schema_error_hint,
    schema_errors,
)
from skm.modules.execution.domain.semantics import STATUS_RANK, drift, outcome_key
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs

REPORT = "stage-report"
REVIEW = "review-findings"
TRIAGE = "triage-result"


def report(**changes: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": "urn:skm:execution:role-result:executor:v1",
        "status": "done",
        "summary": "did it",
        "changed_paths": [],
        "evidence": [],
        "checks_run": [],
        "open_issues": [],
    }
    return {**doc, **changes}


def healed(kind: str, doc: Any) -> tuple[Any, list[str]]:
    found: Any = heal(kind, doc)
    assert found["kind"] == "healed", found
    return found["document"], found["notes"]


def finding(fid: str = "F1", **more: Any) -> dict[str, Any]:
    return {
        "id": fid,
        "severity": "major",
        "confidence": "high",
        "basis": "correctness",
        "category": "time",
        "message": "m",
        "failure_scenario": "s",
        "location": {"mount": "api", "path": "a.py"},
        **more,
    }


# ---------------------------------------------------------------- the donor bug: lists


def test_an_object_where_a_list_is_expected_is_a_list_of_one() -> None:
    """Donor `_list` returned the dict itself, and the next loop iterated its keys."""
    blocker = {"kind": "blocker", "text": "cannot reach the db"}
    doc, notes = healed(REPORT, report(status="blocked", open_issues=blocker))
    issues = doc["open_issues"]
    assert {"kind": "blocker", "text": "cannot reach the db"} in issues  # still a blocker, not notes per key
    assert [issue["kind"] for issue in issues] == ["blocker", "escalation"]
    assert issues[1]["text"] == "cannot reach the db"
    assert issues[1]["escalation_class"] == "decision"
    assert "open_issues was one object; it is read as a list of one" in notes
    assert doc["status"] == "blocked"


def test_a_dict_blocker_stays_a_blocker_for_the_drift_check() -> None:
    raw = report(status="blocked", open_issues={"kind": "blocker", "text": "x"})
    outcome = repair_form(REPORT, raw)
    assert outcome["kind"] == "repaired"
    assert outcome_key(REPORT, outcome["result"])["issue_counts"]["blocker"] == 1  # type: ignore[index]
    assert drift(REPORT, raw, outcome["result"]) == ()  # type: ignore[arg-type]
    # a heal that dropped it would be seen: the raw dict counts as one blocker
    lost = {**outcome["result"], "open_issues": []}  # type: ignore[dict-item]
    assert drift(REPORT, raw, lost) != ()


def test_numbers_in_lists_do_not_raise() -> None:
    """Donor: an int where a list was expected gave TypeError in the next iteration."""
    doc, notes = healed(REPORT, report(evidence=7, changed_paths="a.py"))
    assert doc["evidence"] == ["7"]
    assert doc["changed_paths"] == ["a.py"]
    assert "evidence was one int; it is read as a list of one text" in notes
    doc, _ = healed(REPORT, report(evidence=[1, 2.5, True, "e"]))
    assert doc["evidence"] == ["1", "2.5", "True", "e"]
    for key in ("checks_run", "open_issues", "changed_paths"):
        assert heal(REPORT, report(**{key: 5}))["kind"] == "not_healable"
    assert heal(REPORT, report(open_issues=[3]))["kind"] == "not_healable"
    assert heal(REPORT, report(evidence=[{"a": 1}]))["kind"] == "not_healable"
    assert heal(REPORT, report(checks_run=["V1"]))["kind"] == "not_healable"


def test_missing_and_blank_lists_are_empty() -> None:
    doc = {"status": "done", "summary": "x"}
    result, notes = healed(REPORT, doc)
    assert all(result[key] == [] for key in ("changed_paths", "evidence", "checks_run", "open_issues"))
    assert sum("was missing" in note for note in notes) == 4
    result, _ = healed(REPORT, report(open_issues="   ", evidence=""))
    assert result["open_issues"] == []
    assert result["evidence"] == []
    result, _ = healed(REPORT, report(evidence=None))
    assert result["evidence"] == []


def test_heal_does_not_change_its_input() -> None:
    raw = report(
        status="DONE with-deviations",
        open_issues=["a string", {"kind": "Deviation", "text": "d", "extra": [1]}],
        checks_run=[{"id": "V1", "cmd": "c", "exit": "0"}, {"id": "other", "cmd": "x"}],
        changed_paths="a.py",
    )
    snapshot = copy.deepcopy(raw)
    heal(REPORT, raw)
    repair_form(REPORT, raw)
    assert raw == snapshot


# ---------------------------------------------------------------- stage-report rules


def test_status_is_normalized() -> None:
    for spelled, status, issues in [
        ("DONE", "done", []),
        (" Done-With Deviations ", "done_with_deviations", [{"kind": "deviation", "text": "d"}]),
        ("Done-Pending-Checks", "done_pending_checks", [{"kind": "pending", "text": "p"}]),
        ("blocked", "blocked", [{"kind": "escalation", "text": "e"}]),
    ]:
        doc, notes = healed(REPORT, report(status=spelled, open_issues=issues))
        assert doc["status"] == status
        assert (spelled == status) or any("status was spelled" in note for note in notes)
    odd, _ = healed(REPORT, report(status="finished"))
    assert odd["status"] == "finished"  # no honest reading: the schema rejects it and the role is repeated


def test_status_blocker_means_blocked_and_a_blocker_issue_stays() -> None:
    doc, notes = healed(
        REPORT,
        report(
            status="blocker",
            summary="stuck on X",
            open_issues=[{"kind": "blocker", "text": "no db", "impact": "all", "next": "ask"}],
        ),
    )
    assert doc["status"] == "blocked"
    assert [issue["kind"] for issue in doc["open_issues"]] == ["blocker", "escalation"]
    assert any("status was spelled 'blocker'" in note for note in notes)
    for spelled in ("BLOCKER", " Blocker "):
        spelled_doc, _ = healed(REPORT, report(status=spelled, summary="stuck on X"))
        assert spelled_doc["status"] == "blocked"
        assert [issue["kind"] for issue in spelled_doc["open_issues"]] == ["escalation"]
    review, _ = healed(REVIEW, {"verdict": "red", "findings": [finding("F1", severity="blocker")]})
    assert review["findings"][0]["severity"] == "blocker"
    cased, _ = healed(REVIEW, {"verdict": "red", "findings": [finding("F2", severity="BLOCKER")]})
    assert cased["findings"][0]["severity"] == "blocker"


def test_empty_summary_is_replaced_and_a_number_is_kept_as_text() -> None:
    for blank in ("", "  \n", None):
        doc, notes = healed(REPORT, report(summary=blank))
        assert doc["summary"] == NO_SUMMARY
        assert "summary was empty" in notes
    assert healed(REPORT, report(summary=42))[0]["summary"] == "42"
    assert heal(REPORT, report(summary={"a": 1}))["kind"] == "not_healable"


def test_changed_paths_are_deduplicated_in_order_and_otherwise_untouched() -> None:
    row = {"mount": "api", "path": "b.py", "change": "added"}
    doc, notes = healed(REPORT, report(changed_paths=["b.py", "a.py", "b.py", row, dict(row)]))
    assert doc["changed_paths"] == ["b.py", "a.py", row]
    assert any("collapsed" in note for note in notes)
    assert heal(REPORT, report(changed_paths=[5]))["kind"] == "not_healable"


def test_issue_strings_and_extra_keys() -> None:
    doc, notes = healed(
        REPORT,
        report(
            open_issues=[
                "  something odd  ",
                {
                    "kind": " NOTE ",
                    "text": "t",
                    "color": "red",
                    "weight": 3,
                    "empty": "",
                    "nothing": None,
                    "impact": "  ",
                },
            ]
        ),
    )
    assert doc["open_issues"][0] == {"text": "something odd", "kind": "note"}
    assert doc["open_issues"][1] == {"kind": "note", "text": "t (color: red; weight: 3)"}
    assert "an open issue was a plain string; it is kept as a note" in notes
    assert heal(REPORT, report(open_issues=["  "]))["kind"] == "not_healable"


def test_issue_words_are_normalized_or_folded_into_the_text() -> None:
    doc, notes = healed(
        REPORT,
        report(
            open_issues=[
                {
                    "kind": "deviation",
                    "text": "d",
                    "class": "Spec-Mismatch",
                    "severity": "HIGH",
                    "outcome": "Follow Up",
                    "auto_fixable": "TRUE",
                    "evidence": " one.py ",
                },
                {
                    "kind": "note",
                    "text": "n",
                    "class": "weird",
                    "severity": "urgent",
                    "auto_fixable": "maybe",
                    "evidence": [1],
                },
            ],
            status="done_with_deviations",
        ),
    )
    first, second = doc["open_issues"]
    assert (first["class"], first["severity"], first["outcome"], first["auto_fixable"]) == (
        "spec_mismatch",
        "high",
        "follow_up",
        True,
    )
    assert first["evidence"] == ["one.py"]
    assert first["impact"] == NO_IMPACT
    assert set(second) == {"kind", "text"}
    assert second["text"] == "n (class: weird; severity: urgent; auto_fixable: maybe; evidence: [1])"
    assert any("matched no option" in note for note in notes)


def test_a_deviation_is_never_accepted_by_heal_itself() -> None:
    doc, notes = healed(
        REPORT, report(status="done_with_deviations", open_issues=[{"kind": "deviation", "text": "d"}])
    )
    deviation = doc["open_issues"][0]
    assert (deviation["class"], deviation["outcome"], deviation["impact"]) == (
        "other",
        "follow_up",
        NO_IMPACT,
    )
    assert any("a deviation lacked class, outcome, impact" in note for note in notes)
    # an unmatched outcome becomes the cautious default, not "accepted"
    doc, _ = healed(
        REPORT,
        report(
            status="done_with_deviations",
            open_issues=[{"kind": "deviation", "text": "d", "outcome": "ok", "impact": "i"}],
        ),
    )
    assert doc["open_issues"][0]["outcome"] == "follow_up"
    # and an executor's explicit accepted stays accepted without drift
    raw = report(
        status="done_with_deviations",
        open_issues=[
            {"kind": "deviation", "text": "d", "outcome": "accepted", "impact": "i", "class": "docs"}
        ],
    )
    assert repair_form(REPORT, raw)["kind"] == "repaired"


def test_check_rows() -> None:
    doc, notes = healed(
        REPORT,
        report(
            checks_run=[
                {"id": "V1", "cmd": "pytest -q", "exit": "0"},
                {"id": "V2", "cmd": "ruff", "verdict": "fail"},
                {"id": "V3", "procedure": "look at the page", "verdict": " Pass ", "extra": 1},
                {"id": "V4", "command": "make", "exit": 2},
                {"id": "pytest", "cmd": "uv run pytest", "exit": 0},
                {"id": "tests", "procedure": "p", "verdict": "pass"},
            ],
        ),
    )
    assert doc["checks_run"] == [
        {"id": "V1", "cmd": "pytest -q", "exit": 0},
        {"id": "V2", "cmd": "ruff", "exit": 1},
        {"id": "V3", "procedure": "look at the page", "verdict": "pass"},
        {"id": "V4", "cmd": "make", "exit": 2},
    ]
    outside = [issue for issue in doc["open_issues"] if issue["kind"] == "note"]
    assert len(outside) == 1
    assert "pytest: uv run pytest -> 0" in outside[0]["text"]
    assert "tests:" in outside[0]["text"]
    assert any("keys extra dropped" in note for note in notes)
    # no result is invented
    for row in (
        {"id": "V1", "cmd": "c"},
        {"id": "V1", "cmd": "c", "exit": "x"},
        {"id": "V1", "procedure": "p"},
    ):
        assert heal(REPORT, report(checks_run=[row]))["kind"] == "not_healable", row
    assert (
        heal(REPORT, report(checks_run=[{"id": "V1", "procedure": "p", "verdict": "maybe"}]))["kind"]
        == "not_healable"
    )


def test_status_consequences_are_completed_on_the_cautious_side() -> None:
    doc, _ = healed(REPORT, report(status="done_with_deviations"))
    assert [(i["kind"], i["outcome"]) for i in doc["open_issues"]] == [("deviation", "follow_up")]
    doc, _ = healed(REPORT, report(status="done_pending_checks"))
    assert [i["kind"] for i in doc["open_issues"]] == ["pending"]
    doc, notes = healed(REPORT, report(status="done", open_issues=[{"kind": "escalation", "text": "e"}]))
    assert doc["status"] == "blocked"
    assert "an escalation was reported; the report is blocked for the owner" in notes
    doc, _ = healed(REPORT, report(status="done", questions=[{"id": "Q1", "blocking": True}]))
    assert doc["status"] == "blocked"
    assert doc["open_issues"][0]["kind"] == "escalation"
    doc, _ = healed(REPORT, report(status="done", questions=[{"id": "Q1", "blocking": False}]))
    assert doc["status"] == "done"
    assert doc["open_issues"] == []


def test_blocked_without_escalation_gets_one() -> None:
    doc, _ = healed(REPORT, report(status="blocked", summary="stuck on X", open_issues=[]))
    assert doc["open_issues"] == [
        {
            "text": "the executor reported blocked without naming the gap; its summary: stuck on X",
            "kind": "escalation",
            "escalation_class": "decision",
            "next": "the owner reads the summary and the stream of the step",
        }
    ]
    doc, _ = healed(
        REPORT,
        report(
            status="blocked",
            open_issues=[{"kind": "blocker", "text": "no db", "impact": "all", "next": "ask"}],
        ),
    )
    assert [i["kind"] for i in doc["open_issues"]] == ["blocker", "escalation"]
    assert doc["open_issues"][1] == {
        "impact": "all",
        "next": "ask",
        "text": "no db",
        "kind": "escalation",
        "escalation_class": "decision",
    }


def test_a_healthy_report_is_left_alone() -> None:
    raw = report(changed_paths=[{"mount": "api", "path": "a.py", "change": "modified"}], evidence=["out.txt"])
    doc, notes = healed(REPORT, raw)
    assert doc == raw
    assert notes == []


def test_the_main_repair_pipeline_keeps_the_raw_result() -> None:
    raw = report(
        status="Blocked",
        open_issues={"kind": "blocker", "text": "x"},
        checks_run=[{"id": "V1", "cmd": "c", "exit": "3"}],
    )
    outcome = repair_form(REPORT, raw)
    assert outcome["kind"] == "repaired"
    assert outcome["raw"] is raw
    assert outcome["result"]["checks_run"] == [{"id": "V1", "cmd": "c", "exit": 3}]  # type: ignore[index]
    assert outcome["repairs"]
    assert all(isinstance(note, str) for note in outcome["repairs"])  # type: ignore[union-attr]
    bad = repair_form(REPORT, {"summary": []})
    assert bad["kind"] == "not_healable"
    assert bad["raw"] == {"summary": []}
    assert repair_form(REPORT, "text")["kind"] == "not_healable"  # type: ignore[arg-type]


def test_a_mend_that_would_improve_the_meaning_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A defective heal (here: one that drops the blocker) is stopped by the drift check, not trusted."""
    from skm.modules.execution.domain import repair

    raw = report(
        status="blocked", open_issues=[{"kind": "blocker", "text": "x"}, {"kind": "escalation", "text": "x"}]
    )

    def lossy(kind: str, doc: Any) -> Any:
        document = {**doc, "status": "done", "open_issues": []}
        return {"kind": "healed", "document": document, "notes": ["lost it"]}

    monkeypatch.setattr(repair, "heal", lossy)
    outcome = repair.repair_form(REPORT, raw)
    assert outcome["kind"] == "semantic_drift"
    assert outcome["code"] == "REPAIR_SEMANTIC_DRIFT"
    assert "/status: blocked -> done" in outcome["drift"]  # type: ignore[operator]
    assert outcome["raw"] is raw


# ---------------------------------------------------------------- review-findings


def test_review_normalization_and_ids() -> None:
    doc, notes = healed(
        REVIEW,
        {
            "verdict": "ATTENTION",
            "findings": [
                finding("F1", severity="Major", confidence="HIGH"),
                finding("x", severity="nit"),  # not F<n>
                finding("F3", severity="minor"),
            ],
        },
    )
    assert doc["verdict"] == "attention"
    assert [f["id"] for f in doc["findings"]] == ["F1", "F2", "F3"]  # F3 is reserved, so x becomes F2
    assert [f["severity"] for f in doc["findings"]] == ["major", "nit", "minor"]
    assert any("is not F<number>" in note for note in notes)


def test_review_defaults_and_empty_reproduction() -> None:
    raw = finding("F1", reproduction="  ")
    del raw["confidence"]
    raw["basis"] = ""
    doc, notes = healed(
        REVIEW,
        {
            "verdict": "attention",
            "findings": [raw, finding("F2", reproduction={}), finding("F3", reproduction={"argv": ["x"]})],
        },
    )
    first, second, third = doc["findings"]
    assert first["confidence"] == "medium"
    assert first["basis"] == "correctness"
    assert "reproduction" not in first
    assert "reproduction" not in second
    assert third["reproduction"] == {"argv": ["x"]}
    assert any("medium is assumed" in note for note in notes)


def test_findings_win_over_a_green_verdict() -> None:
    blocker, _ = healed(REVIEW, {"verdict": "green", "findings": [finding("F1", severity="blocker")]})
    assert blocker["verdict"] == "red"
    major, _ = healed(REVIEW, {"verdict": "GREEN", "findings": [finding("F1", severity="major")]})
    assert major["verdict"] == "attention"
    minor, _ = healed(REVIEW, {"verdict": "green", "findings": [finding("F1", severity="minor")]})
    assert minor["verdict"] == "green"


def test_attention_and_red_without_findings_are_not_made_green() -> None:
    for verdict in ("attention", "red"):
        doc, _ = healed(REVIEW, {"verdict": verdict, "findings": []})
        assert doc["verdict"] == verdict
        assert doc["findings"] == []
    doc, _ = healed(REVIEW, {"verdict": "red"})
    assert doc["verdict"] == "red"
    assert doc["findings"] == []


def test_a_single_finding_object_and_bad_findings() -> None:
    doc, _ = healed(REVIEW, {"verdict": "attention", "findings": finding("F1")})
    assert len(doc["findings"]) == 1
    assert heal(REVIEW, {"verdict": "red", "findings": ["F1: bad"]})["kind"] == "not_healable"
    assert heal(REVIEW, {"verdict": "red", "findings": 3})["kind"] == "not_healable"
    many = [finding(f"F{n}") for n in range(1, 4)]
    many[1]["id"] = "F1"
    duplicate: Any = {"verdict": "attention", "findings": many}
    assert heal(REVIEW, duplicate) == {
        "kind": "not_healable",
        "reason": "finding id F1 is duplicated",
    }


def test_review_repair_keeps_every_finding_and_severity() -> None:
    raw = {
        "verdict": "GREEN",
        "findings": [
            finding("F9", severity="BLOCKER"),
            finding("F8", severity="Minor", failure_scenario="other"),
        ],
    }
    outcome = repair_form(REVIEW, raw)
    assert outcome["kind"] == "repaired"
    assert drift(REVIEW, raw, outcome["result"]) == ()  # type: ignore[arg-type]


def test_duplicate_check_and_finding_ids_are_not_healable() -> None:
    checks = heal(
        REPORT,
        report(
            checks_run=[
                {"id": "V1", "cmd": "pytest", "exit": 0},
                {"id": "V2", "cmd": "ruff", "exit": 0},
                {"id": "V1", "cmd": "mypy", "exit": 1},
            ]
        ),
    )
    assert checks == {"kind": "not_healable", "reason": "checks_run id V1 is duplicated"}
    procedure = heal(
        REPORT,
        report(
            checks_run=[
                {"id": "V3", "procedure": "look", "verdict": "pass"},
                {"id": "V3", "procedure": "again", "verdict": "fail"},
            ]
        ),
    )
    assert procedure == {"kind": "not_healable", "reason": "checks_run id V3 is duplicated"}
    findings = heal(
        REVIEW,
        {"verdict": "attention", "findings": [finding("F1"), finding("F2"), finding("F1", severity="nit")]},
    )
    assert findings == {"kind": "not_healable", "reason": "finding id F1 is duplicated"}
    # a repeated id that is not V<number> or F<number> is the same refusal, including after strip
    malformed_checks = heal(
        REPORT,
        report(
            checks_run=[
                {"id": "x", "cmd": "pytest", "exit": 0},
                {"id": "x", "cmd": "ruff", "exit": 1},
            ]
        ),
    )
    assert malformed_checks == {"kind": "not_healable", "reason": "checks_run id x is duplicated"}
    padded_checks = heal(
        REPORT,
        report(
            checks_run=[
                {"id": "x", "cmd": "pytest", "exit": 0},
                {"id": " x ", "cmd": "ruff", "exit": 1},
            ]
        ),
    )
    assert padded_checks == {"kind": "not_healable", "reason": "checks_run id x is duplicated"}
    malformed_findings = heal(
        REVIEW,
        {"verdict": "attention", "findings": [finding("x"), finding("x", failure_scenario="other")]},
    )
    assert malformed_findings == {"kind": "not_healable", "reason": "finding id x is duplicated"}
    padded_findings = heal(
        REVIEW,
        {"verdict": "attention", "findings": [finding("x"), finding(" x ", failure_scenario="other")]},
    )
    assert padded_findings == {"kind": "not_healable", "reason": "finding id x is duplicated"}


# ---------------------------------------------------------------- triage-result


def test_triage_normalization() -> None:
    doc, notes = healed(
        TRIAGE,
        {
            "confirmed": [
                {"finding_id": "F1", "decision": "fix_now", "reproduction": {"argv": ["a"], "exit": " 2 "}}
            ],
            "rejected": [
                {"finding_id": "F2", "reason": "r", "reproduction": None},
                {
                    "finding_id": "F3",
                    "reason": "r",
                    "reproduction": {"argv": ["a"], "exit": "0", "observed": "ok"},
                },
                {"finding_id": "F4", "reason": "r"},
            ],
        },
    )
    assert doc["confirmed"][0]["reproduction"] == {"argv": ["a"], "exit": 2, "observed": "(not described)"}
    assert "reproduction" not in doc["rejected"][0]
    assert "reproduction" not in doc["rejected"][2]
    assert doc["rejected"][1]["reproduction"]["exit"] == 0
    assert any("without an observation" in note for note in notes)


def test_an_integer_string_beyond_the_interpreter_digit_limit_is_not_healable_not_a_crash() -> None:
    """Regression: ``int()`` of 5000 digits raised ``ValueError`` out of ``heal``, which is total."""
    digits = "9" * 5000
    row = {"id": "V1", "cmd": "c", "exit": digits}
    found = heal(REPORT, report(checks_run=[row]))
    assert found["kind"] == "not_healable"
    assert "no integer exit" in str(found["reason"])
    assert repair_form(REPORT, report(checks_run=[row]))["kind"] == "not_healable"
    # with a verdict the row stays healable: the verdict replaces the unusable exit, as for any non-integer
    doc, _ = healed(REPORT, report(checks_run=[{**row, "verdict": "fail"}]))
    assert doc["checks_run"] == [{"id": "V1", "cmd": "c", "exit": 1}]
    # triage keeps the string: no integer is invented, the schema rejects it later
    triage, _ = healed(
        TRIAGE,
        {
            "confirmed": [
                {"finding_id": "F1", "decision": "fix_now", "reproduction": {"argv": ["a"], "exit": digits}}
            ],
            "rejected": [],
        },
    )
    assert triage["confirmed"][0]["reproduction"]["exit"] == digits


def test_triage_lists_and_elements() -> None:
    doc, _ = healed(TRIAGE, {"confirmed": {"finding_id": "F1", "decision": "defer"}})
    assert doc["confirmed"] == [{"finding_id": "F1", "decision": "defer"}]
    assert doc["rejected"] == []
    assert heal(TRIAGE, {"confirmed": ["F1"], "rejected": []})["kind"] == "not_healable"
    assert heal(TRIAGE, {"confirmed": 1, "rejected": []})["kind"] == "not_healable"
    # a finding that the triage leaves out is not completed
    doc, _ = healed(TRIAGE, {"confirmed": [], "rejected": []})
    assert doc == {"confirmed": [], "rejected": []}


# ---------------------------------------------------------------- not healable / unknown kinds


@pytest.mark.parametrize("doc", [None, 3, 2.5, True, "text", [], [{"status": "done"}]])
def test_a_document_that_is_not_an_object_is_not_healable(doc: Any) -> None:
    for kind in (REPORT, REVIEW, TRIAGE):
        found = heal(kind, doc)
        assert found == {"kind": "not_healable", "reason": "the result is not an object"}


def test_a_kind_without_a_form_repair_is_not_healable() -> None:
    assert heal("advisor-result", {"a": 1})["kind"] == "not_healable"


def test_deep_nesting_does_not_raise() -> None:
    deep: Any = {"x": 1}
    for _ in range(3000):
        deep = {"x": deep}
    for kind in (REPORT, REVIEW, TRIAGE):
        assert heal(
            kind,
            {
                "status": "done",
                "summary": "s",
                "findings": [],
                "confirmed": [],
                "rejected": [],
                "extra": deep,
            },
        )["kind"] in (
            "healed",
            "not_healable",
        )


# ---------------------------------------------------------------- totality on arbitrary JSON

LEAVES = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=10)
)
JSON = st.recursive(
    LEAVES,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=6), children, max_size=4)
    ),
    max_leaves=30,
)
KEYS = [
    "status",
    "summary",
    "changed_paths",
    "evidence",
    "checks_run",
    "open_issues",
    "questions",
    "verdict",
    "findings",
    "confirmed",
    "rejected",
    "kind",
    "text",
    "id",
    "cmd",
    "exit",
    "severity",
    "reproduction",
]
STRUCTURED = st.dictionaries(st.sampled_from(KEYS), JSON, max_size=8)


@settings(max_examples=300, deadline=None)
@given(st.sampled_from([REPORT, REVIEW, TRIAGE, "other"]), st.one_of(JSON, STRUCTURED))
def test_heal_is_total_on_arbitrary_json(kind: str, doc: Any) -> None:
    snapshot = copy.deepcopy(doc)
    found: Any = heal(kind, doc)
    assert found["kind"] in ("healed", "not_healable")
    if found["kind"] == "healed":
        assert isinstance(found["document"], dict)
        assert all(isinstance(note, str) for note in found["notes"])
        json.dumps(found["document"])  # the mend is JSON again
    else:
        assert isinstance(found["reason"], str)
        assert found["reason"]
    assert doc == snapshot
    repair_form(kind, doc)  # the whole pipeline is total as well


ISSUE_KINDS = ["escalation", "blocker", "pending", "deviation", "note", "assumption"]
HEALTHY_ISSUES = st.lists(
    st.fixed_dictionaries(
        {"kind": st.sampled_from(ISSUE_KINDS), "text": st.text(min_size=1, max_size=8)},
        optional={
            "outcome": st.sampled_from(["accepted", "follow_up", "owner_decision"]),
            "impact": st.text(min_size=1, max_size=5),
            "class": st.sampled_from(["docs", "other", "write_set"]),
        },
    ),
    max_size=5,
)


# One row per id, including the non-V id "x": a repeated checks_run id is not healable,
# so it is outside this drift property. unique_by keeps those ids from repeating.
@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from([*STATUS_RANK, "Done", "BLOCKED"]),
    st.one_of(
        HEALTHY_ISSUES,
        HEALTHY_ISSUES.flatmap(lambda issues: st.sampled_from(issues) if issues else st.just({})),
    ),
    st.lists(
        st.fixed_dictionaries(
            {"id": st.sampled_from(["V1", "V2", "x"]), "cmd": st.just("c"), "exit": st.integers(0, 3)}
        ),
        max_size=3,
        unique_by=lambda row: row["id"],
    ),
)
def test_mended_reports_never_drift_from_their_raw_form(
    status: str, issues: Any, checks: list[dict[str, Any]]
) -> None:
    raw = report(status=status, open_issues=issues, checks_run=checks)
    found = repair_form(REPORT, raw)
    assert found["kind"] == "repaired", found
    assert drift(REPORT, raw, found["result"]) == ()  # type: ignore[arg-type]


# ---------------------------------------------------------------- schema hints and the result-form counter


def test_schema_errors_are_bounded_and_sorted() -> None:
    issues: list[JsonObject] = [
        {"path": f"/findings/{n}/severity", "message": "m" * 500, "expected": "e" * 500}
        for n in range(30, 0, -1)
    ]
    rows = schema_errors(issues)
    assert len(rows) == MAX_SCHEMA_ERRORS
    assert [row["path"] for row in rows] == sorted(row["path"] for row in rows)  # type: ignore[type-var]
    assert all(len(str(row["message"])) <= 300 and len(str(row["expected"])) <= 200 for row in rows)
    hint = schema_error_hint(issues)
    assert hint.startswith("your previous result did not match the schema: ")
    assert hint.endswith("; return the whole result again")
    assert "… and 10 more errors" in hint


def test_schema_errors_accept_the_shapes_validators_give() -> None:
    rows = schema_errors(
        [
            {"instance_path": ["findings", 0, "a/b", "c~d"], "message": "bad"},
            {"message": "root level", "expected": "an object"},
            {"path": "/summary", "message": "too short"},
        ]
    )
    assert rows == [
        {"path": "", "message": "root level", "expected": "an object"},
        {"path": "/findings/0/a~1b/c~0d", "message": "bad", "expected": ""},
        {"path": "/summary", "message": "too short", "expected": ""},
    ]
    assert schema_error_hint([{"path": "/status", "message": "not one of", "expected": "done|blocked"}]) == (
        "your previous result did not match the schema: /status: not one of (expected: done|blocked); "
        "return the whole result again"
    )
    assert "no details" in schema_error_hint([])
    assert "/: root level" in schema_error_hint([{"message": "root level"}])


def test_result_form_retry_has_its_own_counter_and_ref() -> None:
    """An invalid form is repeated on its own counter and points at the schema errors of a step."""
    assert [result_retry_allowed(used, 1) for used in (0, 1, 2)] == [True, False, False]
    # step.max_result_retries = 0: the first invalid result escalates
    assert result_retry_allowed(0, 0) is False
    assert "schema_errors_step_id" in set(FeedbackRefs.__dataclass_fields__)
