"""Тесты derive.py: code (composer), doc (Brain frontmatter), override, provider-index."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import derive, federation
from maind.config import load_config
from tests.fixtures import make_repo, write_maind_config


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup(tmp, *, with_doc=False, with_override=False):
    root, env = make_repo(tmp)
    base = Path(tmp)
    flex, az = base / "flexcrm", base / "azguard"
    _write(flex / "composer.json",
           {"name": "axioma-studio/flexcrm",
            "require": {"axioma-studio/azguard-core": "@dev", "laravel/framework": "^12"}})
    _write(az / "composer.json", {"name": "axioma-studio/azguard"})
    _write(az / "packages" / "core" / "composer.json",
           {"name": "axioma-studio/azguard-core"})
    if with_override:
        _write(flex / ".maind.graph.json",
               {"links": [{"to": "GetChat", "type": "relates_to",
                           "plane": "runtime", "note": "REST corex/messenger"}]})
    projects = [
        {"id": "flexcrm", "name": "FlexCRM", "type": "php-package", "status": "active",
         "enabled": True, "local_path": str(flex)},
        {"id": "azguard", "name": "AzGuard", "type": "php-package", "status": "active",
         "enabled": True, "local_path": str(az)},
    ]
    if with_doc:
        vault = base / "vault" / "FlexCRM"
        vault.mkdir(parents=True, exist_ok=True)
        (vault / "FlexCRM.md").write_text(
            "---\ntype: project\nuses: [AzGuard, GetChat]\nused_by: []\n---\n# FlexCRM\n",
            encoding="utf-8")
        projects[0]["vault_path"] = str(vault)
    write_maind_config(root, graph={"adapter": "federation"}, projects=projects)
    config, _ = load_config(env)
    return env, config


class TestDerive(unittest.TestCase):
    def test_provider_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            providers = derive.build_provider_index(env, config)
            self.assertEqual(providers["axioma-studio/azguard-core"], "azguard")
            self.assertEqual(providers["axioma-studio/flexcrm"], "flexcrm")

    def test_resolve_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            self.assertEqual(derive.resolve_project("AzGuard", config), ("azguard", True))
            # GetChat — не в .maind.json: алиас, но registered=False
            self.assertEqual(derive.resolve_project("GetChat", config), ("getchat", False))

    def test_code_creates_cross_depends_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            stats = {s["id"]: s for s in derive.derive_all(env, config)}
            self.assertGreaterEqual(stats["flexcrm"]["by_via"]["code"], 3)
            # laravel/framework отфильтрован, остался только first-party
            g = federation.project_graph(env, config, config["projects"][0])
            self.assertIn("package:axioma-studio/azguard-core", g.nodes)
            self.assertNotIn("package:laravel/framework", g.nodes)
            # cross depends_on flexcrm→azguard
            outs = {d for d in g.adj.get("project:flexcrm", {})}
            self.assertIn("project:azguard", outs)

    def test_federated_query_after_derive(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            derive.derive_all(env, config)
            res = federation.Federation(env, config).query("project:flexcrm", depth=1)
            self.assertIn("project:azguard", {n["id"] for n in res["neighbors"]})

    def test_doc_plane_from_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, with_doc=True)
            stats = {s["id"]: s for s in derive.derive_all(env, config)}
            self.assertEqual(stats["flexcrm"]["by_via"]["doc"], 2)  # AzGuard + GetChat
            g = federation.project_graph(env, config, config["projects"][0])
            e = g.adj["project:flexcrm"]["project:getchat"]
            self.assertEqual(e["attrs"]["via"], "doc")
            self.assertFalse(g.nodes["project:getchat"]["attrs"].get("registered"))

    def test_override_plane(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, with_override=True)
            stats = {s["id"]: s for s in derive.derive_all(env, config)}
            self.assertEqual(stats["flexcrm"]["by_via"]["override"], 1)
            g = federation.project_graph(env, config, config["projects"][0])
            e = g.adj["project:flexcrm"]["project:getchat"]
            self.assertEqual(e["attrs"]["via"], "override")
            self.assertEqual(e["attrs"]["note"], "REST corex/messenger")


if __name__ == "__main__":
    unittest.main()
