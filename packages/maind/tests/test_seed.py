"""Tests seed.py: related projects are read from the project graph."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import derive, seed
from maind.config import load_config
from tests.fixtures import FakeMemoryServer, make_repo, write_maind_config


def _setup(tmp, url):
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
    write_maind_config(root, graph={"adapter": "federation"},
                       memory={"url": url}, projects=[flexp, azp])
    config, _ = load_config(env)
    derive.derive_all(env, config)
    return env, config, config["projects"][0]


class TestLinkedProjects(unittest.TestCase):
    def test_linked_from_graph(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config, flex = _setup(tmp, url)
            self.assertEqual(seed.linked_projects(env, config, flex), ["azguard"])

    def test_no_graph_store_means_no_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, projects=[{"id": "x", "name": "X", "status": "active"}])
            config, _ = load_config(env)
            self.assertEqual(seed.linked_projects(env, config, config["projects"][0]), [])


if __name__ == "__main__":
    unittest.main()
