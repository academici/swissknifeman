"""Tests for `task.task_contract` — the P2.2 Task Contract v1 compiler.

Exercises every one of the twelve pre-mutation and three pre-final reason codes declared
by the frozen `root/contracts/task-contract-v1.md` (P0.2), plus the portability tier
classification/lint layer added by `plan-portability-v1.md` (P2.1,
`PORTABILITY_TIER_MISCLASSIFIED`). A base contract is copied from the committed P0.2
example (`artifacts/P0.2/task-contract-examples.json` example `routine-continuation`) so
every mutation starts from a schema-valid, allow/allow baseline — one mutated field per
test, never a hand-authored contract that could silently satisfy the wrong branch.
"""
import copy
import json
import unittest
from pathlib import Path

import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
from task import task_contract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_PATH = (REPO_ROOT / "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.2/"
                 "task-contract-examples.json")


def _load_base_contract():
    document = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    for example in document["examples"]:
        if example["id"] == "routine-continuation":
            return copy.deepcopy(example["contract"])
    raise AssertionError("fixture example 'routine-continuation' not found")


def _rehashed(contract):
    """Deep-copy `contract`, recompute and install a matching content_hash — the
    discipline every structural mutation test follows so it never accidentally also
    trips VERSION_HASH_MISMATCH."""
    mutated = copy.deepcopy(contract)
    mutated["version"]["content_hash"] = task_contract.content_hash(mutated)
    return mutated


class ContentHashTests(unittest.TestCase):
    def test_base_fixture_hash_matches_as_committed(self):
        base = _load_base_contract()
        self.assertEqual(base["version"]["content_hash"], task_contract.content_hash(base))

    def test_mismatched_hash_blocks(self):
        base = _load_base_contract()
        base["version"]["content_hash"] = "0" * 64
        self.assertEqual(task_contract.pre_mutation(base), "VERSION_HASH_MISMATCH")

    def test_hash_excludes_itself_from_the_payload(self):
        base = _load_base_contract()
        a = task_contract.content_hash(base)
        mutated = copy.deepcopy(base)
        mutated["version"]["content_hash"] = "f" * 64
        self.assertEqual(a, task_contract.content_hash(mutated))


class ConflictTests(unittest.TestCase):
    def test_unresolved_conflict_blocks(self):
        base = _load_base_contract()
        base["conflicts"] = [{
            "id": "C1",
            "winner": {"ref": "owner said X", "carrier_class": "owner-instruction"},
            "loser": {"ref": "handoff said Y", "carrier_class": "handoff-carrier"},
            "rule": "latest-owner-instruction-in-scope",
            "resolution": "unknown",
            "question": "which one governs?",
        }]
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "CONFLICT_UNRESOLVED")

    def test_precedence_violation_blocks(self):
        base = _load_base_contract()
        base["conflicts"] = [{
            "id": "C1",
            "winner": {"ref": "item scope", "carrier_class": "item-spec"},
            "loser": {"ref": "plan decision", "carrier_class": "plan-decision"},
            "rule": "frozen-contract-wins",
            "resolution": "resolved",
            "question": None,
        }]
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "CONFLICT_PRECEDENCE_VIOLATION")

    def test_resolved_conflict_with_correct_precedence_allows(self):
        base = _load_base_contract()
        base["conflicts"] = [{
            "id": "C1",
            "winner": {"ref": "plan decision", "carrier_class": "plan-decision"},
            "loser": {"ref": "item scope", "carrier_class": "item-spec"},
            "rule": "frozen-contract-wins",
            "resolution": "resolved",
            "question": None,
        }]
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))


class NextTransitionTests(unittest.TestCase):
    def test_diagnostic_origin_blocks(self):
        base = _load_base_contract()
        base["next"]["origin"] = "diagnostic"
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "NEXT_CHANGED_WITHOUT_TRANSITION")

    def test_typed_finding_without_changed_by_blocks(self):
        base = _load_base_contract()
        base["next"]["origin"] = "typed-finding"
        base["next"]["changed_by"] = None
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "NEXT_CHANGED_WITHOUT_TRANSITION")

    def test_typed_finding_with_changed_by_allows(self):
        base = _load_base_contract()
        base["next"]["origin"] = "typed-finding"
        base["next"]["changed_by"] = {"finding_id": "seam:x", "transition": "typed-finding"}
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))

    def test_approved_goal_with_changed_by_blocks(self):
        base = _load_base_contract()
        base["next"]["changed_by"] = {"finding_id": "seam:x", "transition": "typed-finding"}
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "NEXT_CHANGED_WITHOUT_TRANSITION")


