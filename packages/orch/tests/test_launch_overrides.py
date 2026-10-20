"""The launch catalog is changed by configuration, not by editing the package: ``[orch.launch] catalog`` names another
file and ``[orch.launch.entries.ROLE_PROVIDER]`` changes single fields, per machine or per project (argv, transport and
model_set only per machine); the shipped catalog file stays as it is."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from aicore.config import ConfigError

from orch import launch, settings
from orch.settings import SettingsError
from tests.test_settings import SettingsCase


class ApplyEntriesTests(unittest.TestCase):
    def test_only_the_named_fields_change_and_the_input_is_not_touched(self):
        base = launch.load_catalog()
        before = copy.deepcopy(base)
        merged = launch.apply_entries(base, {"executor_codex": {"effort": "xhigh", "timeout_s": 7200}})
        self.assertEqual(merged["launch"]["executor"]["codex"], {**before["launch"]["executor"]["codex"],
                                                                 "effort": "xhigh", "timeout_s": 7200})
        merged["launch"]["executor"]["codex"] = before["launch"]["executor"]["codex"]
        self.assertEqual(merged, before)  # nothing else changed
        self.assertEqual(base, before)

    def test_an_argv_replaces_the_whole_command_and_builds(self):
        argv = ["codex", "-a", "never", "exec", "--json", "--model", "{model}", "-"]
        merged = launch.apply_entries(launch.load_catalog(), {"executor_codex": {"argv": argv}})
        self.assertEqual(launch.build_argv(merged, "executor", "codex", model="m", cwd="/p"), [
            "codex", "-a", "never", "exec", "--json", "--model", "m", "-"])

    def test_an_entry_the_catalog_does_not_have_is_unknown(self):
        for key in ("executor_nobody", "nobody_codex", "advisor_codex", "executor"):  # advisor/codex is refused
            with self.subTest(key=key), self.assertRaises(launch.LaunchError) as raised:
                launch.apply_entries(launch.load_catalog(), {key: {"effort": "low"}})
            self.assertEqual(raised.exception.code, "LAUNCH_UNKNOWN")

    def test_a_change_that_makes_the_catalog_invalid_is_refused_naming_the_configuration(self):
        with self.assertRaises(launch.LaunchError) as raised:
            launch.apply_entries(launch.load_catalog(), {"executor_codex": {"argv": ["codex", "exec", "-"]}})
        self.assertEqual(raised.exception.code, "LAUNCH_INVALID")
        self.assertIn("[orch.launch.entries]", str(raised.exception))
        self.assertIn("{model}", str(raised.exception))

    def test_a_catalog_file_replaces_the_shipped_one_and_entries_go_over_it(self):
        import tempfile
        catalog = launch.load_catalog()
        catalog["launch"]["executor"]["codex"]["timeout_s"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mine.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            found = launch.effective_catalog({"catalog": str(path), "entries": {"executor_codex": {"effort": "low"}}})
        self.assertEqual((found["launch"]["executor"]["codex"]["timeout_s"],
                          found["launch"]["executor"]["codex"]["effort"]), (99, "low"))

    def test_without_settings_it_is_the_shipped_catalog(self):
        self.assertEqual(launch.effective_catalog(None), launch.load_catalog())
        self.assertEqual(launch.effective_catalog({"catalog": "", "entries": {}}), launch.load_catalog())

    def test_the_origin_of_a_changed_field_is_named(self):
        entries = {"entries": {"executor_codex": {"effort": "xhigh"}}}
        self.assertEqual(launch.entry_origin(entries, "executor", "codex", "effort"),
                         "orch.launch.entries.executor_codex.effort")
        self.assertIsNone(launch.entry_origin(entries, "executor", "codex", "timeout_s"))
        self.assertIsNone(launch.entry_origin(None, "executor", "codex", "effort"))


class LaunchSettingsTests(SettingsCase):
    def test_a_machine_changes_any_field_and_a_project_the_safe_ones(self):
        self.machine('[orch.launch.entries.executor_codex]\neffort = "high"\nargv = ["codex", "--model", "{model}", "-"]\n')
        self.project_file('[orch.launch.entries.executor_codex]\neffort = "xhigh"\n'
                          '[orch.launch.entries.reviewer_grok]\ntimeout_s = 600\n')
        found = self.load(project=self.project)
        self.assertEqual(found.launch["entries"], {
            "executor_codex": {"effort": "xhigh", "argv": ["codex", "--model", "{model}", "-"]},
            "reviewer_grok": {"timeout_s": 600}})
        self.assertIn("project", found.explain_text("launch.entries.executor_codex.effort"))
        self.assertIn("machine", found.explain_text("launch.entries.executor_codex.argv"))

    def test_a_project_cannot_choose_the_command_the_transport_or_the_catalog_file(self):
        for text in ('[orch.launch.entries.executor_codex]\nargv = ["codex", "{model}"]\n',
                     '[orch.launch.entries.executor_codex]\ntransport = "text"\n',
                     '[orch.launch.entries.executor_codex]\nmodel_set = "unknown"\n',
                     '[orch.launch]\ncatalog = "/tmp/mine.json"\n'):
            with self.subTest(text=text):
                self.project_file(text)
                with self.assertRaises(ConfigError) as raised:
                    self.load(project=self.project)
                self.assertEqual(raised.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_the_catalog_file_must_be_absolute(self):
        self.machine('[orch.launch]\ncatalog = "relative/launch.json"\n')
        with self.assertRaises(SettingsError) as raised:
            self.load()
        self.assertEqual(raised.exception.code, "LAUNCH_CATALOG_RELATIVE")

    def test_defaults_change_nothing(self):
        found = self.load()
        self.assertEqual(found.launch, {"catalog": "", "access": "open", "entries": {}})
        self.assertEqual(launch.effective_catalog(found.launch), launch.load_catalog())


class ShippedCatalogTests(unittest.TestCase):
    def test_a_run_without_configuration_reads_the_shipped_file_and_never_writes_it(self):
        path = launch.CATALOG_PATH
        before = path.read_bytes()
        launch.effective_catalog(settings.defaults().launch)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
