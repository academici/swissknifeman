"""Tests for the core -> aicore compatibility shim (module identity, facade, locating aicore)."""
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core

REPO = Path(__file__).resolve().parents[2]

# Snapshot of ``sorted(core.__all__)`` taken before the move to aicore.
FACADE = [
    'AdapterCatalog', 'AdapterDescriptor', 'AdapterSelection', 'AdapterSelectionResult',
    'ArtifactAction', 'ArtifactActionKind', 'ArtifactAdapterIdentity', 'ArtifactLock',
    'ArtifactPlan', 'ArtifactProvenance', 'ArtifactRenderRequest', 'ArtifactRenderResult',
    'ArtifactSource', 'ArtifactTarget', 'BaseEnv', 'BootstrapTransferAdmission',
    'CONTROL_PLANE_VERSION', 'CapabilityId', 'CapabilityRequirement', 'CapabilitySupport',
    'ChainedBootstrapTransferAdmission', 'CommandInvocationPolicy', 'ConfigProvenance',
    'ConfigSource', 'ConnectChannelSpec', 'ControlPlaneDiagnostic', 'ControlPlaneResolution',
    'DEFAULT_DOCS_VISIBILITY', 'DOCS_VISIBILITY_BY_TYPE', 'DesiredSnapshot',
    'DiagnosticSeverity', 'DistributionCatalog', 'DriftObservation', 'EffectiveProvider',
    'HOME', 'InstructionProjectionPolicy', 'LANGUAGE_BY_TYPE', 'LOCK_RELATIVE_PATH',
    'LOCK_SCHEMA_VERSION', 'ManifestCapability', 'ManifestEvidence', 'ManifestNativeExtension',
    'ManifestSupport', 'NativeExtension', 'NativeExtensionId', 'PROJECT_TYPES',
    'ProjectionCatalog', 'ProviderAdapter', 'ProviderCapabilityManifest',
    'ProviderConfigCatalog', 'ProviderConfigLayer', 'ProviderDecision', 'ProviderDiagnostic',
    'ProviderId', 'ProviderManifestDiagnostic', 'ProviderManifestError',
    'ProviderProjectionSpec', 'ProviderSelection', 'RegistryDiagnostic', 'RegistrySeverity',
    'ResolvedProviderConfig', 'SupportLevel', 'VendorChannelSpec', 'apply_plan',
    'artifact_dry_run', 'atomic_write_json', 'atomic_write_text', 'backup_file',
    'canonical_desired_bytes', 'canonical_json_bytes', 'confirm', 'connect_channel',
    'content_hash', 'detect_project_type', 'die', 'docs_visibility_for', 'effective_projection',
    'find_monorepo_root', 'find_repo_root',
    'http_get_json', 'http_post_json', 'is_within', 'is_within_lexical',
    'load_distribution_catalog', 'load_json_db', 'load_projection_catalog',
    'load_provider_manifest', 'managed_block', 'now_iso', 'parse_args',
    'parse_desired_snapshot', 'parse_flags', 'parse_frontmatter', 'parse_inline_list',
    'parse_iso', 'parse_lock', 'parse_provider_manifest', 'pid_alive', 'ping',
    'plan_artifact_lock', 'plan_artifact_render', 'plan_bootstrap_transfer',
    'plan_chained_bootstrap_transfer', 'project_common_instructions', 'projection_spec',
    'provider_config_catalog', 'provider_distribution', 'provider_manifest_canonical_bytes',
    'provider_manifest_sha256', 'provider_support_projection', 'read_ndjson',
    'read_ndjson_iter', 'render_artifact_projection', 'replace_owner_records',
    'resolve_desired_snapshot', 'resolve_provider_config',
    'rollback_chained_bootstrap_transfer', 'run_cmd', 'safe_load_json', 'sanitize',
    'serialize_lock', 'sha256_digest', 'sibling_bin', 'state_dir',
    'support_for', 'upsert_block', 'validate_target_path', 'vendor_channel', 'warn'
]

