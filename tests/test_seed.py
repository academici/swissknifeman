"""Тесты seed.py: базовый факт о связях в приватном бакете + cross-ref в бакет группы
(ns:<имя>, wildcard → global), идемпотентность, изоляция между namespace'ами."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import derive, seed
from maind import memory as memory_mod
from maind.config import load_config
from tests.fixtures import FakeMemoryServer, make_repo, write_maind_config


def _setup(tmp, url, namespaces=None):
    root, env = make_repo(tmp)
    flex, az = Path(tmp) / "flexcrm", Path(tmp) / "azguard"
    for p, data in ((flex, {"name": "axioma-studio/flexcrm",
                            "require": {"axioma-studio/azguard-core": "@dev"}}),
                    (az, {"name": "axioma-studio/azguard"})):
        p.mkdir(parents=True, exist_ok=True)
        (p / "composer.json").write_text(json.dumps(data), encoding="utf-8")
    (az / "packages" / "core").mkdir(parents=True, exist_ok=True)
    (az / "packages" / "core" / "composer.json").write_text(
        json.dumps({"name": "axioma-studio/azguard-core"}), encoding="utf-8")
    flexp = {"id": "flexcrm", "name": "FlexCRM", "type": "php-package", "status": "active",
             "enabled": True, "local_path": str(flex), "memory_scope": "project:flexcrm"}
    azp = {"id": "azguard", "name": "AzGuard", "type": "php-package", "status": "active",
           "enabled": True, "local_path": str(az)}
    if namespaces is not None:
        flexp["namespaces"] = namespaces
        azp["namespaces"] = namespaces
    write_maind_config(root, graph={"adapter": "federation"},
                       memory={"url": url}, projects=[flexp, azp])
    config, _ = load_config(env)
    derive.derive_all(env, config)
    return env, config, config["projects"][0]


class TestSeed(unittest.TestCase):
    def test_seed_text_mentions_shared_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            with FakeMemoryServer() as url:
                env, config, flex = _setup(tmp, url)
                text = seed.seed_text(env, config, flex)
                self.assertIn("ОБЩАЯ", text)
                self.assertIn("project:flexcrm", text)
                self.assertIn("azguard", text)  # связанный проект из графа

    def test_seed_writes_private_and_group_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            with FakeMemoryServer() as url:
                # без namespaces → группа default → cross-ref в ns:default (не в global)
                env, config, flex = _setup(tmp, url)
                r = seed.seed_memory(env, config, flex)
                self.assertEqual(r["status"], "ok")
                self.assertTrue(r["changed"])
                priv = memory_mod.recall(url, "project:flexcrm", "ecosystem-link")
                self.assertTrue(any("ОБЩАЯ" in m["text"] for m in priv))
                grp = memory_mod.recall(url, "ns:default", "ecosystem-link")
                self.assertTrue(any("flexcrm" in m["text"] for m in grp))
                self.assertEqual(memory_mod.recall(url, "global", "ecosystem-link"), [])

    def test_namespace_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with FakeMemoryServer() as url:
                # обе в axioma → cross-ref в ns:axioma; ns:other/global/ns:default — пусты
                env, config, flex = _setup(tmp, url, namespaces=["axioma"])
                seed.seed_memory(env, config, flex)
                shared = memory_mod.recall(url, "ns:axioma", "ecosystem-link")
                self.assertTrue(any("flexcrm" in m["text"] for m in shared))
                self.assertEqual(memory_mod.recall(url, "ns:other", "ecosystem-link"), [])
                self.assertEqual(memory_mod.recall(url, "global", "ecosystem-link"), [])
                self.assertEqual(memory_mod.recall(url, "ns:default", "ecosystem-link"), [])

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with FakeMemoryServer() as url:
                env, config, flex = _setup(tmp, url)
                seed.seed_memory(env, config, flex)
                r2 = seed.seed_memory(env, config, flex)
                self.assertFalse(r2["changed"])
                self.assertEqual(r2["state"], "fresh")

    def test_skip_when_daemon_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, memory={"url": "http://127.0.0.1:1"},
                               projects=[{"id": "x", "name": "X", "status": "active"}])
            config, _ = load_config(env)
            r = seed.seed_memory(env, config, config["projects"][0])
            self.assertEqual(r["status"], "skip")


if __name__ == "__main__":
    unittest.main()
