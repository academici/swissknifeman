"""T7 (P12.3): a secret in the environment of a role or in its stderr is in no progress line, no event, no report of the
observer and no error of the role; the raw streams (``streams/``) are the one place that keeps what the role printed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest import mock

from aicore.ext import events as journal
from orch.conductor import observer, process as role_process
from orch.conductor.progress import Progress
from orch import events as orch_events
from tests.test_conductor import ConductorCase, GREEN, executor_ok

KNOWN = "known-value-7f3a9c2e51"          # the value of an environment variable named like a secret
TOKEN = "ghp_" + "Z9y8X7w6V5u4T3s2R1q0" * 2  # an explicit token format the role printed on its own
FAILING = {"stderr": f"boom: the key {KNOWN} and {TOKEN} were rejected\n", "exit": 1, "text": "x"}


def files_with(root: Path, needles, skip=("streams",)) -> list:
    """The files under ``root`` (outside the raw ``skip`` folders) that hold any of ``needles``."""
    found = []
    for path in root.rglob("*"):
        if path.is_file() and not set(skip) & set(path.relative_to(root).parts):
            data = path.read_bytes().decode("utf-8", errors="replace")
            if any(needle in data for needle in needles):
                found.append(str(path.relative_to(root)))
    return found


class LeakTests(ConductorCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"SKM_TEST_API_TOKEN": KNOWN})
        patcher.start()
        self.addCleanup(patcher.stop)

    def failing_run(self) -> tuple:
        self.script({"executor": [FAILING] * 4, "reviewer": [GREEN]})
        code, out, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        return err, self.run_dir(err)

    def test_the_failure_of_a_role_leaks_into_no_progress_line_and_no_agent_record(self):
        err, run = self.failing_run()
        self.assertNotIn(KNOWN, err)
        self.assertNotIn(TOKEN, err)
        self.assertEqual(files_with(run, (KNOWN, TOKEN)), [])
        self.assertIn("boom", (run / "progress.jsonl").read_text(encoding="utf-8"))  # the line is there, masked

    def test_the_events_hold_no_secret(self):
        err, run = self.failing_run()
        stored, problems = journal.read_events(self.project)
        self.assertEqual(problems, [])
        self.assertTrue(stored)
        self.assertEqual([e.type for e in stored if KNOWN in json.dumps(e.data) or TOKEN in json.dumps(e.data)], [])
        self.assertEqual(files_with(self.project / ".swissknifeman", (KNOWN, TOKEN)), [])

    def test_the_observer_report_holds_no_secret(self):
        err, run = self.failing_run()
        target = self.project.parent / "report"
        observer.write_report(run, self.project, target)
        self.assertEqual(files_with(target, (KNOWN, TOKEN)), [])


class UnitTests(unittest.TestCase):
    def test_progress_masks_every_text_field_and_keeps_the_rest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SKM_TEST_API_TOKEN": KNOWN}):
            line = Progress("cnd-1", Path(tmp), mode="quiet").emit(
                "info", message=f"failed {TOKEN}", detail=f"exit 1: {KNOWN}", item="W1", tokens={"input": 1, "output": 2})
            text = (Path(tmp) / "progress.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(KNOWN, text + json.dumps(line))
        self.assertNotIn(TOKEN, text + json.dumps(line))
        self.assertEqual((line["item"], line["tokens"]), ("W1", {"input": 1, "output": 2}))

    def test_a_role_failure_detail_is_masked_at_its_source(self):
        import sys
        import tempfile
        script = f"import sys; sys.stderr.write({FAILING['stderr']!r}); sys.exit(1)"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SKM_TEST_API_TOKEN": KNOWN}):
            run = role_process.run_role([sys.executable, "-c", script], "", transport="text", cwd=Path(tmp),
                                        timeout_s=20, raw_path=Path(tmp) / "streams" / "x.txt")
        self.assertEqual(run.error, "ROLE_FAILED")
        self.assertNotIn(KNOWN, run.detail)
        self.assertNotIn(TOKEN, run.detail)
        self.assertIn("boom", run.detail)

    def test_event_data_is_masked_before_it_is_journaled(self):
        import tempfile
        from orch import settings
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / "skm").mkdir(parents=True)
            env = {"HOME": str(home), "SKM_HOME": str(home / "skm"), "SKM_AICORE_EVENTS__DELIVERY": "off",
                   "SKM_TEST_API_TOKEN": KNOWN}
            with mock.patch.dict(os.environ, env):
                base = settings.defaults()
                enabled = settings.Settings(**{**base.__dict__, "events_enabled": True})
                orch_events.emit("orch.work.blocked", {"run_id": "r1", "work_id": f"w-{KNOWN}", "code": "X"},
                                 subject="r1/W1", settings=enabled)
                stored, _ = journal.read_events()
        self.assertEqual(len(stored), 1)
        self.assertNotIn(KNOWN, json.dumps(stored[0].data))
        self.assertIn("‹redacted›", json.dumps(stored[0].data, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
