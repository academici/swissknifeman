"""P3.2 Claude publication compatibility and semantic-catalog tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util.repo import find_repo_root
from skiller.host import load_host
from skiller.publication import PublicationCatalog, build_publication_catalog
from skiller.registry import (build_claude_publication, build_plugin_manifests,
                              build_registry)
from tests.fixtures import hub_indexes, make_registry


def _artifact_digest(artifacts, repo_root):
    digest = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: item.target):
        digest.update(artifact.target.relative_to(repo_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(artifact.managed_bytes)
        digest.update(b"\0")
    return digest.hexdigest()


class TestPublicationCatalog(unittest.TestCase):
    def test_catalog_is_immutable_and_provider_path_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_registry(Path(tmp))
            registry, metadata, buckets = build_registry(env)
            catalog = build_publication_catalog(
                registry=registry, bucket_meta=metadata, bucket_dirs=buckets,
                core_skills=(), core_plugin="core", package_version="0.1.0", siblings=(),
                generate_skill_description="Meta-skill")
            self.assertIsInstance(catalog, PublicationCatalog)
            self.assertEqual([unit.unit_id for unit in catalog.units],
                             ["bucket:devops", "bucket:php", "bucket:quality", "generate-skill"])
            self.assertEqual([skill.semantic_id for skill in catalog.skills],
                             ["devops/docker", "php/code-style", "php/laravel-conventions",
                              "quality/test-writer"])
            self.assertEqual(catalog.package_version, "0.1.0")
            with self.assertRaises(AttributeError):
                catalog.package_version = "9.9.9"  # type: ignore[misc]

    def test_renderer_is_repeatable_and_legacy_writer_uses_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_registry(Path(tmp))
            registry, metadata, buckets = build_registry(env)
            first = build_claude_publication(env, metadata, buckets, registry)
            second = build_claude_publication(env, metadata, buckets, registry)
            self.assertEqual(first, second)
            manifest_data = build_plugin_manifests(env, metadata, buckets, registry)
            self.assertEqual([(item.target, json.loads(item.managed_bytes.decode("utf-8")))
                              for item in first], manifest_data)
            self.assertEqual({item.package_version for item in first}, {"0.1.0"})
            self.assertTrue(all(item.source_hash.startswith("sha256:") for item in first))
            self.assertTrue(all(item.rendered_hash.startswith("sha256:") for item in first))


@unittest.skipUnless(load_host(Path(__file__).resolve().parents[1]).root,
                     "golden includes host publications (standalone)")
class TestClaudePublicationGolden(unittest.TestCase):
    def test_repository_claude_artifacts_match_pre_refactor_byte_golden(self):
        package_root = Path(__file__).resolve().parents[1]
        repo_root = find_repo_root(package_root) or package_root
        from skiller.common import Env
        env = Env(package_root)
        registry, metadata, buckets = build_registry(env)
        artifacts = build_claude_publication(env, metadata, buckets, registry)
        golden_path = Path(__file__).parent / "fixtures_data" / "claude-publication-golden.json"
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        self.assertEqual(len(artifacts), golden["artifact_count"])
        self.assertEqual(_artifact_digest(artifacts, repo_root), golden["byte_digest"])


class TestRepositoryBootstrapExclusion(unittest.TestCase):
    """Host bootstrap identities live outside the package and never enter its registry."""

    def test_host_bootstrap_is_absent_from_registry_and_publication(self):
        package_root = Path(__file__).resolve().parents[1]
        from skiller.common import Env
        env = Env(package_root)
        registry, metadata, buckets = build_registry(env)
        private_members = [item for item in registry["skills"]
                           if item["bucket"] == "repository-bootstrap"]
        self.assertEqual(private_members, [])
        self.assertNotIn("repository-bootstrap", buckets)

        artifacts = build_claude_publication(env, metadata, buckets, registry)
        marketplace = hub_indexes(env, metadata, buckets, registry)["claude"]
        names = {plugin["name"] for plugin in marketplace["plugins"]}
        self.assertNotIn("repository-bootstrap", names)
        for artifact in artifacts:
            self.assertNotIn("repository-bootstrap", artifact.target.as_posix())


if __name__ == "__main__":
    unittest.main()
