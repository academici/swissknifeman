"""Healing of role results: one honest reading of a form mismatch is applied and said; meaning is never invented."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import contract, heal, scope  # noqa: E402


def report(**extra):
    doc = {"status": "done", "summary": "s", "changed_paths": [], "checks_run": [], "evidence": [], "open_issues": []}
    doc.update(extra)
    return doc


class StageReportTests(unittest.TestCase):
    def healed(self, doc):
        fixed, notes = heal.heal("stage-report", doc)
        return fixed, notes, contract.problems(fixed, "stage-report")

    def test_a_status_is_never_raised_and_an_impossible_one_drops(self):
        fixed, notes, problems = self.healed(report(status="done_with_deviations"))
        self.assertEqual((fixed["status"], problems), ("done", []))
        self.assertTrue(notes)
        fixed, _, _ = self.healed(report(status="blocked", open_issues=[{"text": "no key", "kind": "blocker"}]))
        self.assertEqual((fixed["status"], fixed["open_issues"][0]["kind"]), ("blocked", "escalation"))
        fixed, _, problems = self.healed(report(status="Blocked", summary="needs the owner's key"))
        self.assertEqual(fixed["status"], "blocked")
        self.assertIn("needs the owner's key", fixed["open_issues"][-1]["text"])
        self.assertEqual(problems, [])

    def test_forms_of_checks_and_issues_are_mended(self):
        fixed, _, problems = self.healed(report(
            checks_run=[{"id": "V1", "cmd": "x", "exit": "0", "seconds": 3}, {"id": "unit", "cmd": "y", "exit": 0}],
            open_issues=["a plain note", {"text": "t", "kind": "Escalation", "where": "a.py"}], evidence=None))
        self.assertEqual(problems, [])
        self.assertEqual(fixed["checks_run"], [{"id": "V1", "cmd": "x", "exit": 0}])
        kinds = [issue["kind"] for issue in fixed["open_issues"]]
        self.assertEqual(kinds, ["note", "difficulty", "note"])
        self.assertIn("where: a.py", fixed["open_issues"][1]["text"])

    def test_a_deviation_without_class_outcome_or_impact_is_filled_and_said(self):
        fixed, notes, problems = self.healed(report(status="done_with_deviations",
                                                    open_issues=[{"text": "t", "kind": "deviation"}]))
        self.assertEqual(problems, [])
        issue = fixed["open_issues"][0]
        self.assertEqual((issue["class"], issue["outcome"], issue["impact"]),
                         ("other", "accepted", "not stated by the executor"))
        self.assertTrue(any("class" in note and "outcome" in note and "impact" in note for note in notes), notes)

    def test_a_deviation_that_names_its_fields_is_kept_and_words_are_matched(self):
        given = {"text": "t", "kind": "deviation", "impact": "api", "class": "Write-Set", "outcome": "Follow up",
                 "severity": "HIGH", "auto_fixable": "true", "evidence": "a.py:3"}
        fixed, notes, problems = self.healed(report(status="done_with_deviations", open_issues=[given]))
        self.assertEqual(problems, [])
        issue = fixed["open_issues"][0]
        self.assertEqual((issue["class"], issue["outcome"], issue["severity"], issue["impact"]),
                         ("write_set", "follow_up", "high", "api"))
        self.assertEqual((issue["auto_fixable"], issue["evidence"]), (True, ["a.py:3"]))

    def test_an_unknown_class_or_outcome_becomes_the_default_and_the_word_is_not_lost(self):
        given = {"text": "t", "kind": "deviation", "impact": "api", "class": "typo", "outcome": "later"}
        fixed, notes, problems = self.healed(report(status="done_with_deviations", open_issues=[given]))
        self.assertEqual(problems, [])
        issue = fixed["open_issues"][0]
        self.assertEqual((issue["class"], issue["outcome"]), ("other", "accepted"))
        self.assertIn("class: typo", issue["text"])
        self.assertIn("outcome: later", issue["text"])

    def test_deviation_fields_on_another_kind_are_kept_when_valid_and_nothing_is_added(self):
        fixed, _, problems = self.healed(report(open_issues=[{"text": "t", "kind": "note", "severity": "low"}]))
        self.assertEqual(problems, [])
        self.assertEqual(fixed["open_issues"][0], {"text": "t", "kind": "note", "severity": "low"})

    def test_what_has_no_honest_reading_is_left_for_the_repair(self):
        _, _, problems = self.healed(report(checks_run=[{"id": "V1", "cmd": "x", "exit": "zero"}]))
        self.assertTrue(problems)
        self.assertIn("expected integer, got string", problems[0])  # the nearest oneOf branch says what is wrong


class ReviewAndTriageTests(unittest.TestCase):
    def finding(self, **extra):
        doc = {"id": "F1", "severity": "Major", "confidence": "high", "location": "a.py:1", "failure_scenario": "x",
               "basis": "correctness"}
        doc.update(extra)
        return doc

    def test_findings_win_over_the_verdict_and_ids_become_unique(self):
        fixed, notes = heal.heal("review-findings", {"verdict": "green", "findings": [
            self.finding(), self.finding(severity="minor", confidence=None)]})
        self.assertEqual(fixed["verdict"], "ATTENTION")
        self.assertEqual([item["id"] for item in fixed["findings"]], ["F1", "F2"])
        self.assertEqual(fixed["findings"][1]["severity"], "Minor")
        self.assertEqual(contract.problems(fixed, "review-findings"), [])
        fixed, _ = heal.heal("review-findings", {"verdict": "RED", "findings": []})
        self.assertEqual(fixed["verdict"], "GREEN")

    def test_a_major_is_not_rejected_without_a_reproduction(self):
        findings = {"findings": [self.finding()]}
        issues = contract.triage_problems(findings, {"confirmed": [], "rejected": [{"finding": "F1", "reason": "outside"}]})
        self.assertTrue(any("without a reproduction" in issue for issue in issues))
        repro = {"cmd": "python3 -c 1", "exit": 0, "observed": "fine"}
        self.assertEqual(contract.triage_problems(findings, {"confirmed": [], "rejected": [
            {"finding": "F1", "reason": "does not hold", "reproduction": repro}]}), [])


class ScopeTests(unittest.TestCase):
    def test_write_set_patterns(self):
        self.assertTrue(scope.matches("a/b/c.py", "a/**"))
        self.assertTrue(scope.matches("a/b/c.py", "a/*/c.py"))
        self.assertTrue(scope.matches("a/b/c.py", "a/"))
        self.assertFalse(scope.matches("a/b/c.py", "a/*.py"))
        self.assertTrue(scope.matches("docs/x.md", "./docs/*.md"))
        self.assertEqual(scope.outside(["a/x.py", "b/y.py"], ["a/**"]), ["b/y.py"])
        self.assertEqual(scope.outside(["b/y.py"], []), [])
        self.assertEqual(scope.own(["plans/P/a", "x"], ["plans/P"]), ["x"])


if __name__ == "__main__":
    unittest.main()
