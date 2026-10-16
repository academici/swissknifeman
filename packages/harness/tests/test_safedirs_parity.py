"""`harness safe-dirs` and the auto-approve hook (no aicore) pick the same safe-dirs.json."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness import safedirs
from harness.common import Env

PKG = Path(__file__).resolve().parents[1]
HOOK_LIB = PKG / "configs/claude-code/hooks/auto-approve/lib/safedirs.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("hook_safedirs_parity", HOOK_LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LadderParityCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.hub = self.tmp / "hub"
        self.hub.mkdir()
        self.hook = load_hook()
        self.env = Env(PKG, "safe-dirs", home=self.home)

    def touch(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "dirs": []}), encoding="utf-8")
        return path

    def both(self, environ, hub=True):
        """(harness choice, hook choice) under `environ`; the legacy hub rung is the same directory."""
        clean = {key: value for key, value in os.environ.items()
                 if key not in ("SKM_HOME", "SKM_SAFE_DIRS_CONFIG", "XDG_CONFIG_HOME")}
        clean.update(environ)
        root = self.hub if hub else None
        with unittest.mock.patch.dict(os.environ, clean, clear=True), \
                unittest.mock.patch.object(safedirs, "find_monorepo_root", lambda _start: root), \
                unittest.mock.patch.object(self.hook, "_repo_root", lambda: str(root) if root else None):
            return (Path(safedirs._state_file(self.env)),
                    Path(self.hook._config_path(str(self.home))))

    def assertSame(self, expected, environ, hub=True):
        harness, hook = self.both(environ, hub)
        self.assertEqual(harness, hook)
        self.assertEqual(harness, expected)

    def test_without_any_file_both_name_the_new_place(self):
        self.assertSame(self.home / ".config/swissknifeman/harness/safe-dirs.json", {})

    def test_skm_home_moves_the_config_directory(self):
        skm = self.tmp / "skm"
        self.assertSame(skm / "config/harness/safe-dirs.json", {"SKM_HOME": str(skm)})

    def test_xdg_config_home_moves_it_and_a_relative_value_is_ignored(self):
        xdg = self.tmp / "xdg"
        self.assertSame(xdg / "swissknifeman/harness/safe-dirs.json", {"XDG_CONFIG_HOME": str(xdg)})
        self.assertSame(self.home / ".config/swissknifeman/harness/safe-dirs.json",
                        {"XDG_CONFIG_HOME": "relative/dir"})

    def test_a_relative_skm_home_is_ignored_by_both(self):
        self.assertSame(self.home / ".config/swissknifeman/harness/safe-dirs.json",
                        {"SKM_HOME": "relative/dir"})

    def test_the_override_is_exclusive(self):
        self.touch(self.home / ".config/swissknifeman/harness/safe-dirs.json")
        other = self.tmp / "other.json"
        self.assertSame(other, {"SKM_SAFE_DIRS_CONFIG": str(other)})

    def test_legacy_rungs_in_order(self):
        legacy_home = self.touch(self.home / ".swissknifeman/safe-dirs.json")
        self.assertSame(legacy_home, {})
        legacy_hub = self.touch(self.hub / "safe-dirs.json")
        self.assertSame(legacy_hub, {})
        self.assertSame(legacy_home, {}, hub=False)

    def test_the_new_place_beats_both_legacy_files(self):
        self.touch(self.home / ".swissknifeman/safe-dirs.json")
        self.touch(self.hub / "safe-dirs.json")
        new = self.touch(self.home / ".config/swissknifeman/harness/safe-dirs.json")
        self.assertSame(new, {})
        skm = self.tmp / "skm"
        isolated = self.touch(skm / "config/harness/safe-dirs.json")
        self.assertSame(isolated, {"SKM_HOME": str(skm)})

    def test_missing_file_stays_fail_closed_in_the_hook(self):
        with unittest.mock.patch.dict(os.environ, {"SKM_SAFE_DIRS_CONFIG": str(self.tmp / "none.json")}):
            self.assertIsNone(self.hook.load_allowlist(str(self.home)))


if __name__ == "__main__":
    unittest.main()
