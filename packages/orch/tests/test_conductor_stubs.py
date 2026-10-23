"""Stubs in a conductor run: the additional instructions of the project and the machine reach the prompt of their role
between the role text and the task, a run keeps the snapshot it started with (a resume says STUBS_CHANGED when the files
moved on), an unusable stub stops the run with STUBS_INVALID before any role starts, and ``orch stubs`` publishes and
explains them."""
from __future__ import annotations

import io
import json
import os
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import unittest
from unittest import mock

from aicore.provider import models
from aicore.util.digest import sha256_hex
from orch import cli as orch_cli
from orch.conductor import engine, gates, stubs
from orch.conductor.application import retry_service

from tests.test_conductor import ConductorCase, executor_ok

CODEX_QUOTA = {"codex_failed": "You\u2019ve hit your usage limit. Try later.", "exit": 1}


class StubRunTests(ConductorCase):
    scenario = "scout-solo"

    def stub(self, layer: str, slot: str, text: str) -> Path:
        root = self.project / ".swissknifeman" / "stubs" if layer == "project" else self.home / "skm" / "config" / "stubs"
        path = root / slot
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if layer == "project":  # a project stub is a file of the repository: committed like any other
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "stub")
        return path

    def orch(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = orch_cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_the_stub_stands_between_the_role_text_and_the_task(self):
        self.stub("machine", "orch/roles/_all.md", "Machine rule for every role.\n")
        self.stub("project", "orch/roles/executor.md", "Project rule: prefer small commits.\n")
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 1)
        heading = prompt.index("## Additional instructions")
        self.assertLess(heading, prompt.index("Goal"))
        self.assertLess(prompt.index("Machine rule for every role."), prompt.index("Project rule: prefer small commits."))
        snapshot = json.loads((self.run_dir(err) / "instructions.json").read_text(encoding="utf-8"))
        run_doc = json.loads((self.run_dir(err) / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run_doc["instructions_digest"], snapshot["digest"])
        self.assertEqual([part["layer"] for part in snapshot["targets"]["orch.role.executor"]["parts"]],
                         ["machine", "project"])
        self.assertNotIn("variant_resolution", snapshot)
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json")
                              .read_text(encoding="utf-8")) \
            if (self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").exists() else None
        if manifest is not None:
            self.assertIn("stub", [block["kind"] for block in manifest["blocks"]])

    def test_without_stubs_the_prompt_has_no_block(self):
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("## Additional instructions", self.prompt("executor", 1))

    def test_an_unusable_stub_stops_before_any_role(self):
        (self.project / ".swissknifeman" / "stubs" / "orch" / "roles").mkdir(parents=True)
        os.symlink("/etc/hostname", self.project / ".swissknifeman" / "stubs" / "orch" / "roles" / "executor.md")
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)[1] if self.lines(err) else None), (1, "STUBS_INVALID"), err) \
            if any(line.get("event") == "run.end" for line in self.lines(err)) else self.assertIn("STUBS_INVALID", err)
        self.assertEqual(self.calls("executor"), 0)

    def test_a_resume_keeps_the_snapshot_and_says_stubs_changed(self):
        self.stub("project", "orch/roles/executor.md", "first text\n")
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        kept = (self.run_dir(err) / "instructions.json").read_text(encoding="utf-8")
        self.stub("project", "orch/roles/executor.md", "second text\n")
        _, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertIn("STUBS_CHANGED", [line.get("reason_code") for line in self.lines(err2)], err2)
        self.assertEqual((self.run_dir(err) / "instructions.json").read_text(encoding="utf-8"), kept)

    def test_a_machine_without_the_project_layer_ignores_project_stubs(self):
        self.write_config(extra='[orch.stubs]\nlayers = ["machine"]')
        self.stub("project", "orch/roles/executor.md", "project text\n")
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("project text", self.prompt("executor", 1))

    def test_publish_list_and_show(self):
        code, out, err = self.orch("stubs", "publish", "--json")
        self.assertEqual(code, 0, err)
        files = json.loads(out)["files"]
        self.assertIn("orch/roles/reviewer.md", [row["slot"] for row in files])
        self.assertNotIn("orch/roles/registrar.md", [row["slot"] for row in files])
        self.assertEqual({row["status"] for row in files}, {"created"})
        self.stub("project", "orch/roles/reviewer.md", "Look at the error paths first.\n")
        code, out, _ = self.orch("stubs", "publish")
        self.assertEqual(code, 0)
        self.assertNotIn("created", out)
        code, out, _ = self.orch("stubs", "show", "reviewer")
        self.assertEqual(code, 0)
        self.assertIn("Look at the error paths first.", out)
        self.assertIn("## Additional instructions", out)
        code, out, _ = self.orch("stubs", "list", "--json")
        self.assertEqual(json.loads(out)["targets"]["orch.role.reviewer"]["parts"][0]["layer"], "project")
        code, _, err = self.orch("stubs", "show", "registrar")
        self.assertEqual(code, 1)
        self.assertIn("STUB_TARGET_UNKNOWN", err)


