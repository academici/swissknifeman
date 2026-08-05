from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from artifex.providers import claude_code
from artifex.providers.common import AdapterRefusal


ROOT = Path(__file__).resolve().parents[3]
ROUTING = ROOT / "packages/task/configs/command-routing.json"


def request():
    return {
        "provider": {"id": "claude-code", "cli_version": "2.1.220 (Claude Code)"},
        "route": {"model_class": "implementation", "effort": "high"},
        "permissions": {"approval_mode": "never", "sandbox_mode": "read_only"},
        "budgets": {"max_event_count": 2, "max_output_bytes": 1024, "max_turns": 2,
                    "timeout_ms": 1000, "cost_limit_microunits": 50000},
        "bundle": {}, "child_policy": {"mode": "forbidden"},
    }


class ClaudeCodeAdapterTests(unittest.TestCase):
    def test_literal_argv_is_bounded_and_does_not_leak_carrier_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"; schema.write_text('{"secret": "schema"}', encoding="utf-8")
            mcp = Path(directory) / "mcp.json"; mcp.write_text('{"token": "mcp"}', encoding="utf-8")
            argv = claude_code.build_argv(request(), routing_path=ROUTING, schema_path=schema,
                                          mcp_config_path=mcp, cwd=directory, native_tools=(), binary="claude-test")
        self.assertEqual(argv[:2], ["claude-test", "-p"])
        self.assertIn("json", argv)
        self.assertIn("--no-session-persistence", argv)
        self.assertIn("dontAsk", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertIn("--max-turns", argv)
        self.assertIn("--max-budget-usd", argv)
        self.assertIn("0.05", argv)
        self.assertNotIn('{"secret": "schema"}', argv)
        self.assertNotIn('{"token": "mcp"}', argv)
        self.assertFalse(any("--bare" in value or "fallback-model" in value or "resume" in value
                             or "bypassPermissions" in value for value in argv))

    def test_refuses_children_and_unknown_version(self):
        value = request(); value["child_policy"] = {"mode": "bounded_read_only"}
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"; schema.write_text("{}", encoding="utf-8")
            mcp = Path(directory) / "mcp.json"; mcp.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AdapterRefusal, "CAPABILITY_UNSUPPORTED"):
                claude_code.build_argv(value, routing_path=ROUTING, schema_path=schema,
                                       mcp_config_path=mcp, cwd=directory, native_tools=(), binary="x")
        value = request(); value["provider"]["cli_version"] = "other"
        self.assertEqual(claude_code.normalize_record("{}", value)["reason_code"], "MAPPING_UNKNOWN")

    def test_fold_requires_one_valid_terminal_result_and_consistent_exit(self):
        result = json.dumps({"type": "result", "is_error": False, "usage": {}, "total_cost_usd": 0,
                             "num_turns": 1, "session_id": "session"})
        self.assertEqual(claude_code.fold_records([result], request(), exit_code=0)["reason_code"], "OK")
        self.assertEqual(claude_code.fold_records([], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(claude_code.fold_records([result], request(), exit_code=1)["reason_code"], "PROVIDER_NONZERO")

    def test_refuses_malformed_denied_budget_agent_and_private_records(self):
        self.assertEqual(claude_code.fold_records(["{"], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        denied = json.dumps({"type": "result", "is_error": False, "permission_denials": ["x"]})
        self.assertEqual(claude_code.fold_records([denied], request(), exit_code=0)["reason_code"], "PERMISSION_REFUSED")
        exhausted = json.dumps({"type": "result", "is_error": False, "num_turns": 3})
        self.assertEqual(claude_code.fold_records([exhausted], request(), exit_code=0)["reason_code"], "BUDGET_TURN_COUNT")
        self.assertEqual(claude_code.fold_records([json.dumps({"type": "assistant", "is_error": False})], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        private = json.dumps({"type": "result", "is_error": False, "prompt": "forbidden"})
        self.assertEqual(claude_code.fold_records([private], request(), exit_code=0)["reason_code"], "PRIVACY_REFUSED")


if __name__ == "__main__":
    unittest.main()