class PortabilityTierTests(unittest.TestCase):
    """Table-driven over the exact five worked cases of
    `artifacts/P2.1/state-transition-cases.json::portability_cases` — the compiler and the
    sealed fixture must agree on every one."""

    CASES = (
        ({"sessions": "single", "risk": "low", "handoff": False, "audit": False},
         "brief-acceptance"),
        ({"sessions": "multi", "risk": "medium", "handoff": True, "audit": False},
         "committed-bundle"),
        ({"sessions": "single", "risk": "medium", "handoff": False, "audit": True},
         "committed-bundle"),
        ({"sessions": "single", "risk": "high", "handoff": False, "audit": False},
         "committed-bundle"),
        ({"sessions": "multi", "risk": "medium", "handoff": True, "audit": False},
         "committed-bundle"),
    )

    def test_classify_tier_matches_p2_1_fixture(self):
        for work, expected in self.CASES:
            with self.subTest(work=work):
                self.assertEqual(task_contract.classify_tier(work), expected)

    def test_misclassified_tier_blocks(self):
        base = _load_base_contract()
        base["portability"]["tier"] = "brief-acceptance"
        base["portability"]["execution_inputs"] = []
        contract = _rehashed(base)
        work = {"sessions": "multi", "risk": "medium", "handoff": True, "audit": False}
        self.assertEqual(task_contract.pre_mutation(contract, work=work),
                         "PORTABILITY_TIER_MISCLASSIFIED")

    def test_correctly_classified_tier_allows(self):
        base = _load_base_contract()
        contract = _rehashed(base)
        work = {"sessions": "multi", "risk": "medium", "handoff": True, "audit": False}
        self.assertIsNone(task_contract.pre_mutation(contract, work=work))

    def test_path_listed_as_both_input_and_provenance_blocks(self):
        base = _load_base_contract()
        dual = base["portability"]["execution_inputs"][0]["path"]
        base["portability"]["provenance_only"].append(dual)
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "PORTABILITY_TIER_MISCLASSIFIED")

    def test_committed_bundle_without_inputs_blocks(self):
        base = _load_base_contract()
        base["portability"]["execution_inputs"] = []
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "PORTABILITY_INPUT_MISSING")

    def test_predecessor_input_without_producer_blocks(self):
        base = _load_base_contract()
        base["portability"]["execution_inputs"].append(
            {"path": "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.2/base-sha.txt",
             "kind": "produced-by-predecessor", "producer": None})
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "PORTABILITY_INPUT_MISSING")

    def test_predecessor_input_with_producer_allows(self):
        base = _load_base_contract()
        base["portability"]["execution_inputs"].append(
            {"path": "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.2/base-sha.txt",
             "kind": "produced-by-predecessor", "producer": "P2.2 step 0"})
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))

    def test_external_execution_input_blocks(self):
        for external in ("/etc/passwd", "~/.codex/session.json", "tmp/scratch.md",
                         "https://example.com/x", "plans/../secrets.json"):
            with self.subTest(path=external):
                base = _load_base_contract()
                base["portability"]["execution_inputs"].append(
                    {"path": external, "kind": "committed", "producer": None})
                contract = _rehashed(base)
                self.assertEqual(task_contract.pre_mutation(contract),
                                 "PORTABILITY_EXTERNAL_INPUT")

    def test_committed_path_containing_tmp_in_a_directory_name_is_not_flagged_by_spelling(self):
        """D47: the role rule, not a substring match — a genuinely committed, repo-relative
        path is not external merely because a directory NAME contains `tmp` without being
        `tmp/`-rooted."""
        base = _load_base_contract()
        base["portability"]["execution_inputs"].append(
            {"path": "packages/task/tests/fixtures_data/tmp-named-fixture.json",
             "kind": "committed", "producer": None})
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))


