from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from artifex.providers import claude_code
from artifex.providers.common import AdapterRefusal


ROOT = Path(__file__).resolve().parents[3]
ROUTING = ROOT / "packages/task/configs/command-routing.json"
PLAN = ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR"
_METRIC_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                  "cost_microunits", "duration_ms", "turns")


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_economy_evidence", PLAN / "artifacts/P1/validate-economy-evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _business_record(**overrides):
    record = {"type": "result", "is_error": False,
              "usage": {"input_tokens": 100, "cache_read_input_tokens": 20, "output_tokens": 50},
              "total_cost_usd": 0.0123, "num_turns": 3, "duration_ms": 4380, "session_id": "s"}
    record.update(overrides)
    return record


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

    def test_business_argv_allow_lists_the_same_tools_it_declares(self):
        """`dontAsk` auto-denies anything not on `--allowedTools`, independent of `--tools`
        (verified live: without `--allowedTools` every real Edit call was silently denied,
        with it real file edits happened) — lock in that the two stay identical, never
        wider than what `--tools`/`--disallowedTools` already declare."""
        value = request(); value["provider"]["cli_version"] = claude_code.BUSINESS_VERSION
        value["permissions"] = {"approval_mode": "never", "sandbox_mode": "workspace_write", "network_mode": "disabled"}
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"; schema.write_text("{}", encoding="utf-8")
            mcp = Path(directory) / "mcp.json"; mcp.write_text("{}", encoding="utf-8")
            argv = claude_code.build_business_argv(value, schema_path=schema, cwd=directory,
                                                    mcp_config_path=mcp, binary="claude-test")
        self.assertIn("--allowedTools", argv)
        self.assertEqual(argv[argv.index("--allowedTools") + 1], argv[argv.index("--tools") + 1])

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

    def test_business_fold_reports_real_max_turns_exhaustion_honestly(self):
        """`errors` is a real key the CLI emits on `subtype: error_max_turns` (observed live
        against a real multi-file business task, not the smoke path's always-succeeds shape);
        must classify as the specific `PROVIDER_NONZERO`, not the generic protocol-unknown."""
        record = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True,
                             "errors": ["Reached maximum number of turns (8)"], "num_turns": 1,
                             "session_id": "s", "usage": {}, "total_cost_usd": 0.01})
        self.assertEqual(claude_code.fold_business_records([record], request(), exit_code=0)["reason_code"],
                         "PROVIDER_NONZERO")

    def test_business_fold_extracts_the_full_economy_envelope_by_key(self):
        """(f) — every reported metric is extracted as a non-negative integer by key."""
        record = _business_record()
        economy = claude_code.fold_business_records([json.dumps(record)], request(), exit_code=0)["economy"]
        self.assertEqual({"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 50,
                          "reasoning_tokens": 0, "cost_microunits": 12300, "duration_ms": 4380, "turns": 3},
                         economy["worker"])
        self.assertEqual({}, economy["unknown_reasons"])
        for field in economy["worker"].values():
            self.assertIsInstance(field, int)
            self.assertNotIsInstance(field, bool)

    def test_business_fold_reasoning_tokens_carries_the_sole_inclusion_basis(self):
        """(g) — reasoning_tokens is 0 WITH inclusion_basis for claude-code; no other field does."""
        economy = claude_code.fold_business_records(
            [json.dumps(_business_record())], request(), exit_code=0)["economy"]
        self.assertEqual(["worker/reasoning_tokens"], list(economy["inclusion_bases"]))
        entry = economy["inclusion_bases"]["worker/reasoning_tokens"]
        self.assertEqual(("claude-code", "reasoning_tokens", "output_tokens"),
                         (entry["provider"], entry["contained_field"], entry["containing_field"]))
        self.assertTrue(entry["evidence_ref"])

    def test_business_fold_coordinator_is_a_measured_zero_with_a_resolvable_zero_basis(self):
        """(h) — the coordinator envelope is seven measured zeros with a resolvable zero_basis;
        fails if that path stops existing."""
        economy = claude_code.fold_business_records(
            [json.dumps(_business_record())], request(), exit_code=0)["economy"]
        self.assertEqual({field: 0 for field in _METRIC_FIELDS}, economy["coordinator"])
        basis = economy["zero_bases"]["coordinator"]
        self.assertEqual("coordinator", basis["component"])
        self.assertTrue((ROOT / basis["path"]).is_file())
        self.assertTrue(basis["statement"])

    def test_business_fold_missing_usage_fields_are_null_with_reasons_never_zero(self):
        cases = {
            "no usage object": _business_record(usage=None),
            "missing input_tokens": _business_record(usage={"cache_read_input_tokens": 20, "output_tokens": 50}),
            "float output_tokens": _business_record(usage={"input_tokens": 1, "cache_read_input_tokens": 2,
                                                            "output_tokens": 3.5}),
            "string cached_input_tokens": _business_record(usage={"input_tokens": 1, "cache_read_input_tokens": "x",
                                                                   "output_tokens": 3}),
        }
        for label, record in cases.items():
            with self.subTest(label=label):
                economy = claude_code.fold_business_records([json.dumps(record)], request(), exit_code=0)["economy"]
                for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
                    if economy["worker"][field] is None:
                        self.assertIn(f"worker/{field}", economy["unknown_reasons"])
                        self.assertTrue(economy["unknown_reasons"][f"worker/{field}"])
                    else:
                        self.assertNotEqual(0, economy["worker"][field])

    def test_business_fold_missing_output_tokens_voids_the_reasoning_inclusion_basis(self):
        record = _business_record(usage={"input_tokens": 1, "cache_read_input_tokens": 2})
        economy = claude_code.fold_business_records([json.dumps(record)], request(), exit_code=0)["economy"]
        self.assertIsNone(economy["worker"]["reasoning_tokens"])
        self.assertIn("worker/reasoning_tokens", economy["unknown_reasons"])
        self.assertEqual({}, economy["inclusion_bases"])

    def test_business_fold_missing_cost_duration_turns_are_null_with_reasons(self):
        record = _business_record(total_cost_usd=None, duration_ms="not-an-int", num_turns=None)
        economy = claude_code.fold_business_records([json.dumps(record)], request(), exit_code=0)["economy"]
        for field in ("cost_microunits", "duration_ms", "turns"):
            self.assertIsNone(economy["worker"][field])
            self.assertIn(f"worker/{field}", economy["unknown_reasons"])

    def test_business_fold_cost_conversion_boundary_values_use_decimal_never_float(self):
        boundaries = {0: 0, 0.0000005: 1, 1.9999995: 2000000, 1.23456789: 1234568}
        for usd, expected_microunits in boundaries.items():
            with self.subTest(usd=usd):
                record = _business_record(total_cost_usd=usd)
                economy = claude_code.fold_business_records([json.dumps(record)], request(), exit_code=0)["economy"]
                self.assertEqual(expected_microunits, economy["worker"]["cost_microunits"])
                self.assertNotIsInstance(economy["worker"]["cost_microunits"], float)

    def test_economy_envelope_conforms_to_economy_evidence_v2_and_bare_zero_is_refused(self):
        """(i) — a fixture built from the emitted envelope shape is accepted by
        validate-economy-evidence.py, and rejected once a bare 0 replaces a null+reason."""
        validator = _load_validator()
        cases = json.loads((PLAN / "artifacts/P1/economy-evidence-cases-v2.json").read_text(encoding="utf-8"))
        base = copy.deepcopy(cases["base_input"])
        economy = claude_code.fold_business_records(
            [json.dumps(_business_record())], request(), exit_code=0)["economy"]
        pointer = "/lanes/candidate/attempts/0"
        base["lanes"]["candidate"]["attempts"][0]["worker"] = economy["worker"]
        base["lanes"]["candidate"]["attempts"][0]["coordinator"] = economy["coordinator"]
        base["inclusion_bases"] = {k: v for k, v in base["inclusion_bases"].items() if not k.startswith(pointer)}
        base["zero_bases"] = {k: v for k, v in base["zero_bases"].items() if not k.startswith(pointer)}
        for key, entry in economy["inclusion_bases"].items():
            base["inclusion_bases"][f"{pointer}/{key}"] = entry
        base["zero_bases"][f"{pointer}/coordinator"] = economy["zero_bases"]["coordinator"]

        baseline_hash, provider_hash = validator.validate_contract_v2(
            PLAN / "root/contracts/economy-evidence-v2.md", PLAN / "artifacts/P0/acceptance-rubric-v1.md",
            PLAN / "artifacts/P0/baseline-catalog.json", PLAN / "artifacts/P0/provider-matrix-v1.json")
        validator.validate_shape_v2(base, baseline_hash, provider_hash, ROOT)

        broken = copy.deepcopy(base)
        del broken["inclusion_bases"][f"{pointer}/worker/reasoning_tokens"]
        with self.assertRaises(validator.InvalidEvidence):
            validator.validate_shape_v2(broken, baseline_hash, provider_hash, ROOT)


if __name__ == "__main__":
    unittest.main()
