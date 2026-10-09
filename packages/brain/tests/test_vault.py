"""Vault ladder: configuration, legacy project block, legacy variable, default candidate, nothing."""
import unittest

from brain import errors, settings, vault
from brain.errors import BrainError
from tests.support import TempCase


class TestLadder(TempCase):
    def resolve(self, env=None, project=True):
        environment = dict(self.env, **(env or {}))
        config = settings.load(self.project if project else None, env=environment, home=self.home)
        return vault.resolve_vault(config, env=environment, home=self.home)

    def test_nothing_found(self):
        info = self.resolve()
        self.assertEqual((None, "none", False, False), (info.path, info.source, info.exists, info.obsidian))
        with self.assertRaises(BrainError) as caught:
            vault.require(info)
        self.assertEqual(errors.VAULT_NOT_FOUND, caught.exception.code)
        self.assertIn("aicore config set brain.vault_path", str(caught.exception))

    def test_configuration_comes_first(self):
        self.machine_config(f'[brain]\nvault_path = "{self.vault}"\n')
        self.legacy({"path": "/old"})
        info = self.resolve({"MAIND_BRAIN_VAULT": "/env"})
        self.assertEqual((self.vault, "config", True, True, ()), (info.path, info.source, info.exists, info.obsidian,
                                                                  info.warnings))

    def test_tilde_is_expanded_against_the_given_home(self):
        target = self.home / "Notes"
        (target / ".obsidian").mkdir(parents=True)
        self.machine_config('[brain]\nvault_path = "~/Notes"\n')
        self.assertEqual(target, self.resolve().path)

    def test_legacy_project_block(self):
        self.legacy({"path": str(self.vault)})
        info = self.resolve()
        self.assertEqual((self.vault, "legacy-project"), (info.path, info.source))
        self.assertEqual((settings.LEGACY_VAULT_WARNING,), info.warnings)

    def test_legacy_string_is_skipped(self):
        self.legacy("core")
        self.assertEqual("none", self.resolve().source)

    def test_legacy_variable(self):
        info = self.resolve({"MAIND_BRAIN_VAULT": str(self.vault)})
        self.assertEqual((self.vault, "env-legacy", True), (info.path, info.source, info.exists))
        self.assertEqual(1, len(info.warnings))
        self.assertTrue(info.warnings[0].startswith(errors.BRAIN_LEGACY_ENV))

    def test_legacy_project_comes_before_the_variable(self):
        self.legacy({"path": str(self.vault)})
        self.assertEqual("legacy-project", self.resolve({"MAIND_BRAIN_VAULT": "/env"}).source)

    def test_default_candidate_needs_obsidian_folder(self):
        candidate = self.home / "Vaults" / "Brain"
        candidate.mkdir(parents=True)
        self.assertEqual(("none", None), (self.resolve().source, self.resolve().path))
        (candidate / ".obsidian").mkdir()
        info = self.resolve()
        self.assertEqual((candidate, "default", True, True, ()), (info.path, info.source, info.exists, info.obsidian,
                                                                  info.warnings))

    def test_missing_configured_path_does_not_fall_through(self):
        (self.home / "Vaults" / "Brain" / ".obsidian").mkdir(parents=True)
        self.machine_config('[brain]\nvault_path = "/does/not/exist"\n')
        info = self.resolve({"MAIND_BRAIN_VAULT": str(self.vault)})
        self.assertEqual((False, "config"), (info.exists, info.source))
        with self.assertRaises(BrainError) as caught:
            vault.require(info)
        self.assertEqual(errors.VAULT_MISSING, caught.exception.code)

    def test_missing_variable_path_does_not_fall_through(self):
        (self.home / "Vaults" / "Brain" / ".obsidian").mkdir(parents=True)
        info = self.resolve({"MAIND_BRAIN_VAULT": "/does/not/exist"})
        self.assertEqual(("env-legacy", False), (info.source, info.exists))

    def test_existing_directory_without_obsidian_folder(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.machine_config(f'[brain]\nvault_path = "{plain}"\n')
        info = self.resolve()
        self.assertEqual((True, False), (info.exists, info.obsidian))
        self.assertEqual(plain, vault.require(info))

    def test_to_dict_is_json_ready(self):
        self.machine_config(f'[brain]\nvault_path = "{self.vault}"\n')
        self.assertEqual({"path": str(self.vault), "source": "config", "exists": True, "obsidian": True,
                          "warnings": []}, self.resolve().to_dict())
        self.assertIsNone(self.resolve_none().to_dict()["path"])

    def resolve_none(self):
        return vault.VaultInfo(None, "none", False, False)


if __name__ == "__main__":
    unittest.main()
