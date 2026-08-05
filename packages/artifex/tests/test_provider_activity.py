from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from artifex import activity


PLAN = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR"


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def prepare(self, request, *, plan_dir, native_tools, content_resolver):
        self.calls.append("preflight")
        self.asserted = (request["route"], native_tools, plan_dir)
        return {"argv": [sys.executable, "-c", "print('{\"type\": \"turn.completed\"}')"], "stdin": b""}

    def fold_records(self, rows, request, *, exit_code):
        self.calls.append("fold")
        return {"worker_succeeded": rows == ['{"type": "turn.completed"}'] and exit_code == 0,
                "reason_code": "OK", "event_count": 1}


class ProviderActivityTests(unittest.TestCase):
    def setUp(self):
        self.admission = json.loads((PLAN / "artifacts/P2/p3-smoke-admissions/codex.json").read_text(encoding="utf-8"))
        self.slice = {"input_hashes": {"admission": self.admission["admission_hash"]}}

    def test_indexed_codex_refuses_before_runner_for_empty_native_tools(self):
        port = activity.ProviderActivityPort(PLAN, self.admission)
        result = port(self.slice)
        self.assertEqual(("provider_unavailable", "CAPABILITY_UNSUPPORTED", 0),
                         (result["kind"], result["reason_code"], result["process_count"]))

    def test_injected_admitted_path_runs_once_and_returns_only_normalized_observation(self):
        fake = FakeAdapter()
        port = activity.ProviderActivityPort(PLAN, self.admission,
                                            registry={"codex": fake, "claude-code": fake})
        result = port(self.slice)
        self.assertEqual(("success", 1, "OK"), (result["kind"], result["process_count"], result["reason_code"]))
        self.assertEqual(["preflight", "fold"], fake.calls)
        self.assertNotIn("turn.completed", str(result))

    def test_linkage_mismatch_refuses_without_preflight(self):
        fake = FakeAdapter()
        port = activity.ProviderActivityPort(PLAN, self.admission,
                                            registry={"codex": fake, "claude-code": fake})
        result = port({"input_hashes": {"admission": "0" * 64}})
        self.assertEqual(("LINKAGE_MISMATCH", []), (result["reason_code"], fake.calls))


if __name__ == "__main__":
    unittest.main()
