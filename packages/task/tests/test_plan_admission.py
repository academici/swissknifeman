"""Negative producer matrix and stage transitions for plan admission."""
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
        items = [_record("P1.1")]
        summary = plan_admission.classify(self.plan_dir, items, {"P1.1": {}})
        self.assertFalse(items[0]["admission_pass"])
        self.assertEqual(items[0]["admission_gaps"][0]["code"],
                         "read_budget_contract_invalid")
        self.assertIsNone(summary["contract"])


if __name__ == "__main__":
    unittest.main()
