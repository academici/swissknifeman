"""unittest for analyst.metrics — reliability metric arithmetic and paired digest.
Run: PYTHONPATH=packages/analyst/lib python3 -m unittest discover -s packages/analyst/tests -p 'test_metrics.py'"""
import unittest

from analyst.metrics import (
    COMPARABLE_PROOF_CLASSES, PROOF_CLASSES, SCHEMA_VERSION, MetricError, build_digest,
    build_metric_record, digest_to_json, find_anomalies, pair_metric, slice_by,
)
from analyst.trace import build_trace_record


def _trace(*, turn_id="t1", **overrides):
    raw = {
        "provenance": {"provider_id": "claude-code", "raw_ref": "local:s1", "sha256": "0" * 64,
                       "reader_id": "harness.provider_trace", "reader_version": "1.0.0"},
        "occurred_at": "2026-07-26T00:00:00Z",
        "plan_ref": {"plan_id": "2026.07.24-DEMO-PLAN", "item_id": "P3.2", "command": "plan-run"},
        "contract_ref": {"contract_id": "task-contract-v1", "version_hash": "a" * 64},
        "route": {"model_class": "implementation", "effort": "high", "model": "sonnet"},
        "dispatch": {"state": "EXECUTING", "event": "dispatch"},
        "public_outcome": {"scope": "public", "check": "unittest", "evidence_ref": "artifacts/x"},
        "finding_refs": ["seam:file:rule:class"],
        "reasons": {},
    }
    raw.update(overrides)
    return build_trace_record(raw, provider_id="claude-code", project_id="swissknifeman",
                              identity="s1", turn_id=turn_id)


class TestBuildMetricRecord(unittest.TestCase):
    def test_full_record_shape_and_value(self):
        record = build_metric_record("critical_requirement_retention", numerator=25,
                                     denominator=25, baseline_proof_class="recomputed")
        self.assertEqual(record["value"], 1.0)
        self.assertEqual(record["completeness"], 1.0)
        self.assertEqual(record["source_trace_ids"], [])
        self.assertEqual(record["exclusions"], [])

    def test_zero_denominator_yields_null_value_not_zero(self):
        record = build_metric_record("first_pass_success", numerator=0, denominator=0,
                                     baseline_proof_class="recomputed")
        self.assertIsNone(record["value"])
        self.assertEqual(record["completeness"], 0.0)

    def test_rejects_unknown_proof_class(self):
        with self.assertRaisesRegex(MetricError, "METRIC_UNKNOWN_PROOF_CLASS"):
            build_metric_record("m", numerator=1, denominator=1, baseline_proof_class="guessed")

    def test_rejects_numerator_exceeding_denominator(self):
        with self.assertRaisesRegex(MetricError, "METRIC_NUMERATOR_EXCEEDS_DENOMINATOR"):
            build_metric_record("m", numerator=5, denominator=2, baseline_proof_class="recomputed")

    def test_rejects_negative_input(self):
        with self.assertRaisesRegex(MetricError, "METRIC_NEGATIVE_INPUT"):
            build_metric_record("m", numerator=-1, denominator=2, baseline_proof_class="recomputed")

    def test_completeness_derives_from_source_traces_when_given(self):
        complete = _trace()
        degraded = _trace(turn_id="t2", route=None,
                          reasons={"route": "no route captured", "contract_ref": "n/a",
                                   "dispatch": "n/a", "public_outcome": "n/a",
                                   "finding_refs": "n/a"})
        record = build_metric_record("trace_completeness", numerator=2, denominator=2,
                                     baseline_proof_class="recomputed",
                                     source_traces=(complete, degraded))
        self.assertAlmostEqual(record["completeness"], (1.0 + 5 / 6) / 2)
        self.assertEqual(sorted(record["source_trace_ids"]),
                         sorted([complete["trace_id"], degraded["trace_id"]]))

    def test_rejects_foreign_schema_trace(self):
        with self.assertRaisesRegex(MetricError, "METRIC_TRACE_SCHEMA_MISMATCH"):
            build_metric_record("m", numerator=1, denominator=1, baseline_proof_class="recomputed",
                                source_traces=({"schema_version": "other/v9"},))

    def test_resumed_duplicate_traces_are_deduped_before_counting(self):
        trace = _trace()
        resumed_duplicate = dict(trace)  # same trace_id (same natural key), same record
        record = build_metric_record("trace_completeness", numerator=1, denominator=1,
                                     baseline_proof_class="recomputed",
                                     source_traces=(trace, resumed_duplicate))
        self.assertEqual(len(record["source_trace_ids"]), 1)
        self.assertEqual(record["completeness"], 1.0)


