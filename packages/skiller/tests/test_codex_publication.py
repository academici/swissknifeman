"""P3.3 native Codex projection conformance tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util.repo import find_repo_root
from skiller.common import Env
from skiller.host import load_host
from skiller.publication import (
    assert_root_bootstrap_set_completeness, load_repository_bootstrap_config,
    render_repository_bootstrap_projections)
from aicore.content.publication import skill_runtime_files as _codex_skill_runtime_files
from skiller.registry import (build_codex_publication, build_registry,
                              build_repository_bootstrap_publication, _sibling_plugins)


class TestCodexPublication(unittest.TestCase):
    def setUp(self):
        self.package_root = Path(__file__).resolve().parents[1]
        self.repo_root = find_repo_root(self.package_root) or self.package_root
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
        for sibling in _sibling_plugins(self.repo_root, self.package_root,
                                         load_host(self.package_root)):
            if sibling.codex_supported:
                plugin = next(p for p in marketplace["plugins"] if p["name"] == sibling.name)
                self.assertEqual(plugin["source"], f"./{sibling.source_path}")
        for plugin in marketplace["plugins"]:
            self.assertTrue(set(self.golden["required_marketplace_fields"]).issubset(plugin))
            self.assertTrue(plugin["source"].startswith("./"))
            self.assertNotIn("..", Path(plugin["source"]).parts)
        manifests = [item for item in first if item.target.name == "plugin.json"]
        self.assertTrue(manifests)
        # D27: per-unit manifest version now comes from configs/publication-versions.json —
        # a bumped unit (core/skm) diverges from the frozen default every other unit keeps.
        versions = json.loads((self.package_root / "configs" /
                               "publication-versions.json").read_text(encoding="utf-8"))
        unit_versions, default_version = versions["units"], versions["default_unit_version"]
        for item in manifests:
            data = json.loads(item.managed_bytes)
            self.assertTrue(set(self.golden["required_plugin_fields"]).issubset(data))
            self.assertEqual(data["version"], unit_versions.get(data["name"], default_version),
                             data["name"])

        blender = next(item for item in manifests
                       if json.loads(item.managed_bytes)["name"] == "blender")
        self.assertEqual(json.loads(blender.managed_bytes)["skills"],
                         ["./mcp-blender", "./version-gotchas"])

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

            stale = cached / "skills" / "general" / "anti-drift" / "SKILL.md"
            stale.write_bytes(stale.read_bytes() + b"\n<!-- deliberately stale -->\n")
            with self.assertRaises(AssertionError):
                self._assert_core_cache_matches_catalog(cached, core_root, core)

    def _general_anti_drift_root(self):
        """Resolve the opt-in general skill through its rendered native manifest."""
        source_root = self.package_root / "skills/general"
        artifacts = build_codex_publication(self.env, self.metadata, self.buckets, self.registry)
        manifest = next(item for item in artifacts
                        if item.target == source_root / ".codex-plugin/plugin.json")
        declared = json.loads(manifest.managed_bytes)["skills"]
        self.assertIn("./anti-drift", declared)
        self.assertNotIn("./plan-protocol", declared)
        return source_root / "anti-drift"

    def test_general_anti_drift_keeps_runtime_tree_and_consumer_exclusions(self):
        skill_root = self._general_anti_drift_root()
        files = _codex_skill_runtime_files(skill_root, source_root=skill_root.parent,
                                          plugin="general")
        artifacts = {path.relative_to(skill_root): path.read_bytes() for path in files}
        runtime_path = Path("snippets/claude-md-anti-drift.md")
        expected_bytes = (skill_root / runtime_path).read_bytes()
        self.assertEqual(artifacts[runtime_path], expected_bytes)
        self.assertNotIn(Path("SKILL.ru.md"), artifacts)
        self.assertNotIn(Path("upstream.json"), artifacts)
        with tempfile.TemporaryDirectory() as tmp:
            cached = Path(tmp) / "cached-general-anti-drift"
            for relative, managed_bytes in artifacts.items():
                target = cached / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(managed_bytes)
            self.assertEqual((cached / runtime_path).read_bytes(), expected_bytes)
            self.assertFalse((cached / "SKILL.ru.md").exists())

    def test_retirement_preserves_modified_files_and_removes_only_prior_owned_bytes(self):
        import tempfile
        from types import SimpleNamespace
        from skiller.registry import _prune_publication_artifacts
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "retired.md"
            old.write_bytes(b"owned")
            lock = root / "publication-lock.json"
            lock.write_text(json.dumps({"artifacts": [{"path": "retired.md",
                "rendered_hash": "sha256:" + hashlib.sha256(b"owned").hexdigest()}]}))
            artifacts = [SimpleNamespace(target=lock)]
            old.write_bytes(b"local change")
            with self.assertRaisesRegex(ValueError, "PUBLICATION_RETIRE_MODIFIED"):
                _prune_publication_artifacts(artifacts)
            self.assertEqual(old.read_bytes(), b"local change")
            old.write_bytes(b"owned")
            _prune_publication_artifacts(artifacts)
            self.assertFalse(old.exists())
            self.assertTrue(lock.exists())

    def test_repository_core_cache_matches_current_catalog(self):
        core_root, core = self._core_artifacts()
        self._assert_core_cache_matches_catalog(core_root, core_root, core)

    def test_repository_bootstrap_bucket_never_leaks_into_normal_codex_publication(self):
        """P1.2 (D31): the private/source-only bucket must never surface as an ordinary
        Codex unit/plugin/marketplace entry. Its sources now belong to the host."""
        member_ids = {skill["path"] for skill in self.registry["skills"]
                      if skill["bucket"] == "repository-bootstrap"}
        self.assertEqual(member_ids, set())
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


def _build_isolated_bootstrap_fixture(tmp):
    """Minimal repo_root/package_root pair with one class-A + one class-B identity, isolated
    from the real repo — used to prove the version/tuple discipline without touching real
    canon (P1.5 negative fixture: canon drift without a unit-version bump)."""
    repo_root = tmp
    package_root = tmp / "pkg"
    canon_dir = repo_root / "bootstrap" / "skills" / "alpha"
    canon_dir.mkdir(parents=True)
    (canon_dir / "SKILL.ru.md").write_text("RU body\n", encoding="utf-8")
    (canon_dir / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: Alpha desc\n---\n\nAlpha canon body.\n", encoding="utf-8")
    donor_dir = package_root / "skills" / "general" / "beta"
    donor_dir.mkdir(parents=True)
    (donor_dir / "SKILL.md").write_text(
        "---\nname: beta\ndescription: Beta desc\n---\n\nBeta canon body v1.\n", encoding="utf-8")
    (package_root / "configs").mkdir()
    (repo_root / "configs").mkdir(exist_ok=True)
    (repo_root / "configs" / "repository-bootstrap-skills.json").write_text(json.dumps({
        "schema_version": 2, "bucket": "repository-bootstrap",
        "publication_unit": "repository-bootstrap", "unit_version": "0.1.0",
        "lock_path": "bootstrap/publication-lock.json",
        "class_a_content_version": "0.1.0",
        "identities": [{"identity": "alpha", "canonical": "bootstrap/skills/alpha/SKILL.md"}],
        "class_b": [{
            "identity": "beta", "source_class": "public-bucket",
            "canonical": "pkg/skills/general/beta/SKILL.md",
            "providers": ["codex"], "asymmetry_reason": "test fixture",
            "precondition": "no enabled unit serves this identity",
        }],
    }), encoding="utf-8")
    (package_root / "configs" / "publication-versions.json").write_text(json.dumps({
        "default_unit_version": "0.1.0",
        "units": {},
    }), encoding="utf-8")
    (repo_root / "configs" / "skiller-host.json").write_text(
        json.dumps({"schema_version": 1, "bootstrap": "configs/repository-bootstrap-skills.json"}))
    (repo_root / ".git").mkdir()
    return repo_root, package_root


class ClassBCanonDriftCase(unittest.TestCase):
    """P1.5 negative fixture: editing the class-B canonical WITHOUT bumping the unit's
    version must yield different rendered bytes at the SAME `(name, version)` tuple — the
    generator always reflects live source; a stale committed target is therefore visible as
    drift under `registry --check`, never silently absorbed (D27 tuple/bytes discipline)."""

    def test_canon_edit_without_version_bump_changes_rendered_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, package_root = _build_isolated_bootstrap_fixture(Path(tmp))
            first = render_repository_bootstrap_projections(
                repo_root=repo_root, package_root=package_root)
            beta_first = next(a for a in first if a.identity == "beta" and a.provider == "codex")
            lock_first = next(a for a in first if a.provider == "lock")

            donor = package_root / "skills" / "general" / "beta" / "SKILL.md"
            donor.write_text(
                "---\nname: beta\ndescription: Beta desc\n---\n\nBeta canon body v2 EDITED.\n",
                encoding="utf-8")

            second = render_repository_bootstrap_projections(
                repo_root=repo_root, package_root=package_root)
            beta_second = next(a for a in second if a.identity == "beta" and a.provider == "codex")
            lock_second = next(a for a in second if a.provider == "lock")

            # same declared unit tuple (version untouched)…
            versions = json.loads((repo_root / "configs" /
                                   "repository-bootstrap-skills.json").read_text())
            self.assertEqual(versions["unit_version"], "0.1.0")
            # …but the rendered bytes AND lock hashes moved — never a same-tuple silent reuse.
            self.assertNotEqual(beta_first.managed_bytes, beta_second.managed_bytes)
            self.assertNotEqual(beta_first.rendered_hash, beta_second.rendered_hash)
            self.assertNotEqual(lock_first.managed_bytes, lock_second.managed_bytes)


@unittest.skipUnless(load_host(Path(__file__).resolve().parents[1]).bootstrap,
                     "no host bootstrap config (standalone)")
class TestRepositoryBootstrapPublication(unittest.TestCase):
    """P1.2 (D31/D38): the sole root-bootstrap producer — thin projections + 1 lock."""

    def setUp(self):
        self.package_root = Path(__file__).resolve().parents[1]
        self.repo_root = find_repo_root(self.package_root) or self.package_root
        self.env = Env(self.package_root)
        from skiller.host import load_host
        self.config = load_repository_bootstrap_config(self.repo_root, load_host(self.package_root))

    def test_config_names_exactly_fourteen_sorted_unique_identities(self):
        identities = [row["identity"] for row in self.config["identities"]]
        self.assertEqual(len(identities), 14)
        self.assertEqual(identities, sorted(identities))
        self.assertEqual(len(set(identities)), 14)

    def test_renders_exactly_28_class_a_projections_byte_identical_shape(self):
        artifacts = build_repository_bootstrap_publication(self.env)
        self.assertEqual(len(artifacts), 30)  # 28 class-A + 1 class-B + 1 lock
        by_provider = {}
        lock_artifact = None
        for artifact in artifacts:
            if artifact.provider == "lock":
                lock_artifact = artifact
                continue
            if artifact.identity == "workflow-craft":
                continue  # class-B (P1.5), asserted separately below
            by_provider.setdefault(artifact.provider, set()).add(artifact.identity)
        self.assertEqual(by_provider.keys(), {"claude", "codex"})
        self.assertEqual(by_provider["claude"], {row["identity"] for row in self.config["identities"]})
        self.assertEqual(by_provider["codex"], {row["identity"] for row in self.config["identities"]})
        self.assertIsNotNone(lock_artifact)
        self.assertEqual(lock_artifact.target, self.repo_root / self.config["lock_path"])
        lock_data = json.loads(lock_artifact.managed_bytes)
        self.assertEqual(len(lock_data["records"]), 29)  # 28 class-A + 1 class-B
        for artifact in artifacts:
            if artifact.provider == "lock" or artifact.identity == "workflow-craft":
                continue
            body = artifact.managed_bytes.decode("utf-8")
            record = next(row for row in self.config["identities"]
                          if row["identity"] == artifact.identity)
            canonical = self.repo_root / record["canonical"]
            canonical_body = canonical.read_text(encoding="utf-8")
            # The projection is thin: it must not carry the canonical file's own prose body
            # (checked via a body-only marker line unlikely to appear in a pointer stub).
            self.assertNotIn("## Provenance (root-bootstrap, P1.2)", body)
            self.assertIn(f"canonical: {record['canonical']}", body)
            self.assertIn("## Provenance (root-bootstrap, P1.2)", canonical_body)

    def test_targets_are_exactly_the_declared_29_and_globally_unique(self):
        artifacts = build_repository_bootstrap_publication(self.env)
        targets = [item.target for item in artifacts if item.provider != "lock"]
        self.assertEqual(len(targets), 29)  # 28 class-A + 1 class-B
        self.assertEqual(len(set(targets)), 29)
        expected = set()
        for row in self.config["identities"]:
            identity = row["identity"]
            expected.add(self.repo_root / ".claude" / "skills" / identity / "SKILL.md")
            expected.add(self.repo_root / ".agents" / "skills" / identity / "SKILL.md")
        expected.add(self.repo_root / ".agents" / "skills" / "workflow-craft" / "SKILL.md")
        self.assertEqual(set(targets), expected)

    def test_second_render_is_byte_identical_noop(self):
        first = build_repository_bootstrap_publication(self.env)
        second = build_repository_bootstrap_publication(self.env)
        self.assertEqual([(a.target, a.managed_bytes) for a in first],
                         [(a.target, a.managed_bytes) for a in second])


@unittest.skipUnless(load_host(Path(__file__).resolve().parents[1]).bootstrap,
                     "no host bootstrap config (standalone)")
class TestClassBRootBootstrapProjection(unittest.TestCase):
    """P1.5 (D43): the one class-B record (`workflow-craft`) — thin, Codex-only, provenance-
    hashed, precondition-gated. Class-A byte/count guards are asserted separately above."""

    def setUp(self):
        self.package_root = Path(__file__).resolve().parents[1]
        self.repo_root = find_repo_root(self.package_root) or self.package_root
        self.env = Env(self.package_root)

    def _class_b_artifacts(self):
        artifacts = build_repository_bootstrap_publication(self.env)
        return [item for item in artifacts if item.identity == "workflow-craft"]

    def test_workflow_craft_is_codex_only_and_thin(self):
        artifacts = self._class_b_artifacts()
        providers = {item.provider for item in artifacts}
        self.assertEqual(providers, {"codex"})  # declared asymmetry (D43) — no Claude target
        [artifact] = artifacts
        self.assertEqual(artifact.target,
                         self.repo_root / ".agents" / "skills" / "workflow-craft" / "SKILL.md")
        body = artifact.managed_bytes.decode("utf-8")
        canonical = self.package_root / "skills" / "general" / "workflow-craft" / "SKILL.md"
        canonical_body = canonical.read_text(encoding="utf-8")
        canonical_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
        # thin: no copied canon body (a paragraph unique to the canonical procedure text)
        self.assertNotIn("Match the 4 canonical templates first", body)
        self.assertIn("Match the 4 canonical templates first", canonical_body)
        self.assertIn(f"canonical_sha256: {canonical_sha256}", body)
        self.assertIn(f"canonical: {canonical.relative_to(self.repo_root).as_posix()}", body)

    def test_precondition_fails_closed_when_donor_bucket_is_enabled(self):
        with self.assertRaises(ValueError) as ctx:
            render_repository_bootstrap_projections(
                repo_root=self.repo_root, package_root=self.package_root,
                donor_enabled={"general": True})
        self.assertIn("precondition", str(ctx.exception))
        self.assertIn("workflow-craft", str(ctx.exception))

    def test_lock_carries_source_and_rendered_hash_for_class_b(self):
        artifacts = build_repository_bootstrap_publication(self.env)
        lock_artifact = next(item for item in artifacts if item.provider == "lock")
        lock_data = json.loads(lock_artifact.managed_bytes)
        record = next(item for item in lock_data["records"] if item["identity"] == "workflow-craft")
        self.assertEqual(record["source_class"], "public-bucket")
        self.assertTrue(record["canonical_sha256"])
        self.assertTrue(record["rendered_sha256"])


@unittest.skipUnless(load_host(Path(__file__).resolve().parents[1]).bootstrap,
                     "no host bootstrap config (standalone)")
class RootBootstrapCompletenessCase(unittest.TestCase):
    """P1.5 (D40 invariant i): the declared root-bootstrap target set is exact, not a floor —
    an undeclared root directory is a hard failure naming the path, never a silent pass."""

    def test_real_repo_root_set_is_currently_clean(self):
        package_root = Path(__file__).resolve().parents[1]
        repo_root = find_repo_root(package_root) or package_root
        env = Env(package_root)
        artifacts = build_repository_bootstrap_publication(env)
        self.assertEqual(assert_root_bootstrap_set_completeness(repo_root, artifacts), [])

    def test_undeclared_directory_is_named_as_a_failure(self):
        package_root = Path(__file__).resolve().parents[1]
        repo_root = find_repo_root(package_root) or package_root
        env = Env(package_root)
        artifacts = build_repository_bootstrap_publication(env)
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp)
            (fake_repo / ".agents" / "skills" / "stray-adapter").mkdir(parents=True)
            (fake_repo / ".claude" / "skills" / "stray-adapter").mkdir(parents=True)
            failures = assert_root_bootstrap_set_completeness(fake_repo, artifacts)
            self.assertTrue(any("stray-adapter" in item and "undeclared" in item
                                for item in failures))
            self.assertTrue(any("codex" in item for item in failures))
            self.assertTrue(any("claude" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
