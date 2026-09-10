"""Regression coverage for P3.1 phase assurance and impact reduction."""
import tempfile
import unittest
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
                self.assertEqual(decision["action"], "audit-required")

    def test_declaration_cannot_hide_non_green_or_material_risk(self):
        plan = self.plan()
        self.assertEqual(plan_assurance.evaluate(plan, "P1", candidate=candidate(statuses=("🟠 Done with deviations",)))["code"],
                         "PHASE_AUDIT_REQUIRED_NON_GREEN")
        self.assertEqual(plan_assurance.evaluate(plan, "P1", candidate=candidate(risks=("security",)))["code"],
                         "PHASE_AUDIT_REQUIRED_MATERIAL_RISK")

    def test_field_level_impact_never_returns_bare_stale_or_implicit_full(self):
        plan = self.plan(impact="internal-integration", seams="policy", intent="auto")
        baseline = candidate(product="a")
        bookkeeping = plan_assurance.evaluate(plan, "P1", candidate=candidate(product="a"), baseline=baseline)
        self.assertEqual(bookkeeping["action"], "gate-rebind")
        self.assertEqual(bookkeeping["impact"]["classification"], "audit-bookkeeping")
        local = plan_assurance.evaluate(plan, "P1", candidate=candidate(product="c"), baseline=baseline)
        self.assertEqual(local["action"], "delta")
        self.assertEqual(local["impact"]["classification"], "local-material")
        wide = plan_assurance.evaluate(plan, "P1", candidate=candidate(product="c", risks=("security",)), baseline=baseline)
        self.assertEqual(wide["action"], "audit-required")

    def test_close_normalizes_new_writer_and_reports_missing_baseline_as_typed_continuation(self):
        plan = self.plan(impact="internal-integration", seams="policy", intent="auto")
        current = candidate(product="b")
        fingerprint = plan_gates._candidate_snapshot_fingerprint(current)
        event = journal.new_entry(plan_id="P", item_id="P1 — режим фазы", command="plan-audit",
                                  actor="model/high", result="audit-green", fingerprint="a" * 64)
        self.assertEqual(event["item_id"], "P1")
        journal.append(plan, event)
        gate = plan_gates.phase_close_gate(plan, "P1", candidate_fingerprint=fingerprint,
                                           candidate_snapshot=current)
        self.assertNotEqual(gate["code"], "PHASE_AUDIT_STALE")
        self.assertEqual(gate["continuation"], "gather-evidence")
