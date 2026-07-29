"""unittest for harness.provider_trace — thin Unified Agent Trace v1 readers (P3.1).
Run: PYTHONPATH=packages/harness/lib python3 -m unittest discover -s packages/harness/tests -p 'test_provider_trace.py'"""
import unittest

from harness.provider_trace import PROVIDER_IDS, build_claude_raw, build_codex_raw

_RUN_REPORT = {
    "schema": 2, "tools": {"total": 3, "by_name": {"Read": 2, "Bash": 1}},
    "reads": {"total": 2, "unique": 2, "top_rereads": []}, "files_changed": [],
}


class TestBuildClaudeRaw(unittest.TestCase):
    def test_minimal_call_degrades_every_nullable_field(self):
        raw = build_claude_raw(_RUN_REPORT, raw_ref="local:s1", occurred_at="2026-07-26T00:00:00Z")
        self.assertEqual(raw["provenance"]["provider_id"], "claude-code")
        self.assertEqual(raw["provenance"]["raw_ref"], "local:s1")
        self.assertEqual(raw["provenance"]["reader_id"], "harness.provider_trace")
        for name in ("plan_ref", "contract_ref", "route", "dispatch", "public_outcome"):
            self.assertIsNone(raw[name])
            self.assertIn("not captured", raw["reasons"][name])
        self.assertEqual(raw["finding_refs"], [])
        self.assertIn("finding_refs", raw["reasons"])

    def test_caller_supplied_fields_are_not_degraded(self):
        raw = build_claude_raw(
            _RUN_REPORT, raw_ref="local:s1", occurred_at="2026-07-26T00:00:00Z",
            plan_ref={"plan_id": "P", "item_id": "P3.1", "command": "plan-run"},
            route={"model_class": "implementation", "effort": "high", "model": "sonnet"},
            dispatch={"state": "EXECUTING", "event": "dispatch"},
            finding_refs=["seam:x:y:z"],
            public_outcome={"scope": "public", "check": "unittest", "evidence_ref": "a"},
            contract_ref={"contract_id": "task-contract-v1", "version_hash": "a" * 64},
        )
        self.assertEqual(raw["reasons"], {})
        self.assertEqual(raw["plan_ref"]["item_id"], "P3.1")
        self.assertEqual(raw["finding_refs"], ["seam:x:y:z"])

    def test_sha256_reflects_source_bytes(self):
        import hashlib
        source = b"transcript bytes"
        raw = build_claude_raw(_RUN_REPORT, raw_ref="local:s1", occurred_at="2026-07-26T00:00:00Z",
                               source_bytes=source)
        self.assertEqual(raw["provenance"]["sha256"], hashlib.sha256(source).hexdigest())

    def test_missing_source_bytes_hashes_empty(self):
        import hashlib
        raw = build_claude_raw(_RUN_REPORT, raw_ref="local:s1", occurred_at="2026-07-26T00:00:00Z")
        self.assertEqual(raw["provenance"]["sha256"], hashlib.sha256(b"").hexdigest())

    def test_non_dict_run_report_rejected(self):
        with self.assertRaises(ValueError):
            build_claude_raw("not-a-dict", raw_ref="local:s1", occurred_at="2026-07-26T00:00:00Z")

    def test_empty_finding_refs_list_is_treated_as_missing(self):
        raw = build_claude_raw(_RUN_REPORT, raw_ref="local:s1", occurred_at="2026-07-26T00:00:00Z",
                               finding_refs=[])
        self.assertIn("finding_refs", raw["reasons"])


class TestBuildCodexRaw(unittest.TestCase):
    def test_minimal_call_degrades_with_codex_specific_reason(self):
        raw = build_codex_raw(raw_ref="local:c1", occurred_at="2026-07-26T00:00:00Z")
        self.assertEqual(raw["provenance"]["provider_id"], "codex")
        for name in ("plan_ref", "contract_ref", "route", "dispatch", "public_outcome", "finding_refs"):
            self.assertEqual(raw["reasons"][name], "codex-hook-not-integrated")

    def test_caller_supplied_route_is_not_degraded(self):
        raw = build_codex_raw(raw_ref="local:c1", occurred_at="2026-07-26T00:00:00Z",
                              route={"model_class": "implementation", "effort": "high", "model": "gpt-5.6"})
        self.assertNotIn("route", raw["reasons"])
        self.assertEqual(raw["route"]["model"], "gpt-5.6")


class TestProviderIds(unittest.TestCase):
    def test_provider_ids_match_analyst_trace_vocabulary(self):
        self.assertEqual(set(PROVIDER_IDS), {"claude-code", "codex"})


if __name__ == "__main__":
    unittest.main()
