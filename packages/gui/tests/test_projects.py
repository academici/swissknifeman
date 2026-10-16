"""gui.core.projects: ids, idempotent adds, audit rows, realpath containment (I5) and the project/v1 documents."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from gui import contracts
from gui.core import projects
from gui.errors import GuiError
from gui.storage import db


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.conn = db.open_db(self.tmp / "state" / "gui.db")
        self.addCleanup(self.conn.close)
        self.registry = projects.ProjectRegistry(self.conn)
        self.root = self.tmp / "My Project"
        (self.root / ".git").mkdir(parents=True)
        (self.root / "src" / "deep").mkdir(parents=True)

    def audit_rows(self):
        return [(row["action"], row["target"]) for row in self.conn.execute("SELECT * FROM audit ORDER BY id")]

    def test_id_and_slug(self):
        self.assertEqual("my-project", projects.slug("My Project"))
        self.assertEqual("project", projects.slug("___"))
        self.assertEqual(40, len(projects.slug("a" * 60)))
        project = self.registry.add(self.root, source="open")
        self.assertRegex(project.id, r"^my-project-[0-9a-f]{8}$")
        self.assertTrue(projects.valid_id(project.id))
        self.assertEqual((str(self.root), "My Project", True, "open"),
                         (project.root, project.name, project.trusted, project.source))

    def test_subfolder_resolves_to_the_marked_root_and_add_is_idempotent(self):
        first = self.registry.add(self.root / "src" / "deep", source="open")
        second = self.registry.add(self.root, source="user")
        self.assertEqual(first, second)
        self.assertEqual([first], self.registry.list())
        self.assertEqual([("project.add", first.id)], self.audit_rows())

    def test_symlinked_path_registers_the_real_root(self):
        link = self.tmp / "link"
        link.symlink_to(self.root)
        self.assertEqual(str(self.root), self.registry.add(link, source="user").root)

    def test_missing_folder_is_not_found(self):
        with self.assertRaises(GuiError) as caught:
            self.registry.add(self.tmp / "absent", source="user")
        self.assertEqual("NOT_FOUND", caught.exception.code)
        with self.assertRaises(ValueError):
            self.registry.add(self.root, source="maind")

    def test_get_remove_and_audit(self):
        project = self.registry.add(self.root, source="user")
        self.assertEqual(project, self.registry.get(project.id))
        self.registry.remove(project.id)
        for call in (lambda: self.registry.get(project.id), lambda: self.registry.remove(project.id)):
            with self.assertRaises(GuiError) as caught:
                call()
            self.assertEqual("NOT_FOUND", caught.exception.code)
        self.assertEqual([("project.add", project.id), ("project.remove", project.id)], self.audit_rows())

    def test_resolve_inside(self):
        project = self.registry.add(self.root, source="open")
        self.assertEqual(self.root, self.registry.resolve(project.id))
        self.assertEqual(self.root / "src" / "deep", self.registry.resolve(project.id, "src/deep"))
        self.assertEqual(self.root / "src", self.registry.resolve(project.id, "src/deep/.."))

    def test_resolve_escapes(self):
        project = self.registry.add(self.root, source="open")
        (self.root / "out").symlink_to(self.tmp)
        for relpath in ("..", "../other", "src/../../x", "/etc", "out", "out/x"):
            with self.subTest(relpath=relpath), self.assertRaises(GuiError) as caught:
                self.registry.resolve(project.id, relpath)
            self.assertEqual("PATH_ESCAPE", caught.exception.code)

    def test_moved_or_replaced_root_is_not_found(self):
        project = self.registry.add(self.root, source="open")
        moved = self.tmp / "moved"
        self.root.rename(moved)
        with self.assertRaises(GuiError) as caught:
            self.registry.resolve(project.id)
        self.assertEqual("NOT_FOUND", caught.exception.code)
        self.root.symlink_to(moved)  # the old root is now a symlink to somewhere else
        with self.assertRaises(GuiError) as caught:
            self.registry.resolve(project.id, "src")
        self.assertEqual("NOT_FOUND", caught.exception.code)

    def test_documents_follow_project_v1(self):
        one = self.registry.add(self.root, source="open")
        other = self.tmp / "other"
        other.mkdir()
        self.registry.add(other, source="user")
        self.assertEqual([], contracts.validate(one.document(), "project"))
        listing = projects.list_document(self.registry.list())
        self.assertEqual([], contracts.validate(listing, "project"))
        self.assertEqual(["My Project", "other"], [entry["name"] for entry in listing["projects"]])


if __name__ == "__main__":
    unittest.main()
