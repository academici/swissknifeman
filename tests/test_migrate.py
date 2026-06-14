"""Тесты migrate.py: from-brain (конфиг+граф, защита от перезаписи), from-agentmemory."""
import tempfile
import unittest
from pathlib import Path

from maind.config import load_config
from maind.migrate import cmd_migrate
from tests.fixtures import capture, make_repo, write_brain_projects


class TestMigrate(unittest.TestCase):
    def test_from_brain_builds_config_and_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            bpath = write_brain_projects(root)
            capture(cmd_migrate, env, ["from-brain", str(bpath)])
            self.assertTrue(env.default_config.exists())
            cfg, source = load_config(env)
            self.assertEqual(source, ".maind.json")
            self.assertIn("brain", [p["id"] for p in cfg["projects"]])
            self.assertTrue(env.graph_db.exists())

    def test_from_brain_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            bpath = write_brain_projects(root)
            capture(cmd_migrate, env, ["from-brain", str(bpath)])
            with self.assertRaises(SystemExit):
                cmd_migrate(env, ["from-brain", str(bpath)])  # без --force

    def test_from_agentmemory_copies_and_renames_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            src = Path(tmp) / "src" / ".agentmemory"
            src.mkdir(parents=True)
            (src / "iii-config.yaml").write_text(
                "workers:\n  - name: iii-observability\n    config:\n"
                "      service_name: agentmemory\n", encoding="utf-8")
            env.memory_config.unlink()  # убираем пред-засеянный конфиг
            capture(cmd_migrate, env, ["from-agentmemory", str(src)])
            text = env.memory_config.read_text(encoding="utf-8")
            self.assertIn("service_name: maind", text)
            self.assertNotIn("service_name: agentmemory", text)


if __name__ == "__main__":
    unittest.main()
