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
    def test_chat_scope_stop_and_explicit_fresh_session_are_distinct(self):
        decision = reduce(estimate(lifecycle="scope-complete", checkpoint="journal:closed-P1.1"))
        self.assertEqual(decision.outcome, "continue-root")
        self.assertEqual(decision.reason, "authorized-scope-complete")
        self.assertEqual(decision_from_dict(decision.as_dict()), decision)
        fresh = reduce(estimate(lifecycle="owner-requested-new-session", checkpoint="handoff:post-close"))
        self.assertEqual(fresh.context, "cold-start-root: owner-requested-new-session")
        self.assertEqual(decision_from_dict(fresh.as_dict()), fresh)
        for lifecycle in ("scope-complete", "owner-requested-new-session"):
            with self.assertRaisesRegex(ContinuityError, "checkpoint"):
                reduce(estimate(lifecycle=lifecycle))
        with self.assertRaisesRegex(ContinuityError, "scope completion"):
            decision_from_dict({**decision.as_dict(), "evidence": []})

    def test_calendar_pause_preserves_window_and_requires_external_predicate(self):
        pause = {"reason": "production observation", "started_at": "2026-09-10T12:00:00Z",
                 "resume_at": "2026-09-13T12:00:00Z", "observed_at": "2026-09-11T12:00:00Z",
                 "fingerprint": "b" * 64, "runnable_after": "72h production evidence complete",
                 "predicate_satisfied": False, "continuation": "task:plan-run PLAN P1.1"}
        waiting = reduce(estimate(lifecycle="waiting-external", checkpoint="artifacts/P1.1/window.json", external_pause=pause))
        self.assertEqual(waiting.outcome, "waiting-external")
        self.assertFalse(waiting.runnable)
        self.assertEqual(decision_from_dict(waiting.as_dict()), waiting)
        from task import command_render, plan_delivery
        persisted = ["| Context | waiting-external |"] + command_render.render_continuity_decision(waiting).splitlines()
        route = plan_delivery._route_from_lines(persisted)
        self.assertEqual(plan_delivery._continuity(route, allow_legacy=False), waiting.as_dict())
        with self.assertRaises(plan_delivery.DeliveryError):
            plan_delivery._continuity({**route, "context": "continue-root"}, allow_legacy=False)
        self.assertIn("started_at:2026-09-10T12:00:00Z", waiting.evidence)
        later = {**pause, "observed_at": "2026-09-13T12:00:00Z"}
        self.assertEqual(reduce(estimate(lifecycle="waiting-external", checkpoint="window", external_pause=later)).outcome,
                         "waiting-external")
        resumed = reduce(estimate(lifecycle="waiting-external", checkpoint="window",
                                  external_pause={**later, "predicate_satisfied": True}))
        self.assertEqual(resumed.outcome, "continue-root")
        self.assertIn("fingerprint:" + "b" * 64, resumed.evidence)
        for invalid in (None, {**pause, "resume_at": "2026-09-09T12:00:00Z"}):
            with self.assertRaises(ContinuityError):
                reduce(estimate(lifecycle="waiting-external", checkpoint="window", external_pause=invalid))

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
                                  batch_receipt_valid=True, boundary="design-root-terminal",
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
                ({"lifecycle": "design-root-terminal"}, "design-root-terminal")):
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

    def test_terminal_is_a_typed_nonrunnable_p1_3_outcome(self):
        decision = reduce(estimate(lifecycle="terminal"))
        self.assertEqual(decision.outcome, "terminal")
        self.assertFalse(decision.runnable)
        self.assertEqual(decision_from_dict(decision.as_dict()), decision)

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
