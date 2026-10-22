"""Heal and the report-fixer keep the meaning of a role result (I9): the drift between two readings of a result, and the
ladder repair → repeat of the role when the report-fixer's block moves the meaning toward ease (REPAIR_SEMANTIC_DRIFT)."""
from __future__ import annotations

import sys
import types
import unittest

from orch.conductor import engine, heal
from orch.conductor.domain import report as report_rules, semantics
from orch.conductor.stages import finish
from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report

ESCALATION = {"text": "needs the owner's key", "kind": "escalation", "next": "the owner gives it"}
PENDING = {"text": "V1 needs docker", "kind": "pending"}
DEVIATION = {"text": "d", "kind": "deviation", "class": "other", "impact": "x", "outcome": "follow_up"}


def stage(status="done", **extra) -> dict:
    doc = {"status": status, "summary": "s", "changed_paths": [], "checks_run": [], "evidence": [], "open_issues": []}
    doc.update(extra)
    return doc


def finding(number=1, severity="Major", location="a.py:1", **extra) -> dict:
    doc = {"id": f"F{number}", "severity": severity, "confidence": "high", "location": location,
           "failure_scenario": "x", "basis": "correctness"}
    doc.update(extra)
    return doc


def review(verdict="ATTENTION", *findings) -> dict:
    return {"verdict": verdict, "findings": list(findings)}


def check_row(number=1, exit=0) -> dict:
    return {"id": f"V{number}", "cmd": "x", "exit": exit}


