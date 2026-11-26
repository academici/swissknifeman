"""Internal documentation."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

PKG = Path(__file__).resolve().parents[1]
CONFIG = PKG / "configs" / "claude-code" / "hooks" / "agent-router" / "config.json"

class RouterConfigCase(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_policy_within_budget(self):
        """Internal documentation."""
        policy = self.cfg["policy"]
        self.assertLessEqual(len(policy), 1700, f"policy swelled: {len(policy)} char")

    def test_version_bumped(self):
        self.assertGreaterEqual(self.cfg["version"], 2)

    def test_no_resident_task_policy_or_keyword_commands(self):
        self.assertEqual(self.cfg["policy"], "")
        self.assertEqual(self.cfg["commands"], [])

    def test_no_automatic_task_dispatch(self):
        self.assertEqual(self.cfg["policy_auto_suffix"], "")


if __name__ == "__main__":
    unittest.main()
