"""The files of a run survive a crash and say clearly when they did not: JSON is replaced through a unique temporary
file with fsync, a torn or foreign file stops with ``STATE_CORRUPT`` naming it, and the run folders are the owner's only."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest import mock

from orch import settings
from orch.conductor import checks, engine, progress
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import files


class DurableStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_concurrent_writers_of_one_file_never_leave_a_torn_or_temporary_file(self):
        target = self.root / "state.json"
        errors = []

        def write(n: int) -> None:
            try:
                for i in range(30):
                    files.write_json(target, {"writer": n, "i": i, "pad": "x" * 2000})
            except Exception as error:  # noqa: BLE001 - the test collects any failure of a thread
                errors.append(error)

        threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(set(files.read_json(target)), {"writer", "i", "pad"})
        self.assertEqual([path.name for path in self.root.iterdir()], ["state.json"])

    def test_a_torn_file_stops_with_state_corrupt_naming_it(self):
        target = self.root / "state.json"
        target.write_text('{"steps": {', encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            files.read_json(target)
        self.assertEqual(caught.exception.code, "STATE_CORRUPT")
        self.assertIn(str(target), str(caught.exception))
        self.assertIsNone(files.read_json(self.root / "missing.json"))

    def test_a_symlinked_target_is_refused(self):
        real = self.root / "real.json"
        real.write_text("{}", encoding="utf-8")
        (self.root / "state.json").symlink_to(real)
        with self.assertRaises(OSError):
            files.write_json(self.root / "state.json", {"a": 1})
        self.assertEqual(real.read_text(encoding="utf-8"), "{}")

    def test_the_run_folders_are_private(self):
        store = files.RunStore(self.root, "cnd-1")
        store.directory = self.root / "conductor" / "cnd-1"
        store.create({"run_id": "cnd-1"})
        for folder in (store.directory, store.directory.parent):
            self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)

    def step_run(self):
        run = engine.Conductor(project=self.root, settings=settings.load(project=self.root), mode="quiet")
        state = {"items": {"W1": {"steps": {}}}}
        run._open("cnd-step", {"items": ["W1"]}, state)
        item = Item("W1", "work-run", state["items"]["W1"], run.directory / "W1", {"attempt_id": "att-1"})
        return run, item

    def test_started_is_durable_before_event_and_work_and_done_keeps_its_old_shape(self):
        run, item = self.step_run()
        seen = []
        emit = run.progress.emit
        def started(event, **fields):
            if event == "stage.start":
                row = files.read_json(run.directory / "state.json")["items"]["W1"]["steps"]["executor.1"]
                self.assertEqual(row["status"], "started")
                seen.append(row)
            return emit(event, **fields)
        def work():
            self.assertEqual(len(seen), 1)
            return {"report": {"status": "done"}}  # records/v1: an executor result carries its stage-report
        with mock.patch.object(checks, "head", return_value="base"), mock.patch.object(run.progress, "emit", started):
            run._step(item, "executor.1", work, role="executor", route="fake/model")
        self.assertEqual(seen[0], {"status": "started", "started_at": seen[0]["started_at"], "role": "executor",
                                   "route": "fake/model", "base_head": "base", "attempt": "att-1", "dirty_before": None})
        row = item.state["steps"]["executor.1"]
        self.assertEqual(set(row), {"status", "result", "verdict", "role", "route", "duration_s", "ended"})
        self.assertEqual(row["status"], "done")

    def test_stop_is_saved_before_propagation_and_resume_repeats_without_interruption(self):
        run, item = self.step_run()
        def work():
            raise Stop("TIMEOUT", "fake stop")
        with self.assertRaises(Stop):
            run._step(item, "executor.1", work)
        row = files.read_json(run.directory / "state.json")["items"]["W1"]["steps"]["executor.1"]
        self.assertEqual(row, {"status": "stopped", "code": "TIMEOUT", "ended": row["ended"]})
        run._reconcile_interrupted()
        done = {"report": {"status": "done"}}
        self.assertEqual(run._step(item, "executor.1", lambda: done), done)
        self.assertNotIn("STAGE_INTERRUPTED", [line.get("reason_code") for line in progress.read_lines(run.directory)])

    def test_unexpected_failure_cannot_leave_a_done_result(self):
        run, item = self.step_run()
        with self.assertRaises(RuntimeError):
            run._step(item, "prepare", mock.Mock(side_effect=RuntimeError("crash")))
        row = files.read_json(run.directory / "state.json")["items"]["W1"]["steps"]["prepare"]
        self.assertEqual(row["status"], "started")
        self.assertIsNone(row["base_head"])
        self.assertNotIn("result", row)


class PathSafetyTests(unittest.TestCase):
    def test_a_reference_of_dots_never_names_a_parent_folder(self):
        self.assertEqual([files.safe(text) for text in ("..", ".", "...", "../x", "P1.2")], ["x", "x", "x", "..-x", "P1.2"])

    def test_a_run_id_that_is_a_path_is_refused(self):
        for run_id in ("../other", "a/b", "", ".."):
            with self.subTest(run_id=run_id), self.assertRaises(Stop) as caught:
                files.RunStore(Path("/tmp"), run_id)
            self.assertEqual(caught.exception.code, "RUN_UNKNOWN")
        self.assertEqual(files.RunStore(Path("/tmp"), "cnd-20261016T000000Z-abc123").run_id, "cnd-20261016T000000Z-abc123")


if __name__ == "__main__":
    unittest.main()
