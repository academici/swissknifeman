"""unittest for analyst.trace — Unified Agent Trace v1 schema owner (P3.1).
Run: PYTHONPATH=packages/analyst/lib python3 -m unittest discover -s packages/analyst/tests -p 'test_trace.py'"""
import hashlib
import json
import unittest

from analyst.trace import (
    PRIVACY_EXCLUDED, SCHEMA_VERSION, TraceError, build_trace_record, dedup_records,
    record_to_json, trace_id,
)


def _provenance(provider_id="claude-code", raw_ref="local:s1", sha=None):
    return {"provider_id": provider_id, "raw_ref": raw_ref,
            "sha256": sha or "0" * 64, "reader_id": "harness.provider_trace",
            "reader_version": "1.0.0"}


def _raw(**overrides):
    base = {
        "provenance": _provenance(),
        "occurred_at": "2026-07-26T00:00:00Z",
        "plan_ref": {"plan_id": "2026.07.24-AGENT-RELIABILITY", "item_id": "P3.1", "command": "plan-run"},
        "contract_ref": {"contract_id": "task-contract-v1", "version_hash": "a" * 64},
        "route": {"model_class": "implementation", "effort": "high", "model": "sonnet"},
        "dispatch": {"state": "EXECUTING", "event": "dispatch"},
        "finding_refs": ["seam:file:rule:class"],
        "public_outcome": {"scope": "public", "check": "unittest", "evidence_ref": "artifacts/x"},
        "reasons": {},
    }
    base.update(overrides)
    return base


class TestTraceId(unittest.TestCase):
    def test_deterministic_same_natural_key_same_id(self):
        a = trace_id("claude-code", "swissknifeman", "session-1", "turn-3")
        b = trace_id("claude-code", "swissknifeman", "session-1", "turn-3")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_different_turn_different_id(self):
        a = trace_id("claude-code", "swissknifeman", "session-1", "turn-3")
        b = trace_id("claude-code", "swissknifeman", "session-1", "turn-4")
        self.assertNotEqual(a, b)

    def test_rejects_empty_identity(self):
        with self.assertRaisesRegex(TraceError, "TRACE_MISSING_IDENTITY"):
            trace_id("claude-code", "p", "", "turn-1")