class StageReportDriftTests(unittest.TestCase):
    def drift(self, before, after):
        return semantics.drift("stage-report", before, after)

    def test_a_cautious_or_equal_report_is_no_drift(self):
        blocked = stage("blocked", open_issues=[ESCALATION])
        self.assertEqual(self.drift(stage(), blocked), [])
        self.assertEqual(self.drift(blocked, blocked), [])
        self.assertEqual(self.drift(stage("done_pending_checks", open_issues=[PENDING]),
                                    stage("blocked", open_issues=[PENDING, ESCALATION])), [])
        self.assertEqual(self.drift(stage(), stage(checks_run=[check_row()], open_issues=[PENDING])), [])

    def test_a_raised_status_is_drift_for_every_step_up(self):
        order = ("blocked", "done_pending_checks", "done_with_deviations", "done")
        for worse, better in zip(order, order[1:]):
            with self.subTest(before=worse, after=better):
                self.assertEqual(self.drift(stage(worse), stage(better)), [f"/status: {worse} -> {better}"])

    def test_a_lost_escalation_blocker_pending_or_deviation_is_drift(self):
        for kind, issue in (("escalation", ESCALATION), ("blocker", {"text": "b", "kind": "blocker"}),
                            ("pending", PENDING), ("deviation", DEVIATION)):
            with self.subTest(kind=kind):
                self.assertEqual(self.drift(stage("blocked", open_issues=[issue, issue]),
                                            stage("blocked", open_issues=[issue])),
                                 [f"/open_issues: {kind} 2 -> 1"])

    def test_a_deviation_set_to_accepted_is_drift_but_one_the_role_accepted_is_not(self):
        accepted = dict(DEVIATION, outcome="accepted")
        self.assertEqual(self.drift(stage("done_with_deviations", open_issues=[DEVIATION]),
                                    stage("done_with_deviations", open_issues=[accepted])),
                         ["/open_issues: deviations accepted 0 -> 1"])
        self.assertEqual(self.drift(stage("done_with_deviations", open_issues=[accepted]),
                                    stage("done_with_deviations", open_issues=[accepted])), [])

    def test_acceptance_moved_to_another_deviation_is_drift_though_the_count_holds(self):
        a, b = dict(DEVIATION, text="deviation A"), dict(DEVIATION, text="deviation B")
        accepted = lambda issue: dict(issue, outcome="accepted")
        before = stage("done_with_deviations", open_issues=[a, accepted(b)])
        swapped = stage("done_with_deviations", open_issues=[accepted(a), b])
        self.assertEqual(self.drift(before, swapped), ["/open_issues: deviation accepted: deviation a"])
        self.assertEqual(self.drift(before, stage("done_with_deviations", open_issues=[b, accepted(a)])),
                         ["/open_issues: deviation accepted: deviation a"])  # the order of the issues is no identity
        self.assertEqual(self.drift(before, stage("done_with_deviations", open_issues=[accepted(b), a])), [])
        self.assertEqual(self.drift(before, stage("done_with_deviations", open_issues=[a, b])), [])  # more cautious
        reworded = stage("done_with_deviations", open_issues=[a, accepted(dict(b, text="another words"))])
        self.assertEqual(self.drift(before, reworded), ["/open_issues: deviation accepted: another words"])
        quiet = stage("done_with_deviations", open_issues=[dict(a, text="  Deviation   A "), accepted(b)])
        self.assertEqual(self.drift(before, quiet), [])  # blanks and case are not identity

    def test_deviations_of_one_text_are_told_apart_by_impact_and_class(self):
        accepted = lambda issue: dict(issue, outcome="accepted")
        for text in ("same words", "   "):
            with self.subTest(text=text):
                a, b = dict(DEVIATION, text=text, impact="impact A"), dict(DEVIATION, text=text, impact="impact B")
                before = stage("done_with_deviations", open_issues=[a, accepted(b)])
                self.assertEqual(len(self.drift(before, stage("done_with_deviations", open_issues=[accepted(a), b]))), 1)
                self.assertEqual(len(self.drift(before, stage("done_with_deviations", open_issues=[b, accepted(a)]))), 1)
                self.assertEqual(self.drift(before, stage("done_with_deviations", open_issues=[accepted(b), a])), [])
                self.assertEqual(self.drift(before, stage("done_with_deviations", open_issues=[a, b])), [])
        c, d = dict(DEVIATION, text="t", **{"class": "docs"}), dict(DEVIATION, text="t", **{"class": "build"})
        before = stage("done_with_deviations", open_issues=[c, accepted(d)])
        self.assertEqual(len(self.drift(before, stage("done_with_deviations", open_issues=[accepted(c), d]))), 1)

    def test_deviations_without_any_content_are_not_a_shared_identity(self):
        accepted = lambda issue: dict(issue, outcome="accepted")
        bare = {"text": " ", "kind": "deviation"}
        before = stage("done_with_deviations", open_issues=[bare, accepted(bare)])
        self.assertEqual(len(self.drift(before, stage("done_with_deviations", open_issues=[accepted(bare), bare]))), 1)
        self.assertEqual(self.drift(before, before), [])
        single = stage("done_with_deviations", open_issues=[accepted(bare)])
        self.assertEqual(self.drift(single, single), [])

    def test_a_lost_question_or_a_blocking_one_made_soft_is_drift(self):
        ask = {"id": "Q1", "revision": 1, "kind": "decision", "text": "t", "blocking": True}
        before = stage("blocked", open_issues=[ESCALATION], questions=[ask])
        self.assertEqual(self.drift(before, stage("blocked", open_issues=[ESCALATION])), ["/questions: Q1 lost"])
        soft = dict(ask, blocking=False, assumed="x")
        self.assertEqual(self.drift(before, stage("blocked", open_issues=[ESCALATION], questions=[soft])),
                         ["/questions: Q1 blocking true -> false"])
        self.assertEqual(self.drift(before, stage("blocked", open_issues=[ESCALATION], questions=[ask, dict(ask, id="Q2")])), [])

    def test_a_lost_or_changed_check_row_is_drift(self):
        before = stage(checks_run=[check_row(1, 1), check_row(2, 0)])
        self.assertEqual(self.drift(before, stage(checks_run=[check_row(1, 1)])), ["/checks_run: V2 lost"])
        self.assertEqual(self.drift(before, stage(checks_run=[check_row(1, 0), check_row(2, 0)])),
                         ["/checks_run: V1 result 1 -> 0"])
        manual = {"id": "V2", "procedure": "p", "verdict": "pass"}  # a verdict is the exit it stands for
        self.assertEqual(self.drift(before, stage(checks_run=[check_row(1, 1), manual])), [])
        self.assertEqual(self.drift(stage(checks_run=[check_row(1, "zero")]), stage(checks_run=[check_row(1, 0)])),
                         ["/checks_run: V1 result zero -> 0"])

    def test_an_unknown_status_has_nothing_to_compare(self):
        self.assertEqual(self.drift(stage("finished"), stage("done")), [])

    def test_a_mend_is_not_drift_for_every_rule_of_the_stage_report(self):  # scenarios a-d
        cases = [
            stage("done_with_deviations"),
            stage("done_pending_checks"),
            stage("done", open_issues=[ESCALATION]),
            stage("done_with_deviations", open_issues=[{"text": "t", "kind": "deviation"}]),
            stage("Blocked", open_issues=[{"text": "no key", "kind": "blocker"}]),
            stage("blocked", checks_run=[{"id": "V1", "cmd": "x", "verdict": "pass"}, {"id": "unit", "cmd": "y", "exit": 0}]),
            stage(open_issues=["a plain note"], checks_run=[{"id": "V1", "cmd": "x", "exit": "0"}]),
        ]
        for raw in cases:
            with self.subTest(status=raw["status"]):
                fixed, _ = heal.heal("stage-report", raw)
                self.assertEqual(self.drift(raw, fixed), [])
                self.assertEqual(report_rules.report_problems(fixed), [])

    def test_a_done_pending_checks_without_a_pending_issue_is_settled_by_the_checks(self):  # scenario b
        fixed, _ = heal.heal("stage-report", stage("done_pending_checks"))
        self.assertEqual(fixed["status"], "done_pending_checks")
        host = types.SimpleNamespace(_blocked=report_rules.blocked)
        settled = finish.settle_pending(host, fixed, [{"id": "V1", "exit": 0}])
        self.assertEqual(settled["status"], "done")
        self.assertNotIn("pending", [issue["kind"] for issue in settled["open_issues"]])
        for rows in ([], [{"id": "V1", "skipped": True}], None):
            with self.subTest(rows=rows):
                blocked = finish.settle_pending(host, fixed, rows)
                self.assertEqual(blocked["status"], "blocked")
                self.assertIn("CHECKS_NOT_RUN", blocked["open_issues"][-1]["text"])

    def test_an_escalation_in_a_done_report_blocks_it_and_stays_an_escalation(self):  # scenario c
        fixed, _ = heal.heal("stage-report", stage("done", open_issues=[ESCALATION]))
        self.assertEqual((fixed["status"], [issue["kind"] for issue in fixed["open_issues"]]), ("blocked", ["escalation"]))

    def test_a_deviation_without_an_outcome_is_a_follow_up_not_accepted(self):  # scenario d
        fixed, _ = heal.heal("stage-report", stage("done_with_deviations", open_issues=[{"text": "t", "kind": "deviation"}]))
        self.assertEqual(fixed["open_issues"][0]["outcome"], "follow_up")


