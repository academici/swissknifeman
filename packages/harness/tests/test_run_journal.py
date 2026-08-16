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


PLAN_ID = "JOURNAL-FIXTURE"


def _outcome(kind, **extra):
    base = {"outcome": kind, "session_id": None, "total_cost_usd": None, "num_turns": None,
           "duration_ms": None, "permission_denials": None, "client_version": None,
           "reason": None}
    base.update(extra)
    return base


class _Plan:
    """Internal documentation."""

    def __init__(self, tmp):
        self.plan_dir = Path(tmp) / PLAN_ID
        self.plan_dir.mkdir(parents=True)

    def entries(self):
        path = self.plan_dir / "journal.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]


class ClassifyTest(unittest.TestCase):
    def test_pre_launch_is_driver_routing_blocked(self):
        category, who = journal.classify(pre_launch=True)
        self.assertEqual(category, "routing-blocked")
        self.assertEqual(who, journal.DRIVER)

    def test_ok_outcome_with_terminal_status_is_worker(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK), item_status="🟢 Done")
        self.assertEqual(category, "ok-terminal")
        self.assertEqual(who, journal.WORKER)

    def test_ok_outcome_with_deviations_status_is_still_worker(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK),
            item_status="🟠 Done with deviations")
        self.assertEqual(who, journal.WORKER)

    def test_ok_outcome_with_blocked_escalation_status_is_worker(self):

        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK), item_status="🔴 Blocked")
        self.assertEqual(who, journal.WORKER)

    def test_ok_outcome_with_non_terminal_status_is_driver_no_op(self):
        category, who = journal.classify(
            pre_launch=False, outcome=_outcome(worker.OUTCOME_OK), item_status="🟡 In progress")
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
                pre_launch=False, outcome=_outcome(kind), item_status="⬜ Not started")
            self.assertEqual(category, kind)
            self.assertEqual(who, journal.DRIVER)

    def test_unknown_outcome_refuses(self):
        with self.assertRaises(journal.JournalWriteRefused):
            journal.classify(pre_launch=False, outcome=_outcome("bogus-outcome"))


class MaybeWriteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plan = _Plan(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_worker_closed_item_gets_no_driver_line(self):
        result = journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.1", run_id="wave-1", attempt=1,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_OK), item_status="🟢 Done",
            monorepo_root=REPO_ROOT)
        self.assertIsNone(result)
        self.assertEqual(self.plan.entries(), [])

    def test_timeout_writes_exactly_one_nonterminal_candidate(self):
        result = journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.1", run_id="wave-1", attempt=1,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_TIMEOUT, reason="30min"),
            item_status="🟡 In progress", monorepo_root=REPO_ROOT)
        self.assertIsNotNone(result)
        entries = self.plan.entries()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["run_id"], "wave-1")
        self.assertEqual(entry["item_id"], "P9.1")
        self.assertEqual(entry["command"], "plan-exec")
        self.assertEqual(entry["result"], "block-candidate")
        self.assertNotIn(entry["result"], ("blocked", "escalated"))
        self.assertTrue(entry["note"].startswith("[wave wave-1]"))

    def test_routing_blocked_writes_routing_rejected_with_friction(self):
        journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.2", run_id="wave-1", attempt=1,
            actor="sonnet/high", pre_launch=True, refusal_detail="EXEC-NOT-PLAN-EXEC",
            monorepo_root=REPO_ROOT)
        entries = self.plan.entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["result"], "routing-rejected")
        self.assertEqual(entries[0]["friction"], ["routing-blocked"])

    def test_worker_failures_are_nonterminal_candidates(self):
        for index, kind in enumerate((
                worker.OUTCOME_TIMEOUT, worker.OUTCOME_TRANSPORT,
                worker.OUTCOME_QUOTA, worker.OUTCOME_ERROR), start=1):
            with self.subTest(kind=kind):
                item_id = f"P8.{index}"
                journal.maybe_write(
                    self.plan.plan_dir, PLAN_ID, item_id, run_id="wave-failures", attempt=1,
                    actor="sonnet/high", outcome=_outcome(kind), item_status="🟡 In progress",
                    monorepo_root=REPO_ROOT)
                entry = self.plan.entries()[-1]
                self.assertEqual(entry["result"], "block-candidate")
                self.assertNotIn(entry["result"], ("blocked", "escalated"))

    def test_no_op_writes_no_op_result_and_friction(self):
        journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.3", run_id="wave-1", attempt=1,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_OK), item_status="⬜ Not started",
            monorepo_root=REPO_ROOT)
        entries = self.plan.entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["result"], "no-op")
        self.assertEqual(entries[0]["friction"], ["no-op"])

    def test_repeat_in_wave_uses_attempt_and_appends_second_line(self):
        journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.4", run_id="wave-1", attempt=1,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_TIMEOUT), item_status="🟡 In progress",
            monorepo_root=REPO_ROOT)
        journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.4", run_id="wave-1", attempt=2,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_TIMEOUT), item_status="🟡 In progress",
            monorepo_root=REPO_ROOT)
        entries = [e for e in self.plan.entries() if e["item_id"] == "P9.4"]
        self.assertEqual(len(entries), 2)
        self.assertEqual([e["attempt"] for e in entries], [1, 2])

    def test_unknown_outcome_refuses_without_calling_cli(self):
        with self.assertRaises(journal.JournalWriteRefused):
            journal.maybe_write(
                self.plan.plan_dir, PLAN_ID, "P9.5", run_id="wave-1", attempt=1,
                actor="sonnet/high", outcome=_outcome("bogus"), item_status="🟡 In progress",
                monorepo_root=REPO_ROOT)
        self.assertEqual(self.plan.entries(), [])

    def test_nonzero_cli_exit_raises_and_stops_wave(self):


        with self.assertRaises(journal.JournalCallFailed):
            journal.maybe_write(
                self.plan.plan_dir, "WRONG-PLAN-ID", "P9.6", run_id="wave-1", attempt=1,
                actor="sonnet/high", outcome=_outcome(worker.OUTCOME_TIMEOUT),
                item_status="🟡 In progress", monorepo_root=REPO_ROOT)

    def test_missing_run_id_is_rejected(self):
        with self.assertRaises(ValueError):
            journal.maybe_write(
                self.plan.plan_dir, PLAN_ID, "P9.7", run_id=None, attempt=1,
                actor="sonnet/high", outcome=_outcome(worker.OUTCOME_TIMEOUT),
                item_status="🟡 In progress", monorepo_root=REPO_ROOT)

    def test_no_two_driver_lines_for_one_item_in_one_wave(self):


        journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.8", run_id="wave-1", attempt=1,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_TIMEOUT), item_status="🟡 In progress",
            monorepo_root=REPO_ROOT)
        by_item = {}
        for entry in self.plan.entries():
            if entry["run_id"] != "wave-1":
                continue
            by_item.setdefault(entry["item_id"], []).append(entry)
        self.assertTrue(all(len(v) <= 1 for v in by_item.values()))

    def test_every_written_line_passes_owner_schema_validation(self):
        journal.maybe_write(
            self.plan.plan_dir, PLAN_ID, "P9.9", run_id="wave-1", attempt=1,
            actor="sonnet/high", outcome=_outcome(worker.OUTCOME_QUOTA), item_status="🟡 In progress",
            monorepo_root=REPO_ROOT)
        proc = subprocess.run(
            [sys.executable, "-c",
            "import json,sys\n"
            "sys.path.insert(0, sys.argv[2])\n"
            "from task.journal import validate_entry\n"
            "[validate_entry(json.loads(l)) for l in open(sys.argv[1]) if l.strip()]\n",
            str(self.plan.plan_dir / "journal.jsonl"),
            str(REPO_ROOT / "packages" / "task" / "lib")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


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
