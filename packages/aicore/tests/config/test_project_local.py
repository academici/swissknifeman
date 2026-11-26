"""The project layer of the configuration follows the project marker to ``local/config.toml`` of the workspace project;
a project without a marker keeps ``.swissknifeman/config.toml``."""
import json
import unittest

from .support import Workspace
from .test_cli import CliCase


class ProjectLayerTests(Workspace):
    def setUp(self):
        super().setUp()
        self.env["SKM_WORKSPACES_ROOT"] = str(self.root / "wss")
        self.local = self.root / "wss" / "axioma" / "projects" / "alpha" / "local"

    def mark(self):
        self.write(self.project / ".swissknifeman" / "project.json",
                   json.dumps({"workspace": "axioma", "project_id": "alpha", "plans_store": "workspace"}))
        self.local.parent.mkdir(parents=True)

    def test_the_project_layer_is_read_from_the_local_folder(self):
        self.mark()
        self.write(self.project / ".swissknifeman" / "config.toml", 'schema_version = 1\n[demo]\nmode = "fast"\n')
        self.write(self.local / "config.toml", 'schema_version = 1\n[demo]\nmode = "safe"\nverbose = true\n')
        resolved = self.resolve()
        self.assertTrue(resolved.get("verbose"))
        self.assertEqual("safe", resolved.get("mode"))
        entry = resolved.explain("verbose")[0]
        self.assertEqual("project", entry.layer)
        self.assertEqual(str(self.local / "config.toml"), str(entry.file))

    def test_a_marked_project_ignores_the_file_in_the_checkout(self):
        self.mark()
        self.write(self.project / ".swissknifeman" / "config.toml", "schema_version = 1\n[demo]\nverbose = true\n")
        self.assertFalse(self.resolve().get("verbose"))

    def test_a_project_without_a_marker_behaves_as_before(self):
        self.write(self.project / ".swissknifeman" / "config.toml", "schema_version = 1\n[demo]\nverbose = true\n")
        self.assertTrue(self.resolve().get("verbose"))


class ProjectCommandTests(CliCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_WORKSPACES_ROOT"] = str(self.tmp / "wss")
        self.local = self.tmp / "wss" / "axioma" / "projects" / "alpha" / "local"
        marker = self.project / ".swissknifeman" / "project.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"workspace": "axioma", "project_id": "alpha", "plans_store": "workspace"}))
        self.local.parent.mkdir(parents=True)

    def test_paths_name_the_local_folder(self):
        code, out, _ = self.run_cli("config", "paths", "--json")
        self.assertEqual(0, code)
        project = json.loads(out)["project"]
        self.assertEqual(str(self.local / "config.toml"), project["config_file"])
        self.assertEqual(str(self.local / "state"), project["state"])
        self.assertEqual(str(self.local / "backups"), project["backups"])

    def test_set_writes_the_local_file_and_backs_it_up_beside_it(self):
        self.local.mkdir()
        (self.local / "config.toml").write_text('schema_version = 1\n[demo]\nmode = "safe"\n', encoding="utf-8")
        code, _out, err = self.run_cli("config", "set", "demo.mode", "fast", "--project")
        self.assertEqual(0, code, err)
        self.assertIn('mode = "fast"', (self.local / "config.toml").read_text(encoding="utf-8"))
        self.assertFalse(self.project_file.exists())
        copies = list((self.local / "backups").glob("*/local/config.toml"))
        self.assertEqual(1, len(copies))
        self.assertIn('mode = "safe"', copies[0].read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".swissknifeman" / "backups").exists())


if __name__ == "__main__":
    unittest.main()
