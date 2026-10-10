from __future__ import annotations

import json
from pathlib import Path
import unittest

from orch import retry
from orch.retry import DEFAULT_ACTIONS, ERROR_CLASSES, RATE_LIMIT_DEFAULT_WAIT_S, RetryInputs, class_of, decide

ROOT = Path(__file__).resolve().parents[1]
AICORE = ROOT.parent / "aicore"
CLAUDE = {"provider": "claude", "model_class": "implementation"}
CODEX = {"provider": "codex", "model_class": "implementation"}


def inputs(error_class="transport", **override):
    values = dict(error_class=error_class, stage_writes=False, worktree_dirty=False, receipt_unresolved=False,
                  attempts_used=1, stage_retries_max=2, budget_left=5)
    values.update(override)
    return RetryInputs(**values)


class RetryTableTests(unittest.TestCase):
    def test_error_classes_equal_the_aicore_enum(self):
        import os
        root = Path(os.environ.get("AICORE_ROOT") or AICORE)
        schema = json.loads((root / "schemas/error/v1/error.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(ERROR_CLASSES), schema["$defs"]["error-class"]["enum"])

    def test_default_actions_cover_every_class_and_unknown_outcome(self):
        self.assertEqual(set(DEFAULT_ACTIONS), set(ERROR_CLASSES) | {"unknown_outcome"})
        self.assertEqual(len(DEFAULT_ACTIONS), 13)
        self.assertTrue(set(DEFAULT_ACTIONS.values()) <= set(retry.ACTIONS))

    def test_read_only_table_gives_the_default_action(self):
        for cls, action in DEFAULT_ACTIONS.items():
            with self.subTest(cls=cls):
                decision = decide(inputs(cls, retry_after_s=10), {})
                expected = "retry" if cls == "unknown_outcome" else action
                self.assertEqual(decision.action, expected)
                self.assertIn(decision.reason_codes[0], ("ACTION_DEFAULT",))

    def test_context_limit_replans_and_unknown_outcome_reconciles(self):
        self.assertEqual(DEFAULT_ACTIONS["context_limit"], "replan")
        self.assertEqual(DEFAULT_ACTIONS["unknown_outcome"], "reconcile")
        self.assertEqual(decide(inputs("context_limit"), {}).reason_codes, ("ACTION_DEFAULT", "CONTEXT_LIMIT"))

    def test_unknown_outcome_of_a_writing_stage_is_reconciled_even_against_policy(self):
        policy = {"on_error": {"unknown_outcome": {"action": "retry"}}}
        for current in ({}, policy):
            decision = decide(inputs("unknown_outcome", stage_writes=True), current)
            self.assertEqual(decision.action, "reconcile")
            self.assertIn("UNKNOWN_OUTCOME_WRITE", decision.reason_codes)

    def test_unknown_outcome_of_a_read_only_stage_is_retried(self):
        decision = decide(inputs("unknown_outcome"), {})
        self.assertEqual((decision.action, decision.reason_codes[-1]), ("retry", "UNKNOWN_OUTCOME_READ_ONLY"))

    def test_partial_changes_of_a_writing_stage_need_reconcile(self):  # R20
        for flag in ("worktree_dirty", "receipt_unresolved"):
            with self.subTest(flag=flag):
                decision = decide(inputs("provider_internal", stage_writes=True, **{flag: True}), {})
                self.assertEqual((decision.action, decision.reason_codes[-1]), ("reconcile", "PARTIAL_CHANGES"))
                clean = decide(inputs("provider_internal", stage_writes=False, **{flag: True}), {})
                self.assertEqual(clean.action, DEFAULT_ACTIONS["provider_internal"])

    def test_a_writing_stage_with_a_clean_tree_is_retried(self):
        self.assertEqual(decide(inputs("transport", stage_writes=True), {}).action, "retry")

    def test_budgets_stop_repeating_actions(self):
        for override in ({"attempts_used": 3}, {"budget_left": 0}):
            with self.subTest(override=override):
                decision = decide(inputs("transport", **override), {})
                self.assertEqual((decision.action, decision.reason_codes[-1]), ("stop", "BUDGET_EXHAUSTED"))
        self.assertEqual(decide(inputs("transport", attempts_used=2), {}).action, "retry")
        self.assertEqual(decide(inputs("transport", stage_retries_max=0), {}).action, "stop")

    def test_budget_does_not_stop_non_repeating_actions(self):
        decision = decide(inputs("context_limit", budget_left=0, attempts_used=9), {})
        self.assertEqual(decision.action, "replan")

    def test_policy_overrides_the_action_and_its_maximum(self):
        policy = {"on_error": {"transport": {"action": "stop"}, "timeout": {"action": "retry", "max": 1}}}
        self.assertEqual(decide(inputs("transport"), policy).reason_codes, ("ACTION_FROM_POLICY",))
        self.assertEqual(decide(inputs("transport"), policy).action, "stop")
        self.assertEqual(decide(inputs("timeout"), policy).action, "retry")
        self.assertEqual(decide(inputs("timeout", attempts_used=2), policy).reason_codes,
                         ("ACTION_FROM_POLICY", "BUDGET_EXHAUSTED"))

    def test_retry_after_waits_for_the_provider_value(self):
        decision = decide(inputs("quota", retry_after_s=90), {})
        self.assertEqual((decision.action, decision.wait_s), ("retry_after", 90))

    def test_retry_after_without_value(self):
        quota = decide(inputs("quota"), {})
        self.assertEqual((quota.action, quota.reason_codes[-1]), ("stop", "RETRY_AFTER_UNKNOWN"))
        limit = decide(inputs("rate_limit"), {})
        self.assertEqual((limit.action, limit.wait_s), ("retry_after", RATE_LIMIT_DEFAULT_WAIT_S))

    def test_fallback_route_picks_the_first_other_route(self):
        policy = {"on_error": {"model_unavailable": {"action": "fallback_route"}},
                  "fallback_routes": [CLAUDE, CODEX]}
        decision = decide(inputs("model_unavailable", current_route=dict(CLAUDE)), policy)
        self.assertEqual((decision.action, decision.route, decision.reason_codes[-1]),
                         ("fallback_route", CODEX, "FALLBACK_ROUTE"))
        self.assertIsNot(decision.route, policy["fallback_routes"][1])

    def test_fallback_without_a_declared_route_stops(self):
        policy = {"on_error": {"model_unavailable": {"action": "fallback_route"}}}
        for current in (policy, dict(policy, fallback_routes=[CLAUDE])):
            decision = decide(inputs("model_unavailable", current_route=dict(CLAUDE)), current)
            self.assertEqual((decision.action, decision.route, decision.reason_codes[-1]),
                             ("stop", None, "FALLBACK_UNDECLARED"))

    def test_fallback_is_a_repeat_and_follows_partial_changes_rule(self):
        policy = {"on_error": {"model_unavailable": {"action": "fallback_route"}}, "fallback_routes": [CODEX]}
        decision = decide(inputs("model_unavailable", stage_writes=True, worktree_dirty=True), policy)
        self.assertEqual(decision.action, "reconcile")

    def test_class_of(self):
        error = {"class": "rate_limit", "code": "SLOW_DOWN", "retryable": True, "safe_message": "slow"}
        self.assertEqual(class_of("failed", error), "rate_limit")
        for kind, cls in (("quota_block", "quota"), ("quota_blocked", "quota"), ("auth_block", "authentication"),
                          ("auth_blocked", "authentication"), ("timeout", "timeout"),
                          ("provider_error", "provider_internal"), ("unknown_outcome", "unknown_outcome"),
                          ("failed", "unknown")):
            with self.subTest(kind=kind):
                self.assertEqual(class_of(kind), cls)
        with self.assertRaises(ValueError):
            class_of("completed")

    def test_unknown_class_is_refused(self):
        with self.assertRaises(ValueError):
            decide(inputs("provider"), {})


if __name__ == "__main__":
    unittest.main()