MOVED_FILES = (
    "block cli env http io paths proc project repo term text usage gitignore_policy".split()
)


class TestAliases(unittest.TestCase):
    def test_every_alias_is_the_same_module_object(self):
        self.assertEqual(len(core._ALIASES), 32)
        for old, new in core._ALIASES.items():
            with self.subTest(old=old):
                self.assertIs(importlib.import_module(old), importlib.import_module(new))

    def test_import_statement_forms_resolve(self):
        import core.provider.lock as lock_alias
        from core.provider import lock as lock_from
        from core.provider.values import ProviderId
        import aicore.artifacts.lock
        import aicore.provider.values
        self.assertIs(lock_alias, aicore.artifacts.lock)
        self.assertIs(lock_from, aicore.artifacts.lock)
        self.assertIs(ProviderId, aicore.provider.values.ProviderId)
        self.assertIs(core.io, importlib.import_module("aicore.util.io"))
        self.assertIs(core.provider, importlib.import_module("aicore.provider"))

    def test_string_patches_reach_the_real_module(self):
        from aicore.util import io as real_io
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "x.txt"
            with mock.patch("core.io.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    real_io.atomic_write_text(target, "data")
            self.assertFalse(target.exists())
        sentinel = object()
        with mock.patch("core.provider.lock._bootstrap_write_state", sentinel):
            import aicore.artifacts.lock as lock
            self.assertIs(lock._bootstrap_write_state, sentinel)


class TestGitignorePolicyAlias(unittest.TestCase):
    def test_policy_module_is_the_state_module(self):
        import aicore.state.gitignore
        from core import gitignore_policy
        import core.gitignore_policy as dotted
        self.assertIs(gitignore_policy, aicore.state.gitignore)
        self.assertIs(dotted, aicore.state.gitignore)
        self.assertIs(core.gitignore_policy, aicore.state.gitignore)
        self.assertIs(importlib.import_module("core.gitignore_policy"), aicore.state.gitignore)

    def test_removed_config_paths_stay_removed(self):
        self.assertFalse((REPO / "core" / "config_paths.py").exists())
        with self.assertRaises(ImportError):
            importlib.import_module("core.config_paths")


class TestFacade(unittest.TestCase):
    def test_all_matches_snapshot(self):
        self.assertEqual(sorted(core.__all__), FACADE)

    def test_every_name_is_available(self):
        for name in FACADE:
            with self.subTest(name=name):
                self.assertTrue(hasattr(core, name))


class TestLayout(unittest.TestCase):
    def test_moved_modules_have_no_files_in_core(self):
        for name in MOVED_FILES:
            self.assertFalse((REPO / "core" / (name + ".py")).exists(), name)
        self.assertFalse((REPO / "core" / "provider").exists())


class TestLocating(unittest.TestCase):
    def _run(self, env_extra, code="import core, aicore; print(aicore.__file__)"):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tempfile.gettempdir()}
        env.update(env_extra)
        return subprocess.run([sys.executable, "-s", "-c", code], capture_output=True, text=True,
                              env=env, cwd=tempfile.gettempdir(), timeout=60)

    def test_found_next_to_repo_root_when_only_the_root_is_on_the_path(self):
        result = self._run({"PYTHONPATH": str(REPO)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(REPO / "packages" / "aicore" / "lib"), result.stdout)

    def test_found_through_aicore_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "aicore-copy"
            shutil.copytree(REPO / "packages" / "aicore" / "lib", root / "lib",
                            ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "core", Path(tmp) / "isolated" / "core",
                            ignore=shutil.ignore_patterns("__pycache__", "tests"))
            result = self._run({"PYTHONPATH": str(Path(tmp) / "isolated"),
                                "AICORE_ROOT": str(root)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(root / "lib"), result.stdout)

    def test_missing_aicore_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(REPO / "core", Path(tmp) / "core",
                            ignore=shutil.ignore_patterns("__pycache__", "tests"))
            result = self._run({"PYTHONPATH": tmp})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("aicore not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
