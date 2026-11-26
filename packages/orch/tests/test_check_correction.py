"""A successful log tail must not hide an earlier failed command in a correction."""
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from orch.conductor import prompts
from orch.conductor.stages import checks_stage


class CheckCorrectionTests(unittest.TestCase):
    def test_failure_before_successful_tail_remains_visible_with_exact_log_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "V90.log"
            log.write_text("[ok] preceding unit\n[fail] hub: golden.py check\nwrong launch list\n"
                           + "[ok] later unit\n" * 200)
            text = prompts.check_correction([{"id": "V90", "cmd": "affected", "exit": 1,
                                              "log": str(log), "tail": "[ok] later unit"}])
            self.assertIn(str(log), text)
            self.assertIn("[fail] hub: golden.py check\nwrong launch list", text)
            self.assertTrue(text.endswith("[ok] later unit"))
            self.assertIn("tail may omit", text)
            self.assertIn("Current correction focus", text)
            self.assertIn("only current correction", text)

    def test_excerpt_is_bounded_even_with_a_long_error_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "long.log"
            log.write_text("ERROR: " + "x" * 10000)
            excerpt = prompts._failure_excerpt(log)
            self.assertTrue(excerpt.startswith("ERROR:"))
            self.assertLessEqual(len(excerpt), 1600)

    def test_missing_log_keeps_path_and_tail_without_raising(self):
        text = prompts.check_correction([{"id": "V2", "cmd": "test", "exit": 1,
                                          "log": "/missing/check.log", "tail": "failed"}])
        self.assertIn("/missing/check.log", text)
        self.assertTrue(text.endswith("failed"))

    def test_legacy_row_without_log_keeps_the_red_facts_under_the_current_focus(self):
        text = prompts.check_correction([{"id": "V2", "procedure": "inspect", "verdict": "RED", "tail": "why"}])
        self.assertIn("These acceptance checks are red on your candidate:\n\nV2: `inspect` → RED\nwhy", text)
        self.assertIn("Stage `checks`. Status: red.", text)
        self.assertNotIn("## Historical causes", text)

    def test_every_failure_header_and_child_log_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "V1.log"
            child = Path(tmp) / "child.txt"
            log.write_text("FAIL: test_one\nfirst\n"
                           "ok line\n"
                           "ERROR: test_two\nsecond\n"
                           f"full output: {child}\n"
                           "[ok] tail\n", encoding="utf-8")
            text = prompts.check_correction([{"id": "V1", "cmd": "suite", "exit": 1, "log": str(log), "tail": "[ok] tail"}])
            self.assertIn("FAIL: test_one\nfirst", text)
            self.assertIn("ERROR: test_two\nsecond", text)
            self.assertIn(f"Child log: `{child}`", text)

    def test_addressed_causes_are_historical_and_not_the_assignment(self):
        text = prompts.check_correction(
            [{"id": "V2", "cmd": "new", "exit": 1}],
            historical=[{"id": "V1", "cmd": "old"}], stage="checks.2")
        self.assertLess(text.index("Current correction focus"), text.index("V2"))
        self.assertLess(text.index("V2"), text.index("## Historical causes"))
        self.assertIn("V1 `old`: addressed", text)
        self.assertIn("not current work", text)
        self.assertIn("Stage `checks.2`", text)

    def test_full_and_resumed_prompts_say_the_correction_supersedes_earlier_instructions(self):
        resumed = prompts.render(prompts.executor_resumed(item="W1", step="executor.2", correction="fix V2"))
        full = prompts._correction("fix V2", True)
        for text in (full, resumed):
            self.assertIn("only assignment of this round", text)
            self.assertIn("historical", text)
            self.assertIn("fix V2", text)
            self.assertIn("stay in force", text)


class IneffectiveCorrectionTests(unittest.TestCase):
    def block(self, report, **extra):
        fields = {"product_changed": False, "input_changed": False, "command_red": ("V1",), "proved": set()}
        fields.update(extra)
        return checks_stage.correction_block(report, **fields)

    def test_a_completion_with_no_product_change_is_not_fixed(self):
        for status in ("done", "done_with_deviations", "done_pending_checks"):
            reason = self.block({"status": status, "open_issues": []})
            self.assertIn("not fixed", reason)
            self.assertIn("Acceptance was not started", reason)

    def test_a_product_or_input_change_may_be_proved(self):
        report = {"status": "done", "open_issues": []}
        self.assertIsNone(self.block(report, product_changed=True))
        self.assertIsNone(self.block(report, input_changed=True))

    def test_an_environment_fix_with_evidence_is_allowed_once(self):
        report = {"status": "done", "open_issues": [
            {"class": "environment", "text": "fixed the runner home", "evidence": ["runs/home.txt"]}]}
        self.assertIsNone(self.block(report))
        again = self.block(report, proved={("V1",)})
        self.assertIn("already had one no-diff environment proof", again)

    def test_a_nondeterministic_claim_needs_the_word_and_evidence(self):
        bare = {"status": "done", "open_issues": [{"text": "nondeterministic flake", "evidence": []}]}
        self.assertIn("not fixed", self.block(bare))
        proved = {"status": "done", "open_issues": [
            {"text": "confirmed nondeterministic isolation", "evidence": ["checks/V1.log"]}]}
        self.assertIsNone(self.block(proved))
        self.assertNotIn("secret", checks_stage.no_diff_cause(proved) or "")

    def test_a_class_without_evidence_is_not_a_cause(self):
        report = {"status": "done", "open_issues": [{"class": "test_env", "text": "home", "evidence": []}]}
        self.assertIn("not fixed", self.block(report))

    def test_addressed_checks_need_a_later_green_and_ignore_skips(self):
        item = type("I", (), {"state": {"steps": {
            "checks.1": {"status": "done", "result": [
                {"id": "V1", "green": False, "cmd": "old"},
                {"id": "V2", "green": False, "cmd": "still"},
                {"id": "V3", "skipped": True, "green": False}]},
            "checks.2": {"status": "done", "result": [
                {"id": "V1", "green": True},
                {"id": "V2", "green": False},
                {"id": "V3", "skipped": True, "green": False}]}}}})()
        found = checks_stage.addressed_checks(item, ["V2"])
        self.assertEqual([row["id"] for row in found], ["V1"])
        self.assertEqual(checks_stage.addressed_checks(item, ["V1", "V2"]), [])

    def test_green_before_red_is_not_closed_and_rounds_are_numeric(self):
        item = SimpleNamespace(state={"steps": {
            "checks.2": {"status": "done", "result": [{"id": "V1", "green": True},
                                                        {"id": "V2", "green": False}]},
            "checks.10": {"status": "done", "result": [{"id": "V1", "green": False},
                                                         {"id": "V2", "green": True}]},
            "checks.11": {"status": "done", "result": [{"id": "V1", "green": True, "skipped": True}]}}})
        self.assertEqual([row["id"] for row in checks_stage.addressed_checks(item, [])], ["V2"])


