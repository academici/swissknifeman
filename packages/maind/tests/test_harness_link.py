"""maind reaches harness only through its public JSON commands (aicore.util.partners)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from aicore.provider.values import ProviderId
from maind import harness_link
from maind.provision import deploy, sync, workspace
from tests.harness_partner import (FakeHarnessCase, NoHarnessCase, RealHarnessCase,
                                   write_executable)
from tests.test_deploy import _config, _project
from tests.fixtures import make_repo

PY = "#!" + sys.executable + "\n"


def script(directory, body):
    return write_executable(Path(directory) / "harness", PY + body)


class CatalogCase(FakeHarnessCase):
    def test_base_projections_are_native_and_empty(self):
        rows = harness_link.base_projections((ProviderId.CLAUDE_CODE, ProviderId.CODEX,
                                              ProviderId.CURSOR, ProviderId.GROK))
        self.assertEqual([(row.provider_id.value, row.target_path, row.servers) for row in rows], [
            ("claude-code", ".mcp.json", ()), ("codex", ".codex/config.toml", ()),
            ("cursor", ".cursor/mcp.json", ()), ("grok", ".grok/config.toml", ())])

    def test_catalog_is_asked_once_per_partner(self):
        harness_link.base_projections((ProviderId.CODEX,))
        harness_link.base_projections((ProviderId.CURSOR,))
        self.assertEqual(self.fake_calls(), [["mcp", "catalog", "--json"]])

    def test_provider_without_bindings_is_refused(self):
        script(self.fake_dir, 'import json,sys\n'
               'doc={"catalog":{"catalog_version":"1.0.0","servers":[{"id":"a","transport":"stdio",'
               '"capability_id":"mcp.catalog","secret_refs":[]}]},"bindings":{},"sources":{},"adapters":{}}\n'
               'print(json.dumps(doc))\n')
        harness_link.clear_cache()
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            harness_link.base_projections((ProviderId.CODEX,))

    def test_output_without_required_keys_is_bad_output(self):
        script(self.fake_dir, 'print("{}")\n')
        harness_link.clear_cache()
        with self.assertRaisesRegex(harness_link.PartnerError, "PARTNER_BAD_OUTPUT"):
            harness_link.mcp_catalog()

    def test_failing_partner_is_partner_failed(self):
        script(self.fake_dir, 'import sys\nprint("boom", file=sys.stderr)\nsys.exit(3)\n')
        harness_link.clear_cache()
        with self.assertRaisesRegex(harness_link.PartnerError, "PARTNER_FAILED: harness mcp exited 3: boom"):
            harness_link.mcp_catalog()


class FragmentCase(FakeHarnessCase):
    def test_fragment_carries_its_lock_source(self):
        fragment = harness_link.observer_fragment()
        self.assertEqual((fragment.target_path, fragment.event), (".codex/hooks.json", "SessionStart"))
        self.assertEqual(fragment.source.source_id, "harness.d104.observer-fragment")
        self.assertTrue(fragment.source.content_hash.startswith("sha256:"))
        self.assertTrue(fragment.handler_bytes.startswith(b"#!/usr/bin/env python3"))

    def test_validation_accepts_or_names_the_refusal(self):
        harness_link.validate_codex_lifecycle(b"{}", "bash memory.sh")
        os.environ["FAKE_HARNESS_VALIDATE"] = "invalid"
        with self.assertRaisesRegex(ValueError, "HARNESS_D104_LIFECYCLE_INVALID"):
            harness_link.validate_codex_lifecycle(b"{}", "bash memory.sh")
        call = self.fake_calls()[-1]
        self.assertEqual(call[:3], ["hooks", "codex-lifecycle", "validate"])
        self.assertEqual(call[call.index("--memory-command") + 1], "bash memory.sh")


class ProfileCase(FakeHarnessCase):
    def test_resolution_arguments_and_verdicts(self):
        green = harness_link.resolve_profile("codex", "workspace-contained", target_scope="project",
                                             trusted=True)
        self.assertTrue(green["green"])
        refused = harness_link.resolve_profile("grok", "workspace-contained", target_scope="project",
                                               trusted=False, origin="project", enabled=False,
                                               operation_id="op", target_identity="repo:x")
        self.assertFalse(refused["green"])
        self.assertEqual(refused["provider_id"], "grok")
        self.assertEqual(self.fake_calls()[-1], [
            "profiles", "resolve", "--provider", "grok", "--profile", "workspace-contained",
            "--target-scope", "project", "--origin", "project", "--json", "--disabled",
            "--operation-id", "op", "--target-identity", "repo:x"])


class InstructionsCase(FakeHarnessCase):
    OUTCOME = {"request": {"provider_ids": ["claude-code", "codex"]}, "green": False,
               "diagnostics": [{"code": "INSTRUCTION_MANAGED_DRIFT"}],
               "targets": [
                   {"scope_id": "root", "provider_id": "codex", "target_path": "AGENTS.md",
                    "observation": "managed-drift", "action": "repair", "changed": False,
                    "diagnostics": [{"code": "INSTRUCTION_MANAGED_DRIFT"}],
                    "ordered_semantic_ids": ["a"], "observed_hash": "sha256:" + "1" * 64},
                   {"scope_id": "root", "provider_id": "claude-code", "target_path": "CLAUDE.md",
                    "observation": "clean", "action": "noop", "changed": False, "diagnostics": [],
                    "ordered_semantic_ids": ["a"]}]}

    def install(self, code):
        script(self.fake_dir, 'import json,sys,os\n'
               'open(os.environ["FAKE_HARNESS_LOG"],"a").write(json.dumps(sys.argv[1:])+"\\n")\n'
               f'print({json.dumps(json.dumps(self.OUTCOME))})\nsys.exit({code})\n')
        harness_link.clear_cache()

    def test_a_non_green_result_is_data(self):
        self.install(1)
        outcome = harness_link.run_instructions(
            "repair", "/work/p", scope_ids=("root", "maind"), provider_ids=("claude-code", "codex"),
            authorized=("AGENTS.md",), observed=(("AGENTS.md", "sha256:" + "1" * 64),))
        self.assertFalse(outcome.green)
        self.assertEqual(outcome.provider_ids, ("claude-code", "codex"))
        self.assertEqual(outcome.diagnostics, ("INSTRUCTION_MANAGED_DRIFT",))
        self.assertEqual(outcome.writable_paths(), ("AGENTS.md",))
        self.assertEqual(outcome.drift_hashes(), (("AGENTS.md", "sha256:" + "1" * 64),))
        self.assertEqual(self.fake_calls()[-1], [
            "instructions", "repair", "--target", "/work/p", "--scope", "root,maind",
            "--provider", "claude-code,codex", "--json", "--authorize", "AGENTS.md",
            "--observed-hash", "AGENTS.md=sha256:" + "1" * 64, "--preimage-dir", "adjacent-backup"])

    def test_a_crash_is_not_data(self):
        self.install(2)
        with self.assertRaisesRegex(harness_link.PartnerError, "PARTNER_FAILED: harness instructions exited 2"):
            harness_link.run_instructions("plan", "/work/p", scope_ids=("root",), provider_ids=("codex",))

    def test_refused_request_has_no_planned_targets(self):
        outcome = harness_link.InstructionOutcome.from_document({
            "request": {"provider_ids": ["codex"]}, "targets": [], "green": False,
            "diagnostics": [{"code": "INSTRUCTION_SCOPE_INVALID"}]})
        self.assertFalse(outcome.planned)
        self.assertEqual(outcome.writable_paths(), ())

    def test_scopes_come_from_the_catalog_command(self):
        document = harness_link.instruction_scopes()
        self.assertEqual(document["scopes"][0], "root")
        self.assertIn("maind", document["scopes"])


class LegacyEnvCase(FakeHarnessCase):
    def test_legacy_launcher_variable_still_finds_the_partner(self):
        legacy = Path(self.fake_dir) / "legacy-harness"
        write_executable(legacy, (Path(os.environ["SKM_HARNESS_BIN"])).read_text())
        os.environ["SKM_HARNESS_BIN"] = "/nonexistent"
        os.environ["MAIND_HARNESS_BIN"] = str(legacy)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertTrue(harness_link.available())
        self.assertEqual(harness_link.instruction_scopes()["scopes"][0], "root")


class WithoutHarnessCase(NoHarnessCase):
    def test_every_link_function_reports_partner_unavailable(self):
        self.assertFalse(harness_link.available())
        with self.assertRaisesRegex(harness_link.PartnerUnavailable, "PARTNER_UNAVAILABLE: harness not found"):
            harness_link.base_projections((ProviderId.CODEX,))
        with self.assertRaises(harness_link.PartnerUnavailable):
            harness_link.observer_fragment()
        with self.assertRaises(harness_link.PartnerUnavailable):
            harness_link.instruction_scopes()

    def test_projection_context_has_no_projections_and_says_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            path = _project(tmp)
            config = _config(path)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                context = deploy.provider_projection_context(env, config, config["projects"][0])
            self.assertEqual(context.projections, ())
            self.assertEqual(context.providers, (ProviderId.CLAUDE_CODE,))
            self.assertIn("PARTNER_UNAVAILABLE: harness not found", err.getvalue())

    def test_deploy_skips_provider_steps_and_still_writes_the_hub_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            path = _project(tmp)
            (path / ".swissknife.json").write_text(json.dumps({"providers": {
                "contract_version": "1.0.0",
                "selection": {"claude-code": {"enabled": True}, "codex": {"enabled": True}}}}),
                encoding="utf-8")
            config = _config(path)
            project = config["projects"][0]
            with contextlib.redirect_stderr(io.StringIO()):
                context = deploy.provider_projection_context(env, config, project)
                result = deploy.deploy_project(env, config, project, with_code=False,
                                               provider_projections=context.projections)
            self.assertIsNone(result["provider_plan"])
            self.assertTrue(deploy.provider_operation_green(result))
            servers = json.loads((path / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("maind", servers)
            self.assertFalse((path / ".codex").exists())
            self.assertFalse((path / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_d108_without_harness_falls_back_to_the_hub_servers_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            path = _project(tmp, "swissknifeman")
            config = _config(path, "swissknifeman")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                result = deploy.deploy_project(env, config, config["projects"][0], d108=True,
                                               with_code=False)
            self.assertIsNone(result["provider_plan"])
            self.assertIn("PARTNER_UNAVAILABLE: harness not found", err.getvalue())

    def test_trust_stays_non_green_and_names_the_missing_partner(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            path = _project(tmp)
            config = _config(path)
            with contextlib.redirect_stderr(io.StringIO()):
                context = sync.contexts(env, config, config["projects"])[0]
                rows = workspace.provider_trust(context, trusted=True)
            self.assertEqual(rows, ({"provider_id": "claude-code", "green": False,
                                     "diagnostics": ["PARTNER_UNAVAILABLE"]},))

    def test_conformance_command_names_the_missing_partner(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                deploy.cmd_deploy(env, ["--conformance", str(Path(tmp) / "report.md")])
            self.assertIn("PARTNER_UNAVAILABLE: harness not found", err.getvalue())


class RealHarnessLinkCase(RealHarnessCase):
    """The same link against the real harness (integration runner)."""

    def test_catalog_scopes_and_fragment_are_well_formed(self):
        rows = harness_link.base_projections((ProviderId.CODEX, ProviderId.GROK))
        self.assertEqual([row.target_path for row in rows], [".codex/config.toml", ".grok/config.toml"])
        self.assertEqual(harness_link.instruction_scopes()["scopes"][0], "root")
        self.assertEqual(harness_link.observer_fragment().event, "SessionStart")

    def test_profile_verdicts_match_the_recorded_ones(self):
        green = harness_link.resolve_profile("codex", "workspace-contained", target_scope="project",
                                             trusted=True)
        refused = harness_link.resolve_profile("codex", "workspace-contained", target_scope="project",
                                               trusted=False)
        self.assertTrue(green["green"])
        self.assertEqual([item["code"] for item in refused["diagnostics"]], ["HARNESS_TRUST_REQUIRED"])


if __name__ == "__main__":
    unittest.main()
