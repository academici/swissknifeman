"""P2.2 — multi-surface Codex lifecycle dispatcher and class A observer bindings."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/task/lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import ProviderId, load_provider_manifest, support_for
from harness.hooks import (LifecycleRequest, adapt_codex_hook_payload, plan_lifecycle,
                           render_codex_hook_handler, render_codex_hooks)
from harness.profiles import load_catalog

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
BINDINGS = PACKAGE / "configs/codex/hooks/lifecycle-context-bindings.json"
MANIFEST = ROOT / "configs/provider-capabilities.json"

CLASS_A_SURFACES = ("lifecycle.command-log", "lifecycle.run-report", "lifecycle.router",
                   "lifecycle.memory")

_COMMON_FIELDS = {"session_id": "s1", "cwd": "/tmp/project", "model": "gpt-5.6-terra"}


def _run_handler(handler_path, surface, payload, *, env=None, cwd=None):
    return subprocess.run([sys.executable, str(handler_path), "--surface", surface],
                         input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, cwd=cwd, timeout=20)


class CodexLifecycleSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)
        self.handler_bytes = render_codex_hook_handler()

    def _write_handler(self, directory):
        path = Path(directory) / "lifecycle.py"
        path.write_bytes(self.handler_bytes)
        return path

    def test_manifest_levels_raised_with_adapter_id_and_evidence(self):
        manifest = load_provider_manifest(MANIFEST)
        for surface_id in CLASS_A_SURFACES:
            support = support_for(manifest, surface_id, ProviderId.CODEX)
            self.assertEqual(support.level.value, "adapted")
            self.assertEqual(support.adapter_id, f"harness.codex.{surface_id}")
            self.assertTrue(support.limitations)
            self.assertTrue(support.evidence)
            for evidence in support.evidence:
                self.assertEqual(evidence.source,
                                 "docs/provider-support.md")

    def test_bindings_are_hook_native_with_manifest_synchronized(self):
        requests = tuple(LifecycleRequest(surface_id) for surface_id in CLASS_A_SURFACES)
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=requests, codex_bindings_path=BINDINGS)
        self.assertTrue(plan.green)
        levels = {binding.surface_id: binding.support_level for binding in plan.bindings}
        self.assertEqual(levels, {surface_id: "hook-native" for surface_id in CLASS_A_SURFACES})
        events = {binding.surface_id: binding.event for binding in plan.bindings}
        self.assertEqual(events, {
            "lifecycle.command-log": "PreToolUse", "lifecycle.run-report": "SessionEnd",
            "lifecycle.router": "UserPromptSubmit", "lifecycle.memory": "SessionStart"})
        rendered = json.loads(render_codex_hooks(plan))
        commands = json.dumps(rendered["hooks"])
        for surface_id in CLASS_A_SURFACES:
            self.assertIn(surface_id, commands)

    def test_adapt_codex_hook_payload_per_event_required_fields(self):
        requests = tuple(LifecycleRequest(surface_id) for surface_id in CLASS_A_SURFACES)
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=requests, codex_bindings_path=BINDINGS)
        by_surface = {binding.surface_id: binding for binding in plan.bindings}
        cases = {
            "lifecycle.command-log": ({**_COMMON_FIELDS, "hook_event_name": "PreToolUse",
                                       "tool_name": "Bash", "tool_input": {"command": "ls"}}, "tool_input"),
            "lifecycle.run-report": ({**_COMMON_FIELDS, "hook_event_name": "SessionEnd",
                                      "reason": "other"}, "reason"),
            "lifecycle.router": ({**_COMMON_FIELDS, "hook_event_name": "UserPromptSubmit",
                                  "prompt": "implement a feature"}, "prompt"),
            "lifecycle.memory": ({**_COMMON_FIELDS, "hook_event_name": "SessionStart",
                                 "permission_mode": "dontAsk", "source": "startup"}, "source"),
        }
        for surface_id, (payload, required_field) in cases.items():
            binding = by_surface[surface_id]
            adapted = adapt_codex_hook_payload(binding, payload)
            self.assertEqual(adapted["event"], binding.event)
            self.assertEqual(adapted[required_field], payload[required_field])
            incomplete = {key: value for key, value in payload.items() if key != required_field}
            with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
                adapt_codex_hook_payload(binding, incomplete)

    def test_permission_mode_optional_outside_session_start(self):
        requests = (LifecycleRequest("lifecycle.command-log"),)
        binding = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                                 requests=requests, codex_bindings_path=BINDINGS).bindings[0]
        payload = {**_COMMON_FIELDS, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                  "tool_input": {"command": "ls"}}
        adapted = adapt_codex_hook_payload(binding, payload)
        self.assertEqual(adapted["permission_mode"], "")

    def test_dispatcher_rejects_unknown_surface_and_malformed_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            handler = self._write_handler(directory)
            rejected = _run_handler(handler, "lifecycle.does-not-exist",
                                    {**_COMMON_FIELDS, "hook_event_name": "PreToolUse"})
            self.assertEqual(rejected.returncode, 2)
            malformed = subprocess.run([sys.executable, str(handler), "--surface",
                                       "lifecycle.command-log"], input=b"not-json",
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            self.assertEqual(malformed.returncode, 2)

    def test_command_log_writes_codex_qualified_line_and_never_touches_claude_log(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            env = {**os.environ, "HOME": home}
            payload = {**_COMMON_FIELDS, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": {"command": "ls -la", "description": "list"}}
            result = _run_handler(handler, "lifecycle.command-log", payload, env=env)
            self.assertEqual(result.returncode, 0)
            log = Path(home) / ".codex/logs/bash-commands.jsonl"
            self.assertTrue(log.is_file())
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(entry["command"], "ls -la")
            self.assertEqual(entry["session"], "s1")
            self.assertFalse((Path(home) / ".claude/logs/bash-commands.jsonl").exists())

    def test_run_report_parses_transcript_when_available(self):
        project = str(PACKAGE.parents[1])
        with tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            transcript = Path(scratch) / "transcript.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "c1", "name": "mcp__codegraph__find_symbol",
                     "input": {"name": "Foo"}}]}}),
                json.dumps({"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": "ok",
                     "is_error": False}]}}),
            ]) + "\n", encoding="utf-8")
            payload = {"session_id": "s1", "cwd": project, "model": "gpt-5.6-terra",
                      "hook_event_name": "SessionEnd", "reason": "other",
                      "transcript_path": str(transcript)}
            result = _run_handler(handler, "lifecycle.run-report", payload)
            self.assertEqual(result.returncode, 0)
            record = json.loads((Path(project) / ".codex/runs/s1.json").read_text(encoding="utf-8"))
            self.assertEqual(record["schema"], 2)
            self.assertEqual(record["provider_id"], "codex")
            self.assertEqual(record["codegraph"]["find_symbol"]["calls"], 1)
            self.assertTrue((Path(project) / ".codex/runs/.gitignore").is_file())
            (Path(project) / ".codex/runs/s1.json").unlink(missing_ok=True)

    def test_run_report_stub_without_transcript(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "SessionEnd",
                      "reason": "other"}
            result = _run_handler(handler, "lifecycle.run-report", payload)
            self.assertEqual(result.returncode, 0)
            record = json.loads((Path(project) / ".codex/runs/s1.json").read_text(encoding="utf-8"))
            self.assertEqual(record["schema"], 1)
            self.assertEqual(record["session_id"], "s1")

    def test_router_does_not_inject_task_for_ordinary_prompts(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            strong = _run_handler(handler, "lifecycle.router", {
                **_COMMON_FIELDS, "hook_event_name": "UserPromptSubmit",
                "prompt": "please implement a new feature endpoint"})
            self.assertEqual(strong.returncode, 0)
            self.assertEqual(strong.stdout, b"")
            weak = _run_handler(handler, "lifecycle.router", {
                **_COMMON_FIELDS, "hook_event_name": "UserPromptSubmit", "prompt": "hello there"})
            self.assertEqual(weak.returncode, 0)
            self.assertEqual(weak.stdout, b"")

    def test_memory_activation_reads_project_scoped_override_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            codex_dir = Path(project) / ".codex"
            codex_dir.mkdir()
            (codex_dir / "memory.env.ini").write_text("MODE=off\n", encoding="utf-8")
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "SessionStart",
                      "permission_mode": "dontAsk", "source": "startup"}
            result = _run_handler(handler, "lifecycle.memory", payload)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
            written = [path for path in Path(project).rglob("*") if path.is_file()]
            self.assertEqual(len(written), 1)  # only the memory.env.ini we wrote ourselves


if __name__ == "__main__":
    unittest.main()
