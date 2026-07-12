"""anti-rebloat-гейт config.json agent-router: policy остаётся терс (v2 ≤1700 симв),
version бампнут, семантика меню сохранена (все 5 /task:* на месте), auto_suffix непуст."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

PKG = Path(__file__).resolve().parents[1]
CONFIG = PKG / "configs" / "claude-code" / "hooks" / "agent-router" / "config.json"

TASK_COMMANDS = (
    "/task:design",
    "/task:dev",
    "/task:research",
    "/task:review",
    "/task:fix",
)


class RouterConfigCase(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_policy_within_budget(self):
        """анти-реблоат: policy ≤1700 симв (~≤400 ток) — держим always-on старт тощим."""
        policy = self.cfg["policy"]
        self.assertLessEqual(len(policy), 1700, f"policy раздулся: {len(policy)} симв")

    def test_version_bumped(self):
        self.assertGreaterEqual(self.cfg["version"], 2)

    def test_all_task_commands_present(self):
        """меню 5 команд сохранено — ни одну не выкинули при компрессии."""
        policy = self.cfg["policy"]
        for cmd in TASK_COMMANDS:
            self.assertIn(cmd, policy, f"в policy пропала команда {cmd}")

    def test_auto_suffix_present(self):
        self.assertTrue((self.cfg.get("policy_auto_suffix") or "").strip())


if __name__ == "__main__":
    unittest.main()
