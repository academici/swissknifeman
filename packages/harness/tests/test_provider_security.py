"""P5.2 focused security regressions for profile resolution."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.provider.values import EffectiveProvider, ProviderId
from harness.profiles import load_catalog, resolve_profile


CATALOG = Path(__file__).resolve().parents[1] / "configs/common/profile-catalog.json"


def effective(provider_id, enabled=True):
    return EffectiveProvider(provider_id, enabled)


class ProviderSecurityTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)

    def test_approval_never_does_not_widen_workspace_sandbox(self):
        resolution = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                     profile_id="workspace-contained", target_scope="project",
                                     trusted=True, origin="operation", effective_provider=effective(ProviderId.CODEX))
        self.assertTrue(resolution.green)
        self.assertEqual(resolution.profile.security.approval_intent, "provider-interactive-or-never")
        self.assertEqual(resolution.profile.security.sandbox_intent, "workspace-contained")

    def test_full_access_needs_trusted_repository_not_only_project_trust(self):
        resolution = resolve_profile(self.catalog, provider_id=ProviderId.CLAUDE_CODE,
                                     profile_id="trusted-full-access", target_scope="project",
                                     trusted=False, operation_id="self-host-apply",
                                     target_identity="repo:fixture", origin="operation",
                                     effective_provider=effective(ProviderId.CLAUDE_CODE))
        self.assertFalse(resolution.green)
        self.assertEqual(resolution.diagnostics[0].code, "HARNESS_TRUST_REQUIRED")

    def test_unknown_profile_and_scope_fail_closed(self):
        resolution = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                     profile_id="yolo", target_scope="fleet", trusted=True,
                                     origin="operation", effective_provider=effective(ProviderId.CODEX))
        self.assertFalse(resolution.green)
        self.assertEqual({item.code for item in resolution.diagnostics},
                         {"HARNESS_ID_INVALID", "HARNESS_SCOPE_UNSUPPORTED"})

    def test_disabled_provider_and_user_full_access_are_refused_before_render(self):
        disabled = resolve_profile(self.catalog, provider_id=ProviderId.CODEX,
                                   profile_id="observe", target_scope="project", trusted=True,
                                   origin="operation", effective_provider=effective(ProviderId.CODEX, False))
        self.assertEqual(disabled.diagnostics[0].code, "HARNESS_PROVIDER_DISABLED")
        global_full_access = resolve_profile(
            self.catalog, provider_id=ProviderId.CODEX, profile_id="trusted-full-access",
            target_scope="user", trusted=True, operation_id="self-host-apply",
            target_identity="repo:fixture", origin="operation",
            effective_provider=effective(ProviderId.CODEX))
        self.assertEqual({item.code for item in global_full_access.diagnostics},
                         {"HARNESS_SCOPE_UNSUPPORTED"})


if __name__ == "__main__":
    unittest.main()
