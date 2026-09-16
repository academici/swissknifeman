"""Regression checks for the compact canonical command surface."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COMMANDS = ROOT / "packages/task/commands"
PROTOCOL = ROOT / "packages/skiller/skills/general/plan-protocol/SKILL.md"


class CompactCanonTests(unittest.TestCase):
    def test_plan_commands_delegate_to_one_runtime_lifecycle(self):
        for name in ("plan-exec.md", "plan-run.md", "plan-audit.md", "plan-design.md"):
            with self.subTest(name=name):
                self.assertIn("task.plan_lifecycle", (COMMANDS / name).read_text(encoding="utf-8"))

    def test_execution_still_names_hard_safety_boundaries(self):
        text = (COMMANDS / "plan-exec.md").read_text(encoding="utf-8")
        for risk in ("security/auth", "destructive migration", "irreversible external action",
                     "payment/accounting", "concurrency/shared state", "public API/schema",
                     "low-confidence impact"):
            self.assertIn(risk, text)

    def test_command_budget_is_below_the_lean_cap(self):
        total = sum(path.stat().st_size for path in COMMANDS.glob("plan-*.md")) + PROTOCOL.stat().st_size
        self.assertLessEqual(total, 105795)

    def test_commands_preserve_v2_and_delivery_owners(self):
        text = (COMMANDS / "plan-exec.md").read_text(encoding="utf-8")
        self.assertIn("task.plan_recovery.prepare()", text)
        self.assertIn("PLAN_CONTEXT_TRUNCATED", text)
        self.assertIn("phase_audit_policy", text)
        self.assertIn("plan_delivery", text)


if __name__ == "__main__":
    unittest.main()
