"""Negative producer matrix and stage transitions for plan admission."""
import json
import tempfile
import unittest
from pathlib import Path

from task import plan_admission


def _record(item_id, *, status="⬜ Not started", gaps=()):
    return {"item_id": item_id, "status": status, "weight_tokens": 10,
            "gaps": list(gaps)}


def _missing(path="out/result.json", entry=None):
    return {"kind": "missing_file", "role": "required_read", "path": path,
            "entry": entry or path}


class TestProducerAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan_dir = Path(self.tmp.name)
        self.contract = {"path": "fixture", "version": "1.1.0", "item_tokens": 100}

    def tearDown(self):
        self.tmp.cleanup()

    def classify(self, items, specs):
        return plan_admission.classify(self.plan_dir, items, specs, contract=self.contract)

    def test_missing_without_producer_fails_closed(self):
        items = [_record("P1.1", gaps=[_missing()])]
        self.classify(items, {"P1.1": {"required_read_entries": ["`out/result.json`"]}})
        self.assertEqual(items[0]["admission_state"], "ready")
        self.assertFalse(items[0]["admission_pass"])
        self.assertEqual(items[0]["admission_gaps"][0]["code"],
                         "missing_without_producer")

    def test_nonexistent_producer_fails_closed(self):
        items = [_record("P1.1", gaps=[_missing()])]
        specs = {"P1.1": {"required_read_entries":
                           ["`out/result.json` (producer: P9.9)"]}}
        self.classify(items, specs)
        self.assertEqual(items[0]["admission_gaps"][0]["code"], "producer_not_found")

    def test_producer_after_consumer_fails_closed(self):
        items = [_record("P1.1", gaps=[_missing()]), _record("P1.2")]
        specs = {"P1.1": {"required_read_entries":
                           ["`out/result.json` (producer: P1.2)"]},
                 "P1.2": {"deliverables": "`out/result.json`"}}
        self.classify(items, specs)
        self.assertEqual(items[0]["admission_gaps"][0]["code"],
                         "producer_not_predecessor")

    def test_terminal_producer_without_deliverable_fails_closed(self):
        items = [_record("P1.1", status="🟢 Done"),
                 _record("P1.2", gaps=[_missing()])]
        specs = {"P1.1": {"deliverables": "другой файл"},
                 "P1.2": {"required_read_entries":
                           ["`out/result.json` (producer: P1.1)"]}}
        self.classify(items, specs)
        self.assertEqual(items[1]["admission_gaps"][0]["code"],
                         "producer_deliverable_mismatch")

    def test_valid_nonterminal_predecessor_is_pending(self):
        items = [_record("P1.1"), _record("P1.2", gaps=[_missing()])]
        specs = {"P1.1": {"deliverables": "`out/result.json`"},
                 "P1.2": {"required_read_entries":
                           ["`out/result.json` (producer=P1.1)"]}}
        summary = self.classify(items, specs)
        self.assertEqual(items[1]["admission_state"], "pending-producer")
        self.assertIsNone(items[1]["admission_pass"])
        self.assertEqual(items[1]["producer_item"], "P1.1")
        self.assertEqual(summary["counts"]["pending-producer"], 1)

    def test_terminal_predecessor_with_missing_output_fails_closed(self):
        items = [_record("P1.1", status="🟢 Done"),
                 _record("P1.2", gaps=[_missing()])]
        specs = {"P1.1": {"deliverables": "`out/result.json`"},
                 "P1.2": {"required_read_entries":
                           ["`out/result.json` (producer: P1.1)"]}}
        self.classify(items, specs)
        self.assertEqual(items[1]["admission_state"], "ready")
        self.assertEqual(items[1]["admission_gaps"][0]["code"],
                         "producer_terminal_missing")

    def test_ready_checks_both_d2_predicates(self):
        items = [_record("P1.1")]
        self.classify(items, {"P1.1": {}})
        self.assertEqual(items[0]["admission_state"], "ready")
        self.assertTrue(items[0]["d2a_pass"])
        self.assertTrue(items[0]["d2b_pass"])
        self.assertTrue(items[0]["admission_pass"])

    def test_missing_public_contract_fails_ready_item_closed(self):
        (self.plan_dir / "root").mkdir()
        items = [_record("P1.1")]
        summary = plan_admission.classify(self.plan_dir, items, {"P1.1": {}})
        self.assertFalse(items[0]["admission_pass"])
        self.assertEqual(items[0]["admission_gaps"][0]["code"],
                         "read_budget_contract_invalid")
        self.assertIsNone(summary["contract"])

    def test_rootless_v2_plan_uses_the_frozen_task_contract(self):
        items = [_record("P1.1")]
        summary = plan_admission.classify(self.plan_dir, items, {"P1.1": {}})
        self.assertEqual(summary["contract"]["version"], "1.1.0")
        self.assertTrue(items[0]["admission_pass"])

    def test_migration_pending_hold_clears_on_first_post_activation_execution(self):
        artifacts = self.plan_dir / "artifacts"
        archive = artifacts / "migration-source-v1"
        archive.mkdir(parents=True)
        (archive / "manifest.json").write_text("{}\n", encoding="utf-8")
        (artifacts / "p2-migration-inventory.json").write_text(json.dumps({
            "schema": "plan-migration-inventory-v1",
            "missing": [],
            "policy_preimage": {
                "source_digest": "0" * 64,
                "defect_classes": ["current-state-import", "read-budget-carrier"],
            },
            "current_state_import": {
                "kind": "canonical-current-state-not-chronology",
                "rows": [{"item": "P1.1", "source_status": "⬜ Not started",
                          "projected_result": None}],
            },
        }), encoding="utf-8")
        activation = {"item_id": "layout-v2", "command": "plan-design",
                      "result": "in-progress", "note": "Layout v2 migration activation"}
        (self.plan_dir / "journal.jsonl").write_text(
            json.dumps(activation) + "\n", encoding="utf-8")
        items = [_record("P1.1", gaps=[_missing()])]
        specs = {"P1.1": {"required_read_entries": ["`out/result.json`"]}}

        self.classify(items, specs)
        self.assertEqual(items[0]["admission_state"], "pending-producer")
        self.assertIsNone(items[0]["admission_pass"])
        self.assertIn("migration_pending_redesign",
                      [gap["code"] for gap in items[0]["admission_gaps"]])

        execution = {"item_id": "P1.1", "command": "plan-run",
                     "result": "in-progress", "note": "start"}
        (self.plan_dir / "journal.jsonl").write_text(
            json.dumps(activation) + "\n" + json.dumps(execution) + "\n",
            encoding="utf-8")
        items = [_record("P1.1", gaps=[_missing()])]
        self.classify(items, specs)
        self.assertEqual(items[0]["admission_state"], "ready")
        self.assertFalse(items[0]["admission_pass"])

    def test_current_state_note_is_not_mistaken_for_activation_boundary(self):
        imported = {"item_id": "P1.1", "command": "plan-run",
                    "result": "closed-green", "note": "Layout v2 current-state import"}
        activation = {"item_id": "layout-v2", "command": "plan-design",
                      "result": "in-progress", "note": "Layout v2 migration activation"}
        (self.plan_dir / "journal.jsonl").write_text(
            json.dumps(imported) + "\n" + json.dumps(activation) + "\n",
            encoding="utf-8")
        items = [_record("P1.1", status="🟢 Done", gaps=[_missing()])]
        self.classify(items, {"P1.1": {"required_read_entries": ["`out/result.json`"]}})
        self.assertEqual(items[0]["admission_state"], "historical-pre-v2")
        self.assertIsNone(items[0]["admission_pass"])


if __name__ == "__main__":
    unittest.main()
