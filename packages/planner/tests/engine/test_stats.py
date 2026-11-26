"""``plan.py stats``: aggregates of scout, delegate and friction events; pure reading of ``log.jsonl``."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import ops, stats, store  # noqa: E402

OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}


class StatsCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plans = Path(tmp.name) / "plans"
        plans.mkdir()
        plan = ops.new_plan("STA", "Stats", plans_root=plans, repository="r", owner="o", authoring=OPUS, message="m",
                            date="2026.10.07")
        self.root = plan.root

    def log(self, kind, summary="s", **fields):
        store.append_log(self.root, store.new_event(kind, summary, OPUS, **fields))

    def delegate(self, status, model="haiku", klass="economy", **extra):
        self.log("delegate", f"U1 {status}", item="P1.1", phase="P1",
                 data={"unit": "U1", "class": klass, "model": model, "status": status, **extra})

    def collect(self):
        return stats.collect(store.load_plan(self.root))


class BatchReportTests(StatsCase):
    def setUp(self):
        super().setUp()
        plan = store.load_plan(self.root)
        ops.add_phase(plan, "One")
        ops.add_item(plan, "P1", "First")
        ops.add_item(plan, "P1", "Second")
        ops.set_batches(plan, "P1", [{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended"}])

    def start(self, item, *requested):
        self.log("start", item=item, phase="P1", data={"requested": list(requested)})

    def batches(self):
        return self.collect()["batches"]

    def test_unstarted_batch_is_pending(self):
        self.assertEqual([b["how"] for b in self.batches()], ["pending"])

    def test_one_start_call_for_all_members_is_a_batch(self):
        self.start("P1.1", "P1.1", "P1.2")
        self.start("P1.2", "P1.1", "P1.2")
        self.assertEqual([b["how"] for b in self.batches()], ["batch"])
        self.assertIn("1 of 1 run as a batch", stats.text(self.collect()))

    def test_separate_starts_are_a_split_and_the_deviation_is_reported(self):
        self.start("P1.1", "P1.1")
        self.start("P1.2", "P1.2")
        row = self.batches()[0]
        self.assertEqual((row["how"], row["deviation_logged"]), ("split", False))
        self.assertIn("B1 (recommended) P1.1, P1.2: split, no deviation logged", stats.text(self.collect()))
        self.log("deviation", item="P1.1", phase="P1")
        self.assertTrue(self.batches()[0]["deviation_logged"])


class CollectTests(StatsCase):
    def test_an_empty_plan_has_no_numbers(self):
        result = self.collect()
        self.assertEqual(result["friction"], {"by_type": {}, "by_item": {}})
        self.assertEqual(result["scout"], {"runs": 0, "outcomes": {"ok": 0, "failed": 0, "skipped": 0}, "mean_seconds": None})
        self.assertEqual(result["units"], [])
        self.assertIn("scout: no runs", stats.text(result))

    def test_friction_by_type_and_item(self):
        self.log("difficulty", item="P1.1", phase="P1")
        self.log("difficulty", item="P1.2", phase="P1")
        self.log("blocker", item="P1.1", phase="P1")
        self.log("note", phase="P1")
        self.log("start", item="P1.1", phase="P1")  # lifecycle events are not friction
        result = self.collect()["friction"]
        self.assertEqual(result["by_type"], {"blocker": 1, "difficulty": 2, "note": 1})
        self.assertEqual(result["by_item"]["P1.1"], {"blocker": 1, "difficulty": 1})
        self.assertEqual(result["by_item"]["P1"], {"note": 1})

    def test_scout_outcomes_and_mean_seconds(self):
        for outcome, seconds in (("ok", 10.0), ("ok", 20.0), ("failed", 3.0), ("skipped", 0.0)):
            self.log("scout", item="P1.1", phase="P1", data={"outcome": outcome, "seconds": seconds, "lines": 5})
        scout = self.collect()["scout"]
        self.assertEqual((scout["runs"], scout["outcomes"], scout["mean_seconds"]),
                         (4, {"ok": 2, "failed": 1, "skipped": 1}, 8.2))

    def test_units_by_class_and_model_with_median_minutes(self):
        self.delegate("dispatched")
        self.delegate("accepted", minutes=4)
        self.delegate("accepted", minutes=10)
        self.delegate("accepted", minutes=6)
        self.delegate("reworked", rework=1)
        self.delegate("rejected", model="sonnet", klass="implementation")
        rows = {(r["class"], r["model"]): r for r in self.collect()["units"]}
        self.assertEqual(rows[("economy", "haiku")], {"class": "economy", "model": "haiku", "accepted": 3, "reworked": 1,
                                                       "rejected": 0, "median_minutes": 6})
        self.assertEqual((rows[("implementation", "sonnet")]["rejected"], rows[("implementation", "sonnet")]["median_minutes"]),
                         (1, None))

    def test_the_text_report_and_json_are_the_same_numbers(self):
        self.delegate("accepted", minutes=5)
        self.log("scout", item="P1.1", phase="P1", data={"outcome": "ok", "seconds": 12, "lines": 9})
        result = self.collect()
        text = stats.text(result)
        self.assertIn("scout: 1 run(s): ok 1, failed 0, skipped 0, mean 12.0s", text)
        self.assertIn("economy/haiku: accepted 1, reworked 0, rejected 0, median 5 min", text)
        json.dumps(result)

    def test_stats_only_reads(self):
        self.delegate("accepted")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.collect()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
