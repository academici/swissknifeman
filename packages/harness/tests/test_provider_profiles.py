"""Focused P5.2 profile catalog and provider-render plan conformance."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.artifacts.lock import ArtifactActionKind, apply_plan, plan_artifact_lock, serialize_lock
from aicore.provider.values import EffectiveProvider, ProviderId
from aicore.artifacts.lock import artifact_dry_run
from harness.profiles import load_catalog, resolve_profile
from harness.provider_render import plan_profile_artifact, render_profile


PACKAGE = Path(__file__).resolve().parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
BINDINGS = PACKAGE / "configs/codex/config/profile-bindings.json"


def effective(provider_id):
    return EffectiveProvider(provider_id, True)


class ProviderProfilesTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)

    def test_exact_catalog_and_common_schema_are_provider_free(self):
        self.assertEqual(tuple(profile.id for profile in self.catalog.profiles),
                         ("observe", "workspace-contained", "trusted-full-access"))
        self.assertEqual(len(self.catalog.surfaces), 26)
        text = CATALOG.read_text(encoding="utf-8")
        for token in (".claude", ".codex", "PreToolUse", "approval_policy", "sandbox_mode"):
            self.assertNotIn(token, text)

    def test_full_access_rejects_inheritance_and_missing_operation(self):
        inherited = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                    profile_id="trusted-full-access", target_scope="project",
                                    trusted=True, origin="project", effective_provider=effective(ProviderId.CODEX))
        self.assertFalse(inherited.green)
        self.assertEqual({item.code for item in inherited.diagnostics},
                         {"HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED",
                          "HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN"})

    def test_workspace_requires_trust_before_render(self):
        refused = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                  profile_id="workspace-contained", target_scope="project",
                                  trusted=False, origin="operation", effective_provider=effective(ProviderId.CODEX))
        self.assertFalse(refused.green)
        self.assertEqual(refused.diagnostics[0].code, "HARNESS_TRUST_REQUIRED")
        with self.assertRaisesRegex(ValueError, "refused"):
            render_profile(refused, codex_bindings_path=BINDINGS)

    def test_provider_renderers_are_independent_and_deterministic(self):
        claude = resolve_profile(self.catalog, provider_id=ProviderId.CLAUDE_CODE,
                                 profile_id="workspace-contained", target_scope="project",
                                 trusted=True, origin="operation", effective_provider=effective(ProviderId.CLAUDE_CODE))
        codex = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                profile_id="workspace-contained", target_scope="project",
                                trusted=True, origin="operation", effective_provider=effective(ProviderId.CODEX))
        claude_bytes = render_profile(claude, codex_bindings_path=BINDINGS)
        codex_bytes = render_profile(codex, codex_bindings_path=BINDINGS)
        self.assertIn(b'"acceptEdits"', claude_bytes)
        self.assertIn(b'approval_policy = "never"', codex_bytes)
        self.assertEqual(codex_bytes, render_profile(codex, codex_bindings_path=BINDINGS))

    def test_one_render_plan_feeds_dry_run_write_check_and_repair(self):
        resolved = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                   profile_id="trusted-full-access", target_scope="project",
                                   trusted=True, operation_id="self-host-apply",
                                   target_identity="repo:fixture", origin="operation",
                                   effective_provider=effective(ProviderId.CODEX))
        expected = plan_profile_artifact(resolved, catalog_path=CATALOG, codex_bindings_path=BINDINGS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = plan_artifact_lock(root, (expected,), lock_bytes=None)
            before = sorted(root.rglob("*"))
            self.assertEqual(artifact_dry_run(plan), artifact_dry_run(plan))
            self.assertEqual(before, sorted(root.rglob("*")))
            applied = apply_plan(root, plan)
            self.assertEqual(applied.actions[0].action, ArtifactActionKind.NOOP)
            lock = serialize_lock(plan.next_lock)
            target = root / expected.target.path
            target.write_text("local drift\n", encoding="utf-8")
            repair = plan_artifact_lock(root, (expected,), lock_bytes=lock,
                                        repair_artifact_ids=(expected.provenance.artifact_id,))
            self.assertEqual(repair.actions[0].action, ArtifactActionKind.REPAIR)


if __name__ == "__main__":
    unittest.main()
