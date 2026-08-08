"""unittest для task.token_estimate — оценщик токенов СВЕРХУ (P0.1, D11/D14).
Запуск: cd packages/task && python3 -m unittest tests.test_token_estimate -v"""
import json
import math
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from task.token_estimate import (  # noqa: E402
    CLASSIFIER, CLASSES, TokenEstimateArtifactError, classify_char, count_classes,
    estimate_text, load_artifact,
)

FIXTURE_ARTIFACT = {
    "version": "2.0.0",
    "calibrated_at": "2026-08-07T00:00:00Z",
    "calibration_target": {"provider": "codex", "adapter": "codex-exec-jsonl-v1",
                           "requested_model_id": "gpt-5.6-terra",
                           "probe_protocol_version": "differential-input-total-v2",
                           "usage_semantics": "provider-reported-input-total-v1"},
    "classifier": CLASSIFIER,
    "corpus": {"files": 3, "total_bytes": 100, "sha256": "0" * 64},
    "classes": {"dense_ascii": 0.9, "ascii_word": 0.3, "ascii_other": 0.4,
                "cyrillic": 0.6, "other": 2.0},
    "per_file_overhead_tokens": 12,
    "safety_multiplier": 1.1,
    "bound": {"violations": 0, "max_true_over_estimate": 0.97},
    "tightness": {"p50": 1.05, "p95": 1.2, "max": 1.35},
}


class TmpArtifactTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.artifact_path = Path(self._tmp.name) / "calibration.json"

    def tearDown(self):
        self._tmp.cleanup()

    def write_artifact(self, data):
        self.artifact_path.write_text(json.dumps(data), encoding="utf-8")


class TestClassifyAndCount(unittest.TestCase):
    def test_classify_char_covers_all_classes(self):
        self.assertEqual(classify_char("a"), "ascii_word")
        self.assertEqual(classify_char("9"), "ascii_word")
        self.assertEqual(classify_char("_"), "ascii_word")
        self.assertEqual(classify_char(" "), "ascii_other")
        self.assertEqual(classify_char("."), "ascii_other")
        self.assertEqual(classify_char("б"), "cyrillic")
        self.assertEqual(classify_char("Я"), "cyrillic")
        self.assertEqual(classify_char("🟢"), "other")
        self.assertEqual(classify_char("中"), "other")

    def test_count_classes_known_vector(self):
        counts = count_classes("aA1_ .,б🟢")
        self.assertEqual(counts, {
            "dense_ascii": 0,
            "ascii_word": 4,   # a A 1 _
            "ascii_other": 3,  # space . ,
            "cyrillic": 1,     # б
            "other": 1,        # 🟢
        })

    def test_count_classes_closed_set(self):
        self.assertEqual(set(count_classes("")), set(CLASSES))


class TestLoadArtifact(TmpArtifactTestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)

    def test_malformed_json_raises(self):
        self.artifact_path.write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)

    def test_missing_required_field_raises(self):
        data = dict(FIXTURE_ARTIFACT)
        del data["safety_multiplier"]
        self.write_artifact(data)
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)

    def test_violations_nonzero_raises(self):
        data = json.loads(json.dumps(FIXTURE_ARTIFACT))
        data["bound"] = {"violations": 1, "max_true_over_estimate": 1.4}
        self.write_artifact(data)
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)

    def test_negative_rate_raises(self):
        data = json.loads(json.dumps(FIXTURE_ARTIFACT))
        data["classes"]["other"] = -0.1
        self.write_artifact(data)
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)

    def test_valid_artifact_loads(self):
        self.write_artifact(FIXTURE_ARTIFACT)
        data = load_artifact(self.artifact_path)
        self.assertEqual(data["calibration_target"]["requested_model_id"], "gpt-5.6-terra")

    def test_v1_is_rejected(self):
        data = json.loads(json.dumps(FIXTURE_ARTIFACT))
        data["version"] = "1.0.0"
        self.write_artifact(data)
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)

    def test_classifier_mismatch_is_rejected(self):
        data = json.loads(json.dumps(FIXTURE_ARTIFACT))
        data["classifier"]["dense_ascii_min_run"] = 33
        self.write_artifact(data)
        with self.assertRaises(TokenEstimateArtifactError):
            load_artifact(self.artifact_path)


class TestEstimateText(unittest.TestCase):
    def test_missing_artifact_is_exception_not_default(self):
        with self.assertRaises(TokenEstimateArtifactError):
            estimate_text("hello", artifact_path=Path("/nonexistent/path/artifact.json"))

    def test_empty_input_gives_overhead_exactly(self):
        self.assertEqual(estimate_text("", artifact=FIXTURE_ARTIFACT),
                          FIXTURE_ARTIFACT["per_file_overhead_tokens"])

    def test_known_short_vector_gives_expected_number(self):
        text = "aA1_ .,б🟢"  # ascii_word=4, ascii_other=3, cyrillic=1, other=1
        rates = FIXTURE_ARTIFACT["classes"]
        raw = 4 * rates["ascii_word"] + 3 * rates["ascii_other"] + 1 * rates["cyrillic"] + 1 * rates["other"]
        expected = math.ceil(raw * FIXTURE_ARTIFACT["safety_multiplier"]) + FIXTURE_ARTIFACT["per_file_overhead_tokens"]
        self.assertEqual(estimate_text(text, artifact=FIXTURE_ARTIFACT), expected)

    def test_monotonic_on_text_growth(self):
        base = ""
        prev = estimate_text(base, artifact=FIXTURE_ARTIFACT)
        for ch in "The план 🟢 continues по шагам with 123 и эмодзи 🔴🟡.":
            base += ch
            cur = estimate_text(base, artifact=FIXTURE_ARTIFACT)
            self.assertGreaterEqual(cur, prev, f"estimate decreased adding {ch!r}")
            prev = cur

    def test_never_underestimates_zero_rate_edge(self):
        data = json.loads(json.dumps(FIXTURE_ARTIFACT))
        data["classes"] = {c: 0.0 for c in CLASSES}
        data["per_file_overhead_tokens"] = 0
        data["safety_multiplier"] = 1.0
        self.assertEqual(estimate_text("anything at all", artifact=data), 0)

    def test_model_mismatch_warns_but_does_not_raise(self):
        result = estimate_text("hi", artifact=FIXTURE_ARTIFACT,
                               session_provider="codex", session_model_id="other")
        self.assertIsInstance(result, int)

    def test_dense_ascii_boundary_and_partition(self):
        self.assertEqual(count_classes("a" * 31)["dense_ascii"], 0)
        counts = count_classes("a" * 32 + "!")
        self.assertEqual(counts["dense_ascii"], 32)
        self.assertEqual(sum(counts.values()), 33)


if __name__ == "__main__":
    unittest.main()
