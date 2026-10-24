"""The metrics of every piece in the observer report (P8.6): synthetic run folders, no provider, no debug, no raw stream."""
from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch.conductor import agents, observer, records
from orch.conductor.infrastructure.files import RUN_FILE, runs_root

RUN = "cnd-20261025T100000Z-a1b2c3"
EXAMPLES = Path(__file__).resolve().parents[1] / "schemas" / "records" / "v1" / "examples" / "valid" / "observer-report"


def line(ts: str, event: str, **fields) -> dict:
    return {"ts": f"2026-10-25T{ts}Z", "event": event, "run": RUN, **fields}


def stage(item: str, key: str, start: str, end: str, seconds: float, role: str = "deterministic", **extra) -> list:
    return [line(start, "stage.start", item=item, stage=key, role=role),
            line(end, "stage.end", item=item, stage=key, role=role, duration_s=seconds, **extra)]


def action(at: str, health: str, reason_code=None, kind: str = "notify") -> dict:
    return {"$schema": records.TAGS["supervisor-action"][1], "at": f"2026-10-25T{at}Z", "run_id": RUN, "health": health,
            "reason_code": reason_code, "action": kind, "detail": f"{health} seen"}


# executor ×2, checks ×2, review ×1, triage ×1, one healed result, one slow-stage beacon
JOURNAL = [line("10:00:00", "run.start"), line("10:00:01", "item.start", item="W1"),
           *stage("W1", "executor.1", "10:00:02", "10:05:02", 300, role="executor"),
           line("10:05:03", "info", item="W1", stage="executor.1", role="executor", reason_code="RESULT_HEALED",
                message="dropped a trailing comma"),
           *stage("W1", "checks.1", "10:05:04", "10:06:04", 60, verdict="red V1"),
           *stage("W1", "executor.2", "10:06:05", "10:08:05", 120, role="executor"),
           *stage("W1", "checks.2", "10:08:06", "10:09:06", 60, verdict="green"),
           *stage("W1", "review.1", "10:09:07", "10:11:07", 120, role="reviewer"),
           line("10:11:08", "info", item="W1", stage="review.1", reason_code="STAGE_SLOW", message="slow"),
           *stage("W1", "triage.1", "10:11:09", "10:11:39", 30, role="triager"),
           line("10:12:00", "item.end", item="W1", outcome="done"),
           line("10:12:01", "run.end")]

def finding(number: int, severity: str) -> dict:
    return {"id": f"F{number}", "severity": severity, "confidence": "high", "location": "lib/x.py:1",
            "failure_scenario": "a wrong outcome", "basis": "correctness"}


STATE = {"status": "finished", "items": {"W1": {
    "outcome": "done", "deviation_ids": ["edited docs/x.md outside the write set"],
    "steps": {"review.1": {"status": "done", "result": {"findings": {
                  "verdict": "ATTENTION", "findings": [finding(1, "Major"), finding(2, "Minor")]}}},
              "triage.1": {"status": "done", "result": {"triage": {
                  "confirmed": [{"finding": "F1", "fix": "fix it",
                                 "reproduction": {"cmd": "python3 x.py", "exit": 1, "observed": "boom"}}],
                  "rejected": [{"finding": "F2", "reason": "already covered"}]}}}}}}}


class MetricsCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(os.path.realpath(temporary.name))
        (self.project / ".git").mkdir()
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.project / "home"), "SKM_HOME": str(self.project / "home/skm"),
                                               "SKM_AICORE_EVENTS__DELIVERY": "off"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_dir(self, journal=JOURNAL, state=STATE, actions=()) -> Path:
        directory = runs_root(self.project) / RUN
        directory.mkdir(parents=True)
        (directory / RUN_FILE).write_text(json.dumps({"items": ["W1"]}), encoding="utf-8")
        (directory / "progress.jsonl").write_text("".join(json.dumps(doc) + "\n" for doc in journal), encoding="utf-8")
        (directory / "state.json").write_text(json.dumps(state), encoding="utf-8")
        if actions:
            (directory / "supervisor.jsonl").write_text("".join(json.dumps(doc) + "\n" for doc in actions), encoding="utf-8")
        for number, (step, role, usage) in enumerate((("executor.1", "executor", (1000, 5000, 100)),
                                                      ("executor.2", "executor", (400, 6000, 50)),
                                                      ("review.1", "reviewer", (300, 0, 40))), 1):
            handle = agents.start(directory / "W1", agents.agent_id(RUN, number), role=role, route={"provider": "codex"},
                                  step=step, attempt=1, prompt=f"W1/prompts/{step}.md", parent=None,
                                  started_at="2026-10-25T10:00:02Z")
            agents.add_usage(handle, dict(zip(("input", "cached", "output"), usage)))
            agents.finish(handle, exit_code=0, error=None, decisions=[], duration_s=1.0, stream=None, lingered=False)
        return directory

    def row(self, directory: Path) -> dict:
        found = observer.item_metrics(directory)["items"]
        self.assertEqual(["W1"], [row["item"] for row in found])
        return found[0]