class TestPairMetric(unittest.TestCase):
    def _record(self, value_num, value_den, proof_class="recomputed"):
        return build_metric_record("first_pass_success", numerator=value_num,
                                   denominator=value_den, baseline_proof_class=proof_class)

    def test_candidate_absent_is_deferred_not_zero(self):
        baseline = self._record(6, 31)
        pair = pair_metric(baseline, None)
        self.assertEqual(pair["status"], "deferred")
        self.assertIsNone(pair["delta"])
        self.assertIsNone(pair["candidate"])

    def test_paired_delta_is_candidate_minus_baseline(self):
        baseline = self._record(6, 31)
        candidate = self._record(28, 31)
        pair = pair_metric(baseline, candidate)
        self.assertEqual(pair["status"], "paired")
        self.assertAlmostEqual(pair["delta"], (28 / 31) - (6 / 31))

    def test_pinned_baseline_forbidden_as_comparator(self):
        pinned = self._record(1, 1, proof_class="pinned-not-recomputable")
        candidate = self._record(1, 1)
        with self.assertRaisesRegex(MetricError, "METRIC_PINNED_BASELINE_FORBIDDEN"):
            pair_metric(pinned, candidate)

    def test_mismatched_metric_ids_rejected(self):
        baseline = build_metric_record("a", numerator=1, denominator=1,
                                       baseline_proof_class="recomputed")
        candidate = build_metric_record("b", numerator=1, denominator=1,
                                        baseline_proof_class="recomputed")
        with self.assertRaisesRegex(MetricError, "METRIC_MISMATCHED_PAIR"):
            pair_metric(baseline, candidate)

    def test_comparable_proof_classes_is_the_deterministic_subset(self):
        self.assertTrue(COMPARABLE_PROOF_CLASSES < PROOF_CLASSES)
        self.assertEqual(COMPARABLE_PROOF_CLASSES, {"recomputed", "cross-checked"})


class TestSliceBy(unittest.TestCase):
    def test_slices_by_project_plan_and_item(self):
        trace_a = _trace()
        trace_b = _trace(plan_ref={"plan_id": "OTHER-PLAN", "item_id": "P1.1", "command": "plan-run"})
        entries = [{"project_id": "swissknifeman", "trace": trace_a},
                   {"project_id": "azguard", "trace": trace_b}]
        by_project = slice_by(entries, "project")
        self.assertEqual(set(by_project), {"swissknifeman", "azguard"})
        by_plan = slice_by(entries, "plan")
        self.assertEqual(set(by_plan), {"2026.07.24-DEMO-PLAN", "OTHER-PLAN"})
        by_item = slice_by(entries, "item")
        self.assertEqual(set(by_item), {"P3.2", "P1.1"})

    def test_null_plan_ref_degrades_to_none_bucket(self):
        trace_no_plan = _trace(plan_ref=None, reasons={"plan_ref": "no plan_ref captured",
                                                        "contract_ref": "n/a", "route": "n/a",
                                                        "dispatch": "n/a", "public_outcome": "n/a",
                                                        "finding_refs": "n/a"})
        entries = [{"project_id": "swissknifeman", "trace": trace_no_plan}]
        self.assertEqual(list(slice_by(entries, "plan")), [None])

    def test_rejects_unknown_axis(self):
        with self.assertRaisesRegex(MetricError, "METRIC_UNKNOWN_SLICE_AXIS"):
            slice_by([], "team")


class TestFindAnomaliesAndDigest(unittest.TestCase):
    def test_finds_regression_beyond_tolerance_with_trace_refs(self):
        baseline = build_metric_record("first_pass_success", numerator=28, denominator=31,
                                       baseline_proof_class="recomputed",
                                       source_traces=(_trace(),))
        candidate = build_metric_record("first_pass_success", numerator=6, denominator=31,
                                        baseline_proof_class="recomputed",
                                        source_traces=(_trace(),))
        pair = pair_metric(baseline, candidate)
        anomalies = find_anomalies([pair], regression_tolerance=0.01)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["metric"], "first_pass_success")
        self.assertEqual(anomalies[0]["baseline_trace_ids"], baseline["source_trace_ids"])

    def test_deferred_pairs_never_counted_as_anomalies(self):
        baseline = build_metric_record("first_pass_success", numerator=0, denominator=31,
                                       baseline_proof_class="recomputed")
        pair = pair_metric(baseline, None)
        self.assertEqual(find_anomalies([pair]), [])

    def test_build_digest_shape_and_overall_completeness(self):
        baseline = build_metric_record("first_pass_success", numerator=6, denominator=31,
                                       baseline_proof_class="recomputed")
        pair = pair_metric(baseline, None)
        digest = build_digest([pair], generated_at="2026-07-26T00:00:00Z",
                              slices={"project": {"swissknifeman": 1}})
        self.assertEqual(digest["schema_version"], SCHEMA_VERSION)
        self.assertEqual(digest["overall_completeness"], 1.0)
        self.assertEqual(digest["anomalies"], [])
        self.assertEqual(digest["slices"], {"project": {"swissknifeman": 1}})

    def test_build_digest_rejects_non_utc_timestamp(self):
        with self.assertRaisesRegex(MetricError, "METRIC_MISSING_TIMESTAMP"):
            build_digest([], generated_at="2026-07-26")

    def test_digest_to_json_is_byte_stable_sorted(self):
        digest = build_digest([], generated_at="2026-07-26T00:00:00Z")
        first = digest_to_json(digest)
        second = digest_to_json(dict(sorted(digest.items(), reverse=True)))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
