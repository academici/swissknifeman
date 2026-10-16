"""Debug mode of a run: three layers (machine, project, --debug), default off; the DEBUG_MODE beacon and the journal."""
from __future__ import annotations

import io
import contextlib
from pathlib import Path
import tempfile
import unittest

from orch import settings
from orch.conductor import cli as conductor_cli, debug_mode
from tests.test_settings import SettingsCase


class _Progress:
    def __init__(self):
        self.lines = []

    def emit(self, event, **fields):
        self.lines.append({"event": event, **fields})


class LayerTests(SettingsCase):
    def test_off_by_default(self):
        found = self.load(project=self.project)
        self.assertFalse(found.debug)
        self.assertEqual("defaults", debug_mode.source(found))

    def test_the_machine_turns_it_on(self):
        self.machine("[orch]\ndebug = true\n")
        found = self.load(project=self.project)
        self.assertTrue(found.debug)
        self.assertEqual("machine", debug_mode.source(found))

    def test_the_project_wins_over_the_machine(self):
        self.machine("[orch]\ndebug = true\n")
        self.project_file("[orch]\ndebug = false\n")
        found = self.load(project=self.project)
        self.assertFalse(found.debug)
        self.assertEqual("project", debug_mode.source(found))

    def test_the_flag_wins_over_the_project(self):
        self.project_file("[orch]\ndebug = false\n")
        found = self.load(project=self.project, flags={"debug": True})
        self.assertTrue(found.debug)
        self.assertEqual("flags", debug_mode.source(found))

    def test_the_environment_sets_it_too(self):
        found = self.load(project=self.project, env={**self.env, "SKM_ORCH_DEBUG": "true"})
        self.assertTrue(found.debug)


class AnnounceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run_dir = Path(tmp.name) / "run"
        self.run_dir.mkdir()

    def test_off_says_and_writes_nothing(self):
        progress = _Progress()
        self.assertIsNone(debug_mode.announce(progress, self.run_dir, "r1", settings.defaults()))
        self.assertEqual([], progress.lines)
        self.assertFalse((self.run_dir / debug_mode.FOLDER).exists())

    def test_on_beacons_the_protocol_and_opens_the_journal(self):
        progress = _Progress()
        on = settings.Settings(**{**settings.defaults().__dict__, "debug": True, "resolved": None})
        folder = debug_mode.announce(progress, self.run_dir, "r1", on)
        self.assertEqual([("info", "DEBUG_MODE")], [(line["event"], line["reason_code"]) for line in progress.lines])
        self.assertIn(str(debug_mode.PROTOCOL), progress.lines[0]["message"])
        self.assertTrue(debug_mode.PROTOCOL.is_file())
        self.assertEqual({"journal.md", "metrics.md", "findings.md"}, {path.name for path in folder.iterdir()})
        self.assertEqual(0o700, folder.stat().st_mode & 0o777)

    def test_a_resume_keeps_what_the_observer_wrote(self):
        on = settings.Settings(**{**settings.defaults().__dict__, "debug": True, "resolved": None})
        folder = debug_mode.announce(_Progress(), self.run_dir, "r1", on)
        (folder / "journal.md").write_text("my notes\n", encoding="utf-8")
        debug_mode.announce(_Progress(), self.run_dir, "r1", on)
        self.assertEqual("my notes\n", (folder / "journal.md").read_text(encoding="utf-8"))


class FlagTests(unittest.TestCase):
    def test_run_and_resume_take_debug_and_no_debug(self):
        for verb in ("run", "resume"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                conductor_cli.main([verb, "--help"])
            self.assertIn("--debug, --no-debug", out.getvalue())


if __name__ == "__main__":
    unittest.main()
