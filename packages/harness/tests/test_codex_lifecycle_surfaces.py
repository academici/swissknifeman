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
from task import journal, terminal_admission

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
                                 "plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/contracts/"
                                 "codex-parity-verdicts-v1.md")

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

    def test_terminal_admission_stop_requires_documented_stop_fields_and_is_inactive_by_default(self):
        binding = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                                 requests=(LifecycleRequest("lifecycle.terminal-admission"),),
                                 codex_bindings_path=BINDINGS).bindings[0]
        payload = {**_COMMON_FIELDS, "hook_event_name": "Stop", "turn_id": "t1",
                   "stop_hook_active": False, "last_assistant_message": "final"}
        self.assertEqual(adapt_codex_hook_payload(binding, payload)["event"], "Stop")
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            adapt_codex_hook_payload(binding, {key: value for key, value in payload.items()
                                               if key != "last_assistant_message"})
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            result = _run_handler(handler, "lifecycle.terminal-admission", {**payload, "cwd": project})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_stop_dispatchers_reject_open_session_without_task_payload_or_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "packages").mkdir()
            (root / "packages/task").symlink_to(ROOT / "packages/task", target_is_directory=True)
            for provider in ("codex", "claude"):
                config = root / f".{provider}/terminal-admission.env.ini"
                config.parent.mkdir()
                config.write_text("MODE=on\n")
            path = root / "plans/DEMO/journal.jsonl"
            path.parent.mkdir(parents=True)
            entry = journal.new_entry(plan_id="DEMO", item_id="P7.4", command="plan-run",
                                      actor="sonnet/medium", result="in-progress",
                                      session_id="s1", run_id="run-1", attempt=1)
            path.write_text(json.dumps(entry) + "\n")
            before = path.read_bytes()
            handler = self._write_handler(root)
            payload = {**_COMMON_FIELDS, "cwd": str(root), "hook_event_name": "Stop",
                       "turn_id": "t1", "stop_hook_active": False,
                       "last_assistant_message": "Subset tests passed. Done."}
            adapters = ([sys.executable, str(handler), "--surface", "lifecycle.terminal-admission"],
                        [sys.executable, str(PACKAGE / "configs/claude-code/hooks/terminal-admission/terminal-admission.py")])
            for command in adapters:
                with self.subTest(adapter=command):
                    result = subprocess.run(command, input=json.dumps(payload), text=True,
                                            capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), {
                        "decision": "block", "reason": "TASK_OPEN_RUN_FINAL_FORBIDDEN"})
                    ordinary = subprocess.run(command, input=json.dumps({**payload, "session_id": "ordinary"}),
                                              text=True, capture_output=True, timeout=20)
                    self.assertEqual(ordinary.returncode, 0, ordinary.stderr)
                    self.assertEqual(ordinary.stdout, "")
            self.assertEqual(path.read_bytes(), before)

    def test_terminal_admission_proves_forty_advancing_boundaries_then_one_exact_final(self):
        """Exercise the shared P4.1 reducer; providers only render its verdict."""
        def continuity(outcome):
            return {
                "schema_version": "session-continuity-decision/v1",
                "outcome": outcome,
                "reason": "terminal-evidence" if outcome == "terminal" else "compatible-active-work",
                "evidence": ["batch:" + "0" * 64],
                "runnable": outcome != "terminal",
            }

        receipt = {
            "schema_version": "terminal-delivery-receipt/v1", "plan_id": "PLAN", "subject": "P4.2",
            "next_exact": "$ task:plan-audit PLAN P4", "recommendation": "Audit P4.",
            "journal": {"run_id": "run-1", "command": "plan-run"},
        }
        identity = terminal_admission.Identity(
            plan_id="PLAN", subject="P4.2", command="plan-run", run_id="run-1",
            task_session="task-session", provider="codex", provider_session="provider-session", turn_id="turn-1",
        )
        with tempfile.TemporaryDirectory() as directory:
            store = terminal_admission.FileStore(Path(directory))
            lease = terminal_admission.arm(store, identity, continuity("continue-root"),
                                           progress_fingerprint="0" * 64, ttl_seconds=60)
            blocked = []
            for boundary in range(1, 41):
                progress = f"{boundary:064x}"
                lease = terminal_admission.refresh(
                    store, identity, expected_sequence=lease.sequence, progress_fingerprint=progress,
                    continuity=continuity("continue-root"), ttl_seconds=60,
                )
                verdict = terminal_admission.evaluate(
                    store, identity, continuity("continue-root"), receipt_reader=lambda: receipt,
                    proposed_message=f"non-terminal-{boundary}",
                )
                blocked.append(verdict)
            lease = terminal_admission.refresh(
                store, identity, expected_sequence=lease.sequence, progress_fingerprint="f" * 64,
                continuity=continuity("terminal"), ttl_seconds=60,
            )
            allowed = terminal_admission.evaluate(
                store, identity, continuity("terminal"), receipt_reader=lambda: receipt,
                proposed_message=terminal_admission.required_final_message(receipt),
            )
            events = (Path(directory) / "events.jsonl").read_text(encoding="utf-8")

        self.assertEqual(len(blocked), 40)
        self.assertTrue(all(not verdict.final_allowed for verdict in blocked))
        self.assertEqual([verdict.sequence for verdict in blocked], list(range(2, 42)))
        self.assertTrue(allowed.final_allowed)
        self.assertEqual(allowed.sequence, lease.sequence + 1)
        self.assertNotIn("non-terminal-1", events)

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

    def test_run_report_captures_session_boundary_only(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "SessionEnd",
                      "reason": "other", "transcript_path": "/tmp/transcript.jsonl"}
            result = _run_handler(handler, "lifecycle.run-report", payload)
            self.assertEqual(result.returncode, 0)
            record_path = Path(project) / ".codex/runs/s1.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record, {"schema": 1, "session_id": "s1", "cwd": project,
                                      "reason": "other", "transcript_path": "/tmp/transcript.jsonl"})
            self.assertTrue((Path(project) / ".codex/runs/.gitignore").is_file())

    def test_router_emits_bare_task_command_bias_above_threshold_and_stays_silent_below(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            strong = _run_handler(handler, "lifecycle.router", {
                **_COMMON_FIELDS, "hook_event_name": "UserPromptSubmit",
                "prompt": "please implement a new feature endpoint"})
            self.assertEqual(strong.returncode, 0)
            hint = json.loads(strong.stdout)["systemMessage"]
            self.assertIn("[intent-router] bias (non-authoritative)", hint)
            self.assertIn("task:", hint)
            self.assertNotIn("/task:", hint)
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
