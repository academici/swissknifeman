"""gui.settings: defaults of configs/config.schema.json and the layers resolved by aicore.config."""
import tempfile
import unittest
from pathlib import Path

from aicore.config import ConfigError

from gui import settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm")}

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n\n" + text, encoding="utf-8")

    def test_defaults(self):
        loaded = settings.load(self.env)
        self.assertEqual(0, loaded.port)
        self.assertTrue(loaded.open_browser)
        self.assertEqual(settings.Runs(4, 2, 2, 16384, 52428800, 600, 5), loaded.runs)
        self.assertEqual(settings.Events(10000, 1000, 15, 1), loaded.events)
        self.assertEqual(settings.Retention(30, 1024), loaded.retention)
        self.assertEqual(settings.Query(1048576), loaded.query)
        self.assertEqual(settings.Config(5, 600), loaded.config)
        self.assertEqual(settings.Plugins(10, 3, 300, 200), loaded.plugins)

    def test_plugins_keys_are_bounded(self):
        path = self.tmp / "skm" / "config" / "config.toml"
        self.write(path, "[gui.plugins]\ndrain_timeout_s = 0\nquarantine_failures = 20\nquarantine_window_s = 10\n"
                         "history_limit = 2000\n")
        self.assertEqual(settings.Plugins(0, 20, 10, 2000), settings.load(self.env).plugins)
        for bad in ("drain_timeout_s = 301", "quarantine_failures = 0", "quarantine_failures = 21",
                    "quarantine_window_s = 9", "history_limit = 9", "history_limit = 2001"):
            self.write(path, f"[gui.plugins]\n{bad}\n")
            with self.assertRaises(ConfigError, msg=bad):
                settings.load(self.env)

    def test_machine_project_and_env_layers(self):
        self.write(self.tmp / "skm" / "config" / "config.toml", "[gui]\nport = 8123\n\n[gui.runs]\nmax_global = 6\n")
        project = self.tmp / "project"
        self.write(project / ".swissknifeman" / "config.toml", "[gui.runs]\nmax_per_project = 1\n")
        loaded = settings.load({**self.env, "SKM_GUI_OPEN_BROWSER": "false"}, project)
        self.assertEqual(8123, loaded.port)
        self.assertEqual(6, loaded.runs.max_global)
        self.assertEqual(1, loaded.runs.max_per_project)
        self.assertFalse(loaded.open_browser)
        self.assertIn("project", loaded.resolved.explain_text("runs.max_per_project"))

    def test_config_keys_are_bounded(self):
        self.write(self.tmp / "skm" / "config" / "config.toml", "[gui.config]\nlock_timeout_s = 0.5\npreview_ttl_s = 60\n")
        self.assertEqual(settings.Config(0.5, 60), settings.load(self.env).config)
        self.write(self.tmp / "skm" / "config" / "config.toml", "[gui.config]\npreview_ttl_s = 5\n")
        with self.assertRaises(ConfigError):
            settings.load(self.env)

    def test_port_is_machine_wide(self):
        project = self.tmp / "project"
        self.write(project / ".swissknifeman" / "config.toml", "[gui]\nport = 9000\n")
        with self.assertRaises(ConfigError):
            settings.load(self.env, project)

    def test_out_of_range_and_unknown_keys_are_refused(self):
        self.write(self.tmp / "skm" / "config" / "config.toml", "[gui]\nport = 70000\n")
        with self.assertRaises(ConfigError):
            settings.load(self.env)
        self.write(self.tmp / "skm" / "config" / "config.toml", "[gui]\nhost = \"0.0.0.0\"\n")
        with self.assertRaises(ConfigError):
            settings.load(self.env)


if __name__ == "__main__":
    unittest.main()
