"""Automatic fix of a deviation inside the piece (P6.6): an ``auto_fixable`` deviation whose evidence lies in the write
set, in a piece with acceptance checks, costs one correction round (``# Fix this deviation``) and then the same checks."""
from __future__ import annotations

import json
import unittest

from orch.conductor import engine
from tests.test_conductor import GREEN, ConductorCase, check, executor_ok, report


def deviation(**extra) -> dict:
    return dict({"text": "kept the old name in out/W1.txt", "kind": "deviation", "class": "other",
                 "impact": "the file keeps its name", "outcome": "follow_up", "auto_fixable": True,
                 "evidence": ["out/W1.txt:1"]}, **extra)


def with_deviation(**extra) -> dict:
    answer = executor_ok("W1")
    answer["result"] = dict(report("W1", "done_with_deviations"), open_issues=[deviation(**extra)])
    return answer


def fixed() -> dict:
    return {"write": {"out/W1.txt": "fixed\n"}, "result": report("W1")}


class AutofixTests(ConductorCase):
    def issues(self) -> list:
        return self.source()["items"]["W1"]["report"]["open_issues"]

    def test_an_auto_fixable_deviation_in_the_write_set_gets_a_correction_and_is_accepted(self):
        self.script({"executor": [with_deviation(), fixed()], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        prompt = self.prompt("executor", 2)
        self.assertIn("\n# Fix this deviation\n", prompt)
        self.assertIn("kept the old name in out/W1.txt", prompt)
        self.assertIn("out/W1.txt:1", prompt)
        self.assertNotIn("\n# Fix this deviation\n", self.prompt("executor", 1))
        deviations = [issue for issue in self.issues() if issue["kind"] == "deviation"]
        self.assertEqual([(issue["text"], issue["outcome"]) for issue in deviations],
                         [("kept the old name in out/W1.txt", "accepted")])
        self.assertIn("deviation fixed in correction 1: kept the old name in out/W1.txt",
                      [issue["text"] for issue in self.issues() if issue["kind"] == "note"])
        self.assertEqual(self.source()["items"]["W1"]["status"], "done_with_deviations")
        stages = [line["stage"] for line in self.lines(err) if line["event"] == "stage.start"]
        self.assertEqual([stage for stage in stages if stage.startswith(("executor", "checks"))],
                         ["executor.1", "executor.2", "checks.2"])  # the checks run on the fixed candidate
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "DEVIATION_AUTOFIX"])

    def test_evidence_outside_the_write_set_gets_no_correction(self):
        self.script({"executor": [with_deviation(evidence=["README.md:3"])], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 1), err)
        self.assertEqual([issue["outcome"] for issue in self.issues() if issue["kind"] == "deviation"], ["follow_up"])

    def test_a_deviation_without_a_path_in_its_evidence_gets_no_correction(self):
        self.script({"executor": [with_deviation(evidence=["V1"])], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 1), err)

    def test_spec_mismatch_and_owner_decision_and_not_auto_fixable_are_left(self):
        for extra in ({"class": "spec_mismatch"}, {"outcome": "owner_decision"}, {"auto_fixable": False}):
            with self.subTest(extra=extra):
                self.setUp()
                self.script({"executor": [with_deviation(**extra)], "reviewer": [GREEN]})
                code, _, err = self.run_items("W1")
                self.assertEqual((code, self.calls("executor")), (0, 1), err)

    def test_a_spent_correction_budget_leaves_the_deviation_with_a_beacon(self):
        options = [{"source": "item:W1", "options": {"limits": {"corrections": 0, "ceiling_factor": 1}}}]
        self.set_items({"W1": {"options": options}})
        self.script({"executor": [with_deviation()], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 1), err)
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "DEVIATION_AUTOFIX_SKIPPED"])
        self.assertEqual([issue["outcome"] for issue in self.issues() if issue["kind"] == "deviation"], ["follow_up"])

    def test_the_fix_leaves_the_review_its_own_correction(self):  # review F3: default corrections target is 1
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        finding = {"result": {"verdict": "ATTENTION", "findings": [
            {"id": "F1", "severity": "Major", "confidence": "high", "location": "out/W1.txt:1",
             "failure_scenario": "wrong", "basis": "input contract"}]}}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "x"}], "rejected": []}}
        self.script({"executor": [with_deviation(), fixed(), executor_ok("W1")], "reviewer": [finding, GREEN],
                     "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 3), err)
        state = self.state(err)["items"]["W1"]
        self.assertEqual((state["autofix_at"], state["corrections_at"], state["corrections_used"]), ([1], [1], 1))

    def test_a_fix_that_stays_red_blocks_and_keeps_the_deviation_as_it_was(self):
        self.script({"executor": [with_deviation(), {"write": {"out/W1.txt": "x\n"}, "result": report("W1")}],
                     "reviewer": [GREEN]})
        self.set_items({"W1": {"checks": [check("W1"), {"id": "V2", "cmd": "test -f out/never.txt",
                                                        "expect": "exit 0", "kind": "acceptance"}]}})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "blocked")
        texts = [issue["text"] for issue in item["report"]["open_issues"]]
        self.assertTrue([text for text in texts if "kept the old name" in text], texts)
        self.assertFalse([text for text in texts if "fixed in correction" in text], texts)

    def test_a_resume_after_the_fix_does_not_fix_again(self):
        self.script({"executor": [with_deviation(), fixed()], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.state(err)["items"]["W1"]["autofix_at"], [1])


class PureTests(unittest.TestCase):
    def test_the_criteria_are_in_the_role_text_and_the_contract(self):
        from orch import render
        _, text = render.load_role("executor")
        self.assertIn("auto_fixable", text)
        self.assertIn("write set", text)

    def test_a_piece_without_acceptance_checks_or_a_write_set_has_nothing_to_fix(self):
        from pathlib import Path
        issue = deviation()
        done = dict(report("W1", "done_with_deviations"), open_issues=[issue])

        def found(input_doc):
            item = engine.Item(ref="W1", orch_run="r", state={}, directory=Path(), claim={}, input_doc=input_doc)
            return engine.Conductor._autofixable(None, item, done)
        acceptance = {"checks": [{"id": "V1", "kind": "acceptance", "cmd": "true"}]}
        scope = {"write_set": ["out/"]}
        self.assertEqual(found({"scope": scope, "acceptance": acceptance}), [issue])
        self.assertEqual(found({"scope": scope, "acceptance": {"checks": [{"id": "V2", "kind": "impact"}]}}), [])
        self.assertEqual(found({"scope": {"write_set": []}, "acceptance": acceptance}), [])
        self.assertEqual(found({"scope": {"write_set": ["docs/"]}, "acceptance": acceptance}), [])

    def test_evidence_paths(self):
        self.assertEqual(engine.evidence_paths(["out/a.py:12", "V1", "docs/x.md", "out/b.py:3-9"]),
                         ["out/a.py", "docs/x.md", "out/b.py"])


if __name__ == "__main__":
    unittest.main()
