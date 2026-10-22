"""UTC event windows, follow lifecycle, journal recovery and the conductor crash boundary."""
from __future__ import annotations

import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest import mock

from aicore.ext import events
from orch.conductor import cli, engine, observer, progress
from orch.conductor.application import loop
from orch.conductor.infrastructure.files import RunStore
from tests import test_conductor


class ObserverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.project / "home"),
                                               "SKM_HOME": str(self.project / "home/skm"),
                                               "SKM_AICORE_EVENTS__DELIVERY": "off"})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.project / ".git").mkdir()
        self.store = RunStore(self.project, "cnd-observer")
        self.store.create({"run_id": self.store.run_id, "items": ["W1"]})
        self.directory = self.store.directory
        self.store.save({"status": "finished", "items": {"W1": {"orch_run": "work-first", "steps": {}}}})
        self.progress = progress.Progress(self.store.run_id, self.directory, "quiet",
                                          clock=lambda: "2026-10-20T10:00:00Z")
        self.progress.emit("run.start")
        self.old_tz = os.environ.get("TZ")

    def tearDown(self):
        if self.old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self.old_tz
        if hasattr(time, "tzset"):
            time.tzset()

    def event(self, kind, stamp, *, subject=None, correlation=None):
        events.emit(kind, {}, source=kind.split(".", 1)[0], subject=subject,
                    correlationid=correlation, now=stamp, project=self.project, delivery="off", strict=True)

    def test_build_counts_are_utc_in_both_timezones(self):
        self.progress.clock = lambda: "2026-10-20T10:00:02Z"
        self.progress.emit("run.end", outcome="finished")
        self.event("orch.run.finished", "2026-10-20T10:00:01.000Z", subject="work-first")
        results = []
        for zone in ("America/New_York", "Europe/Astrakhan"):
            os.environ["TZ"] = zone
            time.tzset()
            results.append(observer.build(self.directory, self.project)["events"])
            self.assertEqual(1792490400, observer._seconds("2026-10-20T10:00:00Z"))
        self.assertEqual([{"orch.run.finished": 1}] * 2, results)

    def test_event_window_and_correlations_exclude_other_runs(self):
        self.progress.clock = lambda: "2026-10-20T10:00:02Z"
        self.progress.emit("run.end", outcome="finished")
        for kind in ("orch.agent.failed", "orch.provider.wait", "orch.review.finished", "orch.deviation.recorded"):
            self.event(kind, "2026-10-20T10:00:01.000Z", subject="agent", correlation="work-first")
        self.event("orch.run.finished", "2026-10-20T10:00:00.000Z", subject="work-first")
        self.event("planner.item.closed", "2026-10-20T10:00:02.000Z", correlation=self.store.run_id)
        self.event("orch.run.finished", "2026-10-20T10:00:01.000Z", subject="work-second", correlation="second")
        self.event("orch.run.finished", "2026-10-20T10:00:02.001Z", subject="work-first")
        self.event("orch.run.finished", "2026-10-20T09:59:59.999Z", subject="work-first")
        report = observer.build(self.directory, self.project)
        self.assertEqual({"orch.run.finished": 1, "planner.item.closed": 1, "orch.agent.failed": 1,
                          "orch.provider.wait": 1, "orch.review.finished": 1, "orch.deviation.recorded": 1}, report["events"])
        self.assertEqual([], report["event_problems"])
        self.assertIn("orch.agent.failed", observer.markdown(report))
        state = self.store.load()[1]
        state["ended"] = "2026-10-20T10:00:01.000Z"
        self.store.save(state)
        self.assertNotIn("planner.item.closed", observer.build(self.directory, self.project)["events"])
        state["status"] = "running"
        self.store.save(state)
        self.assertIn("planner.item.closed", observer.build(self.directory, self.project)["events"])

    def test_follow_exits_after_two_dead_probes_without_writing_run_files(self):
        self.progress.emit("stage.start", item="W1", stage="executor.1")
        before = {p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        out = io.StringIO()
        with mock.patch.object(observer.time, "sleep") as sleep:
            self.assertEqual(3, observer.follow(self.directory, stream=out, poll_s=0.01))
        self.assertEqual(1, sleep.call_count)
        self.assertIn("has no live conductor (orphaned)", out.getvalue())
        self.assertIn("orch conduct resume --run cnd-observer", out.getvalue())
        self.assertEqual(before, {p.relative_to(self.directory): p.read_bytes()
                                  for p in self.directory.rglob("*") if p.is_file()})

    def test_follow_waits_for_the_last_resumed_segment(self):
        self.progress.emit("run.end", outcome="stopped")
        self.progress.emit("run.resume")
        self.progress.emit("stage.start", item="W1", stage="executor.1")
        alive = mock.Mock(return_value=True)
        with mock.patch.object(observer.time, "sleep", side_effect=lambda _: self.progress.emit("run.end", outcome="finished")) as sleep:
            self.assertEqual(0, observer.follow(self.directory, stream=io.StringIO(), poll_s=0.01, alive=alive))
        self.assertEqual(1, sleep.call_count)
        self.assertEqual(1, alive.call_count)

    def test_unknown_and_live_probes_reset_the_dead_probe_count(self):
        alive = mock.Mock(side_effect=[False, None, False, True, False, False])
        with mock.patch.object(observer.time, "sleep"):
            self.assertEqual(3, observer.follow(self.directory, stream=io.StringIO(), poll_s=0.01, alive=alive))
        self.assertEqual(6, alive.call_count)

    def test_silence_and_an_unknown_lease_do_not_report_success(self):
        alive = mock.Mock(side_effect=[None, True, False, False])
        with mock.patch.object(observer.time, "sleep"), \
                mock.patch.object(observer.time, "monotonic", side_effect=range(0, 10000, 100)):
            self.assertEqual(3, observer.follow(self.directory, stream=io.StringIO(), poll_s=0.01,
                                               idle_exit_s=0.01, alive=alive))
        self.assertEqual(4, alive.call_count)

    def test_cli_returns_follow_exit_code(self):
        with mock.patch.object(observer, "follow", return_value=3), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(3, cli.main(["--project", str(self.project), "observe", "--run", self.store.run_id, "--follow"]))

    def test_emit_recovers_a_torn_tail_without_losing_the_new_line(self):
        path = self.directory / progress.PROGRESS_FILE
        with path.open("ab") as handle:
            handle.write(b"garbage-no-newline")
        self.progress.emit("run.resume")
        self.assertIn(b"garbage-no-newline\n", path.read_bytes())
        self.assertEqual(["run.start", "run.resume"], [row["event"] for row in progress.read_lines(self.directory)])


class TimezoneHappyPathTests(unittest.TestCase):
    def test_green_happy_path_in_new_york(self):
        old_tz = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "America/New_York"
            time.tzset()
            result = unittest.TestResult()
            test_conductor.HappyPathTests("test_green_at_once_registers_commits_and_reports").run(result)
            self.assertEqual(1, result.testsRun)
            self.assertEqual([], result.errors + result.failures)
        finally:
            if old_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old_tz
            time.tzset()


class CrashTests(test_conductor.ConductorCase):
    def test_completed_segment_counts_subsecond_event_before_end(self):
        stamp = "2026-10-20T10:00:00Z"
        end = datetime.fromisoformat("2026-10-20T10:00:00.900+00:00")
        def pieces(conductor):
            self.assertNotIn("ended", conductor.state)
            events.emit("orch.run.finished", {}, source="orch", subject=conductor.run_id,
                        now="2026-10-20T10:00:00.500Z", project=self.project, delivery="off", strict=True)
        with mock.patch.object(progress, "utc_now", return_value=stamp), \
                mock.patch.object(loop, "datetime") as clock, \
                mock.patch.object(engine.Conductor, "_pieces", autospec=True, side_effect=pieces):
            clock.now.return_value = end
            code, _, err = self.run_items("W1")
            self.assertEqual(0, code, err)
            directory = self.run_dir(err)
            report = json.loads((self.project / engine.REPORTS / directory.name / "observer.json").read_text())
            self.assertEqual({"orch.run.finished": 1}, report["events"])
            self.assertEqual("2026-10-20T10:00:00.900000Z", self.state(err)["ended"])
            self.assertEqual(0, self.conduct("resume", "--run", directory.name)[0])

    def test_observer_failure_does_not_change_the_run_outcome(self):
        with mock.patch.object(engine.Conductor, "_pieces"), \
                mock.patch.object(observer, "write_report", side_effect=RuntimeError("report unavailable")):
            code, _, err = self.run_items("W1")
        self.assertEqual(0, code, err)
        self.assertEqual("finished", self.state(err)["status"])
        self.assertEqual(("finished", None), self.outcome(err))
        self.assertIn("observer report not written", progress.read_lines(self.run_dir(err))[-1]["message"])

    def test_unexpected_exception_closes_the_run_and_redacts_crash(self):
        secret = "observer-fake-sensitive-value"
        with mock.patch.dict(os.environ, {"P36_TEST_SECRET": secret}), \
                mock.patch.object(engine.Conductor, "_pieces", side_effect=RuntimeError(secret)):
            code, _, err = self.run_items("W1")
        self.assertEqual(1, code, err)
        state = self.state(err)
        self.assertEqual(("stopped", "CONDUCTOR_CRASHED"), (state["status"], state["stop"]["code"]))
        directory = self.run_dir(err)
        last = progress.read_lines(directory)[-1]
        self.assertEqual(("run.end", "stopped", "CONDUCTOR_CRASHED"),
                         (last["event"], last["outcome"], last["reason_code"]))
        crash = (directory / "crash.txt").read_text()
        self.assertIn("RuntimeError", crash)
        self.assertIn("Traceback", crash)
        for text in (crash, err, json.dumps(state), (self.project / engine.REPORTS / directory.name / "observer.json").read_text()):
            self.assertNotIn(secret, text)
        with mock.patch.object(engine.Conductor, "_pieces"):
            self.assertEqual(0, self.conduct("resume", "--run", directory.name)[0])

    def test_crash_artifact_failure_still_stops_with_the_original_error(self):
        secret = "observer-fake-sensitive-value"
        before = signal.getsignal(signal.SIGTERM)
        real = Path.write_text

        def guarded(path, data, *args, **kwargs):
            if Path(path).name == "crash.txt":
                raise PermissionError("denied")
            return real(path, data, *args, **kwargs)

        with mock.patch.dict(os.environ, {"P36_TEST_SECRET": secret}), \
                mock.patch.object(engine.Conductor, "_pieces", side_effect=RuntimeError(secret)), \
                mock.patch.object(Path, "write_text", guarded):
            code, _, err = self.run_items("W1")
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)
        self.assertEqual(1, code, err)
        state = self.state(err)
        self.assertEqual(("stopped", "CONDUCTOR_CRASHED"), (state["status"], state["stop"]["code"]))
        self.assertIn("crash.txt unavailable", state["stop"]["message"])
        self.assertNotIn("see crash.txt", state["stop"]["message"])
        self.assertIn("RuntimeError", state["stop"]["message"])
        directory = self.run_dir(err)
        self.assertFalse((directory / "crash.txt").exists())
        last = progress.read_lines(directory)[-1]
        self.assertEqual(("run.end", "stopped", "CONDUCTOR_CRASHED"),
                         (last["event"], last["outcome"], last["reason_code"]))
        for text in (err, json.dumps(state), last["message"],
                     (self.project / engine.REPORTS / directory.name / "observer.json").read_text()):
            self.assertNotIn(secret, text)
        with mock.patch.object(engine.Conductor, "_pieces"):
            self.assertEqual(0, self.conduct("resume", "--run", directory.name)[0])


if __name__ == "__main__":
    unittest.main()
