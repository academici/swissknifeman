"""The review of round N>1 with ``review.audit_scope: corrected`` reads the diff of the paths changed after review N-1 (and of
the files of the findings still to be fixed); round 1, ``audit_scope: full`` and a run without review marks read the whole
diff."""
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest import mock

from orch.conductor import checks, engine
from tests.test_conductor import GREEN, ConductorCase, report

WRITE_SET = ["out/W1.txt", "out/stable.txt", "out/other.txt"]


def finding(location: str, severity: str = "Major", number: str = "F1") -> dict:
    return {"result": {"verdict": "ATTENTION", "findings": [
        {"id": number, "severity": severity, "confidence": "high", "location": location,
         "failure_scenario": f"{location} is wrong", "basis": "input contract"}]}}


def confirmed(fix: str, number: str = "F1") -> dict:
    return {"result": {"confirmed": [{"finding": number, "reproduction": {"cmd": "true", "exit": 0, "observed": "x"},
                                      "fix": fix}], "rejected": []}}


def writes(*names: str, text: str = "ok\n") -> dict:
    return {"write": {f"out/{name}.txt": text for name in names}, "result": report("W1")}


class ReviewDeltaTests(ConductorCase):
    def setUp(self):
        super().setUp()
        self.options({})

    def options(self, review: dict, **limits) -> None:
        layer = {"review": review, "limits": {"review_rounds": 3, "corrections": 2, **limits}}
        self.set_items({"W1": {"write_set": WRITE_SET, "options": [{"source": "item:W1", "options": layer}]}})

    def diff_names(self, text: str) -> set:
        """The untracked files the diff block of a reviewer prompt names."""
        return {json.loads(line[4:]) for line in text.splitlines() if line.startswith('+++ "')}

    def test_round_two_reads_only_the_paths_changed_after_round_one(self):
        self.script({"executor": [writes("W1", "stable", "other"), writes("W1", text="done\n")],
                     "reviewer": [finding("out/W1.txt:1"), GREEN], "triager": [confirmed("write done")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        first, second = self.prompt("reviewer", 1), self.prompt("reviewer", 2)
        self.assertIn("Diff against the base:\n", first)
        self.assertEqual(self.diff_names(first) & {"out/W1.txt", "out/stable.txt", "out/other.txt"},
                         {"out/W1.txt", "out/stable.txt", "out/other.txt"})  # round 1: the whole diff
        self.assertIn("Diff against the base of the paths changed since review 1 (the full diff was reviewed in round 1; "
                      "read other files as needed):", second)
        self.assertEqual(self.diff_names(second) & {"out/W1.txt", "out/stable.txt", "out/other.txt"}, {"out/W1.txt"})
        marks = self.state(err)["items"]["W1"]["review_marks"]
        self.assertEqual(sorted(marks), ["1", "2"])
        self.assertIn("out/stable.txt", marks["1"])

    def test_a_finding_that_the_correction_did_not_touch_stays_in_the_diff_of_the_next_round(self):
        self.script({"executor": [writes("W1", "stable", "other"), writes("other", text="v2\n")],
                     "reviewer": [finding("out/stable.txt:1"), GREEN], "triager": [confirmed("fix stable")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        names = self.diff_names(self.prompt("reviewer", 2))
        self.assertIn("out/stable.txt", names)  # the correction did not change it, and nobody said it was fixed
        self.assertIn("out/other.txt", names)
        self.assertNotIn("out/W1.txt", names)

    def test_an_earlier_confirmed_finding_stays_an_obligation_of_every_later_round_whatever_its_severity(self):
        self.script({"executor": [writes("W1", "stable", "other"), writes("other", text="v2\n"),
                                  writes("other", text="v3\n")],
                     "reviewer": [finding("out/stable.txt:1", "Minor"), finding("out/other.txt:1"), GREEN],
                     "triager": [confirmed("fix the minor"), confirmed("fix other")]})
        self.options({"correct_min_severity": "Minor"})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 3, err)
        third = self.prompt("reviewer", 3)
        self.assertIn("paths changed since review 2", third)
        self.assertEqual(self.diff_names(third) & {"out/W1.txt", "out/stable.txt", "out/other.txt"},
                         {"out/stable.txt", "out/other.txt"})  # round 2 did not report the Minor: that is no proof it was fixed
        scope = third.split("## Scope of this round", 1)[1]
        self.assertIn("F1 (review 1) (Minor, out/stable.txt:1)", scope)
        self.assertIn("correction asked: fix the minor", scope)
        self.assertIn("F1 (Major, out/other.txt:1)", scope)
        second_scope = self.prompt("reviewer", 2).split("## Scope of this round", 1)[1]
        self.assertIn("F1 (Minor, out/stable.txt:1)", second_scope)  # round 2 names it as before
        self.assertNotIn("(review 1)", second_scope)

    def test_audit_scope_full_keeps_the_whole_diff_in_every_round(self):
        self.options({"audit_scope": "full"})
        self.script({"executor": [writes("W1", "stable", "other"), writes("W1", text="done\n")],
                     "reviewer": [finding("out/W1.txt:1"), GREEN], "triager": [confirmed("write done")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        second = self.prompt("reviewer", 2)
        self.assertIn("Diff against the base:\n", second)
        self.assertNotIn("paths changed since review", second)
        self.assertEqual(self.diff_names(second) & {"out/W1.txt", "out/stable.txt", "out/other.txt"},
                         {"out/W1.txt", "out/stable.txt", "out/other.txt"})
        self.assertNotIn("Scope of this round", second)

    def test_a_run_without_review_marks_reads_the_whole_diff(self):
        self.script({"executor": [writes("W1", "stable", "other"), writes("W1", text="done\n")],
                     "reviewer": [finding("out/W1.txt:1"), GREEN], "triager": [confirmed("write done")]})
        original = engine.Conductor._upgrade_reviewer

        def forget_marks(conductor, item):  # the state of a run made before the marks existed
            item.state.pop("review_marks", None)
            return original(conductor, item)

        with mock.patch.object(engine.Conductor, "_upgrade_reviewer", forget_marks):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        second = self.prompt("reviewer", 2)
        self.assertIn("Diff against the base:\n", second)
        self.assertNotIn("paths changed since review", second)
        self.assertEqual(self.diff_names(second) & {"out/W1.txt", "out/stable.txt", "out/other.txt"},
                         {"out/W1.txt", "out/stable.txt", "out/other.txt"})

    def test_a_correction_that_changed_nothing_says_so(self):
        self.script({"executor": [writes("W1"), {"result": report("W1")}],
                     "reviewer": [finding("README.md:1"), GREEN], "triager": [confirmed("nothing")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        second = self.prompt("reviewer", 2)
        self.assertIn("paths changed since review 1", second)
        self.assertNotIn("out/W1.txt", second.split("paths changed since review 1", 1)[1].split("## Result", 1)[0])


class DiffByPathsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "Test"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
            self.git("config", key, value)
        (self.project / "a.txt").write_text("a\n", encoding="utf-8")
        (self.project / "b.txt").write_text("b\n", encoding="utf-8")
        (self.project / "dir").mkdir()
        (self.project / "dir" / "c.txt").write_text("c\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = checks.head(self.project)
        for name in ("a.txt", "b.txt", "dir/c.txt"):
            (self.project / name).write_text("changed\n", encoding="utf-8")
        (self.project / "new.txt").write_text("new\n", encoding="utf-8")
        (self.project / "dir" / "new2.txt").write_text("new\n", encoding="utf-8")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.project, check=True, capture_output=True)

    def test_without_paths_the_diff_is_whole(self):
        text = checks.diff(self.project, self.base)
        for name in ("a.txt", "b.txt", "dir/c.txt", "new.txt", "dir/new2.txt"):
            self.assertIn(name, text)

    def test_paths_limit_the_tracked_diff_and_the_untracked_names(self):
        text = checks.diff(self.project, self.base, paths=["a.txt", "dir", "new.txt"])
        self.assertIn("diff --git a/a.txt b/a.txt", text)
        self.assertIn("diff --git a/dir/c.txt b/dir/c.txt", text)
        self.assertNotIn("b.txt", text)
        self.assertIn('+++ "new.txt"', text)
        self.assertIn('+++ "dir/new2.txt"', text)  # under a named folder
        self.assertIn("+new", text)

    def test_no_path_is_no_diff_and_not_the_whole_one(self):
        self.assertEqual(checks.diff(self.project, self.base, paths=[]), "")

    def test_a_path_is_taken_literally(self):
        (self.project / "star*.txt").write_text("x\n", encoding="utf-8")
        text = checks.diff(self.project, self.base, paths=["*.txt"])
        self.assertNotIn("diff --git", text)  # not a pattern: no tracked file is named so


if __name__ == "__main__":
    unittest.main()
