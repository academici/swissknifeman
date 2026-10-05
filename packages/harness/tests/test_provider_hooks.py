"""P5.3 native lifecycle/context registration and payload adapters."""
import json
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analyst" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import ArtifactActionKind, ProviderId, apply_plan, plan_artifact_lock, serialize_lock
from harness.hooks import (CodexLifecycleFragment, LifecycleRequest, adapt_codex_hook_payload,
                           block_codex_observer, codex_d104_observer_fragment,
                           plan_codex_capture_artifact, plan_codex_lifecycle_artifacts, plan_lifecycle,
                           render_codex_hook_handler, render_codex_hooks,
                           validate_d104_codex_lifecycle_composition)
from harness.profiles import load_catalog
from analyst.events import read_events
from analyst.cli import main as analyst_main

PACKAGE = Path(__file__).resolve().parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
BINDINGS = PACKAGE / "configs/codex/hooks/lifecycle-context-bindings.json"
CLAUDE_FIXTURE = PACKAGE / "tests/fixtures_data/claude-hook-registration-v1.json"


class ProviderHookTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)
        self.requests = tuple(LifecycleRequest(surface.id) for surface in self.catalog.surfaces
                              if surface.kind in {"lifecycle", "context"})

    def test_exact_common_surface_coverage_and_explicit_unsupported(self):
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=self.requests, codex_bindings_path=BINDINGS)
        self.assertEqual({binding.surface_id for binding in plan.bindings},
                         {request.surface_id for request in self.requests})
        unsupported = {binding.surface_id for binding in plan.bindings
                       if binding.support_level == "unsupported"}
        self.assertEqual(unsupported, {
            "lifecycle.notification", "lifecycle.plan-regen", "context.output-style",
            "context.plans-directory"})
        self.assertEqual({binding.surface_id for binding in plan.bindings
                          if binding.support_level == "config-native"},
                         {"lifecycle.auto-approval"})
        self.assertEqual({binding.surface_id for binding in plan.bindings
                          if binding.support_level == "hook-native"},
                         {"context.observer", "lifecycle.command-log", "lifecycle.tool-telemetry",
                          "lifecycle.run-report",
                          "lifecycle.router", "lifecycle.memory", "lifecycle.pack-guard",
                          "lifecycle.changelog-gate", "lifecycle.review-gate",
                          "lifecycle.daemon-safety", "lifecycle.git-guardrails",
                          "lifecycle.plan-guard"})
        self.assertEqual({item.code for item in plan.diagnostics},
                         {"HARNESS_ACTIVATION_UNSUPPORTED"})

    def test_required_untrusted_and_unsupported_intents_block(self):
        untrusted = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=False,
                                  requests=(LifecycleRequest("context.observer", True),),
                                  codex_bindings_path=BINDINGS)
        self.assertFalse(untrusted.green)
        self.assertEqual(untrusted.diagnostics[0].code, "HARNESS_TRUST_REQUIRED")
        unsupported = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                                    requests=(LifecycleRequest("context.output-style", True),),
                                    codex_bindings_path=BINDINGS)
        self.assertFalse(unsupported.green)
        self.assertEqual(unsupported.diagnostics[0].code, "HARNESS_ACTIVATION_UNSUPPORTED")

    def test_only_hook_native_binding_is_registered(self):
        requests = (LifecycleRequest("context.observer"),)
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=requests, codex_bindings_path=BINDINGS)
        rendered = json.loads(render_codex_hooks(plan))
        self.assertEqual(set(rendered["hooks"]), {"SessionStart"})
        self.assertEqual(rendered["hooks"]["SessionStart"][0]["matcher"],
                         "startup|resume|clear|compact")
        self.assertIn("$(git rev-parse --show-toplevel)/.codex/hooks/lifecycle.py",
                      rendered["hooks"]["SessionStart"][0]["hooks"][0]["command"])
        self.assertTrue(all(binding.kill_switch == "[features].hooks=false" for binding in plan.bindings))

    def test_config_native_and_unsupported_surfaces_never_leak_into_hooks_json(self):
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=(LifecycleRequest("lifecycle.auto-approval"),
                                        LifecycleRequest("context.output-style"),
                                        LifecycleRequest("context.observer")),
                              codex_bindings_path=BINDINGS)
        self.assertTrue(plan.green)
        rendered = json.loads(render_codex_hooks(plan))
        commands = json.dumps(rendered["hooks"])
        self.assertNotIn("lifecycle.auto-approval", commands)
        self.assertNotIn("context.output-style", commands)

    def test_payload_adapter_fixture_and_malformed_shape_fail_closed(self):
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=(LifecycleRequest("context.observer"),),
                              codex_bindings_path=BINDINGS)
        observer = plan.bindings[0]
        adapted = adapt_codex_hook_payload(observer, {"session_id": "s", "cwd": "/tmp/project",
            "hook_event_name": "SessionStart", "model": "gpt-5.6-terra",
            "permission_mode": "dontAsk", "turn_id": "t", "source": "startup"})
        self.assertEqual(adapted["event"], "SessionStart")
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            adapt_codex_hook_payload(observer, {"session_id": "s", "cwd": "/tmp/project",
                "hook_event_name": "SessionStart", "model": "gpt-5.6-terra", "permission_mode": "dontAsk"})

    def test_claude_current_registration_fixture_remains_independent(self):
        fixture = json.loads(CLAUDE_FIXTURE.read_text(encoding="utf-8"))
        bindings = plan_lifecycle(self.catalog, provider_id=ProviderId.CLAUDE_CODE, trusted=True,
                                  requests=(LifecycleRequest("lifecycle.auto-approval"),
                                            LifecycleRequest("lifecycle.router"),
                                            LifecycleRequest("lifecycle.run-report"),
                                            LifecycleRequest("lifecycle.pack-guard"),
                                            LifecycleRequest("lifecycle.changelog-gate"),
                                            LifecycleRequest("lifecycle.plan-guard"),
                                            LifecycleRequest("lifecycle.plan-regen"))).bindings
        actual = {"auto-approval": bindings[0], "router": bindings[1], "run-report": bindings[2],
                  "pack-guard": bindings[3], "changelog-gate": bindings[4],
                  "plan-guard": bindings[5], "plan-regen": bindings[6]}
        for name, expected in fixture.items():
            self.assertEqual(actual[name].event, expected["event"])
            self.assertEqual(actual[name].matcher, expected["matcher"])
            self.assertEqual(actual[name].handler, expected["handler"])
            self.assertEqual(actual[name].kill_switch, expected["kill_switch"])

    def test_claude_projection_covers_the_same_common_surface_set(self):
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CLAUDE_CODE, trusted=True,
                              requests=self.requests)
        self.assertEqual({binding.surface_id for binding in plan.bindings},
                         {request.surface_id for request in self.requests})

    def test_generated_codex_consumer_is_deterministic_and_check_empty(self):
        requests = (LifecycleRequest("context.observer"),)
        lifecycle = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                                   requests=requests, codex_bindings_path=BINDINGS)
        artifacts = plan_codex_lifecycle_artifacts(lifecycle, bindings_path=BINDINGS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = plan_artifact_lock(root, artifacts, lock_bytes=None)
            applied = apply_plan(root, initial)
            self.assertEqual([action.action for action in applied.actions],
                             [ArtifactActionKind.NOOP, ArtifactActionKind.NOOP])
            self.assertTrue((root / ".codex/hooks.json").is_file())
            self.assertTrue((root / ".codex/hooks/lifecycle.py").is_file())
            handler = root / ".codex/hooks/lifecycle.py"
            rendered = json.loads((root / ".codex/hooks.json").read_text(encoding="utf-8"))
            surfaces = [command.rsplit(" ", 1)[-1] for groups in rendered["hooks"].values()
                        for group in groups for hook in group["hooks"] for command in [hook["command"]]]
            self.assertEqual(surfaces, ["context.observer"])
            for surface in surfaces:
                observed = subprocess.run([sys.executable, str(handler), "--surface", surface],
                    input=json.dumps({"session_id": "s", "cwd": str(root), "hook_event_name": "SessionStart",
                        "model": "gpt-5.6-terra", "permission_mode": "dontAsk", "source": "startup"}).encode(),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20)
                self.assertIn("read-only policy active", observed.stdout.decode("utf-8"))
            for argv, payload in ((["--surface", "lifecycle.router"], {"hook_event_name": "SessionStart"}),
                                 (["--surface", "context.observer"], {"hook_event_name": "SessionStart"})):
                rejected = subprocess.run([sys.executable, str(handler), *argv], input=json.dumps(payload).encode(),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
                self.assertEqual(rejected.returncode, 2)
            lock = serialize_lock(initial.next_lock)
            second = plan_artifact_lock(root, artifacts, lock_bytes=lock)
            self.assertEqual([action.action for action in second.actions],
                             [ArtifactActionKind.NOOP, ArtifactActionKind.NOOP])

    def test_d104_fragment_validates_only_native_memory_observer_composition(self):
        lifecycle = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                                   requests=(LifecycleRequest("context.observer", True),),
                                   codex_bindings_path=BINDINGS)
        fragment = codex_d104_observer_fragment(lifecycle)
        self.assertEqual(fragment.target_path, ".codex/hooks.json")
        self.assertEqual(fragment.event, "SessionStart")
        self.assertEqual(fragment.handler_bytes, render_codex_hook_handler())
        memory_command = "bash /home/user/projects/packages/swissknifeman/.claude/maind-memory.sh"
        document = {"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": memory_command}]}, fragment.group
        ]}}
        rendered = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        validate_d104_codex_lifecycle_composition(rendered, memory_command=memory_command,
                                                  fragment=fragment)

        invalid_documents = (
            {"hooks": {"PreToolUse": document["hooks"]["SessionStart"]}},
            {"hooks": {"SessionStart": [fragment.group]}},
            {"hooks": {"SessionStart": [
                {"hooks": [{"type": "command", "command": memory_command}]},
                fragment.group, fragment.group]}},
            {"hooks": {"SessionStart": [
                {"hooks": [{"type": "command", "command": memory_command}]},
                {"hooks": [{"type": "command", "command": memory_command}]}]}},
        )
        for invalid in invalid_documents:
            with self.assertRaisesRegex(ValueError, "HARNESS_D104_LIFECYCLE_INVALID"):
                validate_d104_codex_lifecycle_composition(
                    (json.dumps(invalid) + "\n").encode("utf-8"), memory_command=memory_command,
                    fragment=fragment)
        invalid_target = CodexLifecycleFragment(".codex/not-hooks.json", fragment.event,
                                                fragment.group, fragment.handler_bytes)
        with self.assertRaisesRegex(ValueError, "HARNESS_D104_LIFECYCLE_INVALID"):
            validate_d104_codex_lifecycle_composition(rendered, memory_command=memory_command,
                                                      fragment=invalid_target)

    def test_normal_observer_remains_ownership_conflict_on_d104_preimage(self):
        preimage = '''{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash /home/user/projects/packages/swissknifeman/.claude/maind-memory.sh"
          }
        ]
      }
    ]
  }
}
'''.encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ".codex/hooks.json"
            target.parent.mkdir(parents=True)
            target.write_bytes(preimage)
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                block_codex_observer(SimpleNamespace(root=PACKAGE), root,
                                     trusted=True, repair=False, dry=True)
            self.assertEqual(target.read_bytes(), preimage)
            self.assertFalse((root / ".codex/hooks/lifecycle.py").exists())

    def test_codex_observer_cli_seam_preserves_other_package_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = plan_codex_capture_artifact(bindings_path=BINDINGS)
            initial = plan_artifact_lock(root, (capture,), lock_bytes=None)
            apply_plan(root, initial)
            with redirect_stdout(io.StringIO()):
                block_codex_observer(SimpleNamespace(root=PACKAGE), root,
                                     trusted=True, repair=False, dry=False)
            lock = json.loads((root / ".swissknifeman/provider-artifacts.lock.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual({record["artifact_id"] for record in lock["records"]}, {
                "harness.codex.capture.handler", "harness.codex.lifecycle.handler",
                "harness.codex.lifecycle.hooks"})
            self.assertTrue((root / ".codex/hooks/analytics-capture.py").is_file())

    def test_generated_capture_bundle_redacts_to_supported_semantics(self):
        artifact = plan_codex_capture_artifact(bindings_path=BINDINGS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = plan_artifact_lock(root, (artifact,), lock_bytes=None)
            apply_plan(root, plan)
            handler = root / ".codex/hooks/analytics-capture.py"
            rejected = subprocess.run([sys.executable, str(handler)], input=json.dumps(
                {"session_id": "s", "occurred_at": "2026-07-22T00:00:00Z", "metrics": {"usage": 1},
                 "prompt": "must-not-persist"}).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(rejected.returncode, 2)
            observed = subprocess.run([sys.executable, str(handler)], input=json.dumps(
                {"session_id": "s", "occurred_at": "2026-07-22T00:00:00Z", "metrics": {"usage": 1}}).encode(),
                stdout=subprocess.PIPE, check=True)
            payload_bytes = observed.stdout
            payload = json.loads(payload_bytes)
            self.assertEqual(payload["metrics"], {"usage": 1})
            self.assertNotIn("source_sha256", payload)
            source = root / "generated-capture.json"
            source.write_bytes(payload_bytes)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                with redirect_stdout(io.StringIO()):
                    analyst_main([str(root), "capture", "--provider", "codex", "--schema", "1",
                                  "--input", str(source)])
            finally:
                os.chdir(cwd)
            event = read_events(root)[0]
            self.assertEqual(event.provenance["sha256"], hashlib.sha256(payload_bytes).hexdigest())


if __name__ == "__main__":
    unittest.main()
