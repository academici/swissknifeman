"""Golden of ``plan.py next --parallel 2 --json`` (PLAN4 P6.5): the structure the agent-mode procedure reads (lanes,
running, conflicts, waiting, deferred, next) cannot change silently; the fields are documented in the hub bridge README
("Agent mode"). ``UPDATE_GOLDEN=1`` regenerates the file."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

try:
    from . import test_parallel
except ImportError:  # run as `discover -s tests/engine`
    import test_parallel

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "next-parallel-2.json"


class NextParallelGolden(unittest.TestCase):
    """The ready set of the plan of ``ReadySetTests``: P2 has two items on disjoint paths, P3 is a skeleton phase."""

    def setUp(self):
        self.case = test_parallel.ReadySetTests("ready")  # its plan, not its tests
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def next_json(self, limit=2) -> dict:
        case = self.case
        result = subprocess.run([sys.executable, str(SCRIPT), "next", case.plan().plan["id"], "--parallel", str(limit),
                                 "--json", "--plans-root", str(case.plans)], capture_output=True, text=True,
                                timeout=60, cwd=case.plans.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_the_output_matches_the_golden_file(self):
        actual = self.next_json()
        if os.environ.get("UPDATE_GOLDEN") == "1":  # deliberate regeneration only
            GOLDEN.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.assertEqual(actual, json.loads(GOLDEN.read_text(encoding="utf-8")),
                         "plan.py next --parallel 2 --json changed: update the Agent mode section of the bridge README, then UPDATE_GOLDEN=1")

    def test_the_fields_the_agent_procedure_reads_are_there(self):
        doc = self.next_json()
        self.assertTrue({"plan", "limit", "lanes", "running", "conflicts", "waiting", "deferred"} <= set(doc), sorted(doc))
        run_items = [lane for lane in doc["lanes"] if lane["kind"] == "run-items"]
        self.assertEqual([lane["items"] for lane in run_items], [["P2.1"], ["P2.2"]])
        for lane in run_items:
            self.assertTrue({"lane", "kind", "phase", "items", "command", "launch"} <= set(lane), sorted(lane))
            self.assertTrue(lane["command"].startswith("planner:plan-run "))
        self.assertEqual(doc["deferred"], ["P3"])


if __name__ == "__main__":
    unittest.main()
