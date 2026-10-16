"""Settings: defaults, layers, the forbidden project layer for vault_path, legacy sources and notes.folder."""
import unittest

from aicore.config import ConfigError

from brain import errors, settings
from tests.support import TempCase


class TestDefaults(TempCase):
    def test_defaults_without_files(self):
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertIsNone(config.vault_path)
        self.assertEqual("none", config.vault_source)
        self.assertEqual("05-Projects", config.projects_dir)
        self.assertEqual((False, "pull", ("docs/**/*.md", "README.md"), "defaults"),
                         (config.docs_enabled, config.docs_direction, config.docs_patterns, config.docs_source))
        self.assertEqual((True, "Ecosystem/Plans", "Ecosystem/Plans"),
                         (config.notes_enabled, config.notes_folder, config.notes_fallback_folder))
        self.assertEqual((), config.warnings)

    def test_without_project(self):
        self.assertEqual("none", settings.load(None, env=self.env, home=self.home).vault_source)


class TestLayers(TempCase):
    def test_machine_layer_sets_vault_path(self):
        self.machine_config('[brain]\nvault_path = "/somewhere/vault"\n')
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual(("/somewhere/vault", "config"), (config.vault_path, config.vault_source))

    def test_project_layer_cannot_set_vault_path(self):
        self.project_config('[brain]\nvault_path = "/somewhere/vault"\n')
        with self.assertRaises(ConfigError) as caught:
            settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual("CONFIG_LAYER_FORBIDDEN", caught.exception.code)

    def test_project_layer_sets_docs_and_notes(self):
        self.project_config('[brain.docs]\nenabled = true\ndirection = "bidirectional"\npatterns = ["a/*.md"]\n'
                            '[brain.notes]\nfolder = "Journal"\n')
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual((True, "bidirectional", ("a/*.md",), "config", "Journal"),
                         (config.docs_enabled, config.docs_direction, config.docs_patterns, config.docs_source,
                          config.notes_folder))

    def test_invalid_value_is_a_config_error(self):
        self.project_config('[brain.docs]\ndirection = "sideways"\n')
        with self.assertRaises(ConfigError):
            settings.load(self.project, env=self.env, home=self.home)


class TestLegacy(TempCase):
    def test_object_gives_vault_path_and_docs(self):
        self.legacy({"path": "/old/vault", "sync": {"direction": "bidirectional", "patterns": ["x/*.md"]}})
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual(("/old/vault", "legacy-project"), (config.vault_path, config.vault_source))
        self.assertEqual((True, "bidirectional", "legacy"),
                         (config.docs_enabled, config.docs_direction, config.docs_source))
        self.assertEqual(("x/*.md",), config.docs_patterns)
        self.assertEqual([settings.LEGACY_VAULT_WARNING, settings.LEGACY_DOCS_WARNING], list(config.warnings))
        self.assertTrue(all(w.startswith(errors.BRAIN_LEGACY_CONFIG) for w in config.warnings))

    def test_legacy_defaults_of_the_old_sync(self):
        self.legacy({"path": "/old/vault"})
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual(("pull", ("docs/**/*.md", "README.md"), True),
                         (config.docs_direction, config.docs_patterns, config.docs_enabled))

    def test_string_value_is_not_a_path(self):
        self.legacy("core")
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual(("none", False, "defaults", ()),
                         (config.vault_source, config.docs_enabled, config.docs_source, config.warnings))

    def test_object_without_path_gives_docs_only(self):
        self.legacy({"sync": {"direction": "push"}})
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual(("none", True, "push"), (config.vault_source, config.docs_enabled, config.docs_direction))
        self.assertEqual([settings.LEGACY_DOCS_WARNING], list(config.warnings))

    def test_configuration_wins_over_legacy(self):
        self.machine_config('[brain]\nvault_path = "/new/vault"\n')
        self.project_config('[brain.docs]\nenabled = false\n')
        self.legacy({"path": "/old/vault", "sync": {"direction": "push"}})
        config = settings.load(self.project, env=self.env, home=self.home)
        self.assertEqual(("/new/vault", "config", False, "config", "pull"),
                         (config.vault_path, config.vault_source, config.docs_enabled, config.docs_source,
                          config.docs_direction))
        self.assertEqual((), config.warnings)

    def test_broken_legacy_file_is_ignored(self):
        (self.project / ".swissknife.json").write_text("{not json", encoding="utf-8")
        self.assertEqual("none", settings.load(self.project, env=self.env, home=self.home).vault_source)


class TestNotesFolder(TempCase):
    def test_synchronized_folders_are_refused(self):
        for folder in ("docs", "docs/notes", "docs-public", "plans/x", "./plans"):
            with self.subTest(folder=folder):
                self.project_config(f'[brain.notes]\nfolder = "{folder}"\n')
                with self.assertRaises(ConfigError) as caught:
                    settings.load(self.project, env=self.env, home=self.home)
                self.assertEqual(errors.CONFIG_NOTES_FOLDER, caught.exception.code)

    def test_escaping_or_absolute_folder_is_refused_by_the_schema(self):
        for folder in ("../up", "a/../b", "/abs"):
            with self.subTest(folder=folder):
                self.project_config(f'[brain.notes]\nfolder = "{folder}"\n')
                with self.assertRaises(ConfigError):
                    settings.load(self.project, env=self.env, home=self.home)

    def test_similar_names_are_fine(self):
        self.project_config('[brain.notes]\nfolder = "docs-notes/plans"\n')
        self.assertEqual("docs-notes/plans", settings.load(self.project, env=self.env, home=self.home).notes_folder)


if __name__ == "__main__":
    unittest.main()
