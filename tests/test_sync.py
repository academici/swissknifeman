"""Тесты sync.py (фан-аут + провиженеры mcp/graph) и common.managed_block."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import sync
from maind.common import managed_block, upsert_block
from maind.config import load_config
from maind.mcpconfig import has_server
from tests.fixtures import make_repo, write_maind_config


def _setup(tmp):
    root, env = make_repo(tmp)
    proj = Path(tmp) / "flexcrm"
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    (proj / "composer.json").write_text(
        json.dumps({"name": "axioma-studio/flexcrm",
                    "require": {"axioma-studio/azguard-core": "@dev"}}), encoding="utf-8")
    projects = [{"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
                 "status": "active", "enabled": True, "local_path": str(proj)}]
    write_maind_config(root, graph={"adapter": "federation"}, projects=projects)
    config, _ = load_config(env)
    return env, config, proj


class TestManagedBlock(unittest.TestCase):
    MARK = "maind:healthcheck"

    def test_insert_then_idempotent(self):
        t0 = "# Project\n\nДокументация.\n"
        t1, changed, state = upsert_block(t0, "ПРИОРИТЕТ №1", self.MARK)
        self.assertTrue(changed)
        self.assertEqual(state, "absent")
        self.assertIn("ПРИОРИТЕТ №1", t1)
        self.assertIn("# Project", t1)  # чужой текст сохранён
        t2, changed2, state2 = upsert_block(t1, "ПРИОРИТЕТ №1", self.MARK)
        self.assertFalse(changed2)
        self.assertEqual(state2, "fresh")
        self.assertEqual(t1, t2)

    def test_update_on_drift(self):
        t0, _, _ = upsert_block("# P\n", "старый текст", self.MARK)
        t1, changed, state = upsert_block(t0, "новый текст", self.MARK)
        self.assertTrue(changed)
        self.assertEqual(state, "stale")
        self.assertIn("новый текст", t1)
        self.assertNotIn("старый текст", t1)
        self.assertEqual(t1.count(self.MARK), 2)  # один блок (begin+end), не два

    def test_block_has_hash(self):
        self.assertIn("hash=", managed_block("x", self.MARK))


class TestSync(unittest.TestCase):
    def test_select_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            self.assertEqual([p["id"] for p in
                              sync.select_projects(env, config, {"all": True})], ["flexcrm"])
            self.assertEqual([p["id"] for p in
                              sync.select_projects(env, config, {"project": "flexcrm"})],
                             ["flexcrm"])

    def test_mcp_provisioner_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r1 = sync.run_sync(env, config, projs, only="mcp")
            self.assertTrue(has_server(proj / ".mcp.json", "agentmemory"))
            self.assertTrue(has_server(proj / ".mcp.json", "maind"))
            self.assertTrue(r1[0]["changed"])
            r2 = sync.run_sync(env, config, projs, only="mcp")
            self.assertFalse(r2[0]["changed"])  # повтор — без изменений

    def test_mcp_provisioner_graphify_config_driven(self):
        # graphify:true в записи проекта → провиженер mcp раскатывает graphify
        # (когда бинарь есть); без флага — нет. Бинарь мокаем присутствующим.
        from maind import deploy
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name: f"/usr/bin/{name}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env, config, proj = _setup(tmp)
                config["projects"][0]["graphify"] = True
                projs = sync.select_projects(env, config, {"all": True})
                sync.run_sync(env, config, projs, only="mcp")
                self.assertTrue(has_server(proj / ".mcp.json", "serena"))
        finally:
            deploy.shutil.which = orig

    def test_mcp_provisioner_no_graphify_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="mcp")
            self.assertFalse(has_server(proj / ".mcp.json", "serena"))

    def test_graph_provisioner_builds_stores(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="graph")
            self.assertTrue((env.data_dir / "graphs" / "flexcrm.db").exists())
            self.assertTrue((env.data_dir / "graphs" / "_index.db").exists())

    def test_graph_provisioner_changed_is_honest(self):
        # повторный derive без изменений источников → changed=False (детерминированный стор)
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r1 = sync.run_sync(env, config, projs, only="graph")
            self.assertTrue(all(r["changed"] for r in r1))  # первый прогон — создание
            r2 = sync.run_sync(env, config, projs, only="graph")
            self.assertTrue(all(not r["changed"] for r in r2))  # повтор — без изменений

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="mcp", dry=True)
            self.assertFalse((proj / ".mcp.json").exists())

    def test_unknown_provisioner_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup(tmp)
            with self.assertRaises(SystemExit):
                sync.provisioner_names("bogus")


if __name__ == "__main__":
    unittest.main()
