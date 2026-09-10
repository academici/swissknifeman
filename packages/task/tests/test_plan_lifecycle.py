import unittest

from task.plan_lifecycle import LifecycleInput, execute, select


class PlanLifecycleTests(unittest.TestCase):
    def test_low_risk_normal_path_is_focused_once(self):
        result = select(LifecycleInput(changed_projections=("state", "state", "handoff")))
        self.assertEqual(result.validation, ("focused",))
        self.assertEqual(result.review, "none")
        self.assertEqual(result.audit_action, "not-requested")
        self.assertEqual(result.projections, ("state", "handoff"))
        self.assertEqual(result.commits, 1)
        self.assertEqual(result.context, "continue-root")
        self.assertEqual(result.semantic_next, "exec-items")

    def test_every_hard_boundary_widens(self):
        for risk in ("security-auth", "destructive-migration", "irreversible-external",
                     "payment-accounting", "concurrency-shared-state", "public-api-schema",
                     "low-confidence-impact"):
            with self.subTest(risk=risk):
                result = select(LifecycleInput(risks=frozenset((risk,))))
                self.assertEqual(result.validation, ("focused", "affected-package", "integration"))
                self.assertEqual(result.review, "independent")

    def test_foreign_baseline_and_audit_are_bounded(self):
        result = select(LifecycleInput(audit=True, audit_product_finding=True))
        self.assertEqual(result.audit_action, "return-owning-continuation")
        self.assertEqual(result.foreign_baseline, "visible-non-gating")
        self.assertEqual(select(LifecycleInput(foreign_baseline_intersects=True)).foreign_baseline, "gating")

    def test_route_is_reused_until_a_real_change_and_cost_is_reported(self):
        result = execute(LifecycleInput(), executed=("focused",), started_at=0.0)
        self.assertEqual(result["reused"], ("route-evidence",))
        self.assertEqual(result["executed"], ("focused",))
        self.assertIsNotNone(result["wall_time_ms"])
        self.assertEqual(select(LifecycleInput(route_changed=True)).route_evidence, "recapture")
