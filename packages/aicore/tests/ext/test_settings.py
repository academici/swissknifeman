"""aicore.ext.settings: the [aicore] section through the layered configuration."""
import unittest

from aicore.ext import settings
from aicore.ext.errors import ExtError

from tests.ext.support import TempCase


class SettingsCase(TempCase):
    def machine(self, text):
        path = self.tmp / "skm" / "config" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def project_file(self, text):
        path = self.project / ".swissknifeman" / "config.toml"
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def load(self, project=True, **kwargs):
        return settings.load(self.project if project else None, env=self.env, home=self.home, **kwargs)


class TestDefaults(SettingsCase):
    def test_defaults(self):
        loaded = self.load()
        self.assertEqual((loaded.delivery, loaded.timeout_seconds, loaded.max_attempts), ("background", 30, 3))
        self.assertEqual((loaded.subscriptions, loaded.plugins, loaded.overlays), ({}, {}, {}))
        self.assertEqual(loaded.warnings, ())

    def test_machine_and_project_layers(self):
        self.machine('[aicore.events]\ndelivery = "sync"\nmax_attempts = 5\n')
        self.project_file('[aicore.events]\ntimeout_seconds = 9\n')
        loaded = self.load()
        self.assertEqual((loaded.delivery, loaded.timeout_seconds, loaded.max_attempts), ("sync", 9, 5))
        loaded = self.load(project=False)
        self.assertEqual(loaded.timeout_seconds, 30)


class TestSubscriptionsAndPlugins(SettingsCase):
    def test_machine_defines_commands(self):
        self.machine('[aicore.subscriptions.mine]\non = ["plan.*.closed"]\nrun = ["/bin/true", "--x"]\n'
                     'timeout_seconds = 12\n[aicore.subscriptions."demo:log"]\nenabled = false\n'
                     '[aicore.plugins.tool]\nmanifest = "~/plugins/tool/extension.json"\ntrusted = true\n')
        loaded = self.load()
        self.assertEqual(loaded.subscriptions["mine"]["run"], ["/bin/true", "--x"])
        self.assertEqual(loaded.subscriptions["mine"]["timeout_seconds"], 12)
        self.assertEqual(loaded.subscriptions["mine"]["projects"], [])
        self.assertTrue(loaded.subscriptions["mine"]["enabled"])
        self.assertEqual(loaded.subscriptions["demo:log"], {"enabled": False, "projects": []})
        plugin = loaded.plugins["tool"]
        self.assertEqual(plugin["manifest"], str(self.home / "plugins" / "tool" / "extension.json"))
        self.assertEqual((plugin["trusted"], plugin["timeout_seconds"], plugin["enabled"]), (True, 60, True))

    def test_project_cannot_define_a_command_but_can_disable(self):
        self.project_file('[aicore.subscriptions.evil]\nrun = ["/bin/sh", "-c", "boom"]\n')
        with self.assertRaises(ExtError) as caught:
            self.load()
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        self.project_file('[aicore.plugins.tool]\ntrusted = true\n')
        with self.assertRaises(ExtError):
            self.load()
        self.project_file('[aicore.subscriptions."demo:log"]\nenabled = false\n[aicore.plugins.tool]\nenabled = false\n')
        loaded = self.load()
        self.assertFalse(loaded.subscriptions["demo:log"]["enabled"])
        self.assertFalse(loaded.plugins["tool"]["enabled"])

    def test_invalid_values_are_config_invalid_without_a_traceback_chain(self):
        self.machine('[aicore.events]\ndelivery = "sometimes"\n')
        with self.assertRaises(ExtError) as caught:
            self.load()
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIn("delivery", caught.exception.message)


class TestOverlays(SettingsCase):
    def test_paths_resolve_from_the_layer_file(self):
        machine = self.machine('[aicore.overlays]\n"demo:plan" = ["rules/a.md", "~/b.md", "/abs/c.md"]\n')
        project = self.project_file('[aicore.overlays]\n"demo:plan" = ["p.md"]\n')
        loaded = self.load()
        # the project layer replaces the whole list: arrays are not merged without _append
        self.assertEqual(loaded.overlays, {"demo:plan": [(str(self.project / ".swissknifeman" / "p.md"),
                                                          "project", str(project))]})
        project.write_text('schema_version = 1\n[aicore]\n_append = {"overlays.demo:plan" = ["p.md"]}\n',
                           encoding="utf-8")
        loaded = self.load()
        self.assertEqual(loaded.overlays["demo:plan"], [
            (str(machine.parent / "rules" / "a.md"), "machine", str(machine)),
            (str(self.home / "b.md"), "machine", str(machine)),
            ("/abs/c.md", "machine", str(machine)),
            (str(self.project / ".swissknifeman" / "p.md"), "project", str(project))])


if __name__ == "__main__":
    unittest.main()