class ReviewDriftTests(unittest.TestCase):
    def drift(self, before, after):
        return semantics.drift("review-findings", before, after)

    def test_a_lighter_verdict_is_drift_and_a_heavier_one_is_not(self):
        one = finding()
        self.assertEqual(self.drift(review("RED", one), review("ATTENTION", one)), ["/verdict: RED -> ATTENTION"])
        self.assertEqual(self.drift(review("ATTENTION", one), review("GREEN", one)), ["/verdict: ATTENTION -> GREEN"])
        self.assertEqual(self.drift(review("RED"), review("GREEN")), ["/verdict: RED -> GREEN"])
        self.assertEqual(self.drift(review("GREEN"), review("RED", one)), [])

    def test_a_lowered_severity_or_a_lost_finding_is_drift(self):  # scenario g, h
        before = review("RED", finding(1, "Blocker", "a.py:1"), finding(2, "Minor", "b.py:2"))
        self.assertEqual(self.drift(before, review("RED", finding(1, "Minor", "a.py:1"), finding(2, "Minor", "b.py:2"))),
                         ["severity lowered at a.py:1: Blocker -> Minor"])
        self.assertEqual(self.drift(before, review("RED", finding(1, "Blocker", "a.py:1"))), ["finding lost at b.py:2"])
        self.assertEqual(self.drift(before, review("RED", finding(1, "Blocker", "a.py:1"), finding(2, "Major", "b.py:2"))), [])
        self.assertEqual(self.drift(before, review("RED", finding(1, "Blocker", "a.py:1"), finding(2, "Minor", "b.py:2"),
                                                   finding(3, "Nit", "c.py:3"))), [])

    def test_findings_of_one_place_are_not_merged_when_one_is_lost(self):  # scenario s1
        before = review("ATTENTION", finding(1, "Major", "a.py:1"), finding(2, "Minor", "a.py:1"))
        self.assertEqual(self.drift(before, review("ATTENTION", finding(1, "Major", "a.py:1"))), ["finding lost at a.py:1"])

    def test_findings_of_one_place_are_not_merged_when_one_is_lowered(self):  # scenario s2
        before = review("ATTENTION", finding(1, "Major", "a.py:1"), finding(2, "Minor", "a.py:1"))
        after = review("ATTENTION", finding(1, "Minor", "a.py:1"), finding(2, "Minor", "a.py:1"))
        self.assertEqual(self.drift(before, after), ["severity lowered at a.py:1: Major -> Minor"])
        after = review("ATTENTION", finding(1, "Major", "a.py:1"), finding(2, "Nit", "a.py:1"))
        self.assertEqual(self.drift(before, after), ["severity lowered at a.py:1: Minor -> Nit"])

    def test_a_swap_of_severities_between_findings_of_one_place_is_drift(self):
        before = review("RED", finding(1, "Blocker", "a.py:1", failure_scenario="A breaks"),
                        finding(2, "Minor", "a.py:1", failure_scenario="B breaks"))
        swapped = review("RED", finding(1, "Minor", "a.py:1", failure_scenario="A breaks"),
                         finding(2, "Blocker", "a.py:1", failure_scenario="B breaks"))
        self.assertEqual(self.drift(before, swapped), ["severity lowered at a.py:1: Blocker -> Minor"])
        reordered = review("RED", finding(2, "Minor", "./a.py:1", failure_scenario=" b  BREAKS"),
                           finding(1, "Blocker", "a.py:1", failure_scenario="A breaks"))
        self.assertEqual(self.drift(before, reordered), [])  # order, ids and blanks are not identity
        renumbered = review("RED", finding(8, "Blocker", "a.py:1", failure_scenario="A breaks"),
                            finding(9, "Major", "a.py:1", failure_scenario="B breaks"))
        self.assertEqual(self.drift(before, renumbered), [])  # a raised severity is cautious
        lost = review("RED", finding(1, "Blocker", "a.py:1", failure_scenario="A breaks"),
                      finding(2, "Blocker", "a.py:1", failure_scenario="C breaks"))
        self.assertEqual(self.drift(before, lost), ["finding lost at a.py:1"])

    def test_a_renumbered_finding_id_is_not_drift(self):  # scenario s3
        raw = review("ATTENTION", finding(1, "Major", "a.py:1"), finding(1, "Minor", "b.py:2"))
        fixed, notes = heal.heal("review-findings", raw)
        self.assertEqual([item["id"] for item in fixed["findings"]], ["F1", "F2"])
        self.assertTrue(notes)
        self.assertEqual(self.drift(raw, fixed), [])
        self.assertEqual(self.drift(fixed, review("ATTENTION", finding(7, "Major", "a.py:1"), finding(9, "Minor", "b.py:2"))), [])

    def test_a_place_is_normalized(self):  # scenario s4
        self.assertEqual(semantics.place(" ./a/b.py "), "a/b.py")
        self.assertEqual(semantics.place("a\\b.py"), "a/b.py")
        self.assertEqual(semantics.place(""), "-")
        self.assertEqual(semantics.place(None), "-")
        before = review("ATTENTION", finding(1, "Major", "./a/b.py"))
        self.assertEqual(self.drift(before, review("ATTENTION", finding(1, "Major", "a/b.py"))), [])
        self.assertEqual(self.drift(before, review("ATTENTION", finding(1, "Major", "a\\b.py"))), [])
        self.assertEqual(self.drift(before, review("ATTENTION", finding(1, "Major", "a/b.py:3"))), ["finding lost at a/b.py"])

    def test_a_verdict_without_findings_is_not_healed_so_the_repair_sees_it(self):  # scenario e (the mend)
        for verdict in ("RED", "ATTENTION"):
            raw = review(verdict)
            fixed, _ = heal.heal("review-findings", raw)
            self.assertEqual(fixed["verdict"], verdict)
            self.assertEqual(report_rules.findings_problems(fixed), [f"/verdict: {verdict} without findings"])
            self.assertEqual(self.drift(fixed, review("GREEN")), [f"/verdict: {verdict} -> GREEN"])

    def test_green_with_a_major_becomes_attention_as_before(self):  # scenario k
        raw = review("GREEN", finding(1, "Major"))
        fixed, _ = heal.heal("review-findings", raw)
        self.assertEqual(fixed["verdict"], "ATTENTION")
        self.assertEqual(self.drift(raw, fixed), [])
        fixed, _ = heal.heal("review-findings", review("GREEN", finding(1, "Blocker")))
        self.assertEqual(fixed["verdict"], "RED")


