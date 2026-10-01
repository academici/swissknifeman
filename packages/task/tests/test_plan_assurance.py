"""Regression coverage for P3.1 phase assurance and impact reduction."""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from task import journal, plan_assurance, plan_gates  # noqa: E402


def candidate(*, phase_id="P1", statuses=("🟢 Done",), product="a", risks=()):
    return {
        "phase_id": phase_id,
        "scope": [],
        "terminal_item_heads": [
            {"item_id": f"{phase_id}.{index}", "status": status,
             "spec_sha256": "a" * 64, "terminal_evidence_sha256": "b" * 64}
            for index, status in enumerate(statuses, 1)
        ],
        "material_risks": list(risks),
        "declared_files": ["packages/task/lib/task/example.py"],
        "product_tree_sha256": product * 64,
    }


class PhaseAssuranceTests(unittest.TestCase):
    def plan(self, *, impact="isolated", seams="—", live="no", intent="direct-close-eligible"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "P"
        phase = root / "phases" / "P1"
        phase.mkdir(parents=True)
        (phase / "P1.md").write_text(
            "# P1\n\n> **Phase Assurance | v1.**\n"
            f"> Impact: {impact}\n> Integration Seams: {seams}\n"
            f"> Live or Irreversible: {live}\n> Audit Intent: {intent}\n"
            "> Rationale: regression fixture\n", encoding="utf-8")
        return root

    def test_total_schema_and_direct_close_matrix(self):
        plan = self.plan()
        decision = plan_assurance.evaluate(plan, "P1", candidate=candidate(statuses=("🟢 Done", "🟢 Done")))
        self.assertEqual(decision["action"], "direct-close")
        for kwargs in (
            {"impact": "public-contract", "intent": "auto"},
            {"impact": "security-external", "intent": "auto"},
            {"impact": "isolated", "live": "yes", "intent": "auto"},
        ):
            with self.subTest(kwargs=kwargs):
                decision = plan_assurance.evaluate(self.plan(**kwargs), "P1", candidate=candidate())
                self.assertEqual(decision["action"], "direct-close")
                self.assertTrue(decision["close_allowed"])
                self.assertFalse(decision["audit_required"])

    def test_declaration_cannot_hide_non_green_or_material_risk(self):
        plan = self.plan()
        self.assertEqual(plan_assurance.evaluate(plan, "P1", candidate=candidate(statuses=("🟠 Done with deviations",)))["code"],
                         "PHASE_ACCEPTANCE_NON_GREEN")
        self.assertEqual(plan_assurance.evaluate(plan, "P1", candidate=candidate(risks=("security",)))["code"],
                         "PHASE_DIRECT_CLOSE_ASSURED")

    def test_legacy_intent_and_item_count_do_not_require_audit(self):
        plan = self.plan(
            impact="internal-integration",
            seams="legacy-seam",
            live="none; repository edits are reversible",
            intent="light",
        )
        assurance = plan_assurance.read(plan, "P1")
        self.assertEqual(assurance["audit_intent"], "legacy-light")
        self.assertFalse(assurance["live_or_irreversible"])
        self.assertEqual(
            plan_assurance.evaluate(plan, "P1", candidate=candidate())["code"],
            "PHASE_DIRECT_CLOSE_ASSURED",
        )
        self.assertEqual(
            plan_assurance.evaluate(plan, "P1", candidate=candidate(statuses=("🟢 Done", "🟢 Done")))["code"],
            "PHASE_DIRECT_CLOSE_ASSURED",
        )

    def test_field_level_impact_never_returns_bare_stale_or_implicit_full(self):
        plan = self.plan(impact="internal-integration", seams="policy", intent="auto")
        baseline = candidate(product="a")
        bookkeeping = plan_assurance.evaluate(plan, "P1", candidate=candidate(product="a"), baseline=baseline)
        self.assertEqual(bookkeeping["action"], "gate-rebind")
        self.assertEqual(bookkeeping["impact"]["classification"], "audit-bookkeeping")
        local = plan_assurance.evaluate(plan, "P1", candidate=candidate(product="c"), baseline=baseline)
        self.assertEqual(local["action"], "direct-close")
        self.assertEqual(local["impact"]["classification"], "local-material")
        wide = plan_assurance.evaluate(plan, "P1", candidate=candidate(product="c", risks=("security",)), baseline=baseline)
        self.assertEqual(wide["action"], "direct-close")
        self.assertFalse(wide["audit_required"])

    def test_green_acceptance_does_not_require_repeating_a_legacy_audit(self):
        plan = self.plan(impact="internal-integration", seams="policy", intent="auto")
        current = candidate(product="b")
        fingerprint = plan_gates._candidate_snapshot_fingerprint(current)
        event = journal.new_entry(plan_id="P", item_id="P1 — phase mode", command="plan-audit",
                                  actor="model/high", result="audit-green", fingerprint="a" * 64)
        self.assertEqual(event["item_id"], "P1")
        journal.append(plan, event)
        gate = plan_gates.phase_close_gate(plan, "P1", candidate_fingerprint=fingerprint,
                                           candidate_snapshot=current)
        self.assertNotEqual(gate["code"], "PHASE_AUDIT_STALE")
        self.assertTrue(gate["allow"])

    def test_required_green_phase_closes_without_audit(self):
        plan = self.plan(impact="internal-integration", seams="migration", intent="required")
        snapshot = candidate()
        policy = plan_gates.phase_audit_policy(plan, "P1", candidate_snapshot=snapshot)
        self.assertEqual(policy["next_kind"], "close")
        self.assertTrue(policy["diagnostics"])
        self.assertTrue(plan_gates.phase_close_gate(
            plan, "P1", candidate_snapshot=snapshot,
            candidate_fingerprint=plan_gates._candidate_snapshot_fingerprint(snapshot))["allow"])

    def test_absent_legacy_assurance_is_advisory(self):
        plan = self.plan()
        (plan / "phases/P1/P1.md").write_text("# P1\n", encoding="utf-8")
        result = plan_assurance.evaluate(plan, "P1", candidate=candidate())
        self.assertTrue(result["close_allowed"])
        self.assertFalse(result["audit_required"])
        self.assertEqual(result["assurance"]["schema_version"], "phase-assurance/implicit-v1")
        self.assertEqual(result["diagnostics"], [])

    def test_facade_rebuilds_candidate_once_when_not_supplied(self):
        plan = self.plan()
        with patch.object(plan_gates, "phase_candidate_fingerprint", return_value={"snapshot": candidate()}) as build:
            self.assertTrue(plan_gates.phase_audit_policy(plan, "P1")["close_allowed"])
        build.assert_called_once_with(plan, "P1")

    def test_missing_evidence_is_neither_audit_nor_green(self):
        for snapshot in (None, {}, {**candidate(), "product_tree_sha256": ""},
                         {**candidate(), "terminal_item_heads": []}):
            with self.subTest(snapshot=snapshot):
                result = plan_assurance.evaluate(self.plan(), "P1", candidate=snapshot)
                self.assertFalse(result["close_allowed"])
                self.assertFalse(result["audit_required"])
                self.assertNotEqual(result["next_kind"], "audit-phase")

    def test_non_green_owning_work_cannot_close_without_consent(self):
        plan = self.plan()
        snapshot = candidate(statuses=("🔴 Blocked",))
        result = plan_assurance.evaluate(plan, "P1", candidate=snapshot)
        self.assertEqual(result["next_exact"], "run-items: task:plan-run P P1.1")
        gate = plan_gates.phase_close_gate(
            plan, "P1", candidate_snapshot=snapshot,
            candidate_fingerprint=plan_gates._candidate_snapshot_fingerprint(snapshot))
        self.assertFalse(gate["allow"])
        self.assertFalse(gate["audit_policy"]["audit_required"])

    def test_live_audit_requires_consent_once_and_then_closes(self):
        from test_audit_admission import AuditAdmissionTests, record
        fixture = AuditAdmissionTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        plan = fixture.plan_dir
        snapshot = candidate()
        current = {"snapshot": snapshot, "fingerprint": plan_gates._candidate_snapshot_fingerprint(snapshot)}
        grant = record(snapshot)
        def event(result):
            return journal.new_entry(
                plan_id=plan.name, item_id="P1", command="plan-audit", actor="test/high",
                run_id=grant["run_id"], fingerprint=current["fingerprint"], result=result)
        with patch.object(plan_gates, "phase_candidate_fingerprint", return_value=current):
            with self.assertRaisesRegex(journal.JournalValidationError, "AUDIT_CONSENT"):
                journal.append(plan, event("in-progress"))
            fixture.grant(grant)
            policy = plan_assurance.evaluate(plan, "P1", candidate=snapshot)
            self.assertTrue(policy["audit_required"])
            self.assertFalse(policy["close_allowed"])
            journal.append(plan, event("in-progress"))
            with self.assertRaisesRegex(journal.JournalValidationError, "AUDIT_RUN_ALREADY_STARTED"):
                journal.append(plan, event("in-progress"))
            journal.append(plan, event("audit-green"))
            with self.assertRaisesRegex(journal.JournalValidationError, "AUDIT_CONSENT_CONSUMED"):
                journal.append(plan, event("in-progress"))
            gate = plan_gates.phase_close_gate(
                plan, "P1", candidate_snapshot=snapshot, candidate_fingerprint=current["fingerprint"])
            self.assertTrue(gate["allow"])
            self.assertFalse(gate["audit_policy"]["audit_required"])
