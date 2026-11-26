"""Tests migrate.py: from-brain (config+graph, overwrite protection), from-agentmemory."""
import json
import tempfile
import unittest
from pathlib import Path

from maind.config import load_config
from maind.provision.migrate import cmd_migrate
from tests.fixtures import capture, make_repo, write_brain_projects


class TestMigrate(unittest.TestCase):
    def test_from_brain_builds_config_and_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            bpath = write_brain_projects(root)
            capture(cmd_migrate, env, ["from-brain", str(bpath)])
            self.assertTrue(env.registry_file.exists())
            self.assertFalse(env.legacy_node_config.exists())
            cfg, source = load_config(env)
            self.assertEqual(source, "config")
            self.assertIn("brain", [p["id"] for p in cfg["projects"]])
            # the node settings went to the [maind] table of the machine config, not the registry
            self.assertEqual(cfg["node"]["id"], "hub")
            self.assertEqual(cfg["integrations"]["brain"]["path"], str(bpath))
            self.assertNotIn("node", json.loads(env.registry_file.read_text(encoding="utf-8")))
            # derive → federation: index collected (and not a single one legacy graph.db)
            self.assertTrue((env.data_dir / "graphs" / "_index.db").exists())

    def test_from_brain_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            bpath = write_brain_projects(root)
            capture(cmd_migrate, env, ["from-brain", str(bpath)])
            with self.assertRaises(SystemExit):
                cmd_migrate(env, ["from-brain", str(bpath)])  # without --force

    def test_from_agentmemory_copies_and_renames_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            src = Path(tmp) / "src" / ".agentmemory"
            src.mkdir(parents=True)
            (src / "iii-config.yaml").write_text(
                "workers:\n  - name: iii-observability\n    config:\n"
                "      service_name: agentmemory\n", encoding="utf-8")
            env.memory_config.unlink()  # remove the pre-seeded config
            capture(cmd_migrate, env, ["from-agentmemory", str(src)])
            text = env.memory_config.read_text(encoding="utf-8")
            self.assertIn("service_name: maind", text)
            self.assertNotIn("service_name: agentmemory", text)


if __name__ == "__main__":
    unittest.main()
