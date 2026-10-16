"""Tests Env.state_dir: the machine state directory (aicore.state) with the legacy ~/.swissknifeman/analyst."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore import state

from analyst.common import Env

LEGACY_ENV = ("SKM_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")


class TestStateLocation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()
        self.warnings = []
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        for name in LEGACY_ENV:
            os.environ.pop(name, None)
        state.locations._WARNED.clear()
        self.addCleanup(state.locations._WARNED.clear)
        self.env = Env("/tmp/analyst-root", "doctor", home=self.home)
        self.new = self.home / ".local" / "state" / "swissknifeman" / "analyst"
        self.legacy = self.home / ".swissknifeman" / "analyst"

    def state_dir(self):
        import io
        from contextlib import redirect_stderr
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            path = self.env.state_dir
        self.warnings = [line for line in buffer.getvalue().splitlines() if line]
        return path

    def test_nothing_exists_uses_the_new_place_silently(self):
        self.assertEqual(self.new, self.state_dir())
        self.assertEqual([], self.warnings)

    def test_only_legacy_is_used_with_one_warning(self):
        self.legacy.mkdir(parents=True)
        self.assertEqual(self.legacy, self.state_dir())
        self.assertEqual(1, len(self.warnings))
        self.assertIn("legacy location", self.warnings[0])
        self.assertIn(str(self.legacy), self.warnings[0])
        self.assertEqual(self.legacy, self.state_dir())
        self.assertEqual([], self.warnings)  # once per process

    def test_new_place_wins_without_warning(self):
        self.legacy.mkdir(parents=True)
        self.new.mkdir(parents=True)
        self.assertEqual(self.new, self.state_dir())
        self.assertEqual([], self.warnings)

    def test_skm_home_ignores_legacy(self):
        self.legacy.mkdir(parents=True)
        os.environ["SKM_HOME"] = str(self.home / "sandbox")
        self.assertEqual(self.home / "sandbox" / "state" / "analyst", self.state_dir())
        self.assertEqual([], self.warnings)

    def test_xdg_state_home_is_honoured(self):
        os.environ["XDG_STATE_HOME"] = str(self.home / "xdg")
        self.assertEqual(self.home / "xdg" / "swissknifeman" / "analyst", self.state_dir())


if __name__ == "__main__":
    unittest.main()
