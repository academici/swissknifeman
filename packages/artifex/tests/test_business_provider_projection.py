from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from artifex.providers import claude_code, codex
from artifex.providers.common import AdapterRefusal


class BusinessProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schema = self.root / "output.json"
        self.schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")
        self.mcp = self.root / "mcp.json"
        self.mcp.write_text('{"mcpServers": {}}', encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _request(self, provider, version):
        return {"provider": {"id": provider, "cli_version": version},
                "route": {"model_class": "implementation", "effort": "high"},
                "permissions": {"approval_mode": "never", "sandbox_mode": "workspace_write", "network_mode": "disabled"},
                "budgets": {"max_turns": 2, "cost_limit_microunits": 1000000,
                            "max_event_count": 16, "max_output_bytes": 8192,
                            "timeout_ms": 120000},
                "bundle": {"content_refs": []},
                "child_policy": {"mode": "forbidden", "max_children": 0, "allowed_capabilities": []}}

    def test_codex_r2_is_strict_and_has_no_unproved_caps(self):
        argv = codex.build_business_argv(self._request("codex", codex.BUSINESS_VERSION), schema_path=self.schema, cwd=self.root, binary="fake-codex")
        self.assertIn("--strict-config", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertNotIn("features.rollout_budget=true", argv)
        self.assertNotIn("rollout_budget.limit_tokens=2000", argv)
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("workspace-write", argv)
        self.assertNotIn("--max-turns", argv)
        self.assertNotIn("--max-budget-usd", argv)
        request = self._request("codex", codex.BUSINESS_VERSION)
        request["permissions"]["network_mode"] = "enabled"
        with self.assertRaises(AdapterRefusal):
            codex.build_business_argv(request, schema_path=self.schema, cwd=self.root, binary="fake-codex")

    def test_claude_r2_requires_schema_and_closed_mcp(self):
        argv = claude_code.build_business_argv(self._request("claude-code", claude_code.BUSINESS_VERSION), schema_path=self.schema, cwd=self.root, mcp_config_path=self.mcp, binary="fake-claude")
        self.assertEqual("json", argv[argv.index("--output-format") + 1])
        self.assertEqual({"type": "object"}, json.loads(argv[argv.index("--json-schema") + 1]))
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual("Read,Edit", argv[argv.index("--tools") + 1])
        self.assertTrue(argv[-1].startswith("Return only a JSON object"))
        with self.assertRaises(AdapterRefusal):
            claude_code.build_business_argv(self._request("claude-code", "drift"), schema_path=self.schema, cwd=self.root, mcp_config_path=self.mcp, binary="fake")
        request = self._request("claude-code", claude_code.BUSINESS_VERSION)
        request["permissions"]["network_mode"] = "enabled"
        with self.assertRaises(AdapterRefusal):
            claude_code.build_business_argv(request, schema_path=self.schema, cwd=self.root, mcp_config_path=self.mcp, binary="fake")

    def test_claude_business_result_is_normalized(self):
        result = json.dumps({"type": "result", "is_error": False, "usage": {}, "total_cost_usd": 0,
                             "num_turns": 1, "session_id": "session", "modelUsage": {},
                             "structured_output": {"status": "completed", "summary": "ok"}, "uuid": "id"})
        self.assertEqual("OK", claude_code.fold_records([result], self._request("claude-code", claude_code.BUSINESS_VERSION), exit_code=0)["reason_code"])

    def test_claude_business_accepts_only_the_terminal_bookkeeping_record(self):
        result = json.dumps({"type": "result", "is_error": False, "usage": {}, "total_cost_usd": 0,
                             "num_turns": 3, "session_id": "session"})
        request = self._request("claude-code", claude_code.BUSINESS_VERSION)
        self.assertEqual("OK", claude_code.fold_business_records([result], request, exit_code=0)["reason_code"])
        self.assertEqual("BUDGET_TURN_COUNT", claude_code.fold_business_records([result.replace('3', '4')], request, exit_code=0)["reason_code"])