class TriageDriftTests(unittest.TestCase):
    CONFIRMED = {"finding": "F1", "reproduction": {"cmd": "c", "exit": 1, "observed": "o"}, "fix": "f"}
    REJECTED = {"finding": "F1", "reason": "r"}

    def drift(self, before, after):
        return semantics.drift("triage-result", before, after)

    def test_a_confirmed_finding_turned_rejected_or_lost_is_drift(self):  # scenario i
        before = {"confirmed": [self.CONFIRMED], "rejected": [{"finding": "F2", "reason": "r"}]}
        self.assertEqual(self.drift(before, {"confirmed": [], "rejected": [self.REJECTED, {"finding": "F2", "reason": "r"}]}),
                         ["finding F1 confirmed -> rejected"])
        self.assertEqual(self.drift(before, {"confirmed": [], "rejected": [{"finding": "F2", "reason": "r"}]}),
                         ["finding F1 confirmed -> lost"])

    def test_the_other_ways_are_not_drift(self):
        before = {"confirmed": [self.CONFIRMED], "rejected": [{"finding": "F2", "reason": "r"}]}
        self.assertEqual(self.drift(before, before), [])
        self.assertEqual(self.drift({"confirmed": [], "rejected": [self.REJECTED]},
                                    {"confirmed": [self.CONFIRMED], "rejected": []}), [])

    def test_other_kinds_have_no_outcome(self):
        self.assertEqual(semantics.outcome_key("advice", {"x": 1}), {})
        self.assertEqual(semantics.drift("advice", {"x": 1}, {"x": 2}), [])
        self.assertEqual(semantics.drift("stage-report", None, stage()), [])


