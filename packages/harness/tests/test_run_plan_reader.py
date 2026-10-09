"""Queue of a phase through the planner plan API (`plan.py show|next --json`)."""
import tempfile
import unittest
from pathlib import Path

from harness.run import plan_reader
from packages.harness.tests.plan_fixture import write_plan

REPO_ROOT = Path(__file__).resolve().parents[3]
MEDIUM = ("implementation", "medium")


class QueueTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.plan, _ = write_plan(
            self._tmp.name,
            items=[("todo", MEDIUM), ("done", MEDIUM), ("in_progress", ("frontier", "high"))])

    def test_order_terminal_exclusion_and_drivable_items(self):
        result = plan_reader.queue(self.plan, "P1", monorepo_root=REPO_ROOT)
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        self.assertEqual([it["item_id"] for it in result["items"]], ["P1.1", "P1.3"])
        self.assertEqual([e["item_id"] for e in result["excluded_terminal"]], ["P1.2"])
        self.assertEqual(result["excluded_terminal"][0]["refusal"], plan_reader.ITEM_TERMINAL)
        self.assertEqual(result["excluded_terminal"][0]["status"], "done")
        for item in result["items"]:
            self.assertTrue(item["drivable"], item)
            self.assertIsNone(item["refusal"])
            self.assertEqual(item["exec"], "run")
        self.assertEqual(result["items"][0]["status"], "todo")
        self.assertEqual(result["items"][0]["route"], {"model_class": "implementation", "effort": "medium"})
        self.assertEqual(result["items"][1]["status"], "in_progress")
        self.assertEqual(result["items"][1]["route"], {"model_class": "frontier", "effort": "high"})

    def test_next_form_is_the_semantic_next_of_the_plan(self):
        result = plan_reader.queue(self.plan, "P1", monorepo_root=REPO_ROOT)
        self.assertEqual(result["next_form"]["kind"], "run-items")
        self.assertTrue(result["next_form"]["declaring_line"].startswith("run-items: planner:plan-run "))
        for item in result["items"]:
            self.assertEqual(item["next_form"], result["next_form"])


class RefusalTest(unittest.TestCase):
    def _queue(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            plan, _ = write_plan(tmp, **kwargs)
            return plan_reader.queue(plan, "P1", monorepo_root=REPO_ROOT)

    def test_blocked_item_is_not_drivable(self):
        result = self._queue(items=[("todo", MEDIUM), ("blocked", MEDIUM)])
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        by_id = {item["item_id"]: item for item in result["items"]}
        self.assertTrue(by_id["P1.1"]["drivable"])
        self.assertFalse(by_id["P1.2"]["drivable"])
        self.assertEqual(by_id["P1.2"]["refusal"], plan_reader.ITEM_BLOCKED)
        self.assertEqual(by_id["P1.2"]["status"], "blocked")

    def test_skeleton_phase_refuses_every_item(self):
        result = self._queue(items=[("todo", MEDIUM)], design="skeleton")
        self.assertFalse(result["degraded"], result["degraded_reasons"])
        item = result["items"][0]
        self.assertFalse(item["drivable"])
        self.assertEqual(item["refusal"], plan_reader.PHASE_NOT_DETAILED)
        self.assertIsNone(item["exec"])

    def test_done_with_deviations_is_terminal(self):
        result = self._queue(items=[("done_with_deviations", MEDIUM), ("todo", MEDIUM)])
        self.assertEqual([e["status"] for e in result["excluded_terminal"]], ["done_with_deviations"])
        self.assertEqual([it["item_id"] for it in result["items"]], ["P1.2"])

    def test_frontier_high_route_is_drivable(self):
        result = self._queue(items=[("todo", ("frontier", "high"))])
        item = result["items"][0]
        self.assertTrue(item["drivable"], item)
        self.assertEqual(item["route"], {"model_class": "frontier", "effort": "high"})

    def test_incomplete_route_is_unresolved(self):
        self.assertEqual(
            plan_reader._classify("todo", True, None, "item route is incomplete: {}"),
            (False, plan_reader.ROUTING_UNRESOLVED, "item route is incomplete: {}"))
        self.assertEqual(plan_reader._route({"route": {"class": "frontier"}})[0], None)


class DegradedTest(unittest.TestCase):
    def test_monorepo_root_not_found_is_degraded_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "STANDALONE"
            plan_dir.mkdir()
            result = plan_reader.queue(plan_dir, "P1")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"], [])
        self.assertTrue(result["degraded_reasons"])

    def test_missing_plan_json_is_degraded_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "BROKEN"
            plan_dir.mkdir(parents=True)
            result = plan_reader.queue(plan_dir, "P1", monorepo_root=REPO_ROOT)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"], [])
        self.assertTrue(result["degraded_reasons"])

    def test_unknown_phase_is_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, _ = write_plan(tmp, items=[("todo", MEDIUM)])
            result = plan_reader.queue(plan, "P7", monorepo_root=REPO_ROOT)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
