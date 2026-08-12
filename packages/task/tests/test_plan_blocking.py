"""Continue-first block candidate policy."""
import unittest

from task import plan_blocking


def candidate(**overrides):
    value = {
        "schema_version": "block-candidate/v1",
        "plan_id": "2026.08.12-№1-DEMO",
        "item_id": "P1.1",
        "signal_class": "acceptance-failure",
        "scope_class": "acceptance",
        "external": False,
        "executor_actor": "root-executor",
        "evidence_ids": ["test:validation-red"],
        "resolutions_tried": ["minimal reproduction"],
        "rag": {"required": False, "status": "not-required", "evidence_ids": []},
        "review": None,
    }
    value.update(overrides)
    return value


def review(verdict="JUSTIFIED", **overrides):
    value = {
        "reviewer_actor": "isolated-reviewer",
        "context": "isolated-child-return",
        "verdict": verdict,
        "evidence_ids": ["review:finding-1"],
    }
    value.update(overrides)
    return value


class PlanBlockingTests(unittest.TestCase):
    def assertDecision(self, value, action, terminal=False):
        self.assertEqual(plan_blocking.evaluate(value), {
            "action": action,
            "terminal_allowed": terminal,
            "reason_code": plan_blocking.ACTION_REASON_CODES[action],
        })

    def test_local_reversible_signal_continues_without_reviewer(self):
        value = candidate(signal_class="local-reversible", scope_class="local")
        self.assertDecision(value, "continue-local-repair")

    def test_material_candidate_requires_isolated_review(self):
        self.assertDecision(candidate(), "request-isolated-review")

    def test_external_candidate_requires_verified_rag_before_review(self):
        value = candidate(
            external=True,
            scope_class="external",
            signal_class="external-dependency",
            rag={"required": True, "status": "missing", "evidence_ids": []},
            review=review(),
        )
        self.assertDecision(value, "gather-rag")

    def test_same_actor_review_is_rejected(self):
        value = candidate(review=review(reviewer_actor="root-executor"))
        self.assertDecision(value, "repair-review")

    def test_avoidable_returns_to_local_repair(self):
        self.assertDecision(candidate(review=review("AVOIDABLE")), "continue-local-repair")

    def test_insufficient_evidence_stays_nonterminal(self):
        self.assertDecision(candidate(review=review("INSUFFICIENT_EVIDENCE")), "gather-evidence")

    def test_only_justified_material_candidate_allows_terminal_block(self):
        self.assertDecision(candidate(review=review()), "terminal-block", terminal=True)

    def test_verified_external_candidate_can_reach_terminal_gate(self):
        value = candidate(
            external=True,
            scope_class="external",
            signal_class="external-dependency",
            rag={"required": True, "status": "verified", "evidence_ids": ["rag:source-1"]},
            review=review(),
        )
        self.assertDecision(value, "terminal-block", terminal=True)

    def test_closed_schema_rejects_unknown_field(self):
        with self.assertRaisesRegex(plan_blocking.BlockCandidateError, "неизвестные поля"):
            plan_blocking.evaluate(candidate(extra=True))


if __name__ == "__main__":
    unittest.main()
