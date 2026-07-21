import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from harness.provider_audit import (ProviderAuditReport, audit_package, audited_paths,
                                    render_operator_reference, render_p5_artifact)
from harness.profiles import load_catalog, resolve_profile
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from harness.hooks import LifecycleRequest, plan_lifecycle
from core import EffectiveProvider, ProviderId

PACKAGE = Path(__file__).resolve().parents[1]


class ProviderConformanceTests(unittest.TestCase):
    def test_independent_fixture_has_exact_inventory_and_stable_report(self):
        first, second = audit_package(PACKAGE), audit_package(PACKAGE)
        self.assertEqual(first.render(), second.render())
        self.assertTrue(first.green, first.render())
        report = first.as_dict()
        self.assertTrue(all(not row["missing"] and not row["extra"] and not row["duplicates"] for row in report["rows"]))

    def test_fixture_is_not_renderer_output_and_has_no_secret_or_full_access_default(self):
        fixture = (PACKAGE / "tests/fixtures_data/provider-harness-cases.json").read_text(encoding="utf-8")
        self.assertNotIn("real-token", fixture)
        self.assertNotIn("approval_policy", fixture)
        self.assertEqual(len(json.loads(fixture)["agent_roles"]), 44)

    def test_audit_is_no_write(self):
        before = {path: path.read_bytes() for path in audited_paths(PACKAGE)}
        audit_package(PACKAGE)
        self.assertEqual(before, {path: path.read_bytes() for path in audited_paths(PACKAGE)})

    def test_duplicate_regression_fixtures_are_reported_for_both_inventories(self):
        cases = json.loads((PACKAGE / "tests/fixtures_data/provider-harness-negative-cases.json").read_text())
        for case in cases:
            report = ProviderAuditReport("sha256:test", (),
                (("profiles", tuple(case["expected"])),), (("profiles", tuple(case["actual"])),), ())
            row = report.as_dict()["rows"][0]
            self.assertEqual(row["expected_duplicates"], case["expected_duplicates"])
            self.assertEqual(row["actual_duplicates"], case["actual_duplicates"])

    def test_worktree_local_doctor_json_human_and_exit_behavior(self):
        command = [str(PACKAGE / "bin/harness"), "doctor", "--provider-audit"]
        human = subprocess.run(command, cwd=PACKAGE, text=True, capture_output=True, check=False)
        machine = subprocess.run(command + ["--json"], cwd=PACKAGE, text=True, capture_output=True, check=False)
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertEqual(machine.returncode, 0, machine.stderr)
        self.assertIn("harness provider audit: OK", human.stdout)
        self.assertTrue(json.loads(machine.stdout)["green"])

    def test_provider_doctor_returns_error_exit_for_a_non_green_consumer(self):
        from harness.doctor import cmd_doctor
        from harness.common import Env
        refused = ProviderAuditReport("sha256:test", (), (), (), ("HARNESS_CATALOG_MISMATCH:test",))
        with patch("harness.provider_audit.audit_package", return_value=refused):
            with self.assertRaisesRegex(SystemExit, "2"):
                cmd_doctor(Env(PACKAGE, "doctor"), ["--provider-audit"])

    def test_generated_docs_and_p5_artifact_are_the_validated_report_consumers(self):
        report = audit_package(PACKAGE)
        self.assertEqual((PACKAGE / "docs/reference/provider-harness.md").read_text(), render_operator_reference(report))
        artifact = PACKAGE.parents[1] / "plans/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md"
        self.assertEqual(artifact.read_text(), render_p5_artifact(report))

    def test_security_trust_capability_activation_and_secret_diagnostics(self):
        catalog = load_catalog(PACKAGE / "configs/common/profile-catalog.json")
        effective = EffectiveProvider(ProviderId.CODEX, True)
        accepted = resolve_profile(catalog, provider_id=ProviderId.CODEX,
            profile_id="trusted-full-access", target_scope="project", trusted=True,
            operation_id="self-host-apply", target_identity="repo:fixture", origin="operation",
            effective_provider=effective)
        self.assertTrue(accepted.green)
        missing = resolve_profile(catalog, provider_id=ProviderId.CODEX,
            profile_id="trusted-full-access", target_scope="project", trusted=True,
            origin="operation", effective_provider=effective)
        self.assertEqual({item.code for item in missing.diagnostics}, {"HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED"})
        for origin in ("project", "fleet-project", "fleet-defaults"):
            refused = resolve_profile(catalog, provider_id=ProviderId.CODEX,
                profile_id="trusted-full-access", target_scope="project", trusted=True,
                operation_id="self-host-apply", target_identity="repo:fixture", origin=origin,
                effective_provider=effective)
            self.assertIn("HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN", {item.code for item in refused.diagnostics})
        untrusted = resolve_profile(catalog, provider_id=ProviderId.CODEX,
            profile_id="workspace-contained", target_scope="project", trusted=False,
            origin="operation", effective_provider=effective)
        self.assertEqual({item.code for item in untrusted.diagnostics}, {"HARNESS_TRUST_REQUIRED"})
        lifecycle = plan_lifecycle(catalog, provider_id=ProviderId.CODEX, trusted=True,
            requests=(LifecycleRequest("lifecycle.daemon-safety", True),),
            codex_bindings_path=PACKAGE / "configs/codex/hooks/lifecycle-context-bindings.json")
        self.assertEqual(lifecycle.diagnostics[0].code, "HARNESS_ACTIVATION_UNSUPPORTED")
        mcp = load_mcp_catalog(PACKAGE / "configs/common/mcp/catalog.json")
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "bindings.json"
            altered.write_text((PACKAGE / "configs/codex/mcp/bindings.json").read_text().replace("${PERPLEXITY_API_KEY}", "${WRONG}"))
            with self.assertRaisesRegex(ValueError, "HARNESS_SECRET_REFERENCE_MISSING"):
                plan_mcp_projection(mcp, provider_id=ProviderId.CODEX, bindings_path=altered,
                    selected=("perplexity",), trusted=True)


if __name__ == "__main__":
    unittest.main()
