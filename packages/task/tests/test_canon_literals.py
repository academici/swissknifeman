"""Regression checks for the compact canonical command surface."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COMMANDS = ROOT / "packages/task/commands"
PROTOCOL = ROOT / "packages/skiller/skills/general/plan-protocol/SKILL.md"


class CompactCanonTests(unittest.TestCase):
    def test_plan_commands_delegate_to_the_plan_cli(self):
        for name in ("plan-run.md", "plan-audit.md", "plan-design.md", "plan-close.md"):
            with self.subTest(name=name):
                text = (COMMANDS / name).read_text(encoding="utf-8")
                self.assertIn("scripts/plan.py", text)
                self.assertIn("plan.py", text)

    def test_execution_still_names_hard_risk_and_owner_gates(self):
        text = (COMMANDS / "plan-run.md").read_text(encoding="utf-8")
        for literal in ("Hard risk", "security, schema/public API, data, concurrency, publishing",
                        "Owner gates", "plan.py grant", "ROUTE_UNDERSHOOT"):
            self.assertIn(literal, text)

    def test_command_budget_is_below_the_lean_cap(self):
        total = sum(path.stat().st_size for path in COMMANDS.glob("plan-*.md")) + PROTOCOL.stat().st_size
        self.assertLessEqual(total, 105795)

    def test_plan_run_uses_the_v3_lifecycle_verbs_only(self):
        text = (COMMANDS / "plan-run.md").read_text(encoding="utf-8")
        for verb in ("plan.py next", "plan.py start", "plan.py log", "plan.py finish", "plan.py show"):
            self.assertIn(verb, text)
        for retired in ("plan-work.py", "plan-views.py", "plan-lint.py", "journal", "bundle", "receipt", "continuity"):
            self.assertNotIn(retired, text)


if __name__ == "__main__":
    unittest.main()
