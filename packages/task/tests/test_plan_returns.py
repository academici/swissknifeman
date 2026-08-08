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