class RouteAndCapabilityTests(unittest.TestCase):
    def test_route_undershoot_model_class_blocks(self):
        base = _load_base_contract()
        base["route"]["actual"]["model_class"] = "implementation"
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "ROUTE_UNDERSHOOT")

    def test_route_undershoot_effort_blocks(self):
        base = _load_base_contract()
        base["route"]["actual"]["effort"] = "medium"
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "ROUTE_UNDERSHOOT")

    def test_route_overshoot_allows(self):
        base = _load_base_contract()
        base["route"]["required"]["model_class"] = "implementation"
        base["route"]["required"]["effort"] = "medium"
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))

    def test_unsupported_capability_blocks(self):
        base = _load_base_contract()
        base["route"]["capabilities"].append({"id": "command.interactive-user-input",
                                              "support": "unsupported"})
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "CAPABILITY_UNSUPPORTED")

    def test_unknown_capability_support_blocks(self):
        base = _load_base_contract()
        base["route"]["capabilities"].append({"id": "command.interactive-user-input",
                                              "support": "unknown"})
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "CAPABILITY_UNSUPPORTED")


class AuthorityTests(unittest.TestCase):
    def test_loop_budget_exceeded_blocks(self):
        base = _load_base_contract()
        base["authority"]["observed_rounds"] = 3
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "LOOP_BUDGET_EXCEEDED")

    def test_ungranted_owner_gate_blocks(self):
        base = _load_base_contract()
        base["authority"]["class"] = "owner-gate"
        base["authority"]["granted"] = False
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "AUTHORITY_BOUNDARY")

    def test_granted_owner_gate_allows(self):
        base = _load_base_contract()
        base["authority"]["class"] = "owner-gate"
        base["authority"]["granted"] = True
        base["authority"]["granted_by"] = "owner replied 2026-07-26"
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))


class SliceTests(unittest.TestCase):
    def test_missing_key_blocks(self):
        base = _load_base_contract()
        base["slice"]["root_only_keys"].remove("conflicts")
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "SLICE_INCOMPLETE")

    def test_overlapping_keys_block(self):
        base = _load_base_contract()
        base["slice"]["subagent_keys"].append("evidence")
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "SLICE_INCOMPLETE")

    def test_extra_unknown_key_blocks(self):
        base = _load_base_contract()
        base["slice"]["root_only_keys"].append("not-a-real-key")
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "SLICE_INCOMPLETE")


class ColdStartTests(unittest.TestCase):
    def test_unknown_evidence_reference_blocks(self):
        base = _load_base_contract()
        base["cold_start"]["reads"] = ["E99"]
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "COLD_START_INCOMPLETE")

    def test_carrier_mismatch_blocks(self):
        base = _load_base_contract()
        base["cold_start"]["carrier"] = "task:plan-exec 2026.07.24-AGENT-RELIABILITY P9.9"
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "COLD_START_INCOMPLETE")


class PreFinalTests(unittest.TestCase):
    def test_no_public_acceptance_blocks(self):
        base = _load_base_contract()
        base["done"]["public_acceptance"][0]["scope"] = "internal"
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))
        self.assertEqual(task_contract.pre_final(contract), "ACCEPTANCE_NOT_PUBLIC")

    def test_unknown_evidence_ref_blocks(self):
        base = _load_base_contract()
        base["done"]["public_acceptance"][0]["evidence_ref"] = "E99"
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_final(contract), "EVIDENCE_REF_UNKNOWN")

    def test_insufficient_proof_class_blocks(self):
        base = _load_base_contract()
        base["done"]["public_acceptance"][0]["evidence_ref"] = "E2"  # pinned-not-recomputable
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_final(contract), "EVIDENCE_PROOF_CLASS_INSUFFICIENT")

    def test_base_fixture_pre_final_allows(self):
        base = _load_base_contract()
        self.assertIsNone(task_contract.pre_final(base))


class EvaluateTests(unittest.TestCase):
    def test_base_fixture_evaluates_allow_allow(self):
        base = _load_base_contract()
        result = task_contract.evaluate(base)
        self.assertEqual(result["pre_mutation"], "allow")
        self.assertEqual(result["pre_final"], "allow")
        self.assertEqual(result["content_hash"], base["version"]["content_hash"])

    def test_blocked_pre_mutation_reports_pre_final_as_not_applicable(self):
        base = _load_base_contract()
        base["authority"]["observed_rounds"] = 99
        contract = _rehashed(base)
        result = task_contract.evaluate(contract)
        self.assertEqual(result["pre_mutation"], "block:LOOP_BUDGET_EXCEEDED")
        self.assertEqual(result["pre_final"], "n/a")


if __name__ == "__main__":
    unittest.main()
