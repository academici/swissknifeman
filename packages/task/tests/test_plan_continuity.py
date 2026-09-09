import json
from pathlib import Path
import unittest

from task.plan_continuity import (COLD_START_REASONS, ContinuityDecision,
                                  ContinuityError, WorkEstimate, evaluate,
                                  decision_from_dict, estimate_from_dict,
                                  parse_context, reduce, validate_contracts,
                                  validate_decision)


def estimate(**overrides):
    value = {
        "route_attested": True,
        "capabilities_attested": True,
        "capabilities_sufficient": True,
        "context_attested": True,
        "context_health": "sufficient",
        "batch_receipt_valid": True,
        "remaining_batch_digest": "a" * 64,
        "loaded_inputs_reusable": True,
        "cold_start_cost": 1200,
    }
    value.update(overrides)
    return WorkEstimate(**value)


class ContinuityTests(unittest.TestCase):
    def test_compatible_and_missing_telemetry_continue_in_root(self):
        for telemetry in (True, None):
            self.assertEqual(evaluate(route_attested=True, context_attested=telemetry,
                                      batch_receipt_valid=True).outcome, "continue-root")

    def test_owner_wait_and_isolated_review_are_not_cold_starts(self):
        self.assertFalse(evaluate(route_attested=True, context_attested=True,
                                  batch_receipt_valid=True, waiting_owner=True).runnable)
        self.assertEqual(evaluate(route_attested=True, context_attested=True,
                                  batch_receipt_valid=True, isolated_review=True).outcome,
                         "isolated-child-return")

    def test_cold_start_requires_named_boundary_and_checkpoint(self):
        with self.assertRaises(ContinuityError):
            evaluate(route_attested=True, context_attested=False, batch_receipt_valid=True,
                     boundary="context-budget")
        self.assertEqual(evaluate(route_attested=True, context_attested=False,
                                  batch_receipt_valid=True, boundary="audit-root-terminal",
                                  checkpoint="journal:22").outcome, "cold-start-root")

    def test_unattested_route_or_batch_is_refused(self):
        with self.assertRaises(ContinuityError):
            evaluate(route_attested=False, context_attested=True, batch_receipt_valid=True)

    def test_full_estimate_uses_every_input_without_using_cost_as_a_boundary(self):
        decision = reduce(estimate(
            context_attested=False, context_health="unavailable",
            loaded_inputs_reusable=False, cold_start_cost=999999,
        ))
        self.assertEqual(decision.outcome, "continue-root")
        self.assertIn("loaded-inputs:not-reusable", decision.evidence)
        self.assertIn("cold-start-cost:999999", decision.evidence)

    def test_insufficient_context_and_terminal_lifecycle_require_checkpoint(self):
        for override, reason in (
                ({"context_health": "insufficient"}, "context-budget"),
                ({"lifecycle": "design-root-terminal"}, "design-root-terminal"),
                ({"lifecycle": "audit-root-terminal"}, "audit-root-terminal")):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ContinuityError, "checkpoint"):
                    reduce(estimate(**override))
                decision = reduce(estimate(**override, checkpoint="journal:42"))
                self.assertEqual(decision.context, f"cold-start-root: {reason}")

    def test_capability_boundary_requires_attestation(self):
        with self.assertRaisesRegex(ContinuityError, "capability attestation"):
            reduce(estimate(capabilities_attested=False, capabilities_sufficient=False,
                            checkpoint="journal:42"))
        self.assertEqual(
            reduce(estimate(capabilities_sufficient=False, checkpoint="journal:42")).reason,
            "capability-missing",
        )

    def test_wait_and_isolated_review_cannot_manufacture_a_new_root(self):
        waiting = reduce(estimate(lifecycle="waiting-owner"))
        self.assertEqual(waiting.outcome, "waiting-owner")
        self.assertFalse(waiting.runnable)
        isolated = reduce(estimate(isolated_review=True, reviewer_task="review:P1"))
        self.assertEqual(isolated.outcome, "isolated-child-return")
        self.assertNotEqual(isolated.outcome, "cold-start-root")

    def test_persisted_context_and_decision_are_fail_closed(self):
        for reason in COLD_START_REASONS:
            self.assertEqual(
                parse_context(f"cold-start-root: {reason}").reason, reason)
        with self.assertRaisesRegex(ContinuityError, "one reason"):
            parse_context("cold-start-root")
        with self.assertRaises(ContinuityError):
            validate_decision(ContinuityDecision(
                "waiting-owner", "owner-wait", (), True))
        self.assertEqual(parse_context("fresh session", allow_legacy=True).outcome,
                         "cold-start-root")

    def test_package_schemas_are_complete_and_bound_to_runtime_enums(self):
        self.assertTrue(validate_contracts())
        root = Path(__file__).resolve().parents[1] / "configs"
        work = json.loads((root / "session-work-estimate-v1.schema.json").read_text())
        decision = json.loads((root / "session-continuity-decision-v1.schema.json").read_text())
        self.assertEqual(set(work["required"]), set(work["properties"]))
        self.assertEqual(decision["cold_start_reasons"], list(COLD_START_REASONS))

    def test_json_bridges_reject_missing_extra_and_stale_evidence(self):
        work = estimate().as_dict()
        self.assertEqual(estimate_from_dict(work), estimate())
        for invalid in (
                {key: value for key, value in work.items() if key != "route_attested"},
                {**work, "unknown": True},
                {**work, "remaining_batch_digest": "stale"}):
            with self.subTest(invalid=invalid), self.assertRaises(ContinuityError):
                estimate_from_dict(invalid)
        decision = reduce(estimate()).as_dict()
        self.assertEqual(decision_from_dict(decision).outcome, "continue-root")
        with self.assertRaises(ContinuityError):
            decision_from_dict({**decision, "schema_version": "stale/v0"})
        with self.assertRaises(ContinuityError):
            decision_from_dict({**decision, "evidence": "not-a-list"})


if __name__ == "__main__":
    unittest.main()
