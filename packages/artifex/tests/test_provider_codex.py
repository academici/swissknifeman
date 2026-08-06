from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from artifex.providers import codex
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


def request():
    return {"provider": {"id": "codex", "cli_version": "codex-cli 0.146.0"},
            "route": {"model_class": "implementation", "effort": "high"},
            "permissions": {"approval_mode": "never", "sandbox_mode": "read_only"},
            "budgets": {"max_event_count": 4}, "bundle": {},
            "child_policy": {"mode": "forbidden"}}


class CodexAdapterTests(unittest.TestCase):
    def test_empty_tools_refuse_before_binary_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AdapterRefusal, "CAPABILITY_UNSUPPORTED"):
                codex.build_argv(request(), routing_path=ROUTING, schema_path=schema,
                                 cwd=directory, native_tools=(), binary="missing-binary")

    def test_refuses_children_and_unknown_version(self):
        value = request()
        value["child_policy"] = {"mode": "allowed"}
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"; schema.write_text("{}")
            with self.assertRaisesRegex(AdapterRefusal, "CAPABILITY_UNSUPPORTED"):
                codex.build_argv(value, routing_path=ROUTING, schema_path=schema, cwd=directory, native_tools=(), binary="x")
        value = request(); value["provider"]["cli_version"] = "other"
        self.assertEqual(codex.normalize_record("{}", value)["reason_code"], "MAPPING_UNKNOWN")

    def test_fold_is_closed_over_terminal_and_exit(self):
        success = [json.dumps({"type": "thread.started", "thread_id": "t"}),
                   json.dumps({"type": "turn.completed", "usage": {}})]
        self.assertEqual(codex.fold_records(success, request(), exit_code=0)["reason_code"], "OK")
        self.assertEqual(codex.fold_records(success[:1], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(codex.fold_records(success, request(), exit_code=1)["reason_code"], "PROVIDER_NONZERO")

    def test_malformed_and_over_cap_are_refused(self):
        self.assertEqual(codex.fold_records(["{"], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(codex.fold_records(["{}"] * 5, request(), exit_code=0)["reason_code"], "BUDGET_EVENT_COUNT")

    def test_real_multi_item_work_with_item_started_still_folds_ok(self):
        """`item.started` is a real event a genuine multi-step session emits (observed live
        against real substantive work, not just the smoke-shaped single-item case); a stream
        carrying it must still fold to OK once a terminal `turn.completed` arrives."""
        req = request(); req["budgets"]["max_event_count"] = 8
        records = [
            json.dumps({"type": "thread.started", "thread_id": "t"}),
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "item.started", "item": {"id": "item_0", "type": "command_execution"}}),
            json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "command_execution"}}),
            json.dumps({"type": "item.started", "item": {"id": "item_1", "type": "agent_message"}}),
            json.dumps({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message"}}),
            json.dumps({"type": "turn.completed", "usage": {}}),
        ]
        self.assertEqual(codex.fold_records(records, req, exit_code=0)["reason_code"], "OK")

    def test_smoke_path_default_never_carries_an_economy_key(self):
        success = [json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}})]
        result = codex.fold_records(success, request(), exit_code=0)
        self.assertNotIn("economy", result)

    def test_economy_extracts_by_key_never_a_zero_for_missing_cost(self):
        """(f) — positive extraction, plus codex's cost is always null (D25 ban)."""
        success = [json.dumps({"type": "thread.started", "thread_id": "t"}),
                  json.dumps({"type": "turn.completed",
                             "usage": {"input_tokens": 10, "cached_input_tokens": 1, "output_tokens": 5,
                                      "reasoning_output_tokens": 2}})]
        economy = codex.fold_records(success, request(), exit_code=0, include_economy=True,
                                     wall_duration_ms=1234)["economy"]
        self.assertEqual({"input_tokens": 10, "cached_input_tokens": 1, "output_tokens": 5,
                          "reasoning_tokens": 2, "cost_microunits": None, "duration_ms": 1234, "turns": 1},
                         economy["worker"])
        self.assertEqual(["worker/cost_microunits"], list(economy["unknown_reasons"]))
        self.assertEqual({}, economy["inclusion_bases"])

    def test_economy_missing_usage_fields_are_null_with_reasons_never_a_crash(self):
        cases = {
            "no usage at all": [json.dumps({"type": "turn.completed"})],
            "empty usage": [json.dumps({"type": "turn.completed", "usage": {}})],
            "float token value": [json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1.5}})],
            "string token value": [json.dumps({"type": "turn.completed", "usage": {"input_tokens": "1"}})],
        }
        for label, records in cases.items():
            with self.subTest(label=label):
                economy = codex.fold_records(records, request(), exit_code=0, include_economy=True)["economy"]
                for field in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
                    self.assertIsNone(economy["worker"][field])
                    self.assertIn(f"worker/{field}", economy["unknown_reasons"])

    def test_economy_duration_is_wrapper_derived_and_null_without_it(self):
        success = [json.dumps({"type": "turn.completed", "usage": {}})]
        with_wrapper = codex.fold_records(success, request(), exit_code=0, include_economy=True,
                                          wall_duration_ms=999)["economy"]
        self.assertEqual(999, with_wrapper["worker"]["duration_ms"])
        self.assertNotIn("worker/duration_ms", with_wrapper["unknown_reasons"])
        without_wrapper = codex.fold_records(success, request(), exit_code=0, include_economy=True)["economy"]
        self.assertIsNone(without_wrapper["worker"]["duration_ms"])
        self.assertIn("worker/duration_ms", without_wrapper["unknown_reasons"])

    def test_economy_turns_are_event_derived_from_terminal_turn_completed_count(self):
        two_turns = [json.dumps({"type": "turn.completed", "usage": {}}),
                    json.dumps({"type": "turn.started"}),
                    json.dumps({"type": "turn.completed", "usage": {}})]
        req = request(); req["budgets"]["max_event_count"] = 8
        economy = codex.fold_records(two_turns, req, exit_code=0, include_economy=True)["economy"]
        self.assertEqual(2, economy["worker"]["turns"])
        self.assertNotIn("worker/turns", economy["unknown_reasons"])

    def test_economy_coordinator_is_a_measured_zero_with_a_resolvable_zero_basis(self):
        success = [json.dumps({"type": "turn.completed", "usage": {}})]
        economy = codex.fold_records(success, request(), exit_code=0, include_economy=True)["economy"]
        self.assertEqual({field: 0 for field in _METRIC_FIELDS}, economy["coordinator"])
        basis = economy["zero_bases"]["coordinator"]
        self.assertTrue((ROOT / basis["path"]).is_file())
        self.assertTrue(basis["statement"])

    def test_economy_envelope_conforms_to_economy_evidence_v2(self):
        """(i) — codex's own emitted fragment is a structurally valid v2 attempt envelope."""
        validator = _load_validator()
        cases = json.loads((PLAN / "artifacts/P1/economy-evidence-cases-v2.json").read_text(encoding="utf-8"))
        base = copy.deepcopy(cases["base_input"])
        success = [json.dumps({"type": "turn.completed",
                              "usage": {"input_tokens": 5, "cached_input_tokens": 0, "output_tokens": 3,
                                       "reasoning_output_tokens": 1}})]
        economy = codex.fold_records(success, request(), exit_code=0, include_economy=True,
                                     wall_duration_ms=500)["economy"]
        pointer = "/lanes/candidate/attempts/0"
        base["provider_scope"] = {"mode": "single-provider", "provider": "codex", "owner_grant_ref": "D1"}
        base["lanes"]["candidate"]["attempts"][0]["worker"] = economy["worker"]
        base["lanes"]["candidate"]["attempts"][0]["coordinator"] = economy["coordinator"]
        # `INCLUSION_BASIS_INSTANTIATIONS` is closed to claude-code only; under a codex scope
        # no inclusion basis is admissible at all (rule 1, `parity`/wrong-provider both reject).
        base["inclusion_bases"] = {}
        base["zero_bases"] = {k: v for k, v in base["zero_bases"].items() if not k.startswith(pointer)}
        base["zero_bases"][f"{pointer}/coordinator"] = economy["zero_bases"]["coordinator"]
        for key in economy["unknown_reasons"]:
            base["unknown_reasons"][f"{pointer}/{key}"] = economy["unknown_reasons"][key]

        baseline_hash, provider_hash = validator.validate_contract_v2(
            PLAN / "root/contracts/economy-evidence-v2.md", PLAN / "artifacts/P0/acceptance-rubric-v1.md",
            PLAN / "artifacts/P0/baseline-catalog.json", PLAN / "artifacts/P0/provider-matrix-v1.json")
        validator.validate_shape_v2(base, baseline_hash, provider_hash, ROOT)


if __name__ == "__main__":
    unittest.main()
