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
