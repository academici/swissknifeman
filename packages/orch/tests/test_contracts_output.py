from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from orch import contracts

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("run-event", "stage-result", "effect-receipt", "check-evidence", "launch-plan")
EXPECTED = {
    "stage-result/commit-bad-role.json": "enum",
    "stage-result/commit-duplicate-sha.json": "COMMIT_SHA_DUPLICATE",

    "run-event/bad-kind.json": "enum",
    "run-event/attempt-zero.json": "ATTEMPT_RANGE",
    "stage-result/usage-unknown-with-tokens.json": "USAGE_UNKNOWN_NUMERIC",
    "stage-result/completed-parse-error.json": "COMPLETED_PARSE_ERROR",
    "stage-result/cost-format.json": "COST_FORMAT",
    "effect-receipt/unknown-without-reconcile.json": "RECEIPT_RECONCILE",
    "effect-receipt/extra-field.json": "additional",
    "check-evidence/procedure-with-exit.json": "EVIDENCE_CARRIER",
    "check-evidence/cmd-without-exit.json": "EVIDENCE_CARRIER",
    "launch-plan/missing-refusals.json": "required",
    "launch-plan/bad-transport.json": "enum",
    "launch-plan/env-non-string.json": "type",
    "launch-plan/key-reused.json": "KEY_REUSED",
    "run-event/epoch-zero.json": "EPOCH_INVALID",
    "run-event/key-reused.json": "KEY_REUSED",
    "effect-receipt/precondition-mismatch.json": "PRECONDITION_MISMATCH",
}
SAMPLES = {
    "run-event": "started",
    "stage-result": "completed-reported",
    "effect-receipt": "git-commit-applied",
    "check-evidence": "cmd-pass",
    "launch-plan": "claude-only-solo",
}