class VariantRunTests(ConductorCase):
    scenario = "scout-solo"
    stub = StubRunTests.stub
    orch = StubRunTests.orch

    def options(self, **overrides):
        options = {"stages": [{"role": "executor", "provider": "codex", "model": "gpt-6-sol",
                                "model_class": "implementation"}], **overrides}
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": options}]}})

    def test_selection_order_and_common_layers_once(self):
        self.stub("machine", "_all.md", "common machine\n")
        self.stub("project", "orch/_all.md", "common project\n")
        self.stub("machine", "orch/roles/executor@codex.md", "codex only\n")
        self.stub("project", "orch/roles/executor@codex--gpt-6-sol.md", "sol only\n")
        doc = stubs.snapshot(self.project)
        base = "common machine\n\ncommon project\n"
        self.assertEqual(doc["targets"][stubs.target("executor")]["text"], base)
        self.assertEqual(stubs.text(doc, "executor"), stubs.HEADING + base)
        self.assertEqual(stubs.text(doc, "executor", "codex", "gpt-6-sol"),
                         stubs.HEADING + base + "\ncodex only\n\nsol only\n")
        self.assertEqual(stubs.text(doc, "executor", "codex", "gpt-6-astra"),
                         stubs.HEADING + base + "\ncodex only\n")
        self.assertEqual(stubs.text(doc, "executor", "claude-code", "sonnet"), stubs.HEADING + base)
        self.options()
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 1)
        for body in ("common machine", "common project", "codex only", "sol only"):
            self.assertEqual(prompt.count(body), 1, body)
        snapshot = json.loads((self.run_dir(err) / "instructions.json").read_text())
        self.assertEqual(snapshot["variant_resolution"]["codex/gpt-6-sol"], "gpt-6-sol")

    def fallback_setup(self):
        self.stub("machine", "orch/roles/executor.md", "common executor\n")
        self.stub("machine", "orch/roles/executor@codex.md", "codex exclusive\n")
        self.stub("machine", "orch/roles/executor@claude-code.md", "claude exclusive\n")
        self.options(fallback_routes=[{"role": "executor", "provider": "claude-code",
                                       "model_class": "implementation"}])

    def assert_fallback_prompt(self, err, attempt):
        prompt = self.prompt("executor", attempt)
        self.assertNotIn("codex exclusive", prompt)
        self.assertIn("claude exclusive", prompt)
        self.assertEqual(prompt.count("common executor"), 1)
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").read_text())
        self.assertEqual(manifest["route"]["provider"], "claude-code")
        self.assertEqual(manifest["prompt_sha256"], sha256_hex(prompt.encode("utf-8")))
        stub = [block for block in manifest["blocks"] if block["kind"] == "stub"]
        self.assertEqual(len(stub), 1)
        self.assertIn("executor@claude-code.md", stub[0]["origin"])
        self.assertNotIn("executor@codex.md", stub[0]["origin"])

    def test_provider_fallback_rebuilds_stub_and_manifest(self):
        self.fallback_setup()
        self.script({"executor": [CODEX_QUOTA, executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("codex exclusive", self.prompt("executor", 1))
        self.assertNotIn("claude exclusive", self.prompt("executor", 1))
        self.assert_fallback_prompt(err, 2)

    def test_gated_start_rebuilds_stub_and_manifest(self):
        self.fallback_setup()
        self.script({"executor": [executor_ok("W1")]})

        def gate_then_start(conductor, item, key, role, route, cancel):
            if role == "executor":
                gates.set_gate("codex", until=time.time() + 3600, code="PROVIDER_QUOTA",
                               run_id="other", now=time.time())
            return retry_service.start_route(conductor, item, key, role, route, cancel)

        with mock.patch.object(engine.Conductor, "_start_route", gate_then_start):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assert_fallback_prompt(err, 1)
        # W2: the started event names the route and the digest of the prompt really sent, not the codex one
        from aicore.ext import events as journal
        stored, _ = journal.read_events(self.project)
        started = [event.data for event in stored if event.type == "orch.agent.started" and event.data["role"] == "executor"]
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").read_text())
        self.assertEqual([(data["route"]["provider"], data["prompt_sha256"]) for data in started],
                         [("claude-code", manifest["prompt_sha256"])])

    def test_fallback_to_a_provider_without_variants_removes_the_block(self):
        self.stub("machine", "orch/roles/executor@codex.md", "codex exclusive\n")
        self.options(fallback_routes=[{"role": "executor", "provider": "claude-code",
                                       "model_class": "implementation"}])
        self.script({"executor": [CODEX_QUOTA, executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("## Additional instructions", self.prompt("executor", 2))
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").read_text())
        self.assertNotIn("stub", [block["kind"] for block in manifest["blocks"]])

    def test_resume_keeps_variant_text_and_resolved_family_after_catalog_change(self):
        self.stub("machine", "orch/roles/executor@codex--gpt-6-sol.md", "frozen family\n")
        self.stub("machine", "orch/roles/executor@codex--gpt-6-astra.md", "other family\n")
        self.options(stages=[{"role": "executor", "provider": "codex", "model": "gpt-6-sol-build",
                              "model_class": "implementation"}])
        catalog = json.loads(models.default_model_catalog_path().read_text())
        provider = next(p for p in catalog["providers"] if p["provider_id"] == "codex")
        entries = provider["model_inventory"]["entries"]
        next(e for e in entries if e["id"] == "gpt-6-sol")["patterns"] = ["gpt-6-sol-.*"]
        path = self.home / "models.json"
        path.write_text(json.dumps(catalog))
        self.script({"executor": [CODEX_QUOTA, executor_ok("W1")]})
        code, _, err = self.run_items("W1", extra=("--model-catalog", path))
        self.assertEqual(code, 1, err)
        snapshot_path = self.run_dir(err) / "instructions.json"
        kept = snapshot_path.read_bytes()
        self.assertEqual(json.loads(kept)["variant_resolution"]["codex/gpt-6-sol-build"], "gpt-6-sol")
        self.stub("machine", "orch/roles/executor@codex--gpt-6-sol.md", "changed family\n")
        next(e for e in entries if e["id"] == "gpt-6-sol")["patterns"] = []
        next(e for e in entries if e["id"] == "gpt-6-astra")["patterns"] = ["gpt-6-sol-.*"]
        path.write_text(json.dumps(catalog))
        gates.clear("codex")
        code, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name,
                                     "--model-catalog", path, "--json-lines")
        self.assertEqual(code, 0, err2)
        self.assertIn("STUBS_CHANGED", [line.get("reason_code") for line in self.lines(err2)])
        self.assertEqual(snapshot_path.read_bytes(), kept)
        self.assertIn("frozen family", self.prompt("executor", 2))
        self.assertNotIn("changed family", self.prompt("executor", 2))
        self.assertNotIn("other family", self.prompt("executor", 2))

    def test_variant_cli_list_show_and_publish(self):
        self.stub("machine", "orch/roles/executor@codex.md", "provider text\n")
        self.stub("project", "orch/roles/executor@codex--gpt-6-sol.md", "family text\n")
        self.stub("project", "orch/roles/executor@claude-code.md", "foreign text\n")
        code, out, err = self.orch("stubs", "show", "executor", "--provider", "codex", "--model", "gpt-6-sol")
        self.assertEqual(code, 0, err)
        self.assertIn("provider text", out)
        self.assertIn("family text", out)
        self.assertNotIn("foreign text", out)
        self.assertIn("executor@codex--gpt-6-sol.md", out)
        code, out, err = self.orch("stubs", "show", "executor")
        self.assertEqual(code, 0, err)
        self.assertNotIn("provider text", out)
        code, out, err = self.orch("stubs", "list")
        self.assertEqual(code, 0, err)
        self.assertIn("orch.role.executor@codex--gpt-6-sol", out)
        self.assertIn("machine:orch/roles/executor@codex.md", out)
        code, out, err = self.orch("stubs", "publish", "--json")
        self.assertEqual(code, 0, err)
        self.assertFalse(any("@" in row["slot"] for row in json.loads(out)["files"]))

    def test_disabled_and_machine_only_apply_to_variants(self):
        self.stub("machine", "orch/roles/executor@codex.md", "machine variant\n")
        self.stub("project", "orch/roles/executor@codex--gpt-6-sol.md", "project variant\n")
        self.assertEqual(stubs.snapshot(self.project, {"enabled": False})["targets"], {})
        doc = stubs.snapshot(self.project, {"layers": ["machine"]})
        text = stubs.text(doc, "executor", "codex", "gpt-6-sol")
        self.assertIn("machine variant", text)
        self.assertNotIn("project variant", text)
        self.write_config(extra='[orch.stubs]\nenabled = false')
        self.options()
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("machine variant", self.prompt("executor", 1))
        self.assertNotIn("project variant", self.prompt("executor", 1))
        self.assertNotIn(stubs.HEADING, self.prompt("executor", 1))

    def test_symlink_variant_file_and_directory_are_refused(self):
        root = self.project / ".swissknifeman" / "stubs"
        path = root / "orch" / "roles" / "executor@codex.md"
        path.parent.mkdir(parents=True)
        path.symlink_to("/etc/hostname")
        with self.assertRaises(stubs.core.StubError) as caught:
            stubs.snapshot(self.project)
        self.assertEqual(caught.exception.code, "STUB_SYMLINK_FORBIDDEN")
        path.unlink()
        path.parent.rmdir()
        path.parent.symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(stubs.core.StubError) as caught:
            stubs.snapshot(self.project)
        self.assertEqual(caught.exception.code, "STUB_SYMLINK_FORBIDDEN")
        self.assertEqual(stubs.snapshot(self.project, {"enabled": False})["targets"], {})
        self.assertEqual(stubs.snapshot(self.project, {"layers": ["machine"]})["targets"], {})

    def test_invalid_variant_filename_is_named_in_the_error(self):
        for variant in ("Codex", "codex--gpt--sol", "codex--", ""):
            path = self.stub("machine", f"orch/roles/executor@{variant}.md", "rule\n")
            with self.assertRaises(stubs.core.StubError) as caught:
                stubs.snapshot(self.project)
            self.assertEqual(caught.exception.code, "STUB_TARGET_UNKNOWN")
            self.assertIn(path.name, str(caught.exception))
            path.unlink()


class VariantCompatibilityTests(unittest.TestCase):
    def test_snapshot_without_variants_matches_the_previous_digest_and_shape(self):
        with mock.patch.object(stubs.core, "roots", return_value={"machine": Path("/machine"), "project": Path("/project")}), \
                mock.patch.object(stubs.core, "_read", side_effect=lambda path: b"base\n" if str(path) == "/machine/_all.md" else None):
            doc = stubs.snapshot(Path("/project"))
        # Captured from the pre-variant implementation, including a common part for all six roles.
        expected_part = {"slot": "_all.md", "layer": "machine", "path": "/machine/_all.md", "mode": "replace",
                         "sha256": "f34848ca92665c342abd5816c9e3eda0e82180671195362bcd0080544a3bc2ac",
                         "bytes": 5, "reason": "machine"}
        expected = {"$schema": stubs.core.SCHEMA, "layers": ["machine", "project"],
                    "digest": "sha256:be8fa47b7b02b75c034653e9649bf77474570ee23553b517b4bb2a5ba2b768cd",
                    "targets": {stubs.target(role): {"text": "base\n", "parts": [expected_part]} for role in stubs.ROLES}}
        self.assertEqual(json.dumps(doc, sort_keys=True), json.dumps(expected, sort_keys=True))
        # Old snapshots have neither variant bodies nor route resolution.
        self.assertEqual(stubs.text(expected, "executor", "codex", "gpt-6-sol"), stubs.HEADING + "base\n")

    def test_model_family_prefers_exact_id_then_fullmatch_in_catalog_order(self):
        catalog = models.ModelCatalog("test", (models.ProviderModels("test", {}, {}, {"entries": [
            {"id": "first", "patterns": ["model-.*"]}, {"id": "second", "patterns": ["model-.*"]},
            {"id": "model-exact"}]}),))
        self.assertEqual(stubs.model_family("test", "model-exact", catalog), "model-exact")
        self.assertEqual(stubs.model_family("test", "model-alias", catalog), "first")
        self.assertEqual(stubs.model_family("test", "prefix-model-alias", catalog), "prefix-model-alias")
        self.assertEqual(stubs.model_family("missing", "model-alias", catalog), "model-alias")


if __name__ == "__main__":
    unittest.main()
