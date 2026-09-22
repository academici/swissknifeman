import unittest

from task.plan_lifecycle import LifecycleInput, select


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

    def test_invalid_impact_never_silently_selects_low_risk(self):
        for data in (None, {"audit": True}, LifecycleInput(risks=frozenset(("security_auth",))),
                     LifecycleInput(bounded_integration=None), LifecycleInput(audit_product_finding=True)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                select(data)

    def test_route_is_reused_until_a_real_change(self):
        self.assertEqual(select(LifecycleInput()).route_evidence, "reuse")
        self.assertEqual(select(LifecycleInput(route_changed=True)).route_evidence, "recapture")

    def test_domain_risk_tags_are_accepted_as_advisory_metadata(self):
        result = select(LifecycleInput(
            risk_tags=frozenset(("privacy-retention", "availability-slo"))))
        self.assertEqual(result.validation, ("focused",))
        self.assertEqual(result.review, "none")

    def test_unknown_hard_risk_still_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "risk_tags"):
            select(LifecycleInput(risks=frozenset(("medical",))))
