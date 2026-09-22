"""Cursor P0: native hooks.json rendering and safe-dirs handler conformance."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import ProviderId
from harness.hooks import (LifecycleRequest, block_cursor_lifecycle,
                           plan_lifecycle, render_cursor_hook_handler,
                           render_cursor_hooks)
from harness.profiles import load_catalog

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
CURSOR_BINDINGS = PACKAGE / "configs/cursor/hooks/lifecycle-context-bindings.json"
WIRE_AFTER_FIXTURE = PACKAGE / "tests/fixtures_data/cursor-hook-wire-v1.json"
WIRE_BEFORE_FIXTURE = PACKAGE / "tests/fixtures_data/cursor-hook-wire-before-v1.json"


def _run_handler(handler_path, surface, payload, *, env=None):
    return subprocess.run(
        [sys.executable, str(handler_path), "--surface", surface],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=20,
    )


class CursorHookRenderTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)

    def _cursor_plan(self, *surfaces):
        requests = tuple(LifecycleRequest(surface, True) for surface in surfaces)
        return plan_lifecycle(
            self.catalog,
            provider_id=ProviderId.CURSOR,
            trusted=True,
            requests=requests,
            cursor_bindings_path=CURSOR_BINDINGS,
        )

    def test_real_after_wire_fixture_shape_is_pinned(self):
        value = json.loads(WIRE_AFTER_FIXTURE.read_text(encoding="utf-8"))
        payload = value["payload"]
        self.assertEqual(value["schema"], 1)
        self.assertEqual(value["source"], "native-afterShellExecution-probe")
        self.assertEqual(payload["hook_event_name"], "afterShellExecution")
        self.assertIn("conversation_id", payload)
        self.assertIn("workspace_roots", payload)
        self.assertIn("sandbox", payload)

    def test_real_before_wire_fixture_shape_is_pinned(self):
        value = json.loads(WIRE_BEFORE_FIXTURE.read_text(encoding="utf-8"))
        payload = value["payload"]
        self.assertEqual(value["schema"], 1)
        self.assertEqual(value["source"], "native-beforeShellExecution-probe")
        self.assertEqual(payload["hook_event_name"], "beforeShellExecution")
        self.assertIn("conversation_id", payload)
        self.assertIn("cwd", payload)
        self.assertIn("command", payload)

    def test_render_cursor_hooks_emits_native_flat_shape_with_version(self):
        plan = self._cursor_plan("security.safe-dirs")
        rendered = json.loads(render_cursor_hooks(plan))
        self.assertEqual(rendered["version"], 1)
        entry = rendered["hooks"]["beforeShellExecution"][0]
        self.assertEqual(entry["failClosed"], True)
        self.assertNotIn("hooks", entry)
        self.assertIn("${CURSOR_PROJECT_DIR:-.}/.cursor/hooks/lifecycle.py", entry["command"])

    def test_render_cursor_hooks_includes_p3_observability_events(self):
        plan = self._cursor_plan(
            "security.safe-dirs",
            "lifecycle.command-log",
            "lifecycle.run-report",
        )
        rendered = json.loads(render_cursor_hooks(plan))
        self.assertEqual(set(rendered["hooks"]), {
            "beforeShellExecution", "afterShellExecution", "sessionEnd",
        })
        by_event = {
            event: [entry["command"].rsplit(" ", 1)[-1] for entry in entries]
            for event, entries in rendered["hooks"].items()
        }
        self.assertEqual(by_event["afterShellExecution"], ["lifecycle.command-log"])
        self.assertEqual(by_event["sessionEnd"], ["lifecycle.run-report"])
        self.assertNotIn("failClosed", rendered["hooks"]["afterShellExecution"][0])
        self.assertNotIn("failClosed", rendered["hooks"]["sessionEnd"][0])

    def test_render_is_deterministic_and_preserves_user_entries(self):
        plan = self._cursor_plan("security.safe-dirs")
        existing = {
            "version": 1,
            "hooks": {
                "beforeShellExecution": [
                    {"command": "/usr/local/bin/custom-before.sh", "timeout": 1.0}
                ],
                "afterShellExecution": [
                    {"command": "/usr/local/bin/custom-after.sh"}
                ],
            },
        }
        first = render_cursor_hooks(plan, existing_document=existing)
        second = render_cursor_hooks(plan, existing_document=json.loads(first))
        self.assertEqual(first, second)
        rendered = json.loads(first)
        self.assertEqual(
            rendered["hooks"]["beforeShellExecution"][0],
            {"command": "/usr/local/bin/custom-before.sh", "timeout": 1.0},
        )
        self.assertEqual(
            rendered["hooks"]["afterShellExecution"],
            [{"command": "/usr/local/bin/custom-after.sh"}],
        )

    def test_block_cursor_lifecycle_writes_merge_only_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            hooks_path = target / ".cursor" / "hooks.json"
            with redirect_stdout(io.StringIO()):
                block_cursor_lifecycle(
                    SimpleNamespace(root=PACKAGE),
                    target,
                    surfaces=("security.safe-dirs",),
                    trusted=True,
                    repair=False,
                    dry=False,
                )
            self.assertTrue(hooks_path.is_file())
            self.assertTrue((target / ".cursor/hooks/lifecycle.py").is_file())
            first = json.loads(hooks_path.read_text(encoding="utf-8"))
            self.assertTrue(any(
                item.get("command", "").startswith("python3 \"${CURSOR_PROJECT_DIR:-.}/.cursor/hooks/lifecycle.py\" --surface security.safe-dirs")
                for item in first["hooks"]["beforeShellExecution"]
            ))
            first["hooks"]["beforeShellExecution"].insert(0, {"command": "/opt/custom.sh"})
            hooks_path.write_text(json.dumps(first, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            merged_bytes = hooks_path.read_bytes()
            with redirect_stdout(io.StringIO()):
                block_cursor_lifecycle(
                    SimpleNamespace(root=PACKAGE),
                    target,
                    surfaces=("security.safe-dirs",),
                    trusted=True,
                    repair=True,
                    dry=False,
                )
            self.assertEqual(merged_bytes, hooks_path.read_bytes())
            self.assertTrue((target / ".cursor/hooks.json.provider-artifact.bak").is_file())
            with redirect_stdout(io.StringIO()):
                block_cursor_lifecycle(
                    SimpleNamespace(root=PACKAGE),
                    target,
                    surfaces=("security.safe-dirs",),
                    trusted=True,
                    repair=False,
                    dry=False,
                )
            self.assertEqual(merged_bytes, hooks_path.read_bytes())

    def test_handler_accepts_before_payload_without_session_id(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-1",
                "command": "echo hi",
                "workspace_roots": [str(ROOT)],
            }
            result = _run_handler(handler, "security.safe-dirs", payload)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"permission": "allow"})

    def test_handler_safe_dirs_permits_hook_without_stdin(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            result = subprocess.run(
                [sys.executable, str(handler), "--surface", "security.safe-dirs"],
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(json.loads(result.stdout), {"permission": "allow"})

    def test_handler_safe_dirs_allows_docker_command_with_wire_payload(self):
        wire = json.loads(
            (PACKAGE / "tests/fixtures_data/cursor-hook-wire-before-v1.json").read_text(
                encoding="utf-8"))
        payload = {
            **wire["payload"],
            "command": "cd /home/vostrikov/sibintek/projects/insiders && make up",
        }
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            result = _run_handler(handler, "security.safe-dirs", payload)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(json.loads(result.stdout), {"permission": "allow"})

    def test_handler_uses_workspace_root_fallback_for_cwd(self):
        with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory() as allowed:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            (Path(allowed) / "ok.txt").write_text("x", encoding="utf-8")
            config = Path(scratch) / "safe-dirs.json"
            config.write_text(json.dumps({
                "version": 1,
                "dirs": [allowed],
                "include_registered_projects": False,
            }), encoding="utf-8")
            env = {
                **os.environ,
                "PATH": f"{ROOT / 'bin'}:{os.environ.get('PATH', '')}",
                "SKM_SAFE_DIRS_CONFIG": str(config),
            }
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-2",
                "command": "rm ok.txt",
                "workspace_roots": [allowed],
            }
            result = _run_handler(handler, "security.safe-dirs", payload, env=env)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"permission": "allow"})
            outside = {**payload, "workspace_roots": [scratch], "command": "rm -rf ."}
            refused = _run_handler(handler, "security.safe-dirs", outside, env=env)
            self.assertEqual(refused.returncode, 0)
            verdict = json.loads(refused.stdout)
            self.assertEqual(verdict["permission"], "deny")
            self.assertIn("safe-dirs allowlist", verdict["user_message"])

    def test_handler_command_log_writes_without_output_payload_field(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            payload = {
                "hook_event_name": "afterShellExecution",
                "conversation_id": "conv-log",
                "command": "git status",
                "duration": 12.5,
                "sandbox": False,
                "output": "must-never-be-persisted",
                "workspace_roots": [project],
            }
            result = _run_handler(handler, "lifecycle.command-log", payload)
            self.assertEqual(result.returncode, 0)
            records = (Path(project) / ".cursor/logs/commands.jsonl").read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(records), 1)
            entry = json.loads(records[0])
            self.assertEqual(entry["session_id"], "conv-log")
            self.assertEqual(entry["command_class"], "git")
            self.assertEqual(entry["duration"], 12.5)
            self.assertEqual(entry["sandbox"], False)
            self.assertEqual(entry["outcome"], "observed")
            self.assertIn("command_sha256", entry)
            self.assertNotIn("output", entry)

    def test_handler_run_report_keeps_reason_and_neutral_outcome(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            payload = {
                "hook_event_name": "sessionEnd",
                "conversation_id": "conv-run",
                "session_id": "cursor-session-17",
                "reason": "window_close",
                "duration_ms": 777.0,
                "final_status": "cancelled",
                "workspace_roots": [project],
            }
            result = _run_handler(handler, "lifecycle.run-report", payload)
            self.assertEqual(result.returncode, 0)
            record = json.loads((Path(project) / ".cursor/runs/conv-run.json").read_text(
                encoding="utf-8"))
            self.assertEqual(record["schema"], 2)
            self.assertEqual(record["session_id"], "conv-run")
            self.assertEqual(record["outcome"], "unknown")
            self.assertEqual(record["cursor"]["end_reason"], "window_close")
            self.assertEqual(record["cursor"]["native_session_id"], "cursor-session-17")
            self.assertEqual(record["cursor"]["duration_ms"], 777.0)

    def test_handler_tool_telemetry_merges_into_run_report(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            common = {
                "conversation_id": "conv-cg",
                "workspace_roots": [project],
            }
            tool_payload = {
                **common,
                "hook_event_name": "preToolUse",
                "tool_name": "MCP:plugin-core-codegraph:find_symbol",
                "tool_input": {"name": "Foo"},
            }
            tool_result = _run_handler(handler, "lifecycle.tool-telemetry", tool_payload)
            self.assertEqual(tool_result.returncode, 0)
            self.assertEqual(json.loads(tool_result.stdout), {"permission": "allow"})
            end_payload = {
                **common,
                "hook_event_name": "sessionEnd",
                "reason": "completed",
            }
            self.assertEqual(_run_handler(handler, "lifecycle.run-report", end_payload).returncode, 0)
            record = json.loads((Path(project) / ".cursor/runs/conv-cg.json").read_text(
                encoding="utf-8"))
            self.assertEqual(record["codegraph"]["find_symbol"]["calls"], 1)
            self.assertFalse((Path(project) / ".cursor/state/conv-cg.tools.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
