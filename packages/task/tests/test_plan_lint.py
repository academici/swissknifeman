"""Focused opt-in coverage for plan-level return-loop lint wiring."""
import shutil
import sys
import tempfile
import unittest
import json
from unittest import mock
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_lint, plan_returns  # noqa: E402
from task.plan_lint_checks import engine  # noqa: E402


class ReturnLoopLintTests(unittest.TestCase):
    def test_engine_calls_return_loop_gate_once_with_current_plan_context(self):
        source = Path(__file__).parent / "data" / "plan-v2"
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "plan-v2"
            shutil.copytree(source, plan_dir)
            diag = plan_lint.Diagnostics()

            with mock.patch.object(engine.plan_gates, "lint_return_loop") as lint_return_loop:
                engine.lint_plan(plan_dir, diag)

            lint_return_loop.assert_called_once_with(plan_dir, "v2", diag)

    def test_return_loop_checks_are_silent_until_meta_opt_in(self):
        source = Path(__file__).parent / "data" / "plan-v2"
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "plan-v2"
            shutil.copytree(source, plan_dir)
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan_dir, diag)
            self.assertFalse(any("return-loop-v1" in error for error in diag.errors), diag.errors)

    def test_opted_in_owner_gate_requires_and_accepts_d139_evidence(self):
        source = Path(__file__).parent / "data" / "plan-v2"
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "plan-v2"
            shutil.copytree(source, plan_dir)
            plan_md = plan_dir / "plan.md"
            plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
                "| visibility | private |", "| visibility | private |\n| Return Loop Gate | v1 |"),
                encoding="utf-8")
            rows = []
            for index in range(3):
                for minute, command in ((index * 2, "plan-run"), (index * 2 + 1, "plan-design")):
                    rows.append({"ts": f"2026-07-02T00:{minute:02d}:00Z", "plan_id": "plan-v2",
                                 "item_id": "P1.1", "command": command, "session_id": None,
                                 "run_id": None, "attempt": index + 1, "actor": "test/high",
                                 "friction": ["retry"], "result": "closed-green" if command == "plan-run" else "in-progress",
                                 "cost_usd": None, "num_turns": None, "duration_ms": None, "note": None})
            (plan_dir / "journal.jsonl").write_text(
                "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
            finding = plan_dir / "findings/P1.1-fixture.md"
            finding.write_text("---\nitem: P1.1\ndate: 2026-07-02\nfile: a.py\n"
                               "rule_or_contract_locus: x\ndefect_class: y\n---\n", encoding="utf-8")
            digest = plan_returns.returns(plan_dir)["fingerprints"][0]["digest"]
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan_dir, diag)
            self.assertTrue(any("RETURN_LOOP_OWNER_GATE_REQUIRED" in error for error in diag.errors),
                            diag.errors)
            finding.write_text("---\nitem: P1.1\ndate: 2026-07-02\nfile: a.py\n"
                               "rule_or_contract_locus: x\ndefect_class: y\n"
                               "gate: return-loop-v1\n"
                               f"fingerprint_digest: {digest}\noccurrences: 3\n"
                               "qualification: repeat\nowner_authorization: D1\n---\n", encoding="utf-8")
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan_dir, diag)
            self.assertFalse(any("return-loop-v1" in error for error in diag.errors), diag.errors)


if __name__ == "__main__":
    unittest.main()
