"""Downstream-gate v1 discovery, outcomes, key and opt-in lint tests."""
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from task import plan_downstream, plan_lint


DATA = Path(__file__).resolve().parent / "data" / "plan-v2"


class TestPlanDownstream(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.plan = self.repo / "plans" / "demo"
        shutil.copytree(DATA, self.plan)
        (self.repo / "artifact.txt").write_text("producer output\n", encoding="utf-8")
        producer = self.plan / "phases" / "P0" / "P0.1.md"
        producer.write_text(producer.read_text(encoding="utf-8").replace(
            "**Files:** phases/P0/P0.1.md.", "**Files:** `artifact.txt`."), encoding="utf-8")
        self.consumer = self.plan / "phases" / "P1" / "P1.1.md"
        self._consumer(validation='python3 -c "print(\'green\')"')
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")
        self._git("add", ".")
        self._git("commit", "-qm", "fixture")

    def _git(self, *args):
        return subprocess.run(("git", *args), cwd=self.repo, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def _consumer(self, *, validation):
        text = self.consumer.read_text(encoding="utf-8")
        text = text.replace("**Inputs:** `brief/00-brief.md`", "**Inputs:** `artifact.txt`")
        text = re.sub(r"^\*\*Validation:\*\*.*$", f"**Validation:** {validation}",
                      text, flags=re.MULTILINE)
        self.consumer.write_text(text, encoding="utf-8")

    def _commit_consumer(self, validation):
        self._consumer(validation=validation)
        self._git("add", str(self.consumer.relative_to(self.repo)))
        self._git("commit", "-qm", "consumer")

    def test_mechanical_discovery_and_green_outcome(self):
        consumers = plan_downstream.discover_consumers(self.plan, "P0.1")
        self.assertEqual([row["item"] for row in consumers], ["P1.1"])
        self.assertEqual(consumers[0]["matched_paths"], ["plans/demo/artifact.txt"])
        result = plan_downstream.evaluate(self.plan, "P0.1")
        self.assertEqual(result["outcome"], "green")
        self.assertFalse(result["blocks"])

    def test_markdown_validation_executes_only_inline_code(self):
        self._commit_consumer('`python3 -c "print(\'green\')"` (печатает green)')
        result = plan_downstream.evaluate(self.plan, "P0.1")
        command = result["consumers"][0]["commands"][0]
        self.assertEqual(command["command"], 'python3 -c "print(\'green\')"')
        self.assertEqual(command["returncode"], 0)

    def test_red_blocks_and_cannot_be_made_advisory(self):
        self._commit_consumer('python3 -c "raise SystemExit(3)"')
        result = plan_downstream.evaluate(self.plan, "P0.1")
        self.assertEqual(result["outcome"], "red")
        self.assertTrue(result["blocks"])
        self.assertEqual(result["consumers"][0]["commands"][0]["returncode"], 3)

    def test_unknown_is_recorded_without_collapsing_to_green_or_red(self):
        self._commit_consumer("python3 missing-consumer-test.py")
        result = plan_downstream.evaluate(self.plan, "P0.1")
        self.assertEqual(result["outcome"], "unknown")
        self.assertFalse(result["blocks"])
        self.assertFalse(result["consumers"][0]["commands"][0]["applicable"])
        paths = plan_downstream.record(self.plan, result, date="2026-08-08")
        fields, _body = plan_downstream.parse_result_record(paths[0])
        self.assertEqual(fields["outcome"], "unknown")
        plan_downstream.validate_result_record(fields)

    def test_record_without_content_commit_pair_is_rejected(self):
        with self.assertRaisesRegex(plan_downstream.DownstreamError, "consumer_spec_sha256"):
            plan_downstream.validate_result_record({
                "item": "P0.1", "date": "2026-08-08", "gate": plan_downstream.GATE_ID,
                "producer_commit": "a" * 40, "consumer_item": "P1.1", "outcome": "green",
            })

    def test_result_key_binds_current_consumer_bytes_and_commit(self):
        result = plan_downstream.evaluate(self.plan, "P0.1")
        consumer = result["consumers"][0]
        self.assertEqual(consumer["consumer_spec_sha256"],
                         hashlib.sha256(self.consumer.read_bytes()).hexdigest())
        self.assertEqual(consumer["result_key"]["producer_commit"], self._git("rev-parse", "HEAD"))

    def test_lint_is_silent_by_default_and_opt_in_requires_record(self):
        diag = plan_lint.Diagnostics()
        plan_lint.lint_plan(self.plan, diag)
        self.assertFalse(any(plan_downstream.GATE_ID in row for row in diag.errors), diag.errors)
        plan_md = self.plan / "plan.md"
        plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
            "| Layout | v2 |", "| Layout | v2 |\n| Downstream Gate | v1 |"), encoding="utf-8")
        diag = plan_lint.Diagnostics()
        plan_lint.lint_plan(self.plan, diag)
        self.assertTrue(any("P0.1" in row and "P1.1" in row and plan_downstream.GATE_ID in row
                            for row in diag.errors), diag.errors)
        result = plan_downstream.evaluate(self.plan, "P0.1")
        plan_downstream.record(self.plan, result, date="2026-08-08")
        diag = plan_lint.Diagnostics()
        plan_lint.lint_plan(self.plan, diag)
        self.assertFalse(any(plan_downstream.GATE_ID in row for row in diag.errors), diag.errors)

    def test_opt_in_lint_keeps_recorded_red_blocking(self):
        self._commit_consumer('python3 -c "raise SystemExit(5)"')
        plan_md = self.plan / "plan.md"
        plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
            "| Layout | v2 |", "| Layout | v2 |\n| Downstream Gate | v1 |"), encoding="utf-8")
        result = plan_downstream.evaluate(self.plan, "P0.1")
        self.assertEqual(result["outcome"], "red")
        plan_downstream.record(self.plan, result, date="2026-08-08")
        diag = plan_lint.Diagnostics()
        plan_lint.lint_plan(self.plan, diag)
        self.assertTrue(any("red блокирует" in row and plan_downstream.GATE_ID in row
                            for row in diag.errors), diag.errors)

    def test_newer_green_producer_commit_supersedes_append_only_red(self):
        self._commit_consumer('python3 -c "raise SystemExit(5)"')
        plan_md = self.plan / "plan.md"
        plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
            "| Layout | v2 |", "| Layout | v2 |\n| Downstream Gate | v1 |"), encoding="utf-8")
        plan_downstream.record(self.plan, plan_downstream.evaluate(self.plan, "P0.1"),
                               date="2026-08-08")
        (self.repo / "producer-fix.txt").write_text("fixed\n", encoding="utf-8")
        self._git("add", "producer-fix.txt")
        self._git("commit", "-qm", "producer fix")
        green = plan_downstream.evaluate(
            self.plan, "P0.1",
            runner=lambda _command, _cwd: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        plan_downstream.record(self.plan, green, date="2026-08-08")
        diag = plan_lint.Diagnostics()
        plan_lint.lint_plan(self.plan, diag)
        self.assertFalse(any(plan_downstream.GATE_ID in row for row in diag.errors), diag.errors)

    def test_cli_json_keeps_red_exit_nonzero(self):
        self._commit_consumer('python3 -c "raise SystemExit(4)"')
        script = Path(__file__).resolve().parents[1] / "scripts" / "plan-downstream.py"
        completed = subprocess.run(("python3", str(script), "--plan-dir", str(self.plan),
                                    "--item", "P0.1", "--json"), cwd=self.repo, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["outcome"], "red")


if __name__ == "__main__":
    unittest.main()
