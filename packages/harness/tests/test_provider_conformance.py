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
                                    render_operator_reference, render_p5_artifact,
                                    _map_diagnostics)
from harness.profiles import load_catalog, resolve_profile
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from harness.hooks import LifecycleRequest, plan_lifecycle
from core import (EffectiveProvider, ProviderId, ProviderManifestError,
                  load_provider_manifest)

PACKAGE = Path(__file__).resolve().parents[1]


class ProviderConformanceTests(unittest.TestCase):
    def test_profile_catalog_default_path_cannot_bypass_manifest_gate(self):
        manifest_path = PACKAGE.parents[1] / "configs/provider-capabilities.json"
        manifest = load_provider_manifest(manifest_path)
        with patch("harness.profiles.load_provider_manifest", return_value=manifest) as loader:
            catalog = load_catalog(PACKAGE / "configs/common/profile-catalog.json")
        self.assertEqual(catalog.catalog_version, "1.0.0")
        loader.assert_called_once_with(manifest_path)
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with patch("harness.profiles._CAPABILITY_MANIFEST_PATH", missing):
                with self.assertRaises(ProviderManifestError):
                    load_catalog(PACKAGE / "configs/common/profile-catalog.json")

    def test_manifest_gate_refuses_missing_and_support_mismatch_before_audit_output(self):
        manifest_path = PACKAGE.parents[1] / "configs/provider-capabilities.json"
        source = json.loads(manifest_path.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ProviderManifestError):
                audit_package(PACKAGE, manifest_path=root / "missing.json")
            changed = json.loads(json.dumps(source))
            row = next(item for item in changed["capabilities"]
                       if item["id"] == "doctor.environment")["support"]["codex"]
            row.pop("adapter_id")
            row["level"] = "unsupported"
            row["diagnostic"] = "unsupported fixture; fail closed"
            path = root / "manifest.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            report = audit_package(PACKAGE, manifest_path=path)
            self.assertFalse(report.green)
            self.assertTrue(any(item.startswith(
                "HARNESS_CAPABILITY_MANIFEST_INVALID:codex:doctor.environment")
                for item in report.diagnostics))

    def test_profile_requirement_level_mismatch_is_rejected(self):
        manifest = load_provider_manifest(
            PACKAGE.parents[1] / "configs/provider-capabilities.json")
        value = json.loads((PACKAGE / "configs/common/profile-catalog.json").read_text())
        surface = next(item for item in value["surfaces"]
                       if item["id"] == "doctor.provider")
        surface["required_capabilities"] = [{
            "capability_id": "mcp.catalog", "accepted_levels": ["native"]}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "level-mismatch"):
                load_catalog(path, capability_manifest=manifest)

    def test_independent_fixture_has_exact_inventory_and_stable_report(self):
        first, second = audit_package(PACKAGE), audit_package(PACKAGE)
        self.assertEqual(first.render(), second.render())
        self.assertTrue(first.green, first.render())
        report = first.as_dict()
        self.assertTrue(all(not row["missing"] and not row["extra"] and not row["duplicates"] for row in report["rows"]))

    def test_render_hashes_and_provider_surface_map_are_complete_and_qualified(self):
        report = audit_package(PACKAGE).as_dict()
        hashes = report["render_hashes"]
        self.assertEqual(len(hashes), len(set(hashes)))
        self.assertTrue(all(value.startswith("sha256:") and len(value) == 71 for value in hashes.values()))
        fixture = json.loads((PACKAGE / "tests/fixtures_data/provider-harness-cases.json").read_text())
        for provider in ("claude-code", "codex"):
            self.assertTrue(all(f"profile:{provider}:{profile}" in hashes
                                for profile in ("observe", "workspace-contained", "trusted-full-access")))
            self.assertIn(f"mcp:{provider}:catalog", hashes)
            self.assertTrue(all(f"lifecycle:{provider}:{surface}" in hashes
                                for surface in fixture["surfaces"]
                                if surface.startswith(("lifecycle.", "context."))))
        self.assertTrue(all(f"agent:claude-code:{role}" in hashes for role in fixture["agent_roles"]))
        self.assertTrue(all(f"agent:codex:{role}" in hashes for role in fixture["agent_roles"]
                            if role != "_common.orchestrator"))
        self.assertNotIn("agent:codex:_common.orchestrator", hashes)
        self.assertEqual(len(hashes), 6 + 2 + 44 + 43 + 32)
        expected = {(provider, surface) for provider in ("claude-code", "codex")
                    for surface in fixture["surfaces"]}
        observed = {(row["provider"], row["surface_id"]) for row in report["surface_map"]}
        self.assertEqual(observed, expected)
        self.assertEqual(len(report["surface_map"]), 48)
        self.assertIn({"category": "activation", "provider": "claude-code",
                       "identity": "agents.catalog", "polarity": "positive",
                       "state": "supported", "diagnostic": "HARNESS_AGENT_ARTIFACT_P2_CREATE_NOOP:44"},
                      report["evidence"])
        self.assertIn({"category": "activation", "provider": "codex",
                       "identity": "agents.catalog", "polarity": "positive",
                       "state": "supported", "diagnostic": "HARNESS_AGENT_ARTIFACT_P2_CREATE_NOOP:43"},
                      report["evidence"])
        self.assertFalse(_map_diagnostics(
            [(row["provider"], row["surface_id"], "", "", "", "", "", "")
             for row in report["surface_map"]], tuple(fixture["surfaces"])))
        self.assertTrue(_map_diagnostics([], tuple(fixture["surfaces"])))
        duplicate = [("codex", fixture["surfaces"][0], "", "", "", "", "", "")] * 2
        self.assertTrue(any("duplicate:codex" in item
                            for item in _map_diagnostics(duplicate, tuple(fixture["surfaces"]))))

    def test_temp_managed_lifecycle_evidence_covers_security_mcp_agent_and_context(self):
        lifecycle = audit_package(PACKAGE).as_dict()["managed_lifecycle"]
        self.assertEqual({row["artifact"] for row in lifecycle}, {
            "profile:codex:trusted-full-access", "mcp:codex:catalog",
            "agent:codex:backend-laravel.blade-review", "lifecycle:codex:context.observer",
        })
        self.assertTrue(all(set(row["create"].split("+")) == {"create"}
                            and set(row["check"].split("+")) == {"noop"}
                            and "refuse" in row["drift"].split("+")
                            and "repair" in row["repair"].split("+")
                            and row["outside_managed_preserved"] for row in lifecycle))

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

    def test_public_hook_dry_run_normalizes_relative_and_absolute_targets_without_writes(self):
        repository = PACKAGE.parents[1]
        protected = tuple(repository / relative for relative in (
            ".codex/hooks.json", ".codex/hooks/lifecycle.py"))
        before = {path: path.read_bytes() for path in protected}
        command = [str(PACKAGE / "bin/harness"), "hooks", "--provider", "codex",
                   "--terminal-admission", "on", "--trusted", "--dry-run", "--target"]

        relative = subprocess.run(command + ["."], cwd=repository, text=True,
                                  capture_output=True, check=False)
        absolute = subprocess.run(command + [str(repository)], cwd=repository, text=True,
                                  capture_output=True, check=False)

        self.assertEqual(relative.returncode, 0, relative.stderr)
        self.assertEqual(absolute.returncode, 0, absolute.stderr)
        self.assertEqual(relative.stdout, absolute.stdout)
        self.assertIn("План: sha256:", relative.stdout)
        self.assertIn("Статус: green", relative.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in protected})

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
        artifact = PACKAGE.parents[1] / "plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md"
        self.assertEqual(artifact.read_text(), render_p5_artifact(report))
        evidence = report.as_dict()["evidence"]
        self.assertIn({"category": "activation", "provider": "codex",
                       "identity": "surface:context.output-style", "polarity": "negative",
                       "state": "unsupported", "diagnostic": "HARNESS_ACTIVATION_UNSUPPORTED"}, evidence)
        self.assertIn({"category": "security", "provider": "codex",
                       "identity": "origin:fleet-defaults", "polarity": "negative",
                       "state": "refused", "diagnostic": "HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN"}, evidence)
        self.assertTrue(all(any(item["category"] == category and item["polarity"] == polarity
                                for item in evidence)
                            for category in ("security", "trust", "capability", "activation", "secret")
                            for polarity in ("positive", "negative")))
        for generated in (render_operator_reference(report), render_p5_artifact(report)):
            self.assertIn("Exact provider-surface map", generated)
            self.assertIn("HARNESS_ACTIVATION_UNSUPPORTED", generated)
            self.assertNotIn("literal-", generated)
        self.assertIn("Exact P6 deployment inputs", render_p5_artifact(report))
        self.assertIn("Exact P7 self-host acceptance inputs", render_p5_artifact(report))
        for generated in (render_operator_reference(report), render_p5_artifact(report)):
            self.assertIn("Source and render hashes", generated)
            self.assertIn("Exact provider-surface map", generated)
            self.assertIn("Temp-contained managed lifecycle evidence", generated)
            self.assertIn("project, fleet-project and fleet-defaults", generated)

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
        for provider in ProviderId:
            for origin in ("project", "fleet-project", "fleet-defaults"):
                refused = resolve_profile(catalog, provider_id=provider,
                    profile_id="trusted-full-access", target_scope="project", trusted=True,
                    operation_id="self-host-apply", target_identity="repo:fixture", origin=origin,
                    effective_provider=EffectiveProvider(provider, True))
                self.assertIn("HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN", {item.code for item in refused.diagnostics})
        evidence = audit_package(PACKAGE).as_dict()["evidence"]
        for provider in ("claude-code", "codex"):
            self.assertIn({"category": "security", "provider": provider,
                           "identity": "profile:trusted-full-access", "polarity": "positive",
                           "state": "supported", "diagnostic": "HARNESS_FULL_ACCESS_EXPLICIT"}, evidence)
            for origin in ("project", "fleet-project", "fleet-defaults"):
                self.assertIn({"category": "security", "provider": provider,
                               "identity": f"origin:{origin}", "polarity": "negative",
                               "state": "refused",
                               "diagnostic": "HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN"}, evidence)
        untrusted = resolve_profile(catalog, provider_id=ProviderId.CODEX,
            profile_id="workspace-contained", target_scope="project", trusted=False,
            origin="operation", effective_provider=effective)
        self.assertEqual({item.code for item in untrusted.diagnostics}, {"HARNESS_TRUST_REQUIRED"})
        lifecycle = plan_lifecycle(catalog, provider_id=ProviderId.CODEX, trusted=True,
            requests=(LifecycleRequest("context.output-style", True),),
            codex_bindings_path=PACKAGE / "configs/codex/hooks/lifecycle-context-bindings.json")
        self.assertEqual(lifecycle.diagnostics[0].code, "HARNESS_ACTIVATION_UNSUPPORTED")
        mcp = load_mcp_catalog(PACKAGE / "configs/common/mcp/catalog.json")
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "bindings.json"
            altered.write_text((PACKAGE / "configs/codex/mcp/bindings.json").read_text().replace("${PERPLEXITY_API_KEY}", "${WRONG}"))
            with self.assertRaisesRegex(ValueError, "HARNESS_SECRET_REFERENCE_MISSING"):
                plan_mcp_projection(mcp, provider_id=ProviderId.CODEX, bindings_path=altered,
                    selected=("perplexity",), trusted=True)

    def test_report_retains_nonfatal_unsupported_activation_and_is_green(self):
        report = audit_package(PACKAGE)
        self.assertTrue(report.green, report.render())
        unsupported = [item for item in report.as_dict()["evidence"]
                       if item["state"] == "unsupported"]
        self.assertTrue(unsupported)
        self.assertTrue(all(item["provider"] and item["identity"] for item in unsupported))

    def test_named_lifecycle_and_workflow_consumers_are_provider_qualified(self):
        surface_map = {(row["provider"], row["surface_id"]): row
                       for row in audit_package(PACKAGE).as_dict()["surface_map"]}
        for surface_id, claude_diagnostic, codex_diagnostic, codex_state in (
            # agent-packs.lifecycle: P2.4 closed the Codex half (bounded, role
            # projections only) — codex-parity-verdicts-v1.md §3.12.
            ("agent-packs.lifecycle", "HARNESS_AGENTPACK_LIFECYCLE_NAMED",
             "HARNESS_AGENTPACK_LIFECYCLE_NAMED", "supported"),
            ("workflows.status", "HARNESS_WORKFLOW_STATUS_NAMED",
             "HARNESS_ACTIVATION_UNSUPPORTED:codex:workflows.status:"
             "missing-native-codex-workflow-status-consumer", "unsupported"),
        ):
            self.assertEqual(surface_map[("claude-code", surface_id)]["activation_state"], "supported")
            self.assertEqual(surface_map[("claude-code", surface_id)]["diagnostic"], claude_diagnostic)
            self.assertEqual(surface_map[("codex", surface_id)]["activation_state"], codex_state)
            self.assertEqual(surface_map[("codex", surface_id)]["diagnostic"], codex_diagnostic)


if __name__ == "__main__":
    unittest.main()