class RepairLadderTests(ConductorCase):
    """The report-fixer is a fake role: a block that moves the meaning toward ease is refused, then the role repeats."""

    def setUp(self):
        super().setUp()
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                           for role in ROLES + ("report-fixer",)})

    def info(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line["event"] == "info" and line.get("reason_code") == code]

    def test_a_fixer_that_lightens_a_red_review_without_findings_is_refused_and_the_reviewer_repeats(self):  # scenario e
        red = {"result": {"verdict": "RED", "findings": []}}
        self.script({"executor": [executor_ok("W1")], "reviewer": [red, GREEN],
                     "report-fixer": [{"result": {"verdict": "GREEN", "findings": []}, "tag": "review-findings"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("reviewer"), self.calls("report-fixer")), (2, 1))
        drift = self.info(err, "REPAIR_SEMANTIC_DRIFT")
        self.assertEqual(len(drift), 1, err)
        self.assertEqual(drift[0]["role"], "report-fixer")
        self.assertEqual(drift[0]["message"], "kept the role's answer: /verdict: RED -> GREEN")
        self.assertEqual(self.info(err, "RESULT_REPAIRED"), [])
        self.assertIn("REPAIR_SEMANTIC_DRIFT", self.prompt("reviewer", 2))  # the repeat says why the answer was refused
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["review.1"]["result"]["findings"]["verdict"], "GREEN")

    def test_a_fixer_that_raises_blocked_to_done_is_refused_until_the_role_stops(self):  # scenario f
        broken = report("W1", "blocked", changed_paths=["a", "a"], open_issues=[ESCALATION])
        raised = {"result": report("W1", "done"), "tag": "stage-report"}
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"retries": 1, "repairs": 1}}}]}})
        self.script({"executor": [{"result": broken}], "reviewer": [GREEN], "report-fixer": [raised]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.outcome(err), ("stopped", "ROLE_OUTPUT_INVALID"), err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (2, 2))  # limits.retries 1, limits.repairs 1
        drift = self.info(err, "REPAIR_SEMANTIC_DRIFT")
        self.assertEqual([line["message"] for line in drift],
                         ["kept the role's answer: /status: blocked -> done; /open_issues: escalation 1 -> 0"] * 2)
        self.assertEqual(self.calls("reviewer"), 0)

    def test_a_fixer_that_keeps_the_meaning_is_accepted(self):
        broken = report("W1", "blocked", changed_paths=["a", "a"], open_issues=[ESCALATION])
        mended = report("W1", "blocked", changed_paths=["a"], open_issues=[ESCALATION])
        self.script({"executor": [{"result": broken}], "reviewer": [GREEN],
                     "report-fixer": [{"result": mended, "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(self.info(err, "REPAIR_SEMANTIC_DRIFT"), [], err)
        self.assertEqual(len(self.info(err, "RESULT_REPAIRED")), 1, err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 1))

    def test_a_second_repair_may_succeed_after_a_drift(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"repairs": 2}}}]}})
        broken = report("W1", "blocked", changed_paths=["a", "a"], open_issues=[ESCALATION])
        raised = {"result": report("W1", "done"), "tag": "stage-report"}
        mended = {"result": report("W1", "blocked", changed_paths=["a"], open_issues=[ESCALATION]), "tag": "stage-report"}
        self.script({"executor": [{"result": broken}], "reviewer": [GREEN], "report-fixer": [raised, mended]})
        _, _, err = self.run_items("W1")
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 2))
        self.assertEqual(len(self.info(err, "REPAIR_SEMANTIC_DRIFT")), 1, err)
        self.assertEqual(len(self.info(err, "RESULT_REPAIRED")), 1, err)

    def test_an_answer_without_a_block_is_repaired_from_its_text_and_said(self):  # scenario j
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n"}, "text": "the work is done, no block"}],
                     "reviewer": [GREEN], "report-fixer": [{"result": report("W1"), "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 1))
        self.assertEqual(self.info(err, "REPAIR_SEMANTIC_DRIFT"), [])
        result = self.state(err)["items"]["W1"]["steps"]["executor.1"]["result"]
        self.assertIs(result["repaired_from_text"], True)
        self.assertTrue(any("no block to compare" in note for note in result["healed"]), result["healed"])

    def test_a_repair_with_a_block_to_compare_does_not_claim_repaired_from_text(self):
        broken = report("W1", changed_paths=["out/W1.txt", "out/W1.txt"])
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n"}, "result": broken}], "reviewer": [GREEN],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("repaired_from_text", self.state(err)["items"]["W1"]["steps"]["executor.1"]["result"])


if __name__ == "__main__":
    unittest.main()
