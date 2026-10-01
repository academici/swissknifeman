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
CALIBRATION = ROOT / "packages/task/configs/return-judgement-calibration.json"
BANK = ROOT / "packages/task/configs/return-judgement-bank.jsonl"
RUBRIC = ROOT / "packages/task/prompts/return-judgement-rubric-v1.md"


def judgement(*, verdict="AVOIDABLE", reviewer="reviewer:gpt-5.6-sol", executor="sonnet/medium",
              event_id="RET-test-001", digest="5f474410de10cf4b31d3c72a432203bc8fb311f544c1be5dbb5183d4c23cfc5c",
              model_id=None, rubric_sha256=None):
    calibrated = json.loads(CALIBRATION.read_text(encoding="utf-8"))["calibrated"][0]
    return {
        "schema_version": "return-judgement.v1",
        "judgement_id": "RJ-test-001",
        "return_event_id": event_id,
        "ts": "2026-07-02T00:05:30Z",
        "subject_id": "P1.1",
        "fingerprint_digest": digest,
        "model_id": model_id or calibrated["model_id"],
        "model_version": "test",
        "model_effort": "high",
        "rubric_sha256": rubric_sha256 or calibrated["rubric_sha256"],
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

    def test_calibration_registry_pins_rubric_and_discovery_bank(self):
        import hashlib

        registry = json.loads(CALIBRATION.read_text(encoding="utf-8"))
        digest = hashlib.sha256(RUBRIC.read_bytes()).hexdigest()
        self.assertEqual(registry["rubric"]["rubric_sha256"], digest)
        self.assertTrue(any(
            row["model_id"].startswith("openai:")
            and row["rubric_sha256"] == digest
            and row["mode"] == "rubric-discovery"
            for row in registry["calibrated"]
        ))
        cases = [json.loads(line) for line in BANK.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(cases), 30)
        swaps = [row for row in cases if row["swap_applied"]]
        self.assertGreaterEqual(len(swaps), 3)
        self.assertTrue(all(row["judge_verdict"] == "INSUFFICIENT_EVIDENCE" for row in swaps))

    def test_every_enum_value_is_monotone(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        baseline = plan_returns.decide(verdict=None)
        self.assertEqual(len(schema["properties"]["verdict"]["enum"]), 5)
        for verdict in schema["properties"]["verdict"]["enum"]:
            with self.subTest(verdict=verdict):
                self.assertTrue(plan_returns.at_least_as_strict(
                    plan_returns.decide(verdict=verdict), baseline))

    def test_three_order_sensitive_swaps_abstain(self):
        for forward, reverse in (
            ("JUSTIFIED", "AVOIDABLE"),
            ("AVOIDABLE", "JUSTIFIED"),
            ("OUT_OF_SCOPE", "INSUFFICIENT_EVIDENCE"),
        ):
            with self.subTest(forward=forward, reverse=reverse):
                self.assertEqual(
                    plan_returns.conservative_swap_verdict(forward, reverse),
                    "INSUFFICIENT_EVIDENCE",
                )

    def test_monotonicity_rejects_an_artificially_weakened_branch(self):
        baseline = plan_returns.decide(occurrences=3)
        weakened = plan_returns.decide(verdict="JUSTIFIED", occurrences=3)
        weakened["continue_allowed"] = True
        weakened["stop_required"] = False
        weakened["owner_gate_required"] = False
        self.assertFalse(plan_returns.at_least_as_strict(weakened, baseline))

    def test_first_schema_valid_record_wins_over_later_record(self):
        findings = self.plan / "findings"
        digest = plan_returns.returns(self.plan)["fingerprints"][0]["digest"]
        (findings / "A-judgement.md").write_text(
            carrier(judgement(verdict="JUSTIFIED", event_id="journal.jsonl:7", digest=digest)), encoding="utf-8")
        (findings / "Z-judgement.md").write_text(
            carrier(judgement(verdict="MALFORMED", event_id="journal.jsonl:7", digest=digest)), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["judgement"]["verdict"], "JUSTIFIED")
        self.assertEqual(gate["action"], "owner-gate")

    def test_uncalibrated_pair_is_interpreted_as_abstention(self):
        findings = self.plan / "findings"
        digest = plan_returns.returns(self.plan)["fingerprints"][0]["digest"]
        for path in findings.glob("*judgement*.md"):
            path.unlink()
        (findings / "A-uncalibrated.md").write_text(carrier(judgement(
            verdict="AVOIDABLE", event_id="journal.jsonl:7", digest=digest,
            model_id="anthropic:claude-pending", rubric_sha256="f" * 64,
        )), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["judgement"]["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_missing_provenance_is_ignored(self):
        bad = judgement()
        del bad["input_digest"]
        (self.plan / "findings/P1.1-fixture.md").unlink()
        for path in (self.plan / "findings").glob("*judgement*.md"):
            path.unlink()
        (self.plan / "findings/A-invalid.md").write_text(carrier(bad, seam=True), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertNotIn("judgement", gate)

    def test_self_judgement_is_rejected_without_later_retry(self):
        findings = self.plan / "findings"
        digest = plan_returns.returns(self.plan)["fingerprints"][0]["digest"]
        (findings / "A-self.md").write_text(carrier(judgement(
            reviewer="sonnet/medium", executor="sonnet/medium", event_id="journal.jsonl:7", digest=digest)),
            encoding="utf-8")
        (findings / "Z-later.md").write_text(carrier(judgement(
            verdict="MALFORMED", event_id="journal.jsonl:7", digest=digest)), encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertNotIn("judgement", gate)
        self.assertEqual([row["return_event_id"] for row in gate["owner_packet"]["judgements"]],
                         ["journal.jsonl:3", "journal.jsonl:5"])

    def test_classified_fixture_exercises_packet_and_verdict(self):
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["namespace"], "classified")
        self.assertTrue(gate["blocks"])
        self.assertEqual(gate["action"], "owner-gate")
        self.assertEqual(gate["judgement"]["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual([row["return_event_id"] for row in gate["owner_packet"]["judgements"]],
                         ["journal.jsonl:3", "journal.jsonl:5", "journal.jsonl:7"])

    def test_gate_rows_never_block_and_allow_continuation_together(self):
        rows = []
        for occurrence in range(2):
            minute = occurrence * 2
            rows.extend((
                {"ts": f"2026-07-03T00:{minute:02d}:00Z", "plan_id": "plan-v2", "item_id": "P1.1",
                 "command": "plan-run", "session_id": None, "run_id": None, "attempt": occurrence + 1,
                 "actor": "executor", "friction": ["retry"], "result": "closed-green", "cost_usd": None,
                 "num_turns": None, "duration_ms": None, "note": None},
                {"ts": f"2026-07-03T00:{minute + 1:02d}:00Z", "plan_id": "plan-v2", "item_id": "P1.1",
                 "command": "plan-design", "session_id": None, "run_id": None, "attempt": occurrence + 1,
                 "actor": "executor", "friction": [], "result": "in-progress", "cost_usd": None,
                 "num_turns": None, "duration_ms": None, "note": None},
            ))
        (self.plan / "journal.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        for path in (self.plan / "findings").glob("*judgement*.md"):
            path.unlink()
        incomplete = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual((incomplete["action"], incomplete["blocks"], incomplete["continue_allowed"]),
                         ("isolated-review", True, False))
        digest = plan_returns.returns(self.plan)["fingerprints"][0]["digest"]
        for verdict, action, blocks, allowed in (
            ("JUSTIFIED", "return-to-root", False, True),
            ("INSUFFICIENT_EVIDENCE", "return-to-root", False, True),
            ("AVOIDABLE", "judgement-stop", True, False),
            ("OUT_OF_SCOPE", "judgement-stop", True, False),
            ("MALFORMED", "judgement-stop", True, False),
        ):
            with self.subTest(verdict=verdict):
                path = self.plan / "findings/A-current.md"
                path.write_text(carrier(judgement(
                    verdict=verdict, event_id="journal.jsonl:4", digest=digest)), encoding="utf-8")
                gate = plan_returns.return_loop_gates(self.plan)[0]
                self.assertEqual((gate["action"], gate["blocks"], gate["continue_allowed"]),
                                 (action, blocks, allowed))
                self.assertFalse(gate["blocks"] and gate["continue_allowed"])