class CorrectionReplayTests(unittest.TestCase):
    def setup_round(self, execute, run_checks):
        item = SimpleNamespace(ref="W1", state={"steps": {}, "check_fixes_at": []},
                               input_doc={"goal": "fix", "digest": "a", "provenance": {"ts": "a"}})
        owner = SimpleNamespace(project=Path("."), store=SimpleNamespace(mutating=nullcontext),
                                _save=mock.Mock(), _red_signature=checks_stage.red_signature,
                                _allowance=lambda *args: None, _execute=execute, _run_checks=run_checks,
                                progress=SimpleNamespace(emit=mock.Mock()),
                                _blocked=lambda report, code, reason: dict(report, status="blocked", reason=code))
        return owner, item

    def test_corrected_tree_survives_resume_after_checks_interrupt(self):
        current = [("base", ())]
        def execute(item, *args):
            if "executor.2" not in item.state["steps"]:
                current[0] = ("base", (("fixed.py", "new"),))
                item.state["steps"]["executor.2"] = {"status": "done"}
            return {"status": "done"}
        checks = mock.Mock(side_effect=[KeyboardInterrupt(), [{"id": "V1", "green": True}]])
        owner, item = self.setup_round(execute, checks)
        red = [{"id": "V1", "green": False, "cmd": "check"}]
        with mock.patch.object(checks_stage, "product_snapshot", side_effect=lambda project: current[0]):
            with self.assertRaises(KeyboardInterrupt):
                checks_stage.green(owner, item, red, {"status": "done"}, 1, "")
            rows, report, _ = checks_stage.green(owner, item, red, {"status": "done"}, 1, "")
        self.assertTrue(rows[0]["green"])
        self.assertEqual(report["status"], "done")
        self.assertEqual(checks.call_count, 2)

    def test_environment_admission_is_saved_before_checks_and_not_spent_twice_on_resume(self):
        report = {"status": "done", "open_issues": [{"class": "environment", "evidence": ["proof.log"]}]}
        checks = mock.Mock(side_effect=KeyboardInterrupt())
        owner, item = self.setup_round(lambda *args: report, checks)
        red = [{"id": "V1", "green": False, "cmd": "check"}]
        with mock.patch.object(checks_stage, "product_snapshot", return_value=("base", ())):
            for _ in range(2):
                with self.assertRaises(KeyboardInterrupt):
                    checks_stage.green(owner, item, red, report, 1, "")
                self.assertEqual(item.state["no_diff_proofs"], [["V1"]])
                self.assertEqual(item.state["no_diff_admitted"], [2])
            # A distinct correction round cannot spend the same evidence again.
            _, blocked, _ = checks_stage.green(owner, item, red, report, 2, "")
        self.assertEqual(blocked["reason"], "CORRECTION_INEFFECTIVE")
        self.assertEqual(checks.call_count, 2)

    def test_provenance_rebuild_does_not_turn_no_change_into_a_fix(self):
        def execute(item, *args):
            item.input_doc.update(digest="b", provenance={"ts": "b"})
            return {"status": "done"}
        checks = mock.Mock()
        owner, item = self.setup_round(execute, checks)
        with mock.patch.object(checks_stage, "product_snapshot", return_value=("base", ())):
            _, report, _ = checks_stage.green(owner, item,
                                             [{"id": "V1", "green": False, "cmd": "check"}],
                                             {"status": "done"}, 1, "")
        self.assertEqual(report["reason"], "CORRECTION_INEFFECTIVE")
        checks.assert_not_called()


class ResumedContractTests(unittest.TestCase):
    def test_executor_owned_acceptance_is_not_forbidden_in_the_same_prompt(self):
        text = prompts._correction("repair V1", False)
        self.assertIn("run the acceptance checks again", text)
        self.assertNotIn("Do not rerun acceptance", text)

    def test_continuation_uses_latest_full_contract_after_an_input_rebuild(self):
        blocks = prompts.executor_resumed(item="P3.1", step="executor.2", correction="repair V1")
        continuation = next(block.text for block in blocks if block.kind == "resumed")
        self.assertIn("latest full prompt", continuation)
        self.assertNotIn("first prompt", continuation)
        self.assertTrue(any(block.kind == "result_contract" for block in blocks))
        self.assertTrue(any(block.kind == "correction" for block in blocks))
