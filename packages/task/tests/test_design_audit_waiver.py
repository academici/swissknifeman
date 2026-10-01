"""Owner waiver affects only the current finished design audit gate."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from task import journal, plan_readiness

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan


class DesignAuditWaiverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = write_valid_plan(Path(temporary.name), "2026.09.30-DEMO-OWNER-WAIVER")
        (self.root / "journal.jsonl").write_text("")
        core = self.root / "plan.md"
        core.write_text(core.read_text() + "\n**Design Audit Waiver:** D7\n")
        self.provenance = self.root / "artifacts" / "owner-waiver.md"
        self.provenance.parent.mkdir(exist_ok=True)
        self.provenance.write_text("Owner: execute this finished design without another design audit.\n")
        self.decision = self.root / "decisions" / "D7-owner-waiver.md"
        self.decision.parent.mkdir(exist_ok=True)
        self.fingerprint = plan_readiness.design_snapshot(self.root)["fingerprint"]
        self.record = {
            "schema_version": "design-audit-waiver/v1", "plan_id": self.root.name,
            "decision_id": "D7", "scope": "whole-plan-design-audit",
            "design_fingerprint": self.fingerprint,
            "owner_provenance": {
                "path": "artifacts/owner-waiver.md",
                "sha256": hashlib.sha256(self.provenance.read_bytes()).hexdigest(),
                "message": "execute this finished design without another design audit",
            },
            "reason": "Owner accepts the focused repaired design evidence.",
        }
        self.write_decision()
        self.finish()

    def write_decision(self, status="accepted"):
        self.decision.write_text(
            f"---\nid: D7\nstatus: {status}\n---\n\n"
            "```design-audit-waiver/v1\n" + json.dumps(self.record) + "\n```\n")

    def finish(self):
        fingerprint = plan_readiness.design_snapshot(self.root)["fingerprint"]
        journal.append(self.root, journal.new_entry(
            plan_id=self.root.name, item_id="finish", command="plan-design",
            actor="test", result="no-op", fingerprint=fingerprint))

    def test_owner_waiver_admits_without_fabricating_audit_green(self):
        gate = plan_readiness.design_gate(self.root)
        self.assertTrue(gate["allowed"])
        self.assertEqual(gate["code"], "PLAN_DESIGN_AUDIT_WAIVED_BY_OWNER")
        self.assertEqual(gate["owner_decision"], "D7")
        plan_readiness.validate_execution_design(self.root)
        events = journal.read_authoritative_entries(self.root)
        self.assertFalse(any(row["command"] == "plan-audit" for row in events))

    def test_plans_without_explicit_selection_keep_the_normal_gate(self):
        core = self.root / "plan.md"
        core.write_text(core.read_text().replace("**Design Audit Waiver:** D7", ""))
        self.finish()
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_MISSING")

    def test_missing_finish_is_not_waived(self):
        (self.root / "journal.jsonl").write_text("")
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_FINISH_MISSING")

    def test_changed_design_needs_a_new_explicit_grant_even_after_finish(self):
        core = self.root / "plan.md"
        core.write_text(core.read_text() + "\nMaterial new requirement.\n")
        self.finish()
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_STALE")

    def test_proposed_or_revoked_decision_is_not_authority(self):
        for status in ("proposed", "revoked"):
            with self.subTest(status=status):
                self.write_decision(status)
                self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_INVALID")

    def test_mutated_owner_evidence_is_rejected(self):
        self.provenance.write_text("Another message.\n")
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_INVALID")

    def test_foreign_plan_or_scope_is_rejected(self):
        for field, value in (("plan_id", "FOREIGN"), ("scope", "item-validation")):
            with self.subTest(field=field):
                original = self.record[field]
                self.record[field] = value
                self.write_decision()
                self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_INVALID")
                self.record[field] = original

    def test_external_owner_evidence_path_is_rejected(self):
        self.record["owner_provenance"]["path"] = "../foreign-owner.md"
        self.write_decision()
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_INVALID")

    def test_ambiguous_decisions_are_rejected(self):
        self.decision.with_name("D7-duplicate.md").write_text(self.decision.read_text())
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_INVALID")

    def test_recorded_current_red_audit_is_not_hidden_by_waiver(self):
        journal.append(self.root, journal.new_entry(
            plan_id=self.root.name, item_id="design", command="plan-audit",
            actor="test", result="audit-red", fingerprint=self.fingerprint))
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_NOT_GREEN")

    def test_closed_schema_rejects_unknown_waiver_fields(self):
        self.record["skip_other_gates"] = True
        self.write_decision()
        self.assertEqual(plan_readiness.design_gate(self.root)["code"], "PLAN_DESIGN_AUDIT_WAIVER_INVALID")


if __name__ == "__main__":
    unittest.main()
