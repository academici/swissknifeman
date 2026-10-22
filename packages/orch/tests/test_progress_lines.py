"""Progress lines against ``conductor/v1`` ``progress-line``: PROGRESS_LINE_INVALID, the sidecar, the counted reads and
``discarded_lines`` of the observer report."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch.conductor import observer, progress, records
from orch.conductor.infrastructure.files import RunStore

TS = "2026-10-20T10:00:00Z"


class ProgressCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        patcher = mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.progress = progress.Progress("cnd-lines", self.directory, "quiet", clock=lambda: TS)

    def journal(self) -> list:
        return [json.loads(row) for row in (self.directory / "progress.jsonl").read_text(encoding="utf-8").splitlines()]

    def sidecar(self) -> list:
        return [json.loads(row) for row in (self.directory / "progress.invalid.jsonl").read_text(encoding="utf-8").splitlines()]


class InvalidLineTests(ProgressCase):
    def test_a_valid_line_is_written_as_before_and_leaves_no_sidecar(self):
        line = self.progress.emit("info", reason_code="STAGE_SLOW", item="W1", message="slow")
        self.assertEqual(self.journal(), [line])
        self.assertEqual(line["event"], "info")
        self.assertFalse((self.directory / "progress.invalid.jsonl").exists())

    def test_a_line_with_an_unknown_field_goes_to_the_sidecar_and_the_journal_gets_the_info_line(self):
        returned = self.progress.emit("info", message="x", surprise=1)
        self.assertEqual(self.sidecar(), [{"event": "info", "message": "x", "run": "cnd-lines", "surprise": 1, "ts": TS}])
        self.assertEqual(self.journal(), [returned])
        self.assertEqual((returned["event"], returned["reason_code"]), ("info", "PROGRESS_LINE_INVALID"))
        self.assertEqual(returned["message"], "info: /surprise: unexpected property 'surprise'")
        self.assertEqual(progress.read_lines(self.directory), [returned])  # the replacement is a valid line

    def test_an_unknown_event_and_a_bad_time_are_caught_too(self):
        self.progress.emit("item.started", item="W1")
        self.progress.clock = lambda: "yesterday"
        self.progress.emit("run.start")
        self.assertEqual([row["event"] for row in self.sidecar()], ["item.started", "run.start"])
        lines = self.journal()
        self.assertEqual([row["reason_code"] for row in lines], ["PROGRESS_LINE_INVALID"] * 2)
        self.assertEqual(lines[1]["ts"][-1], "Z")  # a broken time is replaced by the clock of the process
        self.assertEqual(len(progress.read_lines(self.directory)), 2)

    def test_the_message_names_the_event_and_is_at_most_500_characters(self):
        self.progress.emit("info", **{"x" * 600: 1})
        message = self.journal()[0]["message"]
        self.assertTrue(message.startswith("info: "), message)
        self.assertLessEqual(len(message), 500)

    def test_the_text_mode_prints_the_replacement_line(self):
        out = io.StringIO()
        shown = progress.Progress("cnd-lines", self.directory, "text", stream=out, clock=lambda: TS)
        shown.emit("info", surprise=1)
        self.assertIn("PROGRESS_LINE_INVALID", out.getvalue())
        self.assertNotIn("surprise=1", out.getvalue())

    def test_an_unwritable_sidecar_does_not_stop_the_run(self):
        (self.directory / "progress.invalid.jsonl").mkdir()  # opening a directory for append fails
        returned = self.progress.emit("info", surprise=1)
        self.assertEqual(returned["reason_code"], "PROGRESS_LINE_INVALID")
        self.assertEqual(self.journal(), [returned])

    def test_a_field_with_mixed_key_types_is_quarantined_and_does_not_stop_the_run(self):
        returned = self.progress.emit("info", surprise={1: "one", "two": 2})
        self.assertEqual(returned["reason_code"], "PROGRESS_LINE_INVALID")
        self.assertEqual(self.journal(), [returned])
        [kept] = self.sidecar()
        self.assertEqual(kept["surprise"], {"1": "one", "two": 2})  # the original data, as JSON
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            with self.assertRaises(ValueError):
                self.progress.emit("info", surprise={1: "one", "two": 2})

    def test_a_field_json_cannot_hold_is_quarantined_as_text(self):
        returned = self.progress.emit("info", surprise=object())
        self.assertEqual(returned["reason_code"], "PROGRESS_LINE_INVALID")
        [kept] = self.sidecar()
        self.assertIn("object object", kept["surprise"])

    def test_a_line_that_cannot_be_serialized_at_all_is_kept_as_text(self):
        loop: list = []
        loop.append(loop)
        text = progress._quarantine_text({"event": "info", "surprise": loop})
        self.assertIn("unserializable", json.loads(text))

    def test_strict_mode_raises_and_writes_nothing(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            with self.assertRaises(ValueError) as caught:
                self.progress.emit("info", surprise=1)
        self.assertIn("PROGRESS_LINE_INVALID", str(caught.exception))
        self.assertFalse((self.directory / "progress.jsonl").exists())
        self.assertFalse((self.directory / "progress.invalid.jsonl").exists())

    def test_every_step_key_the_conductor_uses_is_a_valid_stage(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            for key in ("brief", "prepare", "scout", "research.1", "executor.2", "executor.1-q1", "checks.1", "review.3",
                        "triage.3", "triage.3-a", "advice.1", "close", "register", "commit"):
                with self.subTest(stage=key):
                    self.progress.emit("info", stage=key, message="x")

    def test_strict_mode_accepts_every_valid_line(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            self.progress.emit("run.start", message="plan x")
            self.progress.emit("stage.end", item="W1", stage="executor.1", role="executor", route="a/b/c", verdict="done",
                               duration_s=1.5, tokens={"input": 1, "output": 2})
        self.assertEqual(len(self.journal()), 2)


class ReadTests(ProgressCase):
    def write(self, *rows: str, end: str = "\n") -> None:
        (self.directory / "progress.jsonl").write_text("\n".join(rows) + end, encoding="utf-8")

    def good(self, event="info", **fields) -> str:
        return json.dumps({"ts": TS, "run": "cnd-lines", "event": event, **fields})

    def test_a_missing_journal_is_empty(self):
        self.assertEqual(progress.read_lines_counted(self.directory), ([], 0))

    def test_valid_lines_are_kept_and_the_others_counted(self):
        self.write(self.good("run.start"), "not json", json.dumps([1]), json.dumps({"ts": TS, "event": "info"}),
                   json.dumps({"ts": TS, "run": "cnd-lines", "event": "info", "extra": 1}), self.good("run.end"))
        lines, discarded = progress.read_lines_counted(self.directory)
        self.assertEqual([row["event"] for row in lines], ["run.start", "run.end"])
        self.assertEqual(discarded, 4)
        self.assertEqual(progress.read_lines(self.directory), lines)

    def test_a_torn_last_line_is_not_counted_and_a_blank_line_is_not_a_line(self):
        self.write(self.good("run.start"), "", '{"ts": "2026-10-2', end="")
        self.assertEqual(progress.read_lines_counted(self.directory), ([json.loads(self.good("run.start"))], 0))

    def test_a_valid_last_line_without_a_newline_is_kept(self):
        self.write(self.good("run.start"), self.good("run.end"), end="")
        self.assertEqual(len(progress.read_lines(self.directory)), 2)

    def test_a_torn_line_that_a_later_write_completed_is_counted(self):
        self.write(self.good("run.start"), '{"ts": "2026-10-2', end="")
        self.progress.emit("run.end", outcome="finished")  # the writer ends the torn line, then appends
        lines, discarded = progress.read_lines_counted(self.directory)
        self.assertEqual(([row["event"] for row in lines], discarded), (["run.start", "run.end"], 1))

    def test_the_quarantined_lines_are_counted_apart(self):
        self.assertEqual(progress.quarantined(self.directory), 0)
        self.progress.emit("info", surprise=1)
        self.progress.emit("info", surprise=2)
        self.assertEqual(progress.quarantined(self.directory), 2)

    def test_summarize_does_not_see_a_line_without_a_time(self):
        self.write(self.good("run.start"), json.dumps({"run": "cnd-lines", "event": "run.end", "outcome": "finished"}))
        self.assertEqual(progress.summarize(progress.read_lines(self.directory))["status"], "running")


class ObserverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        patcher = mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "", "HOME": str(self.project / "home"),
                                               "SKM_HOME": str(self.project / "home/skm"),
                                               "SKM_AICORE_EVENTS__DELIVERY": "off"})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.project / ".git").mkdir()
        self.store = RunStore(self.project, "cnd-observer")
        self.store.create({"run_id": self.store.run_id, "items": []})
        self.store.save({"status": "finished", "items": {}})
        self.directory = self.store.directory
        self.progress = progress.Progress(self.store.run_id, self.directory, "quiet", clock=lambda: TS)
        self.progress.emit("run.start")

    def test_a_clean_journal_has_no_count(self):
        self.assertNotIn("discarded_lines", observer.build(self.directory, self.project))

    def test_the_report_counts_quarantined_and_unreadable_lines(self):
        self.progress.emit("info", surprise=1)  # quarantined when written, replaced by PROGRESS_LINE_INVALID
        with open(self.directory / "progress.jsonl", "a", encoding="utf-8") as handle:
            handle.write("not json\n" + json.dumps({"ts": TS, "event": "info"}) + "\n")
        report = observer.build(self.directory, self.project)
        self.assertEqual(report["discarded_lines"], 3)
        self.assertEqual(report["beacons"], {"PROGRESS_LINE_INVALID": 1})
        self.assertEqual(records.problems(report, "observer-report"), [])
        self.assertIn("Discarded progress lines: 3", observer.markdown(report))

    def test_write_report_stores_the_count_through_records(self):
        self.progress.emit("info", surprise=1)
        target = self.project / "reports"
        observer.write_report(self.directory, self.project, target)
        stored = records.read(target / "observer.json", "observer-report")
        self.assertEqual(stored["discarded_lines"], 1)
        self.assertEqual(stat_mode(target / "observer.json"), 0o600)


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


class ReportSchemaTests(unittest.TestCase):
    EXAMPLES = Path(__file__).resolve().parents[1] / "schemas" / "records" / "v1" / "examples"

    def load(self, group: str, name: str) -> dict:
        return json.loads((self.EXAMPLES / group / "observer-report" / name).read_text(encoding="utf-8"))

    def test_a_report_without_the_field_is_still_valid(self):
        report = self.load("valid", "resumed-run.json")
        self.assertNotIn("discarded_lines", report)
        self.assertEqual(records.problems(report, "observer-report"), [])

    def test_a_report_with_the_field_is_valid(self):
        report = self.load("valid", "discarded-lines.json")
        self.assertEqual(report["discarded_lines"], 2)
        self.assertEqual(records.problems(report, "observer-report"), [])

    def test_a_negative_or_text_count_is_refused(self):
        report = self.load("invalid", "minimum-discarded-lines-negative.json")
        self.assertEqual(report["discarded_lines"], -1)
        self.assertNotEqual(records.problems(report, "observer-report"), [])
        report["discarded_lines"] = "2"
        self.assertNotEqual(records.problems(report, "observer-report"), [])


if __name__ == "__main__":
    unittest.main()