class ItemMetricsTests(MetricsCase):
    def test_a_known_run_gives_the_expected_numbers(self):  # (a)
        row = self.row(self.run_dir())
        self.assertEqual(719.0, row["wall_s"])  # item.start 10:00:01 → item.end 10:12:00
        self.assertEqual({"checks": 120.0, "executor": 420.0, "review": 120.0, "triage": 30.0}, row["active_s"])
        self.assertEqual(0.17, row["checks_share"])
        self.assertEqual({"executor": 2, "review": 1, "checks": 2}, row["rounds"])
        self.assertEqual(0, row["resume_repeats"])
        self.assertEqual({"healed": 1, "repaired": 0, "unrepairable": 0}, row["heal"])
        self.assertEqual({"RESULT_HEALED": 1, "STAGE_SLOW": 1}, row["beacons"])
        self.assertEqual({"input": 1700, "cached": 11000, "output": 190}, row["tokens"])
        self.assertEqual(1, row["deviations"])
        self.assertEqual({"confirmed": 1, "rejected": 1, "by_severity": {"Major": 1, "Minor": 1}}, row["findings"])
        self.assertEqual([], row["health_transitions"])

    def test_without_debug_the_report_carries_the_metrics_and_they_read_back(self):  # (b)
        directory = self.run_dir()
        target = self.project / "reports"
        written = observer.write_report(directory, self.project, target)
        self.assertFalse((directory / "debug").exists())
        doc = records.read(Path(written["json"]), "observer-report")
        self.assertEqual(self.row(directory), doc["metrics"]["items"][0])
        markdown = Path(written["markdown"]).read_text(encoding="utf-8")
        self.assertIn("## Item metrics", markdown)
        self.assertIn("| W1 | 719.0 | checks 120.0, executor 420.0, review 120.0, triage 30.0 | 17 % | 2/1/2 | 0 | 1/0/0 |",
                      markdown)

    def test_supervisor_transitions_are_health_transitions_of_the_piece_it_was_on(self):  # (c)
        actions = [action("10:05:30", "suspected_stall", "STALL_SUSPECTED"),
                   action("10:05:40", "suspected_stall", "STALL_SUSPECTED"),  # no change: no transition
                   action("10:07:00", "running"),
                   action("10:12:00", "finished", kind="busy")]  # the piece ended at that line: the run's only
        report = observer.item_metrics(self.run_dir(actions=actions))
        self.assertEqual([("suspected_stall", None), ("running", "suspected_stall"), ("finished", "running")],
                         [(step["to"], step["from"]) for step in report["health_transitions"]])
        self.assertEqual([{"at": "2026-10-25T10:05:30Z", "from": None, "to": "suspected_stall",
                           "reason_code": "STALL_SUSPECTED", "action": "notify"},
                          {"at": "2026-10-25T10:07:00Z", "from": "suspected_stall", "to": "running",
                           "reason_code": None, "action": "notify"}],
                         report["items"][0]["health_transitions"])

    def test_a_line_that_is_not_a_supervisor_action_is_left_out(self):
        directory = self.run_dir(actions=[action("10:05:30", "hung", "HEARTBEAT_STALE")])
        with (directory / "supervisor.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("not json\n" + json.dumps({"at": "2026-10-25T10:06:00Z", "health": "running"}) + "\n")
        self.assertEqual(["hung"], [step["to"] for step in observer.item_metrics(directory)["health_transitions"]])

    def test_a_resume_sums_the_wall_time_of_each_process_and_counts_repeated_steps(self):
        journal = [line("10:00:00", "run.start"), line("10:00:01", "item.start", item="W1"),
                   line("10:00:02", "stage.start", item="W1", stage="executor.1", role="executor"),
                   line("10:01:01", "info", item="W1", stage="executor.1", reason_code="STAGE_IDLE", message="idle"),
                   line("13:00:00", "run.resume"),  # three hours of a dead conductor are not the piece's time
                   line("13:00:01", "stage.start", item="W1", stage="executor.1", role="executor"),
                   line("13:02:01", "stage.end", item="W1", stage="executor.1", role="executor", duration_s=120),
                   line("13:02:02", "stage.start", item="W1", stage="checks.1"),
                   line("13:03:02", "stage.end", item="W1", stage="checks.1", duration_s=60, verdict="green"),
                   line("13:03:03", "item.end", item="W1", outcome="done")]
        row = self.row(self.run_dir(journal=journal, state={"status": "finished", "items": {"W1": {"outcome": "done"}}}))
        self.assertEqual(60.0 + 182.0, row["wall_s"])
        self.assertEqual(1, row["resume_repeats"])
        self.assertEqual({"executor": 1, "review": 0, "checks": 1}, row["rounds"])
        self.assertEqual(0, row["deviations"])

    def test_no_raw_stream_is_opened(self):
        directory = self.run_dir()
        streams = directory / "W1" / "streams"
        streams.mkdir()
        (streams / "executor.1.jsonl").write_text("{}\n", encoding="utf-8")
        opened = []
        real_open, real_io_open = builtins.open, io.open

        def spy(real):
            def wrapper(file, *args, **kwargs):
                opened.append(str(file))
                return real(file, *args, **kwargs)
            return wrapper

        with mock.patch("builtins.open", spy(real_open)), mock.patch("io.open", spy(real_io_open)):
            observer.build(directory, self.project)
        self.assertTrue(any(name.endswith("progress.jsonl") for name in opened))
        self.assertEqual([], [name for name in opened if f"{os.sep}streams{os.sep}" in name])


class CompatibilityTests(MetricsCase):
    def test_a_report_written_before_the_metrics_still_reads(self):
        for name in ("resumed-run.json", "slow-run-with-agents.json"):
            old = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
            self.assertNotIn("metrics", old)
            path = self.project / name
            path.write_text(json.dumps(old), encoding="utf-8")
            self.assertEqual(old["run"], records.read(path, "observer-report")["run"])

    def test_a_report_with_a_broken_metrics_row_is_refused(self):
        doc = json.loads((EXAMPLES / "item-metrics.json").read_text(encoding="utf-8"))
        self.assertEqual([], records.problems(doc, "observer-report"))
        del doc["metrics"]["items"][0]["rounds"]
        self.assertTrue(records.problems(doc, "observer-report"))

    def test_the_report_is_rebuilt_after_a_resume(self):
        directory = self.run_dir()
        target = self.project / "reports"
        observer.write_report(directory, self.project, target)
        with (directory / "progress.jsonl").open("a", encoding="utf-8") as handle:
            for doc in (line("11:00:00", "run.resume"), line("11:00:01", "item.start", item="W1"),
                        *stage("W1", "executor.1", "11:00:02", "11:01:02", 60, role="executor"),
                        line("11:01:03", "item.end", item="W1", outcome="done")):
                handle.write(json.dumps(doc) + "\n")
        observer.write_report(directory, self.project, target)
        row = records.read(target / "observer.json", "observer-report")["metrics"]["items"][0]
        self.assertEqual({"executor": 3, "review": 1, "checks": 2}, row["rounds"])
        self.assertEqual(1, row["resume_repeats"])
        self.assertEqual(719.0 + 62.0, row["wall_s"])


if __name__ == "__main__":
    unittest.main()
