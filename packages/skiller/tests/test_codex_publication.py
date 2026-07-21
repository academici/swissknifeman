"""P3.3 native Codex projection conformance tests."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.registry import build_codex_publication, build_registry


class TestCodexPublication(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.package_root = self.repo_root / "packages" / "skiller"
        self.env = Env(self.package_root)
        self.registry, self.metadata, self.buckets = build_registry(self.env)
        self.golden = json.loads((Path(__file__).parent / "fixtures_data" /
                                  "codex-publication-golden.json").read_text(encoding="utf-8"))

    def _core_artifacts(self):
        """Return the renderer-derived core cache contract, never cached bytes."""
        artifacts = build_codex_publication(self.env, self.metadata, self.buckets, self.registry)
        core_root = self.package_root / "adapters" / "codex" / "core"
        core = [item for item in artifacts if item.target.is_relative_to(core_root)]
        return core_root, core

    def _assert_core_cache_matches_catalog(self, cache_root, core_root, artifacts):
        """Every declared cached core artifact, including its lock, matches the catalog."""
        expected = {
            item.target.relative_to(core_root): item.managed_bytes
            for item in artifacts
        }
        actual = {
            path.relative_to(cache_root): path.read_bytes()
            for path in cache_root.rglob("*") if path.is_file()
        }
        self.assertEqual(set(actual), set(expected))
        for relative_path, managed_bytes in expected.items():
            self.assertEqual(actual[relative_path], managed_bytes, relative_path.as_posix())

    def test_native_projection_is_deterministic_and_contract_shaped(self):
        first = build_codex_publication(self.env, self.metadata, self.buckets, self.registry)
        second = build_codex_publication(self.env, self.metadata, self.buckets, self.registry)
        self.assertEqual(first, second)
        paths = [item.target.relative_to(self.repo_root).as_posix() for item in first]
        self.assertIn(".agents/plugins/marketplace.json", paths)
        marketplace = json.loads(next(item.managed_bytes for item in first
                                      if item.target.name == "marketplace.json"))
        self.assertEqual(marketplace["name"], self.golden["marketplace_name"])
        names = [plugin["name"] for plugin in marketplace["plugins"]]
        self.assertEqual(names, sorted(names))
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("task", names)
        task = next(plugin for plugin in marketplace["plugins"]
                    if plugin["name"] == "task")
        self.assertEqual(task["source"], "./packages/task")
        for plugin in marketplace["plugins"]:
            self.assertTrue(set(self.golden["required_marketplace_fields"]).issubset(plugin))
            self.assertTrue(plugin["source"].startswith("./"))
            self.assertNotIn("..", Path(plugin["source"]).parts)
        manifests = [item for item in first if item.target.name == "plugin.json"]
        self.assertTrue(manifests)
        for item in manifests:
            data = json.loads(item.managed_bytes)
            self.assertTrue(set(self.golden["required_plugin_fields"]).issubset(data))
            self.assertEqual(data["version"], "0.4.0")

    def test_core_bundle_is_allowlisted_and_cache_contained(self):
        core_root, core = self._core_artifacts()
        skill_paths = sorted(item.target.relative_to(core_root).as_posix() for item in core
                             if item.target.name == "SKILL.md")
        expected = sorted(f"skills/{member}/SKILL.md" for member in self.golden["core_members"])
        self.assertEqual(skill_paths, expected)
        self.assertTrue(all("SKILL.ru.md" not in path and "upstream.json" not in path
                            for path in skill_paths))
        with tempfile.TemporaryDirectory() as tmp:
            cached = Path(tmp) / "cached-core"
            for item in core:
                target = cached / item.target.relative_to(core_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.managed_bytes)
            self.assertTrue((cached / ".codex-plugin/plugin.json").is_file())
            self.assertTrue(all((cached / path).is_file() for path in expected))
            self.assertTrue((cached / "publication-lock.json").is_file())
            self.assertFalse((cached / "SKILL.ru.md").exists())
            self._assert_core_cache_matches_catalog(cached, core_root, core)

            stale = cached / "skills" / "general" / "plan-protocol" / "SKILL.md"
            stale.write_bytes(stale.read_bytes() + b"\n<!-- deliberately stale -->\n")
            with self.assertRaises(AssertionError):
                self._assert_core_cache_matches_catalog(cached, core_root, core)

    def test_repository_core_cache_matches_current_catalog(self):
        core_root, core = self._core_artifacts()
        self._assert_core_cache_matches_catalog(core_root, core_root, core)


if __name__ == "__main__":
    unittest.main()
