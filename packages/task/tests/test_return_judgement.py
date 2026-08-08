import filecmp
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_returns


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "packages/task/configs/return-judgement-v1.schema.json"


def judgement(*, verdict="AVOIDABLE", reviewer="reviewer:gpt-5.6-sol", executor="sonnet/medium"):
    return {
        "schema_version": "return-judgement.v1",
        "judgement_id": "RJ-test-001",
        "return_event_id": "RET-test-001",
        "ts": "2026-07-02T00:05:30Z",
        "subject_id": "P1.1",
        "fingerprint_digest": "5f474410de10cf4b31d3c72a432203bc8fb311f544c1be5dbb5183d4c23cfc5c",
        "model_id": "gpt-5.6-sol",
        "model_version": "test",
        "model_effort": "high",
        "rubric_sha256": "1" * 64,
        "input_digest": "2" * 64,
        "capsule_digest": "3" * 64,
        "evidence_ids": ["test:return-loop"],
        "verdict": verdict,
        "parser_version": "return-judgement-parser.v1",
        "policy_version": "return-loop.v1",
        "root_session_id": "root-session-test",
        "root_run_id": "root-run-test",
        "executor_actor": executor,
        "reviewer_actor": reviewer,
        "review_route": {"model_class": "frontier", "effort": "high", "model": "gpt-5.6-sol"},
        "return_control_to": "root",
    }


def carrier(record, *, seam=False):
    seam_fields = ("file: fixture.py\nrule_or_contract_locus: return-loop-v1\ndefect_class: security\n"
                   if seam else "")
    return "---\nitem: P1.1\ndate: 2026-07-02\n" + seam_fields + "return_judgement: " + json.dumps(
        record, sort_keys=True, separators=(",", ":")) + "\n---\n"


class ReturnJudgementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan-v2"
        shutil.copytree(Path(__file__).parent / "data" / "plan-v2", self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lifted_schema_is_byte_identical(self):
        self.assertTrue(filecmp.cmp(
            SCHEMA,
            ROOT / "plans/2026.08.07-PLAN-ECONOMY/root/contracts/return-judgement-v1.schema.json",
            shallow=False,
        ))

    def test_every_enum_value_is_monotone(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        baseline = plan_returns.decide(verdict=None)
        self.assertEqual(len(schema["properties"]["verdict"]["enum"]), 5)
        for verdict in schema["properties"]["verdict"]["enum"]:
            with self.subTest(verdict=verdict):
                self.assertTrue(plan_returns.at_least_as_strict(
                    plan_returns.decide(verdict=verdict), baseline))

    def test_monotonicity_rejects_an_artificially_weakened_branch(self):
        baseline = plan_returns.decide(occurrences=3)
        weakened = plan_returns.decide(verdict="JUSTIFIED", occurrences=3)
        weakened["continue_allowed"] = True
        weakened["stop_required"] = False
        weakened["owner_gate_required"] = False
        self.assertFalse(plan_returns.at_least_as_strict(weakened, baseline))

    def test_first_schema_valid_record_wins_over_later_record(self):
        findings = self.plan / "findings"
        (findings / "A-judgement.md").write_text(carrier(judgement(verdict="JUSTIFIED")), encoding="utf-8")
        (findings / "Z-judgement.md").write_text(carrier(judgement(verdict="MALFORMED")), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["judgement"]["verdict"], "JUSTIFIED")
        self.assertEqual(gate["action"], "owner-gate")

    def test_missing_provenance_is_ignored(self):
        bad = judgement()
        del bad["input_digest"]
        (self.plan / "findings/P1.1-fixture.md").unlink()
        (self.plan / "findings/A-invalid.md").write_text(carrier(bad, seam=True), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertNotIn("judgement", gate)

    def test_self_judgement_is_rejected_without_later_retry(self):
        (self.plan / "findings/P1.1-fixture.md").unlink()
        findings = self.plan / "findings"
        (findings / "A-self.md").write_text(
            carrier(judgement(reviewer="sonnet/medium", executor="sonnet/medium"), seam=True),
            encoding="utf-8")
        (findings / "Z-later.md").write_text(carrier(judgement(verdict="MALFORMED")), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertNotIn("judgement", gate)

    def test_classified_fixture_exercises_packet_and_verdict(self):
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["namespace"], "classified")
        self.assertTrue(gate["blocks"])
        self.assertEqual(gate["action"], "owner-gate")
        self.assertEqual(gate["judgement"]["verdict"], "AVOIDABLE")
        self.assertEqual(gate["owner_packet"]["judgements"], [gate["judgement"]])
