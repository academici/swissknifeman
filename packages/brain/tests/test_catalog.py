"""Catalog: .projects.json, control notes, ambiguity, broken catalog, realpath and symlinks."""
import json
import os
import unittest

from brain import catalog, errors
from tests.support import TempCase


class TestCatalog(TempCase):
    def find(self, repo=None, **kwargs):
        warnings = []
        found = catalog.find_project(self.vault, repo or self.project, home=self.home, warnings=warnings, **kwargs)
        return found, warnings

    def write_catalog(self, text):
        (self.vault / ".projects.json").write_text(text if isinstance(text, str) else json.dumps(text),
                                                   encoding="utf-8")

    def test_fixture_note_claims_its_repo_with_tilde(self):
        repo = self.home / "projects" / "demo"
        repo.mkdir(parents=True)
        found, warnings = self.find(repo)
        self.assertEqual(("Demo", self.vault / "05-Projects" / "03-Packages" / "Demo", "control-note"),
                         (found.name, found.folder, found.via))
        self.assertEqual([], warnings)

    def test_unknown_project_is_none(self):
        self.assertEqual((None, []), self.find())

    def test_control_note_with_absolute_repo(self):
        self.claim_project(self.project)
        found, _ = self.find()
        self.assertEqual("control-note", found.via)

    def test_control_note_one_level_below_projects_dir(self):
        flat = self.vault / "05-Projects" / "Flat"
        flat.mkdir()
        (flat / "Flat.md").write_text(f"---\nrepo: {self.project}\n---\n", encoding="utf-8")
        found, _ = self.find()
        self.assertEqual(("Flat", flat), (found.name, found.folder))

    def test_note_whose_name_differs_from_its_folder_is_not_a_control_note(self):
        other = self.vault / "05-Projects" / "03-Packages" / "Demo" / "Other.md"
        other.write_text(f"---\nrepo: {self.project}\n---\n", encoding="utf-8")
        self.assertIsNone(self.find()[0])

    def test_projects_dir_is_configurable(self):
        moved = self.vault / "Work" / "Demo"
        moved.mkdir(parents=True)
        (moved / "Demo.md").write_text(f"---\nrepo: {self.project}\n---\n", encoding="utf-8")
        self.assertEqual(moved, self.find(projects_dir="Work")[0].folder)
        self.assertIsNone(self.find()[0])

    def test_catalog_wins_over_notes(self):
        self.claim_project(self.project)
        folder = self.vault / "Elsewhere"
        folder.mkdir()
        self.write_catalog({"version": 1, "projects": [{"name": "Cat", "enabled": True, "vault_path": str(folder),
                                                        "repo": str(self.project)}]})
        found, warnings = self.find()
        self.assertEqual(("Cat", folder, "catalog", []), (found.name, found.folder, found.via, warnings))

    def test_catalog_relative_vault_path_and_disabled_entry(self):
        self.write_catalog({"projects": [
            {"name": "Off", "enabled": False, "vault_path": "Off", "repo": str(self.project)},
            {"name": "On", "vault_path": "Sub/On", "repo": str(self.project)}]})
        found, _ = self.find()
        self.assertEqual((self.vault / "Sub" / "On", "On"), (found.folder, found.name))

    def test_broken_catalog_warns_and_falls_back_to_notes(self):
        self.claim_project(self.project)
        self.write_catalog("{broken")
        found, warnings = self.find()
        self.assertEqual("control-note", found.via)
        self.assertEqual(1, len(warnings))
        self.assertTrue(warnings[0].startswith(errors.CATALOG_INVALID))

    def test_catalog_with_wrong_shape_is_invalid(self):
        self.write_catalog({"projects": "no"})
        _, warnings = self.find()
        self.assertTrue(warnings[0].startswith(errors.CATALOG_INVALID))

    def test_two_notes_are_ambiguous_and_the_first_by_path_wins(self):
        self.claim_project(self.project)
        second = self.vault / "05-Projects" / "00-First" / "Second"
        second.mkdir(parents=True)
        (second / "Second.md").write_text(f"---\nrepo: {self.project}\n---\n", encoding="utf-8")
        found, warnings = self.find()
        self.assertEqual("Second", found.name)
        self.assertEqual(1, len(warnings))
        self.assertTrue(warnings[0].startswith(errors.CATALOG_AMBIGUOUS))

    def test_symlinked_project_matches_by_realpath(self):
        self.claim_project(self.project)
        link = self.root / "link"
        os.symlink(self.project, link)
        self.assertEqual("Demo", self.find(link)[0].name)

    def test_repo_given_as_symlink_in_note(self):
        link = self.root / "link"
        os.symlink(self.project, link)
        self.claim_project(link)
        self.assertEqual("Demo", self.find()[0].name)

    def test_repo_list_in_note(self):
        note = self.claim_project(self.project)
        note.write_text(f"---\nrepo: [/nowhere, {self.project}]\n---\n", encoding="utf-8")
        self.assertEqual("Demo", self.find()[0].name)

    def test_missing_projects_dir(self):
        self.assertIsNone(self.find(projects_dir="Absent")[0])


if __name__ == "__main__":
    unittest.main()
