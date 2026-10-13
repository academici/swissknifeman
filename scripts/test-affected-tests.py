#!/usr/bin/env python3
"""scripts/affected-tests.py: the tests a change needs, the tools kept out of the core, the foundation touching all."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "affected-tests.py"


def plan(*paths, tier="fast", extra=()):
    done = subprocess.run([sys.executable, str(SCRIPT), "--json", "--tier", tier, "--paths", *paths, *extra],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


class AffectedTestsTests(unittest.TestCase):
    def test_a_tool_is_tested_when_its_own_files_change(self):
        self.assertEqual(plan("packages/maind/lib/maind/x.py")["units"], ["packages/maind"])

    def test_a_module_brings_the_bridges_that_require_it_and_no_other_module(self):
        self.assertEqual(plan("packages/skiller/lib/skiller/cli.py")["units"], ["bridges/orch-skiller", "packages/skiller"])

    def test_the_foundation_affects_every_unit_except_the_tools(self):
        units = plan("packages/aicore/lib/aicore/util/io.py")["units"]
        self.assertIn("packages/harness", units)
        self.assertIn("bridges/planner-orch", units)
        self.assertNotIn("packages/maind", units)  # a tool joins only for its own changes, or with --with-tools
        self.assertIn("packages/maind", plan("packages/aicore/x.py", extra=("--with-tools",))["units"])

    def test_a_hub_path_runs_only_the_cheap_hub_checks(self):
        result = plan("docs/develop.md")
        self.assertEqual(result["units"], [])
        self.assertTrue(result["hub"])
        self.assertEqual({item["folder"] for item in result["commands"]}, {"hub"})

    def test_the_full_tier_adds_validate_and_all_is_every_core_unit(self):
        folders = [(item["folder"], item["argv"][-1]) for item in plan("packages/skiller/x.py", tier="full")["commands"]]
        self.assertIn(("packages/skiller", "scripts/validate.sh"), folders)
        everything = plan(tier="all")["units"]
        self.assertIn("packages/planner", everything)
        self.assertNotIn("packages/maind", everything)


if __name__ == "__main__":
    unittest.main()
