"""Internal documentation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "harness" / "lib"))

from harness.run import journal, worker  # noqa: E402


from packages.harness.tests.plan_fixture import write_plan  # noqa: E402


def _outcome(kind, **extra):
    base = {"outcome": kind, "session_id": None, "total_cost_usd": None, "num_turns": None,
           "duration_ms": None, "permission_denials": None, "client_version": None,
           "reason": None}
    base.update(extra)
    return base


class _Plan:
    """A v3 plan with one open item; `events()` reads its append-only `log.jsonl`."""

    def __init__(self, tmp):
        self.plan_dir, _ = write_plan(Path(tmp), items=[("in_progress", ("implementation", "medium"))])

    def events(self, type_=None):
        path = self.plan_dir / "log.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        return [row for row in rows if type_ is None or row["type"] == type_]


class ClassifyTest(unittest.TestCase):
    def test_pre_launch_is_driver_routing_blocked(self):
        category, who = journal.classify(pre_launch=True)
        self.assertEqual(category, "routing-blocked")
        self.assertEqual(who, journal.DRIVER)

    def test_ok_outcome_with_terminal_status_is_worker(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK), item_status="done")
        self.assertEqual(category, "ok-terminal")
        self.assertEqual(who, journal.WORKER)

    def test_ok_outcome_with_deviations_status_is_still_worker(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK),
            item_status="done_with_deviations")
        self.assertEqual(who, journal.WORKER)

    def test_ok_outcome_with_blocked_escalation_status_is_worker(self):

        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK), item_status="blocked")
        self.assertEqual(who, journal.WORKER)

    def test_ok_outcome_with_non_terminal_status_is_driver_no_op(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK), item_status="in_progress")
        self.assertEqual(category, "no-op")
        self.assertEqual(who, journal.DRIVER)

    def test_timeout_is_driver_regardless_of_status(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_TIMEOUT), item_status=None)
        self.assertEqual(category, worker.OUTCOME_TIMEOUT)
        self.assertEqual(who, journal.DRIVER)

    def test_transport_and_quota_and_error_are_driver(self):
        for kind in (worker.OUTCOME_TRANSPORT, worker.OUTCOME_QUOTA, worker.OUTCOME_ERROR):
            category, who = journal.classify(
                pre_launch=False, outcome=_outcome(kind), item_status="todo")
            self.assertEqual(category, kind)
            self.assertEqual(who, journal.DRIVER)

    def test_unknown_outcome_refuses(self):
        with self.assertRaises(journal.JournalWriteRefused):
            journal.classify(pre_launch=False, outcome=_outcome("bogus-outcome"))


class MaybeWriteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.plan = _Plan(self._tmp.name)

    def _write(self, **kwargs):
        kwargs.setdefault("run_id", "wave-1")
        kwargs.setdefault("monorepo_root", REPO_ROOT)
        return journal.maybe_write(self.plan.plan_dir, "P1.1", **kwargs)

    def _driver_events(self):
        return [e for e in self.plan.events() if e["actor"]["model"] == "driver"]

    def test_worker_closed_item_gets_no_driver_event(self):
        result = self._write(outcome=_outcome(worker.OUTCOME_OK), item_status="done")
        self.assertIsNone(result)
        self.assertEqual(self._driver_events(), [])

    def test_timeout_writes_exactly_one_difficulty_event(self):
        result = self._write(outcome=_outcome(worker.OUTCOME_TIMEOUT, reason="30min"),
                             item_status="in_progress")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "difficulty")
        events = self._driver_events()
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event["type"], event["item"]), ("difficulty", "P1.1"))
        self.assertEqual(event["actor"], {"provider": "harness", "model": "driver"})
        self.assertTrue(event["summary"].startswith("[wave wave-1] timeout"))
        self.assertIn("run:wave-1", event["refs"])

    def test_routing_blocked_writes_a_blocker_with_the_refusal(self):
        self._write(pre_launch=True, refusal_detail="PHASE-NOT-DETAILED: phase is a skeleton")
        events = self._driver_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "blocker")
        self.assertIn("routing-blocked: PHASE-NOT-DETAILED", events[0]["summary"])

    def test_worker_failures_are_difficulties_not_blockers(self):
        for kind in (worker.OUTCOME_TIMEOUT, worker.OUTCOME_TRANSPORT,
                     worker.OUTCOME_QUOTA, worker.OUTCOME_ERROR):
            with self.subTest(kind=kind):
                self._write(run_id=f"wave-{kind}", outcome=_outcome(kind),
                            item_status="in_progress")
                self.assertEqual(self._driver_events()[-1]["type"], "difficulty")

    def test_no_op_writes_a_difficulty(self):
        self._write(outcome=_outcome(worker.OUTCOME_OK), item_status="todo")
        events = self._driver_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "difficulty")
        self.assertIn("no-op", events[0]["summary"])

    def test_run_metrics_are_recorded_in_the_impact(self):
        self._write(outcome=_outcome(worker.OUTCOME_ERROR, session_id="s-1", total_cost_usd=0.5,
                                     num_turns=3, duration_ms=1200),
                    item_status="in_progress")
        impact = self._driver_events()[0]["impact"]
        for fragment in ("session=s-1", "cost_usd=0.5", "turns=3", "duration_ms=1200"):
            self.assertIn(fragment, impact)

    def test_repeat_in_wave_appends_a_second_event(self):
        for _ in range(2):
            self._write(outcome=_outcome(worker.OUTCOME_TIMEOUT), item_status="in_progress")
        self.assertEqual(len(self._driver_events()), 2)

    def test_unknown_outcome_refuses_without_calling_cli(self):
        with self.assertRaises(journal.JournalWriteRefused):
            self._write(outcome=_outcome("bogus"), item_status="in_progress")
        self.assertEqual(self._driver_events(), [])

    def test_nonzero_cli_exit_raises_and_stops_wave(self):
        with self.assertRaises(journal.JournalCallFailed):
            journal.maybe_write(
                self.plan.plan_dir, "P9.9", run_id="wave-1",
                outcome=_outcome(worker.OUTCOME_TIMEOUT), item_status="in_progress",
                monorepo_root=REPO_ROOT)

    def test_missing_run_id_is_rejected(self):
        with self.assertRaises(ValueError):
            self._write(run_id=None, outcome=_outcome(worker.OUTCOME_TIMEOUT),
                        item_status="in_progress")

    def test_every_written_event_passes_check(self):
        self._write(outcome=_outcome(worker.OUTCOME_QUOTA), item_status="in_progress")
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "packages/task/scripts/plan.py"), "check",
             str(self.plan.plan_dir)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class SummarizeWaveTest(unittest.TestCase):
    def test_counts_and_totals_from_records_no_second_counter(self):
        records = [
            {"item_id": "P9.1", "verdict": "GREEN",
             "outcome": {"total_cost_usd": 0.1, "duration_ms": 1000, "client_version": "2.1.220"},
             "wrote_driver_line": False},
            {"item_id": "P9.2", "verdict": "RED",
             "outcome": {"total_cost_usd": None, "duration_ms": None, "client_version": None},
             "wrote_driver_line": True},
            {"item_id": "P9.3", "verdict": "ATTENTION", "outcome": None, "wrote_driver_line": False},
        ]
        summary = journal.summarize_wave("wave-1", records)
        self.assertEqual(summary["run_id"], "wave-1")
        self.assertEqual(summary["queued"], 3)
        self.assertEqual(summary["green"], 1)
        self.assertEqual(summary["attention"], 1)
        self.assertEqual(summary["red"], 1)
        self.assertEqual(summary["interventions"], 1)
        self.assertEqual(summary["cost_usd_total"], 0.1)
        self.assertEqual(summary["duration_ms_total"], 1000)
        self.assertEqual(summary["client_versions"], ["2.1.220"])
        self.assertEqual(
            summary["verdicts"],
            [{"item_id": "P9.1", "verdict": "GREEN"}, {"item_id": "P9.2", "verdict": "RED"},
             {"item_id": "P9.3", "verdict": "ATTENTION"}])

    def test_no_cost_seen_gives_none_not_zero(self):
        records = [{"item_id": "P9.1", "verdict": "GREEN", "outcome": None,
                   "wrote_driver_line": False}]
        summary = journal.summarize_wave("wave-1", records)
        self.assertIsNone(summary["cost_usd_total"])
        self.assertIsNone(summary["duration_ms_total"])


if __name__ == "__main__":
    unittest.main()
