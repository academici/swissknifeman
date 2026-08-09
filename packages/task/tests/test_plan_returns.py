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


def entry(ts, command, result, *, item="P1.1", friction=(), note=None, attempt=1):
    return {"ts": ts, "plan_id": "plan-v2", "item_id": item, "command": command,
            "session_id": None, "run_id": None, "attempt": attempt, "actor": "test/high",
            "friction": list(friction), "result": result, "cost_usd": None,
            "num_turns": None, "duration_ms": None, "note": note}


class PlanReturnsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan-v2"
        source = Path(__file__).parent / "data" / "plan-v2"
        shutil.copytree(source, self.plan)
        # P4.6 promotes the shared fixture to the classified acceptance path.
        # These reducer-unit cases retain their own provisional baseline.
        (self.plan / "findings/P1.1-fixture.md").write_text(
            "---\nitem: P1.1\ndate: 2026-07-02\n---\n\n# Fixture finding\n",
            encoding="utf-8")
        rows = [entry("2026-07-02T00:00:00Z", "plan-run", "escalated", friction=("escalation",)),
                entry("2026-07-02T00:01:00Z", "plan-design", "in-progress", note="rewritten", attempt=2),
                entry("2026-07-02T00:02:00Z", "plan-run", "closed-green"),
                entry("2026-07-02T00:03:00Z", "plan-design", "in-progress")]
        raw = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
        raw += '\n{"bad":"row"}\n'
        (self.plan / "journal.jsonl").write_text(raw, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_digest_ignores_note_and_attempt_but_seam_changes_it(self):
        first = plan_returns.returns(self.plan)["fingerprints"][0]
        text = (self.plan / "journal.jsonl").read_text(encoding="utf-8")
        (self.plan / "journal.jsonl").write_text(text.replace("rewritten", "different words"), encoding="utf-8")
        self.assertEqual(first["digest"], plan_returns.returns(self.plan)["fingerprints"][0]["digest"])
        finding = self.plan / "findings/P1.1-fixture.md"
        finding.write_text("---\nitem: P1.1\ndate: 2026-07-02\nfile: a.py\nrule_or_contract_locus: x\ndefect_class: y\n---\n", encoding="utf-8")
        classified = plan_returns.returns(self.plan)["fingerprints"][0]
        self.assertEqual(classified["namespace"], "classified")
        self.assertNotEqual(first["digest"], classified["digest"])

    def test_invalid_trigger_is_ungroupable_and_missing_journal_is_unknown(self):
        result = plan_returns.returns(self.plan)
        self.assertGreater(result["metrics"]["schema_invalid_rows"], 0)
        self.assertEqual(result["fingerprints"][1]["namespace"], "ungroupable")
        (self.plan / "journal.jsonl").unlink()
        self.assertEqual(plan_returns.durable_count(self.plan, "a" * 64), "unknown")

    def test_lifted_schema_is_byte_identical(self):
        root = Path(__file__).resolve().parents[3]
        self.assertTrue(filecmp.cmp(root / "packages/task/configs/return-fingerprint-v1.schema.json",
                                     root / "plans/2026.08.07-PLAN-ECONOMY/root/contracts/return-fingerprint-v1.schema.json",
                                     shallow=False))

    def test_committed_fixture_emits_physical_return_event_ids_outside_fingerprint(self):
        fixture = Path(__file__).parent / "data" / "plan-v2"
        result = plan_returns.returns(fixture)
        history = [event for events in result["history"].values() for event in events]
        ids = [event["return_event_id"] for event in history]
        self.assertEqual(ids, ["journal.jsonl:3", "journal.jsonl:5", "journal.jsonl:7"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(event_id.startswith("journal.jsonl:") for event_id in ids))
        self.assertEqual(result["counts"], {
            "5f474410de10cf4b31d3c72a432203bc8fb311f544c1be5dbb5183d4c23cfc5c": 3,
        })
        self.assertTrue(all("return_event_id" not in record["tuple"]
                            for record in result["fingerprints"]))

    def test_downstream_record_is_not_a_return_seam(self):
        fixture = Path(__file__).parent / "data" / "plan-v2"
        record = next((fixture / "findings").glob("*downstream*.md"))
        self.assertFalse(plan_returns._is_seam_candidate(record.read_text(encoding="utf-8")))
        self.assertTrue(plan_returns.returns(fixture)["fingerprints"])

    def test_committed_fixture_has_multiple_event_scoped_judgement_carriers(self):
        fixture = Path(__file__).parent / "data" / "plan-v2" / "findings"
        carriers = sorted(fixture.glob("*judgement*.md"))
        self.assertGreaterEqual(len(carriers), 2)
        ids = []
        for carrier in carriers:
            fields = plan_returns._frontmatter(carrier)
            record = json.loads(fields["return_judgement"])
            plan_returns.validate_judgement(record)
            ids.append(record["return_event_id"])
        self.assertEqual(ids, ["journal.jsonl:5", "journal.jsonl:7"])

    def test_return_loop_owner_packet_uses_lifted_cap_and_durable_history(self):
        rows = []
        for index in range(3):
            minute = index * 2
            rows.extend((
                entry(f"2026-07-02T00:{minute:02d}:00Z", "plan-run", "closed-green",
                      friction=("retry",), attempt=index + 1),
                entry(f"2026-07-02T00:{minute + 1:02d}:00Z", "plan-design", "in-progress",
                      attempt=index + 1),
            ))
        (self.plan / "journal.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        gates = plan_returns.return_loop_gates(self.plan)
        owner = next(gate for gate in gates if gate["action"] == "owner-gate")
        self.assertEqual(owner["cap"], 2)
        self.assertEqual(owner["reason_code"], "RETURN_LOOP_OWNER_GATE_REQUIRED")
        self.assertEqual(owner["qualification"], "repeat")
        self.assertEqual(owner["owner_packet"]["fingerprint_tuple"]["friction_class"]["result"], "closed-green")
        self.assertIsNone(owner["owner_packet"]["fingerprint_tuple"]["seam"])
        self.assertEqual(owner["owner_packet"]["occurrences"], 3)
        self.assertEqual(len(owner["owner_packet"]["history"]), 3)
        self.assertEqual(set(owner["owner_packet"]), {
            "fingerprint_tuple", "fingerprint_digest", "occurrences", "cap", "history",
            "judgements", "resolutions_tried"})

    def test_triage_keeps_blocked_word_out_of_review_and_emits_unqualifiable(self):
        rows = [entry("2026-07-02T00:00:00Z", "plan-run", "blocked"),
                entry("2026-07-02T00:01:00Z", "plan-design", "in-progress")]
        (self.plan / "journal.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["action"], "local-fix")
        self.assertFalse(gate["review_required"])
        self.assertEqual(gate["qualification"], "new")
        rows[0]["result"] = "closed-green"
        (self.plan / "journal.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        unqualifiable = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(unqualifiable["qualification"], "unqualifiable")
        self.assertIn("missing_carrier_reason", unqualifiable)

    def test_observed_risk_trigger_requires_isolated_review_on_first_occurrence(self):
        (self.plan / "findings/P1.1-fixture.md").write_text(
            "---\nitem: P1.1\ndate: 2026-07-02\nfile: a.py\n"
            "rule_or_contract_locus: x\ndefect_class: security\n---\n", encoding="utf-8")
        gate = plan_returns.return_loop_gates(self.plan)[0]
        self.assertEqual(gate["action"], "isolated-review")
        self.assertTrue(gate["blocks"])
        self.assertTrue(gate["review_required"])

    def test_lifted_return_loop_spec_is_byte_identical(self):
        root = Path(__file__).resolve().parents[3]
        self.assertTrue(filecmp.cmp(root / "packages/task/configs/return-loop-v1.spec.json",
                                     root / "plans/2026.08.07-PLAN-ECONOMY/root/contracts/return-loop-v1.spec.json",
                                     shallow=False))
