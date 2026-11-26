"""The project-local folder ``projects/<code>/local/``: layout helpers, ``config.toml`` and ``repo.path``."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from aicore import workspace as ws
from aicore.workspace import documents

PRJ = "billium"


class LocalConfigCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.ws = self.tmp / "axioma"
        (self.ws / "projects" / PRJ).mkdir(parents=True)
        self.checkout = self.tmp / "src" / "skm"
        self.checkout.mkdir(parents=True)

    def file(self) -> Path:
        return ws.local_config_file(self.ws, PRJ)


class LayoutTests(LocalConfigCase):
    def test_paths_are_below_the_project_folder_and_nothing_is_created(self):
        folder = self.ws / "projects" / PRJ / "local"
        self.assertEqual(ws.local_dir(self.ws, PRJ), folder)
        self.assertEqual(ws.local_config_file(self.ws, PRJ), folder / "config.toml")
        self.assertEqual(ws.local_state_dir(self.ws, PRJ), folder / "state")
        self.assertEqual(ws.local_state_dir(self.ws, PRJ, "orch"), folder / "state" / "orch")
        self.assertEqual(ws.local_backups_dir(self.ws, PRJ), folder / "backups")
        self.assertEqual(ws.local_stubs_dir(self.ws, PRJ), folder / "stubs")
        self.assertFalse(folder.exists())

    def test_a_project_id_that_is_not_a_code_is_refused(self):
        with self.assertRaises(ValueError):
            ws.local_dir(self.ws, "../x")

    def test_ensure_local_makes_the_folders_private_and_is_repeatable(self):
        folder = ws.ensure_local(self.ws, PRJ)
        ws.ensure_local(self.ws, PRJ)
        self.assertEqual(sorted(child.name for child in folder.iterdir()), ["backups", "state", "stubs"])
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)

    def test_ensure_local_of_an_unknown_project_creates_nothing(self):
        with self.assertRaises(ws.WorkspaceError) as caught:
            ws.ensure_local(self.ws, "ghost")
        self.assertEqual(caught.exception.code, "PROJECT_UNKNOWN")
        self.assertFalse((self.ws / "projects" / "ghost").exists())


class RepoPathTests(LocalConfigCase):
    def test_without_a_file_there_is_no_config_and_no_repo(self):
        self.assertIsNone(ws.read_local_config(self.ws, PRJ))
        self.assertIsNone(ws.repo_path(self.ws, PRJ))

    def test_set_repo_path_writes_the_real_path_and_a_valid_document(self):
        link = self.tmp / "link"
        link.symlink_to(self.checkout)
        self.assertEqual(ws.set_repo_path(self.ws, PRJ, link), str(self.checkout))
        self.assertEqual(self.file().read_text(encoding="utf-8"),
                         f'schema_version = 1\n\n[repo]\npath = "{self.checkout}"\n')
        document = ws.read_local_config(self.ws, PRJ)
        self.assertEqual(document, {"schema_version": 1, "repo": {"path": str(self.checkout)}})
        self.assertEqual(ws.validate_document("project-local-config", document), [])
        self.assertEqual(ws.repo_path(self.ws, PRJ), str(self.checkout))
        self.assertEqual(stat.S_IMODE(self.file().stat().st_mode), 0o600)
        self.assertTrue(ws.local_stubs_dir(self.ws, PRJ).is_dir())

    def test_the_project_layer_of_the_file_is_kept(self):
        ws.ensure_local(self.ws, PRJ)
        self.file().write_text('schema_version = 1\n\n# kept\n[orch.conductor]\nforeign_untracked = "keep"\n',
                               encoding="utf-8")
        ws.set_repo_path(self.ws, PRJ, self.checkout)
        text = self.file().read_text(encoding="utf-8")
        self.assertIn("# kept\n[orch.conductor]\nforeign_untracked = \"keep\"\n", text)
        self.assertEqual(ws.read_local_config(self.ws, PRJ)["orch"], {"conductor": {"foreign_untracked": "keep"}})
        other = self.tmp / "src" / "other"
        other.mkdir()
        ws.set_repo_path(self.ws, PRJ, other)
        self.assertEqual(ws.repo_path(self.ws, PRJ), str(other))
        self.assertEqual(text.count("[repo]"), 1)
        self.assertEqual(self.file().read_text(encoding="utf-8").count("[repo]"), 1)

    def test_the_same_path_again_does_not_rewrite_the_file(self):
        ws.set_repo_path(self.ws, PRJ, self.checkout)
        before = self.file().stat().st_mtime_ns
        inode = self.file().stat().st_ino
        ws.set_repo_path(self.ws, PRJ, self.checkout)
        self.assertEqual((self.file().stat().st_mtime_ns, self.file().stat().st_ino), (before, inode))

    def test_set_repo_path_of_an_unknown_project_writes_nothing(self):
        with self.assertRaises(ws.WorkspaceError) as caught:
            ws.set_repo_path(self.ws, "ghost", self.checkout)
        self.assertEqual(caught.exception.code, "PROJECT_UNKNOWN")
        self.assertFalse((self.ws / "projects" / "ghost").exists())

    def test_clear_repo_path_removes_the_table_and_keeps_the_rest(self):
        self.assertFalse(ws.clear_repo_path(self.ws, PRJ))
        ws.ensure_local(self.ws, PRJ)
        self.file().write_text('schema_version = 1\n\n[planner.bridges]\nroots = ["bridges"]\n', encoding="utf-8")
        ws.set_repo_path(self.ws, PRJ, self.checkout)
        self.assertTrue(ws.clear_repo_path(self.ws, PRJ))
        self.assertFalse(ws.clear_repo_path(self.ws, PRJ))
        self.assertIsNone(ws.repo_path(self.ws, PRJ))
        text = self.file().read_text(encoding="utf-8")
        self.assertNotIn("[repo]", text)
        self.assertEqual(ws.read_local_config(self.ws, PRJ),
                         {"schema_version": 1, "planner": {"bridges": {"roots": ["bridges"]}}})

    def test_a_damaged_file_is_refused_and_left_alone(self):
        ws.ensure_local(self.ws, PRJ)
        for text in ("schema_version = 1\n[repo\n", 'schema_version = 1\n[repo]\npath = "src/skm"\n',
                     '[repo]\npath = "/x"\n', 'schema_version = 1\nname = "x"\n'):
            with self.subTest(text=text):
                self.file().write_text(text, encoding="utf-8")
                for call in (lambda: ws.read_local_config(self.ws, PRJ), lambda: ws.repo_path(self.ws, PRJ),
                             lambda: ws.set_repo_path(self.ws, PRJ, self.checkout)):
                    with self.assertRaises(ws.WorkspaceError) as caught:
                        call()
                    self.assertEqual(caught.exception.code, "PROJECT_LOCAL_CONFIG_INVALID")
                self.assertEqual(self.file().read_text(encoding="utf-8"), text)

    def test_the_local_config_is_a_machine_document(self):
        self.assertIn("project-local-config", documents.MACHINE_KINDS)
        document = {"schema_version": 1, "repo": {"path": "/home/user/src/skm"}}
        self.assertEqual(ws.validate_document("project-local-config", document), [])


if __name__ == "__main__":
    unittest.main()
