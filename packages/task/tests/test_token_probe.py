"""Provider-neutral P0.1 probe contract and bracket-core tests."""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from task.token_probe import ProbeRecord, ProbeRecordError, RECORD_SCHEMA_VERSION, ensure_same_target


def record(total, *, model="gpt-5.6-terra"):
    return ProbeRecord(
        schema_version=RECORD_SCHEMA_VERSION, provider_id="fake", provider_adapter="fake-v1",
        requested_model_id=model, effective_model_id=None,
        protocol_version="differential-input-total-v2", input_tokens_total=total,
        usage_breakdown={"cached_input_tokens": 99}, wrapper_sha256="w" * 64,
        environment_cli="fake", environment_version="1", command_sha256="c" * 64,
    )


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def probe(self, payload):
        self.calls.append(payload)
        return record(100 + len(payload))


class TestProbeRecord(unittest.TestCase):
    def test_record_rejects_negative_total(self):
        with self.assertRaises(ProbeRecordError):
            record(-1)

    def test_mixed_targets_rejected(self):
        with self.assertRaises(ProbeRecordError):
            ensure_same_target([record(1), record(2, model="other")])

    def test_serialized_record_keeps_total_separate_from_cache(self):
        data = record(100).as_dict()
        self.assertEqual(data["input_tokens_total"], 100)
        self.assertEqual(data["usage_breakdown"]["cached_input_tokens"], 99)


class TestBracketSchedule(unittest.TestCase):
    def test_eight_samples_use_twelve_calls_and_shared_controls(self):
        script = Path(__file__).resolve().parents[1] / "scripts/calibrate-token-estimate.py"
        spec = importlib.util.spec_from_file_location("calibrate_token_estimate", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        adapter = FakeAdapter()
        samples = [{"payload": str(index), "source_path": str(index), "full_source_sha256": "a" * 64,
                    "byte_range": {"start": 0, "end_exclusive": 1}, "sample_sha256": "b" * 64,
                    "sample_bytes": 1, "whole_file": True, "full_text": str(index)} for index in range(8)]
        accepted, rejected, calls = module.run_brackets(adapter, samples)
        self.assertEqual((len(accepted), len(rejected), len(calls)), (8, 0, 12))
        self.assertEqual(adapter.calls.count(""), 4)