class TestBuildTraceRecord(unittest.TestCase):
    def test_full_record_is_complete_and_closed_schema(self):
        record = build_trace_record(_raw(), provider_id="claude-code", project_id="swissknifeman",
                                     identity="session-1", turn_id="turn-3")
        self.assertEqual(record["schema_version"], SCHEMA_VERSION)
        self.assertEqual(record["quality"], {"completeness": 1.0, "missing": [], "degraded": False})
        self.assertEqual(record["reasons"], {})
        self.assertEqual(record["privacy"]["excluded"], list(PRIVACY_EXCLUDED))
        self.assertEqual(record["trace_id"],
                         trace_id("claude-code", "swissknifeman", "session-1", "turn-3"))

    def test_missing_optional_fields_degrade_to_null_with_reason(self):
        raw = _raw(route=None, dispatch=None, reasons={"route": "no route captured",
                                                        "dispatch": "no hook signal"})
        record = build_trace_record(raw, provider_id="claude-code", project_id="p",
                                    identity="s", turn_id="t")
        self.assertIsNone(record["route"])
        self.assertIsNone(record["dispatch"])
        self.assertEqual(sorted(record["quality"]["missing"]), ["dispatch", "route"])
        self.assertTrue(record["quality"]["degraded"])
        self.assertAlmostEqual(record["quality"]["completeness"], 4 / 6)
        self.assertEqual(record["reasons"]["route"], "no route captured")

    def test_missing_field_without_reason_is_rejected(self):
        raw = _raw(route=None, reasons={})
        with self.assertRaisesRegex(TraceError, "TRACE_MISSING_IDENTITY"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_empty_finding_refs_counts_as_missing(self):
        raw = _raw(finding_refs=[], reasons={"finding_refs": "no findings raised"})
        record = build_trace_record(raw, provider_id="claude-code", project_id="p",
                                    identity="s", turn_id="t")
        self.assertIn("finding_refs", record["quality"]["missing"])

    def test_unknown_provider_rejected(self):
        raw = _raw(provenance=_provenance(provider_id="gpt-5"))
        with self.assertRaisesRegex(TraceError, "TRACE_UNKNOWN_PROVIDER"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_provider_id_mismatch_rejected(self):
        raw = _raw(provenance=_provenance(provider_id="codex"))
        with self.assertRaisesRegex(TraceError, "TRACE_UNKNOWN_PROVIDER"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_bad_occurred_at_rejected(self):
        raw = _raw(occurred_at="2026-07-26 00:00:00")
        with self.assertRaisesRegex(TraceError, "TRACE_MISSING_IDENTITY"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_bad_dispatch_state_rejected(self):
        raw = _raw(dispatch={"state": "RUNNING", "event": "dispatch"})
        with self.assertRaisesRegex(TraceError, "TRACE_CORRUPT_RECORD"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_bad_public_outcome_scope_rejected(self):
        raw = _raw(public_outcome={"scope": "secret", "check": "x", "evidence_ref": "y"})
        with self.assertRaisesRegex(TraceError, "TRACE_CORRUPT_RECORD"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_source_bytes_hash_mismatch_rejected(self):
        source = b"actual bytes"
        raw = _raw(provenance=_provenance(sha=hashlib.sha256(b"other bytes").hexdigest()))
        with self.assertRaisesRegex(TraceError, "TRACE_CORRUPT_RECORD"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s",
                               turn_id="t", source_bytes=source)

    def test_source_bytes_hash_match_accepted(self):
        source = b"actual bytes"
        sha = hashlib.sha256(source).hexdigest()
        raw = _raw(provenance=_provenance(sha=sha))
        record = build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s",
                                    turn_id="t", source_bytes=source)
        self.assertEqual(record["provenance"]["sha256"], sha)

    def test_privacy_violation_key_rejected(self):
        raw = _raw()
        raw["route"] = {"model_class": "implementation", "effort": "high",
                        "model": "sonnet", "chain_of_thought": "leaked"}
        with self.assertRaisesRegex(TraceError, "TRACE_PRIVACY_VIOLATION"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_privacy_violation_nested_key_rejected(self):
        raw = _raw()
        raw["public_outcome"] = {"scope": "public", "check": "x",
                                 "evidence_ref": "y", "tool_result": {"secret": "z"}}
        with self.assertRaisesRegex(TraceError, "TRACE_PRIVACY_VIOLATION"):
            build_trace_record(raw, provider_id="claude-code", project_id="p", identity="s", turn_id="t")

    def test_malformed_raw_input_not_a_dict_rejected(self):
        with self.assertRaisesRegex(TraceError, "TRACE_CORRUPT_RECORD"):
            build_trace_record("not-a-dict", provider_id="claude-code", project_id="p",
                               identity="s", turn_id="t")

    def test_partial_raw_input_missing_provenance_rejected(self):
        with self.assertRaisesRegex(TraceError, "TRACE_MISSING_IDENTITY"):
            build_trace_record({"occurred_at": "2026-07-26T00:00:00Z"},
                               provider_id="claude-code", project_id="p", identity="s", turn_id="t")


class TestDedupRecords(unittest.TestCase):
    def _record(self, *, turn_id, route=True):
        raw = _raw()
        if not route:
            raw["route"] = None
            raw["reasons"] = {"route": "resumed before route captured"}
        return build_trace_record(raw, provider_id="claude-code", project_id="p",
                                  identity="session-1", turn_id=turn_id)

    def test_resume_duplicate_keeps_higher_completeness(self):
        partial = self._record(turn_id="turn-1", route=False)
        full = dict(partial)
        # Simulate the resumed session re-normalizing the SAME natural key once route
        # evidence became available — same trace_id, higher completeness.
        raw = _raw()
        complete = build_trace_record(raw, provider_id="claude-code", project_id="p",
                                      identity="session-1", turn_id="turn-1")
        self.assertEqual(partial["trace_id"], complete["trace_id"])
        result = dedup_records([partial, complete])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["quality"]["completeness"], 1.0)

    def test_distinct_turns_both_kept(self):
        a = self._record(turn_id="turn-1")
        b = self._record(turn_id="turn-2")
        result = dedup_records([a, b])
        self.assertEqual(len(result), 2)

    def test_tie_keeps_first_seen(self):
        a = self._record(turn_id="turn-1")
        b = dict(a)
        result = dedup_records([a, b])
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], a)


class TestRecordToJson(unittest.TestCase):
    def test_round_trips_and_is_sorted(self):
        record = build_trace_record(_raw(), provider_id="claude-code", project_id="p",
                                    identity="s", turn_id="t")
        text = record_to_json(record)
        self.assertEqual(json.loads(text), record)
        self.assertEqual(text, json.dumps(record, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
