"""P3.3 native Codex projection conformance tests."""
import json
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.publication import load_repository_bootstrap_config
from skiller.registry import (build_codex_publication, build_registry,
                              build_repository_bootstrap_publication)


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
        # D27: per-unit manifest version now comes from configs/publication-versions.json —
        # a bumped unit (core/skm) diverges from the frozen default every other unit keeps.
        versions = json.loads((self.repo_root / "packages" / "skiller" / "configs" /
                               "publication-versions.json").read_text(encoding="utf-8"))
        unit_versions, default_version = versions["units"], versions["default_unit_version"]
        for item in manifests:
            data = json.loads(item.managed_bytes)
            self.assertTrue(set(self.golden["required_plugin_fields"]).issubset(data))
            self.assertEqual(data["version"], unit_versions.get(data["name"], default_version),
                             data["name"])

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

    def test_core_bundle_keeps_runtime_tree_and_consumer_exclusions(self):
        core_root, core = self._core_artifacts()
        runtime_path = Path(
            "skills/general/plan-protocol/snippets/plan-template.md")
        excluded_path = Path(
            "skills/general/plan-protocol/SKILL.ru.md")
        expected_bytes = (
            self.package_root / "skills/general/plan-protocol/snippets/plan-template.md"
        ).read_bytes()
        artifacts = {
            item.target.relative_to(core_root): item.managed_bytes
            for item in core
        }

        self.assertEqual(artifacts[runtime_path], expected_bytes)
        self.assertNotIn(excluded_path, artifacts)
        with tempfile.TemporaryDirectory() as tmp:
            cached = Path(tmp) / "cached-core"
            for relative, managed_bytes in artifacts.items():
                target = cached / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(managed_bytes)
            self.assertEqual((cached / runtime_path).read_bytes(), expected_bytes)
            self.assertFalse((cached / excluded_path).exists())

    def test_repository_core_cache_matches_current_catalog(self):
        core_root, core = self._core_artifacts()
        self._assert_core_cache_matches_catalog(core_root, core_root, core)

    def test_repository_bootstrap_bucket_never_leaks_into_normal_codex_publication(self):
        """P1.2 (D31): the private/source-only bucket must never surface as an ordinary
        Codex unit/plugin/marketplace entry, even though `build_registry` indexes its 13
        members for ownership/hash lookup."""
        member_ids = {skill["path"] for skill in self.registry["skills"]
                      if skill["bucket"] == "repository-bootstrap"}
        self.assertEqual(len(member_ids), 13)
        first = build_codex_publication(self.env, self.metadata, self.buckets, self.registry)
        marketplace = json.loads(next(item.managed_bytes for item in first
                                      if item.target.name == "marketplace.json"))
        names = {plugin["name"] for plugin in marketplace["plugins"]}
        self.assertNotIn("repository-bootstrap", names)
        self.assertFalse(any(item.publication_unit_id in {"bucket:repository-bootstrap",
                                                           "repository-bootstrap"}
                             for item in first))
        for item in first:
            self.assertNotIn("repository-bootstrap", item.target.as_posix())


class TestRepositoryBootstrapPublication(unittest.TestCase):
    """P1.2 (D31/D38): the sole root-bootstrap producer — 26 thin projections + 1 lock."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.package_root = self.repo_root / "packages" / "skiller"
        self.env = Env(self.package_root)
        self.config = load_repository_bootstrap_config(self.package_root)

    def test_config_names_exactly_thirteen_sorted_unique_identities(self):
        identities = self.config["identities"]
        self.assertEqual(len(identities), 13)
        self.assertEqual(identities, sorted(identities))
        self.assertEqual(len(set(identities)), 13)

    def test_renders_exactly_26_projections_plus_one_lock_with_no_copied_body(self):
        artifacts = build_repository_bootstrap_publication(self.env)
        self.assertEqual(len(artifacts), 27)
        by_provider = {}
        lock_artifact = None
        for artifact in artifacts:
            if artifact.provider == "lock":
                lock_artifact = artifact
                continue
            by_provider.setdefault(artifact.provider, set()).add(artifact.identity)
        self.assertEqual(by_provider.keys(), {"claude", "codex"})
        self.assertEqual(by_provider["claude"], set(self.config["identities"]))
        self.assertEqual(by_provider["codex"], set(self.config["identities"]))
        self.assertIsNotNone(lock_artifact)
        self.assertEqual(lock_artifact.target, self.repo_root / self.config["lock_path"])
        lock_data = json.loads(lock_artifact.managed_bytes)
        self.assertEqual(len(lock_data["records"]), 26)
        for artifact in artifacts:
            if artifact.provider == "lock":
                continue
            body = artifact.managed_bytes.decode("utf-8")
            canonical = self.package_root / "skills" / "repository-bootstrap" / \
                artifact.identity / "SKILL.md"
            canonical_body = canonical.read_text(encoding="utf-8")
            # The projection is thin: it must not carry the canonical file's own prose body
            # (checked via a body-only marker line unlikely to appear in a pointer stub).
            self.assertNotIn("## Provenance (root-bootstrap, P1.2)", body)
            self.assertIn(f"canonical: packages/skiller/skills/repository-bootstrap/"
                          f"{artifact.identity}/SKILL.md", body)
            self.assertIn("## Provenance (root-bootstrap, P1.2)", canonical_body)

    def test_targets_are_exactly_the_declared_26_and_globally_unique(self):
        artifacts = build_repository_bootstrap_publication(self.env)
        targets = [item.target for item in artifacts if item.provider != "lock"]
        self.assertEqual(len(targets), 26)
        self.assertEqual(len(set(targets)), 26)
        expected = set()
        for identity in self.config["identities"]:
            expected.add(self.repo_root / ".claude" / "skills" / identity / "SKILL.md")
            expected.add(self.repo_root / ".agents" / "skills" / identity / "SKILL.md")
        self.assertEqual(set(targets), expected)

    def test_second_render_is_byte_identical_noop(self):
        first = build_repository_bootstrap_publication(self.env)
        second = build_repository_bootstrap_publication(self.env)
        self.assertEqual([(a.target, a.managed_bytes) for a in first],
                         [(a.target, a.managed_bytes) for a in second])


if __name__ == "__main__":
    unittest.main()
