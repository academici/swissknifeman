"""Continue-first block candidate policy."""
import itertools
import json
import unittest
from pathlib import Path

from task import journal, plan_blocking


PERPLEXITY_EVIDENCE_ID = f"rag:perplexity:sha256:{'a' * 64}"


def candidate(**overrides):
    value = {
        "schema_version": "block-candidate/v1",
        "plan_id": "2026.08.12-№1-DEMO",
        "item_id": "P1.1",
        "signal_class": "acceptance-failure",
        "scope_class": "acceptance",
        "external": False,
        "scope_coverage": "outside-scope",
        "boundary_evidence": ["decision:D42-approved-boundary"],
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
            "journal_result": plan_blocking.ACTION_OBSERVATION_RESULTS[action],
        })

    def test_local_reversible_signal_continues_without_reviewer(self):
        value = candidate(signal_class="local-reversible", scope_class="local")
        self.assertDecision(value, "continue-local-repair")

    def test_material_candidate_requires_isolated_review(self):
        self.assertDecision(candidate(), "request-isolated-review")

    def test_broad_in_scope_acceptance_failure_repairs_even_after_justified_review(self):
        value = candidate(
            scope_coverage="in-scope",
            boundary_evidence=[],
            evidence_ids=["phpstan:max:no-baseline:1591-errors:266-paths"],
            resolutions_tried=["partition inventory by owning namespace"],
            review=review("JUSTIFIED"),
        )
        self.assertDecision(value, "continue-local-repair")

    def test_justified_without_concrete_boundary_evidence_stays_nonterminal(self):
        self.assertDecision(
            candidate(boundary_evidence=[], review=review("JUSTIFIED")),
            "gather-evidence",
        )

    def test_generic_boundary_evidence_is_rejected(self):
        with self.assertRaisesRegex(plan_blocking.BlockCandidateError, "specific"):
            plan_blocking.validate(candidate(boundary_evidence=["generic"]))

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

    def test_continue_first_signal_matrix_stays_nonterminal_at_acceptance_scope(self):
        signal_classes = (
            "procedural",
            "transient",
            "dependency-not-ready",
            "unrelated-pre-existing",
            "routing-rejection",
            "tool-noise",
            "local-reversible",
        )
        for signal_class in signal_classes:
            with self.subTest(signal_class=signal_class):
                value = candidate(
                    signal_class=signal_class,
                    scope_class="acceptance",
                    review=review(),
                )
                self.assertDecision(value, "continue-local-repair")

    def test_only_justified_material_candidate_allows_terminal_block(self):
        self.assertDecision(candidate(review=review()), "terminal-block", terminal=True)

    def test_verified_external_candidate_can_reach_terminal_gate(self):
        value = candidate(
            external=True,
            scope_class="external",
            signal_class="external-dependency",
            rag={"required": True, "status": "verified", "evidence_ids": [PERPLEXITY_EVIDENCE_ID]},
            review=review(),
        )
        self.assertDecision(value, "terminal-block", terminal=True)

    def test_closed_schema_validator_rejects_unknown_field(self):
        with self.assertRaisesRegex(plan_blocking.BlockCandidateError, "unknown fields"):
            plan_blocking.validate(candidate(extra=True))

    def test_malformed_candidate_fails_closed_to_nonterminal_repair(self):
        self.assertDecision(candidate(extra=True), "repair-candidate")

    def test_verified_rag_rejects_fallback_or_unqualified_evidence(self):
        for evidence_id in ("fallback:web:result", "rag:perplexity:sha256:example"):
            value = candidate(
                external=True,
                scope_class="external",
                signal_class="external-dependency",
                rag={"required": True, "status": "verified", "evidence_ids": [evidence_id]},
                review=review(),
            )
            self.assertDecision(value, "gather-rag")

    def test_external_not_required_claim_routes_to_rag_pending(self):
        value = candidate(
            external=True,
            scope_class="external",
            signal_class="external-dependency",
            rag={"required": True, "status": "not-required", "evidence_ids": []},
            review=review(),
        )
        self.assertDecision(value, "gather-rag")

    def test_external_enum_cannot_bypass_rag_with_false_flag(self):
        external_classes = (
            {"scope_class": "external"},
            {"signal_class": "external-dependency"},
            {"scope_class": "external", "signal_class": "external-dependency"},
        )
        for classes in external_classes:
            with self.subTest(classes=classes):
                value = candidate(
                    **classes,
                    external=False,
                    rag={"required": False, "status": "not-required", "evidence_ids": []},
                    review=review(),
                )
                self.assertDecision(value, "gather-rag")

    def test_external_rag_states_remain_nonterminal_until_verified(self):
        for status in ("missing", "pending", "unavailable", "fallback-only"):
            with self.subTest(status=status):
                value = candidate(
                    external=True,
                    scope_class="external",
                    signal_class="external-dependency",
                    rag={
                        "required": True,
                        "status": status,
                        "evidence_ids": (["fallback:web:result"]
                                         if status == "fallback-only" else []),
                    },
                    review=review(),
                )
                self.assertDecision(value, "gather-rag")

    def test_reducer_matrix_has_exact_nonterminal_outcome(self):
        rag_states = ("missing", "pending", "unavailable", "fallback-only", "verified")
        verdicts = (None, "JUSTIFIED", "AVOIDABLE", "INSUFFICIENT_EVIDENCE",
                    "OUT_OF_SCOPE", "MALFORMED")
        for status, verdict in itertools.product(rag_states, verdicts):
            with self.subTest(status=status, verdict=verdict):
                value = candidate(
                    external=True,
                    scope_class="external",
                    signal_class="external-dependency",
                    rag={
                        "required": True,
                        "status": status,
                        "evidence_ids": (
                            [PERPLEXITY_EVIDENCE_ID] if status == "verified"
                            else ["fallback:web:result"] if status == "fallback-only"
                            else []
                        ),
                    },
                    review=review(verdict) if verdict else None,
                )
                decision = plan_blocking.evaluate(value)
                if status != "verified":
                    expected = "gather-rag"
                elif verdict is None:
                    expected = "request-isolated-review"
                elif verdict == "JUSTIFIED":
                    expected = "terminal-block"
                elif verdict == "AVOIDABLE":
                    expected = "continue-local-repair"
                elif verdict == "INSUFFICIENT_EVIDENCE":
                    expected = "gather-evidence"
                else:
                    expected = "repair-candidate"
                self.assertEqual(decision["action"], expected)
                self.assertEqual(decision["reason_code"],
                                 plan_blocking.ACTION_REASON_CODES[expected])
                self.assertEqual(decision["journal_result"],
                                 plan_blocking.ACTION_OBSERVATION_RESULTS[expected])
                self.assertEqual(decision["terminal_allowed"], expected == "terminal-block")

    def test_every_observation_result_is_a_nonterminal_journal_enum(self):
        observations = {
            value for value in plan_blocking.ACTION_OBSERVATION_RESULTS.values() if value
        }
        self.assertLessEqual(observations, set(journal.RESULT_VALUES))
        self.assertTrue(observations.isdisjoint(journal.TERMINAL_CLOSE_RESULTS))

    def test_json_schema_parses_and_names_all_rag_states(self):
        schema_path = (
            Path(plan_blocking.__file__).resolve().parents[2]
            / "configs" / "block-candidate-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        statuses = schema["properties"]["rag"]["properties"]["status"]["enum"]
        self.assertEqual(statuses, [
            "not-required", "missing", "pending", "unavailable", "fallback-only", "verified",
        ])
        external_guard = schema["allOf"][0]
        self.assertEqual(external_guard["then"]["properties"]["external"], {"const": True})
        self.assertEqual(external_guard["if"]["anyOf"], [
            {"properties": {"scope_class": {"const": "external"}}},
            {"properties": {"signal_class": {"const": "external-dependency"}}},
        ])


if __name__ == "__main__":
    unittest.main()
