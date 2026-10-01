from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from artifex.providers import claude_code, codex, parity
from artifex.providers.common import AdapterRefusal
from support import FIXTURE_PLAN as PLAN


ROOT = Path(__file__).resolve().parents[3]
PARITY = PLAN / "artifacts/P3/provider-parity-v1.json"
CASES = PLAN / "artifacts/P3/provider-parity-cases-v1.json"
ROUTING = ROOT / "packages/task/configs/command-routing.json"


def codex_request() -> dict:
    return {"provider": {"id": "codex", "cli_version": "codex-cli 0.146.0"},
            "route": {"model_class": "implementation", "effort": "high"},
            "permissions": {"approval_mode": "never", "sandbox_mode": "read_only"},
            "budgets": {"max_event_count": 4}, "bundle": {},
            "child_policy": {"mode": "forbidden"}}


def claude_request() -> dict:
    return {"provider": {"id": "claude-code", "cli_version": "2.1.220 (Claude Code)"},
            "route": {"model_class": "implementation", "effort": "high"},
            "permissions": {"approval_mode": "never", "sandbox_mode": "read_only"},
            "budgets": {"max_event_count": 2, "max_output_bytes": 1024, "max_turns": 2,
                        "timeout_ms": 1000, "cost_limit_microunits": 50000}, "bundle": {},
            "child_policy": {"mode": "forbidden"}}


class ProviderParityTests(unittest.TestCase):
    def test_mapping_loads_and_registry_is_exact(self):
        mapping = parity.load_mapping(PARITY)
        registry = parity.build_registry(mapping["registry"])
        self.assertEqual(parity.lookup_provider(registry, "codex"), "artifex.providers.codex")
        self.assertEqual(parity.lookup_provider(registry, "claude-code"), "artifex.providers.claude_code")
        with self.assertRaisesRegex(AdapterRefusal, "MAPPING_UNKNOWN"):
            parity.lookup_provider(registry, "Codex")
        duplicate = [*mapping["registry"], mapping["registry"][0]]
        with self.assertRaisesRegex(AdapterRefusal, "MAPPING_UNKNOWN"):
            parity.build_registry(duplicate)

    def test_independent_cases_keep_success_unknown_and_refusal_boundaries_distinct(self):
        cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
        by_id = {case["id"]: case for case in cases}
        self.assertEqual(by_id["codex-success"]["expected"]["reason_code"], "OK")
        self.assertEqual(by_id["claude-success"]["expected"]["reason_code"], "OK")
        self.assertEqual(by_id["codex-malformed"]["expected"]["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(by_id["claude-malformed"]["expected"]["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(by_id["codex-missing-usage"]["expected"]["usage_observed"], False)
        self.assertEqual(by_id["claude-missing-usage"]["expected"]["usage_observed"], False)

    def test_both_adapters_refuse_children_and_non_never_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"; schema.write_text("{}", encoding="utf-8")
            mcp = Path(directory) / "mcp.json"; mcp.write_text("{}", encoding="utf-8")
            for request, build in ((codex_request(), codex.build_argv), (claude_request(), claude_code.build_argv)):
                request["child_policy"] = {"mode": "bounded_read_only"}
                with self.assertRaisesRegex(AdapterRefusal, "CAPABILITY_UNSUPPORTED"):
                    if build is codex.build_argv:
                        build(request, routing_path=ROUTING, schema_path=schema, cwd=directory, native_tools=(), binary="test")
                    else:
                        build(request, routing_path=ROUTING, schema_path=schema, mcp_config_path=mcp, cwd=directory, native_tools=(), binary="test")
                request = codex_request() if build is codex.build_argv else claude_request()
                request["permissions"]["approval_mode"] = "ask"
                with self.assertRaisesRegex(AdapterRefusal, "PERMISSION_REFUSED"):
                    if build is codex.build_argv:
                        build(request, routing_path=ROUTING, schema_path=schema, cwd=directory, native_tools=(), binary="test")
                    else:
                        build(request, routing_path=ROUTING, schema_path=schema, mcp_config_path=mcp, cwd=directory, native_tools=(), binary="test")

    def test_one_field_mutations_do_not_create_default_success(self):
        codex_success = [json.dumps({"type": "thread.started", "thread_id": "t"}),
                         json.dumps({"type": "turn.completed"})]
        claude_success = [json.dumps({"type": "result", "is_error": False, "num_turns": 1})]
        self.assertEqual(codex.fold_records(codex_success, codex_request(), exit_code=0)["reason_code"], "OK")
        self.assertEqual(claude_code.fold_records(claude_success, claude_request(), exit_code=0)["reason_code"], "OK")
        self.assertEqual(codex.fold_records(["{"], codex_request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(claude_code.fold_records(["{"], claude_request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(codex.fold_records(codex_success, codex_request(), exit_code=1)["reason_code"], "PROVIDER_NONZERO")
        self.assertEqual(claude_code.fold_records(claude_success, claude_request(), exit_code=1)["reason_code"], "PROVIDER_NONZERO")


if __name__ == "__main__":
    unittest.main()
