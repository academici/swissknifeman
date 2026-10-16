from unittest import TestCase

from aicore.artifacts.reconcile import (Observation, ReconcileState,
                                        apply_reconciliation, plan_reconciliation)
from aicore.provider.values import ProviderId


class FakeReconciler:
    def __init__(self, provider_id, identity):
        self.provider_id = provider_id
        self.identity = identity
        self.applied = []

    def observe(self, target_id):
        return Observation(self.provider_id, target_id, self.identity, ReconcileState.CLEAN)

    def apply(self, plan):
        self.applied.append(plan)
        self.identity = plan.desired_identity


class TestReconciliation(TestCase):
    def test_no_write_plan_is_deterministic(self):
        adapter = FakeReconciler(ProviderId.CODEX, "before")
        plan = plan_reconciliation(provider_id=ProviderId.CODEX, target_id="commands",
                                   desired_identity="after", observe=adapter.observe)
        self.assertEqual(ReconcileState.DRIFTED, plan.state)
        self.assertEqual([], adapter.applied)

    def test_apply_requires_readback(self):
        adapter = FakeReconciler(ProviderId.CODEX, "before")
        plan = plan_reconciliation(provider_id=ProviderId.CODEX, target_id="commands",
                                   desired_identity="after", observe=adapter.observe)
        result = apply_reconciliation(plan, reconciler=adapter)
        self.assertEqual(ReconcileState.APPLIED, result.state)
        self.assertEqual("after", result.readback.identity)

    def test_cross_provider_observation_refuses(self):
        def wrong_provider(target_id):
            return Observation(ProviderId.CLAUDE_CODE, target_id, "before", ReconcileState.CLEAN)
        plan = plan_reconciliation(provider_id=ProviderId.CODEX, target_id="commands",
                                   desired_identity="after", observe=wrong_provider)
        self.assertEqual(ReconcileState.REFUSED, plan.state)
        self.assertEqual("RECONCILE_CROSS_PROVIDER_OBSERVATION", plan.diagnostics[0].code)

    def test_cross_provider_apply_refuses(self):
        plan = plan_reconciliation(provider_id=ProviderId.CODEX, target_id="commands",
                                   desired_identity="after",
                                   observe=FakeReconciler(ProviderId.CODEX, "before").observe)
        with self.assertRaisesRegex(ValueError, "RECONCILE_CROSS_PROVIDER_APPLY"):
            apply_reconciliation(plan, reconciler=FakeReconciler(ProviderId.CLAUDE_CODE, "before"))


class StaleReconciler(FakeReconciler):
    """Accepts the write but reads back something else (another identity or another target)."""

    def __init__(self, provider_id, identity, readback_target=None):
        super().__init__(provider_id, identity)
        self.readback_target = readback_target

    def apply(self, plan):
        self.applied.append(plan)

    def observe(self, target_id):
        return Observation(self.provider_id, self.readback_target or target_id, self.identity, ReconcileState.CLEAN)


class TestReconciliationOutcomes(TestCase):
    def plan(self, adapter, desired="after"):
        return plan_reconciliation(provider_id=ProviderId.CODEX, target_id="commands",
                                   desired_identity=desired, observe=adapter.observe)

    def test_a_clean_target_is_not_written(self):
        adapter = FakeReconciler(ProviderId.CODEX, "after")
        result = apply_reconciliation(self.plan(adapter), reconciler=adapter)
        self.assertEqual((ReconcileState.CLEAN, None, []), (result.state, result.readback, adapter.applied))

    def test_a_refused_observation_without_diagnostics_gets_one(self):
        def refused(target_id):
            return Observation(ProviderId.CODEX, target_id, "before", ReconcileState.REFUSED)
        plan = plan_reconciliation(provider_id=ProviderId.CODEX, target_id="commands",
                                   desired_identity="after", observe=refused)
        self.assertEqual(ReconcileState.REFUSED, plan.state)
        self.assertEqual(["RECONCILE_OBSERVATION_REFUSED"], [item.code for item in plan.diagnostics])
        self.assertFalse(plan.can_apply)

    def test_a_readback_with_the_old_identity_fails(self):
        adapter = StaleReconciler(ProviderId.CODEX, "before")
        result = apply_reconciliation(self.plan(adapter), reconciler=adapter)
        self.assertEqual(ReconcileState.READBACK_FAILED, result.state)
        self.assertEqual("before", result.readback.identity)

    def test_a_readback_of_another_target_fails_without_a_readback(self):
        adapter = StaleReconciler(ProviderId.CODEX, "before")
        plan = self.plan(adapter)
        adapter.readback_target = "other"
        result = apply_reconciliation(plan, reconciler=adapter)
        self.assertEqual((ReconcileState.READBACK_FAILED, None), (result.state, result.readback))

    def test_invalid_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            Observation(ProviderId.CODEX, "", "x", ReconcileState.CLEAN)
        with self.assertRaises(TypeError):
            Observation(ProviderId.CODEX, "t", "x", "clean")
        with self.assertRaises(ValueError):
            plan_reconciliation(provider_id=ProviderId.CODEX, target_id="t", desired_identity="",
                                observe=FakeReconciler(ProviderId.CODEX, "x").observe)
        with self.assertRaises(TypeError):
            plan_reconciliation(provider_id=ProviderId.CODEX, target_id="t", desired_identity="x",
                                observe=lambda target: "not an observation")
        with self.assertRaises(TypeError):
            apply_reconciliation("not a plan", reconciler=FakeReconciler(ProviderId.CODEX, "x"))
