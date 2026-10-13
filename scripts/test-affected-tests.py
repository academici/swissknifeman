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
    def test_a_bridge_gets_its_partners_from_the_hub_layout(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = module.bridge_env()
        for name in ("PLANNER_ROOT", "PLANNER_PLAN_PY", "SKM_ORCH_ROOT", "SKM_SKILLER_ROOT", "SKM_HARNESS_ROOT", "AICORE_ROOT"):
            self.assertTrue(Path(env[name]).exists(), name)

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

    def test_hub_paths_bring_their_own_checks(self):
        argv = [" ".join(item["argv"]) for item in plan("bootstrap/skills/x/SKILL.md", "scripts/docs-impact.py")["commands"]]
        self.assertIn("python3 scripts/golden.py check", argv)
        self.assertIn("python3 scripts/test-docs-impact.py", argv)
        self.assertNotIn("python3 scripts/golden.py check",
                         [" ".join(item["argv"]) for item in plan("docs/develop.md")["commands"]])

    def test_analyst_and_maind_are_tools(self):
        units = plan("packages/aicore/lib/aicore/util/io.py")["units"]
        self.assertNotIn("packages/analyst", units)
        self.assertEqual(plan("packages/analyst/lib/analyst/x.py")["units"], ["packages/analyst"])

    def test_planner_has_a_quick_test_command(self):
        commands = plan("packages/planner/lib/planner/plan/x.py")["commands"]
        self.assertIn(("packages/planner", ["bash", "scripts/test.sh"]),
                      [(item["folder"], item["argv"]) for item in commands])

    def test_the_cache_key_follows_the_content_of_the_unit_and_its_requirements(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        units = module.units()
        self.assertEqual(module.requirements(units, "bridges/planner-orch", "aicore"),
                         ["bridges/planner-orch", "packages/aicore", "packages/orch", "packages/planner"])
        key = module.content_key(["packages/brain"], ["bash", "scripts/test.sh"])
        self.assertEqual(key, module.content_key(["packages/brain"], ["bash", "scripts/test.sh"]))
        self.assertNotEqual(key, module.content_key(["packages/brain"], ["bash", "scripts/validate.sh"]))

    def test_the_full_tier_adds_validate_and_all_is_every_core_unit(self):
        folders = [(item["folder"], item["argv"][-1]) for item in plan("packages/skiller/x.py", tier="full")["commands"]]
        self.assertIn(("packages/skiller", "scripts/validate.sh"), folders)
        everything = plan(tier="all")["units"]
        self.assertIn("packages/planner", everything)
        self.assertNotIn("packages/maind", everything)


if __name__ == "__main__":
    unittest.main()
