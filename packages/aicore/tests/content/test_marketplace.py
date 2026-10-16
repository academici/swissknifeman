"""aicore.content.marketplace: the hub indexes assembled from provides.plugins of the modules."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from aicore import cli
from aicore.content import marketplace

CATALOG = {
    "schema": "urn:swissknifeman:aicore:plugin-catalog:v1",
    "marketplace": {"name": "demo", "owner": {"name": "Owner", "email": "owner@example.com"}},
    "plugins": [
        {"name": "zeta", "source": "skills/zeta", "description": "Zeta", "category": "dev", "tags": ["z"],
         "codex": {"install_policy": "explicit", "auth": "none"}},
        {"name": "core", "source": "./", "skills": ["skills/zeta/one"], "description": "Core",
         "category": "meta", "tags": ["core", "always-on"],
         "codex": {"source": "adapters/codex/core", "description": "Core for Codex", "category": "meta",
                   "tags": ["core"], "install_policy": "explicit", "auth": "none"}},
        {"name": "old", "source": "./", "skills": ["skills/zeta/one"], "description": "Alias",
         "category": "", "tags": [], "alias_of": "zeta"},
    ],
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class Hub:
    def __init__(self, test):
        temporary = tempfile.TemporaryDirectory()
        test.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.packages = self.root / "packages"

    def unit(self, unit_id, plugins, folder=None):
        root = self.packages / (folder or unit_id)
        write_json(root / "unit.json", {"id": unit_id, "provides": {"plugins": plugins}})
        return root

    def plugin(self, root, relative, name, *, codex, **fields):
        write_json(root / relative / ".claude-plugin" / "plugin.json", {"name": name, **fields})
        if codex:
            write_json(root / relative / ".codex-plugin" / "plugin.json", {"name": name})

    def units(self):
        return marketplace.discover({"SKM_UNITS_PATH": str(self.packages)})

    def assemble(self, **kwargs):
        return {key: json.loads(value) for key, value in marketplace.assemble(self.units(), self.root, **kwargs).items()}


class AssembleCase(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(self)

    def test_manifest_and_source_forms(self):
        alpha = self.hub.unit("alpha", [{"name": "alpha", "manifest": ".claude-plugin/plugin.json"}])
        self.hub.plugin(alpha, ".", "alpha", codex=True, description="Alpha", category="tools",
                        keywords=["a", "b"])
        beta = self.hub.unit("beta", [{"name": "alias", "source": "aliases/alias"}])
        self.hub.plugin(beta, "aliases/alias", "alias", codex=False, description="Alias")
        result = self.hub.assemble(name="demo", owner={"name": "Owner", "email": "o@example.com"})
        claude = result[marketplace.CLAUDE_INDEX]
        self.assertEqual(claude["name"], "demo")
        self.assertEqual(claude["owner"], {"name": "Owner", "email": "o@example.com"})
        self.assertEqual(claude["plugins"], [
            {"name": "alias", "source": "./packages/beta/aliases/alias", "description": "Alias",
             "category": "ecosystem", "tags": [], "package": "beta"},
            {"name": "alpha", "source": "./packages/alpha", "description": "Alpha", "category": "tools",
             "tags": ["a", "b"], "package": "alpha"}])
        self.assertEqual(result[marketplace.CODEX_INDEX], {"name": "demo", "plugins": [
            {"name": "alpha", "source": "./packages/alpha", "description": "Alpha", "category": "tools",
             "tags": ["a", "b"], "install_policy": "explicit", "auth": "none"}]})

    def test_catalog_entries_get_hub_paths_package_and_codex_fields(self):
        root = self.hub.unit("lib", [{"name": "lib", "catalog": ".claude-plugin/catalog.json"}])
        write_json(root / ".claude-plugin" / "catalog.json", CATALOG)
        result = self.hub.assemble()
        claude = result[marketplace.CLAUDE_INDEX]
        self.assertEqual(claude["name"], "demo")
        by_name = {entry["name"]: entry for entry in claude["plugins"]}
        self.assertEqual(list(by_name), ["core", "old", "zeta"])
        self.assertEqual(by_name["zeta"], {
            "name": "zeta", "source": "./packages/lib/skills/zeta", "description": "Zeta", "category": "dev",
            "tags": ["z"], "package": "lib"})
        self.assertEqual(list(by_name["core"]), ["name", "source", "skills", "description", "category", "tags",
                                                 "package"])
        self.assertEqual(by_name["core"]["source"], "./")
        self.assertEqual(by_name["core"]["skills"], ["./packages/lib/skills/zeta/one"])
        self.assertEqual(list(by_name["old"])[-2:], ["package", "alias_of"])
        codex = {entry["name"]: entry for entry in result[marketplace.CODEX_INDEX]["plugins"]}
        self.assertEqual(sorted(codex), ["core", "zeta"])
        self.assertEqual(codex["core"], {
            "name": "core", "source": "./packages/lib/adapters/codex/core", "description": "Core for Codex",
            "category": "meta", "tags": ["core"], "install_policy": "explicit", "auth": "none"})
        self.assertEqual(codex["zeta"]["source"], "./packages/lib/skills/zeta")

    def test_bytes_are_two_space_json_with_trailing_newline(self):
        root = self.hub.unit("lib", [{"name": "lib", "catalog": ".claude-plugin/catalog.json"}])
        write_json(root / ".claude-plugin" / "catalog.json", CATALOG)
        data = marketplace.assemble(self.hub.units(), self.hub.root)[marketplace.CODEX_INDEX]
        self.assertTrue(data.endswith(b"}\n"))
        self.assertTrue(data.startswith(b'{\n  "name": "demo",\n  "plugins": [\n'))

    def test_duplicate_name_is_refused(self):
        for unit_id in ("one", "two"):
            root = self.hub.unit(unit_id, [{"name": "same", "manifest": ".claude-plugin/plugin.json"}])
            self.hub.plugin(root, ".", "same", codex=False)
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble(name="demo", owner={"name": "O", "email": "e"})
        self.assertEqual(caught.exception.code, "MARKETPLACE_DUPLICATE")
        self.assertTrue(str(caught.exception).startswith("MARKETPLACE_DUPLICATE: "))

    def test_manifest_naming_another_plugin_is_refused(self):
        root = self.hub.unit("one", [{"name": "one", "manifest": ".claude-plugin/plugin.json"}])
        self.hub.plugin(root, ".", "other", codex=False)
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble(name="demo", owner={"name": "O", "email": "e"})
        self.assertEqual(caught.exception.code, "MARKETPLACE_NAME_MISMATCH")

    def test_invalid_or_missing_catalog_is_refused(self):
        root = self.hub.unit("lib", [{"name": "lib", "catalog": "catalog.json"}])
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble()
        self.assertEqual(caught.exception.code, "MARKETPLACE_CATALOG_MISSING")
        write_json(root / "catalog.json", {"schema": CATALOG["schema"], "plugins": [{"name": "x"}]})
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble()
        self.assertEqual(caught.exception.code, "MARKETPLACE_CATALOG_INVALID")

    def test_plugin_outside_the_hub_is_refused(self):
        root = self.hub.unit("lib", [{"name": "lib", "source": "../../../outside"}])
        self.hub.plugin(root, "../../../outside", "lib", codex=False)
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble(name="demo", owner={"name": "O", "email": "e"})
        self.assertEqual(caught.exception.code, "MARKETPLACE_SOURCE_OUTSIDE")

    def test_identity_comes_from_arguments_then_umbrella_then_catalog(self):
        root = self.hub.unit("lib", [{"name": "lib", "catalog": "catalog.json"}])
        write_json(root / "catalog.json", CATALOG)
        self.assertEqual(self.hub.assemble()[marketplace.CLAUDE_INDEX]["name"], "demo")
        write_json(self.hub.root / "configs" / "umbrella.json", {
            "marketplace": {"name": "umbrella", "owner": {"name": "U", "email": "u@example.com"}}})
        claude = self.hub.assemble()[marketplace.CLAUDE_INDEX]
        self.assertEqual((claude["name"], claude["owner"]["name"]), ("umbrella", "U"))
        claude = self.hub.assemble(name="given", owner={"name": "G", "email": "g@example.com"})[marketplace.CLAUDE_INDEX]
        self.assertEqual((claude["name"], claude["owner"]["name"]), ("given", "G"))

    def test_the_hub_root_ships_its_own_plugins(self):
        alpha = self.hub.unit("alpha", [{"name": "alpha", "manifest": ".claude-plugin/plugin.json"}])
        self.hub.plugin(alpha, ".", "alpha", codex=False)
        self.hub.plugin(self.hub.root, "plugins/face", "face", codex=True, description="Face")
        write_json(self.hub.root / "configs" / "umbrella.json", {
            "marketplace": {"name": "demo", "owner": {"name": "O", "email": "e"}},
            "plugins": [{"name": "face", "manifest": "plugins/face/.claude-plugin/plugin.json"}]})
        result = self.hub.assemble()
        face = [entry for entry in result[marketplace.CLAUDE_INDEX]["plugins"] if entry["name"] == "face"]
        self.assertEqual([{"name": "face", "source": "./plugins/face", "description": "Face",
                           "category": "ecosystem", "tags": [], "package": "root"}], face)
        self.assertEqual(["face"], [entry["name"] for entry in result[marketplace.CODEX_INDEX]["plugins"]])

    def test_a_hub_plugin_list_must_hold_manifest_or_source_entries(self):
        for plugins in ({"name": "x"}, [{"name": "x", "catalog": "c.json"}], ["x"]):
            write_json(self.hub.root / "configs" / "umbrella.json", {"plugins": plugins})
            with self.assertRaises(marketplace.MarketplaceError) as caught:
                self.hub.assemble(name="demo", owner={"name": "O", "email": "e"})
            self.assertEqual(caught.exception.code, "MARKETPLACE_HUB_PLUGINS_INVALID")

    def test_a_hub_plugin_named_like_a_module_plugin_is_a_duplicate(self):
        alpha = self.hub.unit("alpha", [{"name": "same", "manifest": ".claude-plugin/plugin.json"}])
        self.hub.plugin(alpha, ".", "same", codex=False)
        self.hub.plugin(self.hub.root, "plugins/same", "same", codex=False)
        write_json(self.hub.root / "configs" / "umbrella.json", {
            "plugins": [{"name": "same", "source": "plugins/same"}]})
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble(name="demo", owner={"name": "O", "email": "e"})
        self.assertEqual(caught.exception.code, "MARKETPLACE_DUPLICATE")

    def test_identity_is_required(self):
        root = self.hub.unit("one", [{"name": "one", "manifest": ".claude-plugin/plugin.json"}])
        self.hub.plugin(root, ".", "one", codex=False)
        with self.assertRaises(marketplace.MarketplaceError) as caught:
            self.hub.assemble()
        self.assertEqual(caught.exception.code, "MARKETPLACE_IDENTITY_MISSING")

    def test_supplied_catalog_bytes_replace_the_file(self):
        root = self.hub.unit("lib", [{"name": "lib", "catalog": "catalog.json"}])
        write_json(root / "catalog.json", CATALOG)
        changed = dict(CATALOG, plugins=CATALOG["plugins"][:1])
        result = self.hub.assemble(catalogs={root / "catalog.json": json.dumps(changed).encode()})
        self.assertEqual([p["name"] for p in result[marketplace.CLAUDE_INDEX]["plugins"]], ["zeta"])


class BuildCommandCase(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(self)
        root = self.hub.unit("lib", [{"name": "lib", "catalog": "catalog.json"}])
        write_json(root / "catalog.json", CATALOG)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["marketplace", *args], env={}, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_build_writes_and_check_passes_then_detects_drift(self):
        code, out, err = self.run_cli("build", "--hub", str(self.hub.root), "--check")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT", err)
        self.assertIn(marketplace.CLAUDE_INDEX, err)
        code, out, err = self.run_cli("build", "--hub", str(self.hub.root))
        self.assertEqual((code, err), (0, ""))
        self.assertTrue((self.hub.root / marketplace.CODEX_INDEX).is_file())
        self.assertEqual(self.run_cli("build", "--hub", str(self.hub.root), "--check")[0], 0)
        (self.hub.root / marketplace.CLAUDE_INDEX).write_text("{}\n", encoding="utf-8")
        code, out, err = self.run_cli("build", "--hub", str(self.hub.root), "--check")
        self.assertEqual(code, 1)
        self.assertIn(marketplace.CLAUDE_INDEX, err)
        self.assertNotIn(marketplace.CODEX_INDEX, err)

    def test_refusal_is_exit_one_with_code(self):
        write_json(self.hub.packages / "lib" / "catalog.json", {"plugins": []})
        code, out, err = self.run_cli("build", "--hub", str(self.hub.root), "--check")
        self.assertEqual(code, 1)
        self.assertIn("MARKETPLACE_CATALOG_INVALID", err)

    def test_missing_hub_is_a_usage_error(self):
        self.assertEqual(self.run_cli("build")[0], 2)


if __name__ == "__main__":
    unittest.main()
