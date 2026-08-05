from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from artifex import compiler
from support import clone, p2_1_pending_s3_fixture


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans" / ("2026" + ".08.03-ARTIFEX-SUPERVISOR")


class CompilerTests(unittest.TestCase):
    def _sources(self):
        s1, s2, _ = compiler.observe_sources(ROOT, PLAN, "P2.1")
        s1 = clone(s1)
        fields = s1["plans"][PLAN.name]["phases"]["P2"]["items"]["P2.1"]["fields"]
        fields["Status"] = "⬜ Not started"
        return s1, s2, p2_1_pending_s3_fixture()

    def test_live_harness_projection_tracks_p2_1_lifecycle(self):
        s1, _, s3 = compiler.observe_sources(ROOT, PLAN, "P2.1")
        fields = s1["plans"][PLAN.name]["phases"]["P2"]["items"]["P2.1"]["fields"]
        runnable = [row for row in s3["items"] if row["item_id"] == "P2.1"]
        excluded = [row for row in s3["excluded_terminal"] if row["item_id"] == "P2.1"]
        terminal = fields["Status"] in (
            "🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision",
        )
        if terminal:
            self.assertEqual([], runnable)
            self.assertEqual(["ITEM-TERMINAL"], [row["refusal"] for row in excluded])
        else:
            self.assertEqual(1, len(runnable))
            self.assertEqual([], excluded)

    def test_live_manual_projection_is_deterministic(self):
        sources = self._sources()
        first = compiler.compile_slice(ROOT, PLAN, "P2.1", sources=sources)
        second = compiler.compile_slice(ROOT, PLAN, "P2.1", sources=sources)
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual("manual", first["route"]["exec"])
        self.assertEqual("implementation", first["route"]["model_class"])
        self.assertEqual("high", first["route"]["effort"])
        self.assertEqual(first["task_contract"]["public_acceptance_ids"], first["scope"]["evidence_refs"])

    def test_source_drift_refuses_before_manifest(self):
        s1, s2, s3 = self._sources()
        next(row for row in s3["items"] if row["item_id"] == "P2.1")["route"]["effort"] = "medium"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SOURCE_DRIFT"):
            compiler.compile_slice(ROOT, PLAN, "P2.1", sources=(s1, s2, s3))

    def test_malformed_files_refuse(self):
        s1, s2, s3 = self._sources()
        s1["plans"][PLAN.name]["phases"]["P2"]["items"]["P2.1"]["fields"]["Files"] += " prose"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SLICE_INPUT_MISSING"):
            compiler.compile_slice(ROOT, PLAN, "P2.1", sources=(s1, s2, s3))

    def test_external_file_refuses(self):
        s1, s2, s3 = self._sources()
        fields = s1["plans"][PLAN.name]["phases"]["P2"]["items"]["P2.1"]["fields"]
        fields["Files"] = "`../escape.py`"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SLICE_INPUT_EXTERNAL"):
            compiler.compile_slice(ROOT, PLAN, "P2.1", sources=(s1, s2, s3))

    def test_frozen_contract_case_bank_remains_green(self):
        result = subprocess.run([
            "python3", str(PLAN / "artifacts/P1/validate-slice-manifest.py"),
            "--contract", str(PLAN / "root/contracts/slice-manifest-v1.md"),
            "--cases", str(PLAN / "artifacts/P1/slice-manifest-cases-v1.json"),
            "--execution-policy", str(ROOT / "packages/harness/configs/common/agent-packs/execution-policy.json"),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