def fixture(kind, name=None):
    path = ROOT / "fixtures/exec/v1/valid" / kind / ((name or SAMPLES[kind]) + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


class OutputContractTests(unittest.TestCase):
    def assert_code(self, kind, doc, code):
        issues = contracts.validate(doc, kind)
        self.assertIn(code, [issue.code for issue in issues], issues)

    def test_valid_fixtures(self):
        for kind in KINDS:
            paths = sorted((ROOT / "fixtures/exec/v1/valid" / kind).glob("*.json"))
            self.assertTrue(paths, kind)
            for path in paths:
                with self.subTest(kind=kind, name=path.name):
                    issues = contracts.validate(json.loads(path.read_text(encoding="utf-8")), kind)
                    self.assertEqual([i for i in issues if i.level == "error"], [])

    def test_invalid_fixtures_have_one_expected_error(self):
        paths = [p for kind in KINDS for p in (ROOT / "fixtures/exec/v1/invalid" / kind).glob("*.json")]
        self.assertEqual({str(p.relative_to(ROOT / "fixtures/exec/v1/invalid")) for p in paths}, set(EXPECTED))
        for kind in KINDS:
            self.assertGreaterEqual(sum(p.parent.name == kind for p in paths), 2, kind)
        for path in paths:
            key = str(path.relative_to(ROOT / "fixtures/exec/v1/invalid"))
            with self.subTest(fixture=key):
                issues = contracts.validate(json.loads(path.read_text(encoding="utf-8")), path.parent.name)
                self.assertEqual([i.code for i in issues if i.level == "error"], [EXPECTED[key]])

    def test_schemas_load_with_descriptions(self):
        registry = contracts.load_registry()

        def check(node):
            if isinstance(node, dict):
                for name, prop in node.get("properties", {}).items():
                    self.assertIsInstance(prop.get("description"), str, name)
                    self.assertTrue(prop["description"], name)
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)

        for kind in KINDS:
            node, schema_id = registry.for_kind(kind)
            self.assertEqual(schema_id, contracts.URN_PREFIX + kind + ":v1")
            check(node)

    def test_synthetic_trace_rows_and_sequence(self):
        expected = {
            "native-claude-code-ok": ["started", "model_wait", "tool", "output", "completed"],
            "native-codex-quota": ["started", "model_wait", "quota_block"],
            "native-grok-unknown": ["started", "output"],
        }
        run_ids = set()
        for name, kinds in expected.items():
            path = ROOT / "fixtures/traces" / (name + ".jsonl")
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([event["kind"] for event in events], kinds)
            self.assertEqual([event["seq"] for event in events], list(range(len(events))))
            for event in events:
                with self.subTest(trace=name, seq=event["seq"]):
                    self.assertEqual(contracts.validate(event, "run-event"), [])
                    run_ids.add(event["run_id"])
            if name == "native-claude-code-ok":
                self.assertEqual(events[-1]["data"]["usage"], {"input_tokens": 100, "output_tokens": 25})
        self.assertEqual(len(run_ids), 1)

    def test_commit_entries_shape_digest_and_duplicate_pointer(self):
        doc = fixture("stage-result", "with-commits")
        doc["commits"][1]["sha"] = doc["commits"][0]["sha"]
        self.assertEqual([(i.path, i.code) for i in contracts.validate(doc, "stage-result")],
                         [("/commits/1/sha", "COMMIT_SHA_DUPLICATE")])
        for field in ("sha", "role", "ref", "paths_digest"):
            doc = fixture("stage-result", "with-commits")
            del doc["commits"][0][field]
            self.assert_code("stage-result", doc, "required")
        for field, value in (("sha", "xyz"), ("ref", ""), ("paths_digest", "abc")):
            doc = fixture("stage-result", "with-commits")
            doc["commits"][0][field] = value
            self.assertTrue(contracts.validate(doc, "stage-result"))
        for value in (None, {}, "wrong", 1):
            doc = fixture("stage-result", "with-commits")
            doc["commits"] = value
            self.assert_code("stage-result", doc, "type")
        for value in (None, [], "wrong", 1, {"sha": []}):
            doc = fixture("stage-result", "with-commits")
            doc["commits"] = [value]
            self.assertTrue(contracts.validate(doc, "stage-result"))
        doc = fixture("stage-result", "with-commits")
        doc["commits"] = []
        self.assertEqual(contracts.validate(doc, "stage-result"), [])

    def test_attempt_and_sequence_ranges_and_types(self):
        for kind in ("run-event", "stage-result"):
            for value in (0, -1):
                doc = fixture(kind)
                doc["attempt"] = value
                self.assert_code(kind, doc, "ATTEMPT_RANGE")
            for value in (True, 1.5):
                doc = fixture(kind)
                doc["attempt"] = value
                self.assert_code(kind, doc, "type")
        doc = fixture("run-event")
        doc["seq"] = -1
        self.assert_code("run-event", doc, "ATTEMPT_RANGE")
        doc["seq"] = 0
        self.assertEqual(contracts.validate(doc, "run-event"), [])

    def test_unknown_usage_never_reports_zero_or_cost(self):
        for field, value in (("input_tokens", 0), ("output_tokens", 0), ("cost_usd", "0")):
            doc = fixture("stage-result", "quota-unknown-usage")
            doc["usage"][field] = value
            self.assert_code("stage-result", doc, "USAGE_UNKNOWN_NUMERIC")
        for status in ("quota_blocked", "auth_blocked", "unknown_outcome"):
            doc = fixture("stage-result", "quota-unknown-usage")
            doc["status"] = status
            self.assertEqual(contracts.validate(doc, "stage-result"), [])

    def test_completed_cannot_hide_parse_errors(self):
        doc = fixture("stage-result")
        doc["errors"] = [{"class": "parse", "message": "Synthetic parser error."}]
        self.assert_code("stage-result", doc, "COMPLETED_PARSE_ERROR")
        doc["status"] = "unknown_outcome"
        self.assertEqual(contracts.validate(doc, "stage-result"), [])
        doc["status"] = "completed"
        doc["errors"][0]["class"] = "provider"
        self.assertEqual(contracts.validate(doc, "stage-result"), [])

    def test_cost_is_decimal_ascii_string(self):
        for value in ("0", "0.01", "123.456"):
            doc = fixture("stage-result")
            doc["usage"]["cost_usd"] = value
            self.assertEqual(contracts.validate(doc, "stage-result"), [])
        for value in ("-1", "1e3", "1.", ".1", "1\n", "١.٢", ""):
            doc = fixture("stage-result")
            doc["usage"]["cost_usd"] = value
            self.assert_code("stage-result", doc, "COST_FORMAT")
        doc["usage"]["cost_usd"] = 0
        self.assert_code("stage-result", doc, "type")

    def test_unknown_effect_reconciliation_and_open_results(self):
        doc = fixture("effect-receipt", "task-finish-unknown")
        doc["reconcile"]["method"] = "none"
        self.assert_code("effect-receipt", doc, "RECEIPT_RECONCILE")
        for method in ("task_show", "git_rev_parse", "file_hash"):
            doc["reconcile"]["method"] = method
            doc["intent"]["expected_prior"] = {"nested": {"status": [None, True]}}
            doc["result"] = {"arbitrary": {"detail": 1}}
            self.assertEqual(contracts.validate(doc, "effect-receipt"), [])
        doc["outcome"] = "applied"
        doc["reconcile"]["method"] = "none"
        self.assertEqual(contracts.validate(doc, "effect-receipt"), [])

    def test_evidence_carriers_do_not_invent_shell_exits(self):
        for procedure in ({}, {"cmd": "true", "procedure": "observe"}):
            doc = fixture("check-evidence")
            doc["procedure"] = procedure
            self.assert_code("check-evidence", doc, "EVIDENCE_CARRIER")
        doc = fixture("check-evidence")
        doc["verdict"] = "pass"
        self.assert_code("check-evidence", doc, "EVIDENCE_CARRIER")
        for field in ("verdict", "observation"):
            doc = fixture("check-evidence", "procedure-pass")
            del doc[field]
            self.assert_code("check-evidence", doc, "EVIDENCE_CARRIER")
        doc = fixture("check-evidence")
        doc["exit"] = 1
        self.assertEqual(contracts.validate(doc, "check-evidence"), [])

    def test_launch_env_string_values_and_open_extensions(self):
        doc = fixture("launch-plan")
        doc["extensions"] = {"binding-specific": {"arbitrary": [1, None, True]}}
        doc["stages"][0]["env"] = {"SYNTHETIC_MODE": "dry-run", "EMPTY": ""}
        self.assertEqual(contracts.validate(doc, "launch-plan"), [])
        for value in (True, 1, None, [], {}):
            invalid = copy.deepcopy(doc)
            invalid["stages"][0]["env"]["~/name"] = value
            issues = contracts.validate(invalid, "launch-plan")
            self.assertEqual([(i.path, i.code) for i in issues], [("/stages/0/env/~0~1name", "type")])
        doc["stages"][0]["unexpected"] = True
        self.assert_code("launch-plan", doc, "additional")

    def test_malformed_shapes_report_issues_without_crashing(self):
        for kind in KINDS:
            for value in (None, [], "wrong", 1):
                with self.subTest(kind=kind, value=value):
                    self.assert_code(kind, value, "type")
            original = fixture(kind)
            for field in original:
                if field in ("$schema", "contract_version"):
                    continue
                with self.subTest(kind=kind, field=field):
                    doc = copy.deepcopy(original)
                    doc[field] = None
                    self.assertTrue(contracts.validate(doc, kind))
