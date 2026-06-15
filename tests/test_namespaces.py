"""Тесты namespaces: правила membership/shares + изоляция связей в derive/federation,
валидация конфига, выборка по namespace, команда `maind namespaces`."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import derive, federation, namespaces, projects as projects_mod
from maind.config import load_config, validate_config
from tests.fixtures import capture, make_repo, write_maind_config


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup(tmp, flex_ns=None, az_ns=None):
    """flexcrm требует azguard-core. namespaces задаются через flex_ns/az_ns."""
    root, env = make_repo(tmp)
    base = Path(tmp)
    flex, az = base / "flexcrm", base / "azguard"
    _write(flex / "composer.json",
           {"name": "axioma-studio/flexcrm",
            "require": {"axioma-studio/azguard-core": "@dev"}})
    _write(az / "composer.json", {"name": "axioma-studio/azguard"})
    _write(az / "packages" / "core" / "composer.json",
           {"name": "axioma-studio/azguard-core"})
    flexp = {"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
             "status": "active", "enabled": True, "local_path": str(flex)}
    azp = {"id": "azguard", "name": "AzGuard", "type": "php-package",
           "status": "active", "enabled": True, "local_path": str(az)}
    if flex_ns is not None:
        flexp["namespaces"] = flex_ns
    if az_ns is not None:
        azp["namespaces"] = az_ns
    write_maind_config(root, graph={"adapter": "federation"}, projects=[flexp, azp])
    config, _ = load_config(env)
    return env, config


def _flex_neighbors(env, config):
    res = federation.Federation(env, config).query("project:flexcrm", depth=1)
    return {n["id"] for n in res["neighbors"]}


# ── правила membership ───────────────────────────────────────────────────────
class TestRules(unittest.TestCase):
    def test_default_when_absent(self):
        self.assertEqual(namespaces.namespaces_of({"id": "x"}), {"default"})
        self.assertEqual(namespaces.namespaces_of({"id": "x", "namespaces": []}),
                         {"default"})

    def test_shares(self):
        a = {"namespaces": ["axioma"]}
        b = {"namespaces": ["axioma", "other"]}
        c = {"namespaces": ["other"]}
        self.assertTrue(namespaces.shares(a, b))
        self.assertFalse(namespaces.shares(a, c))
        # default ↔ default
        self.assertTrue(namespaces.shares({"id": "x"}, {"id": "y"}))

    def test_wildcard_shares_with_all(self):
        star = {"namespaces": ["*"]}
        self.assertTrue(namespaces.shares(star, {"namespaces": ["axioma"]}))
        self.assertTrue(namespaces.shares({"namespaces": ["other"]}, star))

    def test_link_allowed_unregistered_target(self):
        config = {"projects": [{"id": "flexcrm", "namespaces": ["axioma"]}]}
        flex = config["projects"][0]
        # незарегистрированный getchat → не режем
        self.assertTrue(namespaces.link_allowed(flex, "getchat", config))

    def test_in_namespace(self):
        self.assertTrue(namespaces.in_namespace({"namespaces": ["*"]}, "anything"))
        self.assertTrue(namespaces.in_namespace({"namespaces": ["axioma"]}, "axioma"))
        self.assertFalse(namespaces.in_namespace({"namespaces": ["axioma"]}, "other"))
        self.assertTrue(namespaces.in_namespace({"id": "x"}, "default"))


# ── изоляция связей (derive + federation) ────────────────────────────────────
class TestIsolation(unittest.TestCase):
    def test_same_namespace_keeps_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, flex_ns=["axioma"], az_ns=["axioma"])
            derive.derive_all(env, config)
            self.assertIn("project:azguard", _flex_neighbors(env, config))

    def test_default_keeps_link_backward_compat(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)  # без namespaces → default ↔ default
            derive.derive_all(env, config)
            self.assertIn("project:azguard", _flex_neighbors(env, config))

    def test_different_namespace_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, flex_ns=["axioma"], az_ns=["other"])
            stats = {s["id"]: s for s in derive.derive_all(env, config)}
            # cross depends_on не построен — only own provided package остаётся
            self.assertNotIn("project:azguard", _flex_neighbors(env, config))
            g = federation.project_graph(env, config, config["projects"][0])
            self.assertNotIn("package:axioma-studio/azguard-core", g.nodes)
            # индекс cross-слоя пуст
            self.assertEqual(federation.rebuild_index(env, config)["cross_edges"], 0)
            # стор azguard всё ещё имеет свой пакет (внутри проекта, не cross)
            self.assertGreaterEqual(stats["azguard"]["nodes"], 1)

    def test_wildcard_bridges_across_namespaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, flex_ns=["axioma"], az_ns=["*"])
            derive.derive_all(env, config)
            self.assertIn("project:azguard", _flex_neighbors(env, config))

    def test_cross_view_filtered_by_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, flex_ns=["axioma"], az_ns=["axioma"])
            derive.derive_all(env, config)
            fed = federation.Federation(env, config)
            self.assertTrue(fed.cross("axioma")["nodes"])
            self.assertFalse(fed.cross("other")["nodes"])


# ── валидация конфига ────────────────────────────────────────────────────────
class TestValidation(unittest.TestCase):
    def test_namespaces_must_be_list_of_strings(self):
        cfg = {"projects": [{"id": "x", "namespaces": "axioma"}]}
        with self.assertRaises(SystemExit):
            validate_config(cfg, "x.json")
        cfg2 = {"projects": [{"id": "x", "namespaces": [1, 2]}]}
        with self.assertRaises(SystemExit):
            validate_config(cfg2, "x.json")

    def test_valid_namespaces_pass(self):
        cfg = {"namespaces": {"axioma": {"name": "Axioma"}},
               "projects": [{"id": "x", "namespaces": ["axioma", "*"]}]}
        validate_config(cfg, "x.json")  # не должно бросать


# ── выборка и команда ────────────────────────────────────────────────────────
class TestSelectionAndCommand(unittest.TestCase):
    def test_select_projects_by_namespace(self):
        from maind.sync import select_projects
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, flex_ns=["axioma"], az_ns=["other"])
            sel = select_projects(env, config, {"namespace": "axioma"})
            self.assertEqual([p["id"] for p in sel], ["flexcrm"])

    def test_namespaces_command_lists_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp, flex_ns=["axioma"], az_ns=["*"])
            _, out = capture(projects_mod.cmd_namespaces, env, ["--json"])
            data = json.loads(out)
            self.assertIn("flexcrm", data["axioma"]["members"])
            self.assertIn("azguard", data["axioma"]["wildcard"])


if __name__ == "__main__":
    unittest.main()
