"""Tests start.py: cmd_start --only graph creates a graph; cmd_status gives a summary."""
import json
import tempfile
import unittest

from maind.provision.start import cmd_start, cmd_status
from tests.fixtures import FakeMemoryServer, capture, make_repo, write_maind_config


class TestStartStatus(unittest.TestCase):
    def test_start_only_graph_creates_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root)
            _, out = capture(cmd_start, env, ["--only", "graph"])
            # federation: project store + index (and not a single one legacy graph.db)
            self.assertTrue((env.data_dir / "graphs" / "alpha.db").exists())
            self.assertTrue((env.data_dir / "graphs" / "_index.db").exists())
            self.assertIn("graph ready", out)

    def test_status_json_against_fake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                write_maind_config(root, memory={"url": url})
                _, out = capture(cmd_status, env, ["--json"])
                snap = json.loads(out)
                self.assertEqual(snap["config_source"], "config.json")
                self.assertTrue(snap["memory"]["running"])
                self.assertEqual(snap["projects"]["total"], 1)  # alpha from fixture

    def test_start_bad_only_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root)
            with self.assertRaises(SystemExit):
                cmd_start(env, ["--only", "nope"])


if __name__ == "__main__":
    unittest.main()
