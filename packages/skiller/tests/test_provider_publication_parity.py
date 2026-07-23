"""Independent P3.5 publication inventory and channel-parity conformance.

Expected inventory is read directly from the committed registry and core policy;
it is deliberately not reconstructed from either provider renderer.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.publication import run_codex_native_install
from skiller.publication import validate_publication_capabilities
from core import ProviderId, ProviderManifestError
from skiller.registry import (build_claude_publication, build_codex_publication,
                              build_registry)
from skiller.skillset import do_sync
from tests import fixtures as fx


def _snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _digest(artifacts, repo_root):
    value = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: item.target):
        value.update(artifact.target.relative_to(repo_root).as_posix().encode())
        value.update(b"\0")
        value.update(artifact.managed_bytes)
        value.update(b"\0")
    return value.hexdigest()


class TestProviderPublicationParity(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.package_root = self.repo_root / "packages" / "skiller"
        self.env = Env(self.package_root)
        self.cases = json.loads((Path(__file__).parent / "fixtures_data" /
                                 "provider-publication-cases.json").read_text(encoding="utf-8"))

    def test_independent_canonical_inventory_matches_catalog_and_projections(self):
        registry_disk = json.loads((self.package_root / "skills.json").read_text(encoding="utf-8"))
        policy = json.loads((self.package_root / "configs" / "core-policy.json").read_text(encoding="utf-8"))
        expected_ids = tuple(sorted(f"{item['bucket']}/{item['name']}"
                                    for item in registry_disk["skills"]))
        expected_buckets = tuple(sorted({item["bucket"] for item in registry_disk["skills"]}))
        self.assertEqual(len(expected_ids), len(set(expected_ids)))
        self.assertEqual(tuple(policy["skills"]), tuple(dict.fromkeys(policy["skills"])))
        self.assertTrue(set(policy["skills"]).issubset(expected_ids))

        registry, metadata, buckets = build_registry(self.env)
        claude = build_claude_publication(self.env, metadata, buckets, registry)
        codex = build_codex_publication(self.env, metadata, buckets, registry)
        catalog_ids = tuple(sorted(f"{item['bucket']}/{item['name']}" for item in registry["skills"]))
        self.assertEqual(catalog_ids, expected_ids)
        self.assertEqual(tuple(sorted(buckets)), expected_buckets)

        claude_marketplace = json.loads(next(item.managed_bytes for item in claude
                                             if item.target.name == "marketplace.json"))
        codex_marketplace = json.loads(next(item.managed_bytes for item in codex
                                            if item.target.name == "marketplace.json"))
        claude_names = {item["name"] for item in claude_marketplace["plugins"]}
        codex_names = {item["name"] for item in codex_marketplace["plugins"]}
        expected_plugins = set(expected_buckets) | {policy["core_plugin"], "generate-skill", "skm"}
        expected_plugins.update(
            json.loads((package / ".codex-plugin" / "plugin.json").read_text())["name"]
            for package in (self.repo_root / "packages").iterdir()
            if package != self.package_root
            and (package / ".claude-plugin" / "plugin.json").is_file()
            and (package / ".codex-plugin" / "plugin.json").is_file())
        self.assertTrue(expected_plugins.issubset(claude_names))
        self.assertEqual(codex_names, expected_plugins)

        core = next(item for item in codex if item.publication_unit_id == "core"
                    and item.target.name == "plugin.json")
        core_manifest = json.loads(core.managed_bytes)
        self.assertEqual(core_manifest["version"],
                         json.loads((self.package_root / "package.json").read_text())["version"])
        bundled = {item.target.parts[-3] + "/" + item.target.parts[-2]
                   for item in codex if item.publication_unit_id == "core"
                   and item.target.name == "SKILL.md"}
        self.assertEqual(bundled, set(policy["skills"]))

    def test_rendering_is_repeatable_and_provider_provenance_is_complete(self):
        registry, metadata, buckets = build_registry(self.env)
        first_claude = build_claude_publication(self.env, metadata, buckets, registry)
        first_codex = build_codex_publication(self.env, metadata, buckets, registry)
        self.assertEqual(first_claude, build_claude_publication(self.env, metadata, buckets, registry))
        self.assertEqual(first_codex, build_codex_publication(self.env, metadata, buckets, registry))
        for artifact in (*first_claude, *first_codex):
            self.assertTrue(artifact.source_hash.startswith("sha256:"))
            self.assertTrue(artifact.rendered_hash.startswith("sha256:"))
            self.assertEqual(artifact.package_version, "0.4.0")
        self.assertEqual(_digest(first_claude, self.repo_root),
                         _digest(build_claude_publication(self.env, metadata, buckets, registry), self.repo_root))
        self.assertEqual(_digest(first_codex, self.repo_root),
                         _digest(build_codex_publication(self.env, metadata, buckets, registry), self.repo_root))

    def test_manifest_gate_refuses_missing_unsupported_and_catalog_mismatch_before_write(self):
        source = json.loads((self.repo_root / "configs/provider-capabilities.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "sentinel"
            sentinel.write_text("unchanged\n", encoding="utf-8")
            before = sentinel.read_bytes()
            with self.assertRaises(ProviderManifestError):
                validate_publication_capabilities(
                    ProviderId.CODEX, manifest_path=root / "missing.json")

            unsupported = json.loads(json.dumps(source))
            row = next(item for item in unsupported["capabilities"]
                       if item["id"] == "skills.repository")["support"]["codex"]
            row.pop("binding")
            row["level"] = "unsupported"
            row["limitations"] = ["fixture refusal"]
            row["diagnostic"] = "unsupported fixture; fail closed"
            path = root / "unsupported.json"
            path.write_text(json.dumps(unsupported), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "REGISTRY_CAPABILITY_UNSUPPORTED"):
                validate_publication_capabilities(ProviderId.CODEX, manifest_path=path)

            mismatch = json.loads(json.dumps(source)); mismatch["catalog_version"] = "1.1.0"
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "REGISTRY_CATALOG_VERSION_MISMATCH"):
                validate_publication_capabilities(ProviderId.CODEX, manifest_path=path)
            self.assertEqual(sentinel.read_bytes(), before)

    def test_render_only_leaves_protected_repository_paths_unchanged(self):
        """Render receives explicit roots and must not mutate bootstrap/FOREMAN paths."""
        protected = [self.repo_root / ".claude-plugin", self.repo_root / ".agents" / "skills",
                     self.repo_root / "plans" / "2026.07.18-FOREMAN"]
        before = {str(path): _snapshot(path) if path.exists() else {} for path in protected}
        registry, metadata, buckets = build_registry(self.env)
        build_claude_publication(self.env, metadata, buckets, registry)
        build_codex_publication(self.env, metadata, buckets, registry)
        after = {str(path): _snapshot(path) if path.exists() else {} for path in protected}
        self.assertEqual(after, before)

    def test_vendor_dry_run_idempotence_and_repair_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = fx.make_registry(tmp)
            registry, *_ = build_registry(env)
            (root / "skills.json").write_text(json.dumps(registry), encoding="utf-8")
            project = fx.make_laravel_project(tmp)
            (project / ".swissknifeman").mkdir()
            (project / ".swissknifeman" / "config.json").write_text(
                json.dumps({"mode": "vendor", "include": ["code-style"]}), encoding="utf-8")
            (project / ".swissknife.json").write_text(json.dumps({"providers": {
                "contract_version": "1.0.0", "selection": {
                    "claude-code": {"enabled": True}, "codex": {"enabled": True}}}}), encoding="utf-8")

            before = _snapshot(project)
            with contextlib.redirect_stdout(io.StringIO()):
                do_sync(env, project, {"dry_run": True, "no_core": True}, register=False)
            self.assertEqual(_snapshot(project), before)

            with contextlib.redirect_stdout(io.StringIO()):
                do_sync(env, project, {"no_core": True}, register=False)
            self.assertTrue((project / ".claude/skills/code-style/SKILL.md").is_file())
            codex_skill = project / ".agents/skills/code-style/SKILL.md"
            self.assertTrue(codex_skill.is_file())
            applied = _snapshot(project)
            with contextlib.redirect_stdout(io.StringIO()):
                do_sync(env, project, {"no_core": True}, register=False)
            self.assertEqual(_snapshot(project), applied)

            codex_skill.write_text("local drift\n", encoding="utf-8")
            drifted = _snapshot(project)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                do_sync(env, project, {"no_core": True}, register=False)
            self.assertEqual(_snapshot(project), drifted)
            with contextlib.redirect_stdout(io.StringIO()):
                repaired = do_sync(env, project, {"no_core": True, "repair": True}, register=False)
            evidence = next(record for record in repaired["providers"] if record["provider"] == "codex")["repair"][0]
            self.assertEqual(set(evidence), {"name", "observed", "expected", "source"})
            self.assertTrue(all(value.startswith("sha256:") for key, value in evidence.items()
                                if key != "name"))
            self.assertTrue(codex_skill.with_name("SKILL.md.provider-artifact.bak").is_file())

    def test_unmanaged_corrupt_lock_and_native_default_are_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = fx.make_registry(tmp)
            registry, *_ = build_registry(env)
            (root / "skills.json").write_text(json.dumps(registry), encoding="utf-8")
            project = fx.make_laravel_project(tmp)
            (project / ".swissknifeman").mkdir()
            (project / ".swissknifeman" / "config.json").write_text(
                json.dumps({"mode": "vendor", "include": ["code-style"]}), encoding="utf-8")
            (project / ".swissknife.json").write_text(json.dumps({"providers": {
                "contract_version": "1.0.0", "selection": {
                    "claude-code": {"enabled": True}, "codex": {"enabled": True}}}}), encoding="utf-8")
            unmanaged = project / ".agents/skills/code-style/SKILL.md"
            unmanaged.parent.mkdir(parents=True)
            unmanaged.write_text("user-owned\n", encoding="utf-8")
            before = _snapshot(project)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                do_sync(env, project, {"no_core": True}, register=False)
            self.assertEqual(_snapshot(project), before)

            unmanaged.unlink()
            unmanaged.parent.rmdir()
            (project / "skills-lock.json").write_text('{"version": 2, "skills": {}}', encoding="utf-8")
            corrupt = _snapshot(project)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                do_sync(env, project, {"no_core": True}, register=False)
            self.assertEqual(_snapshot(project), corrupt)

            calls = []
            ok, message = run_codex_native_install(repo_root=root, plugin="core", dry_run=True,
                                                   runner=lambda *args, **kwargs: calls.append(args))
            self.assertTrue(ok)
            self.assertIn("SPUB_INSTALL_EXPLICIT_REQUIRED", message)
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
