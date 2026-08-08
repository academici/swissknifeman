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
import re
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
from task import task_contract  # noqa: E402
from core.repo import resolve_plan_dir  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_ROOT = resolve_plan_dir(REPO_ROOT, "2026.07.24-AGENT-RELIABILITY")
EXAMPLES_PATH = PLAN_ROOT / "artifacts/P0.2/task-contract-examples.json"
ARTIFEX_PLAN_ROOT = REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR"


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

    def test_unresolved_actual_route_blocks_as_route_undershoot_not_crash(self):
        # D74/D78 root: `_rank(MODEL_CLASS_ORDER, None)` used to raise
        # `ValueError: tuple.index(x): x not in tuple` instead of a typed code.
        base = _load_base_contract()
        base["route"]["actual"]["model_class"] = None
        base["route"]["actual"]["effort"] = None
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "ROUTE_UNDERSHOOT")

    def test_out_of_ladder_required_model_class_blocks_as_route_undershoot_not_crash(self):
        # D78 М4: an unresolved §3 Routing cell used to fabricate `required = ""` and
        # crash `_rank`; `pre_mutation` now guards the required side too, defensively,
        # for any contract fed to `check` regardless of how it was produced.
        base = _load_base_contract()
        base["route"]["required"]["model_class"] = ""
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "ROUTE_UNDERSHOOT")

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


class AuthorityCarrierBuildTests(unittest.TestCase):
    """TASK-AUTHORITY-CARRIER-01: build-time provenance is plan-native, never kwargs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        decision_rows = self._decision_rows(
            "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
            "branch=`go-branch`; scope=`finite-scope`; "
            "owner-message=`brief/00-brief.md#grant-g-test` | test |")
        plan_md = fixtures.plan_md("DEMO-AUTH", decision_log_rows=decision_rows).replace(
            "## 3. Routing\n\n", "## 3. Routing" + _routing_row())
        self.plan_dir = fixtures.write_valid_plan(self.root, "DEMO-AUTH")
        (self.plan_dir / "plan.md").write_text(plan_md, encoding="utf-8")
        (self.plan_dir / "brief" / "00-brief.md").write_text(
            "# Owner message\n\n"
            "[REPOSITORY-OWNER-MESSAGE:grant-g-test] [OWNER-GRANT:G-TEST] "
            "branch=`go-branch`; scope=`finite-scope`; provenance=`repository-owner`\n",
            encoding="utf-8")
        phase_path = self.plan_dir / "phases" / "P1.md"
        phase_path.write_text(
            fixtures.phase_md().replace(
                "**Required Reads:** 1) lib/pkg/config.py",
                "**Required Reads:** 1) `lib/pkg/config.py`").replace(
                "**Implementation Rules:** stdlib-only.",
                "**Implementation Rules:** [OWNER-GRANT:G-TEST] protects this transition."),
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _actual_route(self):
        from task import route_evidence
        return route_evidence.capture_actual("implementation", "medium",
                                             source="self-attested", ts="t", model="test")

    def _protected(self, **overrides):
        request = {"gate_id": "G-TEST", "branch": "go-branch", "scope": "finite-scope"}
        request.update(overrides)
        return task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route(),
                                   protected_transition=request)

    @staticmethod
    def _decision_rows(*tail, prefix_count=64):
        """A checked D1…Dn Decision Log; tail cases mutate only its final carrier."""
        prefix = [f"| D{number} | 2026-08-03 | ordinary decision {number} | test |"
                  for number in range(1, prefix_count + 1)]
        return "\n".join([*prefix, *tail])

    def _replace_decision_rows(self, rows):
        plan = fixtures.plan_md("DEMO-AUTH", decision_log_rows=rows).replace(
            "## 3. Routing\n\n", "## 3. Routing" + _routing_row())
        (self.plan_dir / "plan.md").write_text(plan, encoding="utf-8")

    def test_routine_authority_uses_the_current_item_carrier(self):
        contract = task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())
        self.assertEqual(contract["authority"]["class"], "routine")
        self.assertTrue(contract["authority"]["granted"])
        self.assertEqual(contract["authority"]["granted_by"], "phases/P1.md:P1.1")
        self.assertEqual(task_contract.evaluate(contract)["pre_mutation"], "allow")

    def test_exact_matching_owner_grant_allows_the_protected_transition(self):
        contract = self._protected()
        self.assertEqual(contract["authority"]["class"], "owner-gate")
        self.assertTrue(contract["authority"]["granted"])
        self.assertIn("[OWNER-GRANT:G-TEST]", contract["authority"]["granted_by"])
        self.assertEqual(task_contract.evaluate(contract)["pre_mutation"], "allow")

    def test_missing_forged_wrong_scope_and_revoked_grants_fail_closed(self):
        cases = {
            "missing": self._decision_rows("| D65 | 2026-08-03 | another decision | test |"),
            "synthetic-d999-with-valid-owner-message": self._decision_rows(
                "| D999 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |"),
            "duplicate-old-d50-with-valid-owner-message": self._decision_rows(
                "| D65 | 2026-08-03 | ordinary decision 65 | test |",
                "| D50 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |"),
            "wrong-gate": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-OTHER] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |"),
            "branch-superstring": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch-extra`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |"),
            "scope-superstring": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope-extra`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |"),
            "wrong-owner-message-reference": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#unknown` | test |"),
            "ambiguous-two-exact-grants": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |",
                "| D66 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |"),
            "ambiguous-malformed-duplicate": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |",
                "| D66 | 2026-08-03 | [OWNER-GRANT:G-TEST] malformed | test |"),
            "revoked": self._decision_rows(
                "| D65 | 2026-08-03 | [OWNER-GRANT:G-TEST] "
                "branch=`go-branch`; scope=`finite-scope`; "
                "owner-message=`brief/00-brief.md#grant-g-test` | test |",
                "| D66 | 2026-08-03 | [OWNER-REVOKE:G-TEST] | test |"),
        }
        for name, rows in cases.items():
            with self.subTest(case=name):
                self._replace_decision_rows(rows)
                self.assertEqual(task_contract.evaluate(self._protected())["pre_mutation"],
                                 "block:AUTHORITY_BOUNDARY")

    def test_explicit_owner_message_not_approval_owner_identity_allows(self):
        plan = (self.plan_dir / "plan.md").read_text(encoding="utf-8").replace(
            "| Approval Owner | dv |", "| Approval Owner | copied-display-name |")
        (self.plan_dir / "plan.md").write_text(plan, encoding="utf-8")
        self.assertEqual(task_contract.evaluate(self._protected())["pre_mutation"], "allow")

    def test_legacy_manual_authority_kwargs_are_refused_by_the_api(self):
        with self.assertRaises(TypeError):
            task_contract.build(self.plan_dir, "P1.1", authority_granted_by="D50 (foreign)")


@unittest.skipUnless(ARTIFEX_PLAN_ROOT.is_dir(), "Artifex plan is not present in this checkout")
class ArtifexOrdinaryAuthorityRegressionTests(unittest.TestCase):
    """The prerequisite's ordinary-path proof: every current Artifex item stays runnable."""

    def test_all_current_unique_items_allow_without_foreign_d50_provenance(self):
        item_ids = []
        for phase_path in sorted((ARTIFEX_PLAN_ROOT / "phases").glob("P*.md")):
            item_ids.extend(re.findall(r"^###\s+(P\d+\.\d+)\b", phase_path.read_text(encoding="utf-8"), re.M))
        self.assertTrue(item_ids)
        self.assertEqual(len(item_ids), len(set(item_ids)))
        self.assertTrue({"P3.5", "P3.6", "P3.7", "P3.8"}.issubset(item_ids))
        from task import route_evidence
        for item_id in item_ids:
            with self.subTest(item=item_id):
                required = task_contract.build(ARTIFEX_PLAN_ROOT, item_id)["route"]["required"]
                actual = route_evidence.capture_actual(
                    required["model_class"], required["effort"], source="self-attested",
                    ts="t", model="regression")
                contract = task_contract.build(ARTIFEX_PLAN_ROOT, item_id, actual_route=actual)
                self.assertEqual(task_contract.evaluate(contract), {
                    "pre_mutation": "allow", "pre_final": "allow",
                    "content_hash": task_contract.content_hash(contract)})
                self.assertNotIn("D50", contract["authority"]["granted_by"])


class AuthorityCommandBoundaryTests(unittest.TestCase):
    """Both write-sites consume the compiler; plan-run inherits rather than forks it."""

    def test_plan_exec_boundaries_and_plan_run_share_the_checked_compiler(self):
        exec_text = (REPO_ROOT / "packages/task/commands/plan-exec.md").read_text(encoding="utf-8")
        run_text = (REPO_ROOT / "packages/task/commands/plan-run.md").read_text(encoding="utf-8")
        self.assertEqual(exec_text.count("task_contract.build("), 2)
        self.assertNotIn("authority_granted", exec_text)
        self.assertNotIn("authority_granted_by", exec_text)
        self.assertIn("Прочти `packages/task/commands/plan-exec.md` ЦЕЛИКОМ", run_text)


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


class EvaluateFindingHookTests(unittest.TestCase):
    """`evaluate_finding` (P2.3) — the ONE new call-site this compiler gains for
    `task.review_policy`, lazily imported so the predicate tests above never need
    it importable. Behavioural coverage of the policy itself lives in
    `test_review_policy.py`; this class only proves the hook actually delegates."""

    def test_delegates_to_review_policy_review_transition(self):
        finding = {
            "type": "product", "severity": "major", "file": "f.py",
            "rule_or_contract_locus": "rule:1", "defect_class": "bug",
        }
        result = task_contract.evaluate_finding("VERIFYING", finding, profile="self-host")
        self.assertEqual(result["decision"], "retry-fix")
        self.assertEqual(result["to_state"], "FIXING")

    def test_shared_budget_across_calls_reaches_the_cap(self):
        from task.review_policy import LoopBudget
        budget = LoopBudget()
        finding = {
            "type": "product", "severity": "major", "file": "f.py",
            "rule_or_contract_locus": "rule:1", "defect_class": "bug",
        }
        decisions = [task_contract.evaluate_finding("VERIFYING", finding, budget=budget,
                                                     profile="owner-gated")["decision"]
                    for _ in range(3)]
        self.assertEqual(decisions, ["retry-fix", "retry-fix", "incident"])


class BuildSelfConformanceTests(unittest.TestCase):
    """P2.6 F1 — `build()` self-conformance over REAL, already-closed items of
    this same plan: P2.1 (a terminal P2 item), P2.6 (this item, live), and
    P0.1 (a terminal P0 item) — Implementation Rules' own anti-self-deception
    requirement (не только собранный самим item свежий кейс)."""

    def test_builds_over_three_real_items_with_nonempty_required_arrays(self):
        for item_id in ("P0.1", "P2.1", "P2.6"):
            with self.subTest(item=item_id):
                contract = task_contract.build(PLAN_ROOT, item_id)
                self.assertGreaterEqual(len(contract["must"]), 1)
                self.assertGreaterEqual(len(contract["never"]), 1)
                self.assertGreaterEqual(len(contract["evidence"]), 1)
                self.assertGreaterEqual(len(contract["done"]["public_acceptance"]), 1)
                self.assertEqual(contract["version"]["content_hash"],
                                task_contract.content_hash(contract))

    def test_build_is_byte_deterministic_across_two_calls(self):
        first = json.dumps(task_contract.build(PLAN_ROOT, "P2.6"), sort_keys=True)
        second = json.dumps(task_contract.build(PLAN_ROOT, "P2.6"), sort_keys=True)
        self.assertEqual(first, second)

    def test_default_actual_route_is_unresolved_and_dispatch_guard_denies_it(self):
        from task import route_evidence as re_
        contract = task_contract.build(PLAN_ROOT, "P2.6")
        required, actual = contract["route"]["required"], contract["route"]["actual"]
        self.assertIsNone(actual["model_class"])
        self.assertEqual(re_.dispatch_guard(required, actual, contract["route"]["capabilities"]),
                         "ROUTE_UNDERSHOOT")

    def test_live_actual_route_matching_required_allows_both_predicates(self):
        from task import route_evidence as re_
        for item_id in ("P0.1", "P2.1", "P2.6"):
            with self.subTest(item=item_id):
                contract = task_contract.build(PLAN_ROOT, item_id)
                required = contract["route"]["required"]
                actual = re_.capture_actual(required["model_class"], required["effort"],
                                           source="self-attested", ts="t", model="sonnet")
                caps = re_.capability_support(["command.subagents"], {"command.subagents": "native"})
                contract["route"] = re_.build_task_contract_route(required, actual, caps)
                contract["version"]["content_hash"] = task_contract.content_hash(contract)
                self.assertIsNone(task_contract.pre_mutation(contract))
                self.assertIsNone(task_contract.pre_final(contract))

    def test_unknown_item_id_fails_closed(self):
        with self.assertRaises(task_contract.TaskContractBuildError):
            task_contract.build(PLAN_ROOT, "P2.999")


def _routing_row(model_effort="implementation/medium"):
    return (f"\n\n| Items | Model class/effort | Exec | Почему |\n"
           f"|:--|:--|:--|:--|\n"
           f"| P1.1 | {model_effort} | plan-exec | test |\n")


class BuildFixtureTests(unittest.TestCase):
    """Synthetic minimal plan (fixtures.py) — proves the negative anti-padding
    path Implementation Rules (2) demands directly, without depending on this
    plan's own (always-populated) fields ever going empty by accident."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        plan_md = fixtures.plan_md("DEMO-1").replace("## 3. Routing\n\n", "## 3. Routing" + _routing_row())
        self.plan_dir = fixtures.write_valid_plan(self.root, "DEMO-1")
        (self.plan_dir / "plan.md").write_text(plan_md, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_minimal_valid_item_builds_successfully(self):
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(len(contract["must"]), 1)
        self.assertEqual(len(contract["never"]), 1)
        self.assertEqual(contract["route"]["required"],
                         {"model_class": "implementation", "effort": "medium"})

    def test_v2_phase_carrier_builds_through_layout_resolver(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = fixtures.write_valid_plan(Path(tmp), "DEMO-V2", layout="v2")
            text = (plan / "plan.md").read_text(encoding="utf-8").replace(
                "## 3. Routing\n\n", "## 3. Routing" + _routing_row())
            (plan / "plan.md").write_text(text, encoding="utf-8")
            contract = task_contract.build(plan, "P1.1")
            self.assertEqual(contract["route"]["required"],
                             {"model_class": "implementation", "effort": "medium"})

    def test_empty_validation_field_refuses_to_fabricate_an_acceptance_entry(self):
        phase_path = self.plan_dir / "phases" / "P1.md"
        phase_path.write_text(
            fixtures.phase_md().replace(
                "**Validation:** bash scripts/test.sh — зелёный.", "**Validation:** —"),
            encoding="utf-8")
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Validation")
        self.assertEqual(ctx.exception.item_id, "P1.1")

    def test_missing_routing_row_fails_closed(self):
        # fixtures.plan_md() leaves §3 Routing empty; P1.1's default row was added in
        # setUp only for THIS plan.md, so an item absent from it (P1.2) has no row.
        (self.plan_dir / "phases" / "P1.md").write_text(
            fixtures.phase_md(item_id="P1.2"), encoding="utf-8")
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.2")
        self.assertEqual(ctx.exception.field, "Routing")

    def test_routing_range_row_matches_an_item_inside_the_range(self):
        plan_md = fixtures.plan_md("DEMO-1").replace(
            "## 3. Routing\n\n", "## 3. Routing" + _routing_row("frontier/high").replace(
                "P1.1", "P1.1–P1.3"))
        (self.plan_dir / "plan.md").write_text(plan_md, encoding="utf-8")
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(contract["route"]["required"],
                         {"model_class": "frontier", "effort": "high"})


def _routing_row_with_header(header, model_effort="implementation/medium", items="P1.1"):
    return (f"\n\n| Items | {header} | Exec | Почему |\n"
           f"|:--|:--|:--|:--|\n"
           f"| {items} | {model_effort} | plan-exec | test |\n")


class RoutingFormTests(unittest.TestCase):
    """P2.10/D78 — §3 Routing form coverage: closed legacy header set, provider model
    names resolved through the committed carrier, and every unparseable/ambiguous form
    fails TYPED, never with an unhandled exception. Each negative case here reproduces
    a shape `findings/14` M4/M4.1 measured live on the fleet."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plan_dir = fixtures.write_valid_plan(self.root, "DEMO-1")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_plan(self, table_text):
        plan_md = fixtures.plan_md("DEMO-1").replace("## 3. Routing\n\n", "## 3. Routing" + table_text)
        (self.plan_dir / "plan.md").write_text(plan_md, encoding="utf-8")

    def test_legacy_header_model_effort_is_recognized(self):
        self._write_plan(_routing_row_with_header("Model/effort", "implementation/high"))
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(contract["route"]["required"],
                         {"model_class": "implementation", "effort": "high"})

    def test_legacy_header_model_effort_capitalized_is_recognized(self):
        self._write_plan(_routing_row_with_header("Model/Effort", "economy/low"))
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(contract["route"]["required"],
                         {"model_class": "economy", "effort": "low"})

    def test_unrecognized_header_fails_closed_not_silently_empty(self):
        # `findings/14` M4.1: this exact composite header appears live on the fleet and
        # is NOT in the closed set (Scope Excluded) — must stay a typed refusal, never
        # a fabricated empty `required` (D78 M4).
        self._write_plan(_routing_row_with_header("Model/effort И/ИЛИ Tool Capability",
                                                   "implementation/high"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")

    def test_provider_model_name_maps_to_class_via_committed_carrier(self):
        # FOREMAN §3 form: a concrete provider model name, not a class.
        self._write_plan(_routing_row_with_header("Model/effort", "opus/high"))
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(contract["route"]["required"],
                         {"model_class": "frontier", "effort": "high"})

    def test_unknown_model_name_fails_closed(self):
        self._write_plan(_routing_row_with_header("Model/effort", "gpt-9-nonexistent/high"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")

    def test_prose_tail_in_cell_fails_closed(self):
        self._write_plan(_routing_row_with_header(
            "Model class/effort", "sonnet/medium (экстракция fan-out)"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")

    def test_cell_without_slash_fails_closed(self):
        self._write_plan(_routing_row_with_header("Model class/effort", "fable ИЛИ opus"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")

    def test_no_section_at_all_fails_closed(self):
        plan_md = fixtures.plan_md("DEMO-1").replace("## 3. Routing\n\n", "")
        (self.plan_dir / "plan.md").write_text(plan_md, encoding="utf-8")
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")

    def _write_phase_item(self, item_id):
        # `build()` parses the phase item BEFORE §3 Routing, so an item_id absent from
        # phases/P1.md would refuse on field `item` and never reach the branch under test.
        (self.plan_dir / "phases" / "P1.md").write_text(
            fixtures.phase_md(item_id=item_id), encoding="utf-8")

    def _assert_comma_list_diagnostic(self, message, cell, item_id):
        self.assertIn("comma list", message)
        self.assertIn(cell, message)                       # the offending cell, verbatim
        self.assertIsNotNone(re.search(r"\(line \d+\)", message))  # its line in plan.md
        self.assertIn(f"'{item_id}'", message)             # legal form 1 — a single item
        self.assertIn("P1.a–P1.b", message)                # legal form 2 — single-phase range
        self.assertIn("Batch", message)                    # where the group actually belongs

    def test_comma_list_cell_refuses_with_a_diagnostic_naming_the_cell(self):
        # P8.10/D124, `research/25` §1: this shape blocked 7 live fleet items behind a blind
        # `no §3 Routing row found`. The refusal STAYS a refusal (the list never becomes a
        # legal form through the back door) — only its text learns to name the fix.
        self._write_plan(_routing_row_with_header("Model class/effort", items="P1.1, P1.2"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")
        self.assertEqual(ctx.exception.item_id, "P1.1")
        self._assert_comma_list_diagnostic(str(ctx.exception), "P1.1, P1.2", "P1.1")

    def test_comma_list_diagnostic_is_symmetric_across_tokens(self):
        # The second token of the same cell must diagnose identically — the blocked FOREMAN
        # items sit in every position of the list, not only the first.
        self._write_phase_item("P1.2")
        self._write_plan(_routing_row_with_header("Model class/effort", items="P1.1, P1.2"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.2")
        self.assertEqual(ctx.exception.field, "Routing")
        self._assert_comma_list_diagnostic(str(ctx.exception), "P1.1, P1.2", "P1.2")

    def test_mixed_range_and_list_cell_is_diagnosed_too(self):
        # The live `2026.07.18-FOREMAN` shape (`P4.1–P4.2, P4.4`): a range AND a list in one
        # cell — the matched token here is covered by neither способ of the two matchers.
        self._write_phase_item("P1.4")
        self._write_plan(_routing_row_with_header("Model class/effort", items="P1.1–P1.2, P1.4"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.4")
        self.assertEqual(ctx.exception.field, "Routing")
        self._assert_comma_list_diagnostic(str(ctx.exception), "P1.1–P1.2, P1.4", "P1.4")

    def test_absent_row_keeps_the_previous_blind_text(self):
        # Anti-regress (Implementation Rules): a cell with neither a comma nor a matching
        # token is «строки действительно нет» — the diagnostic must NOT claim a comma list.
        self._write_plan(_routing_row_with_header("Model class/effort", items="P1.3"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")
        self.assertIn("no §3 Routing row found for this item", str(ctx.exception))
        self.assertNotIn("comma list", str(ctx.exception))

    def test_ambiguous_model_name_across_two_classes_fails_closed(self):
        self._write_plan(_routing_row_with_header("Model/effort", "shared-name/high"))
        routing_config = self.root / "ambiguous-command-routing.json"
        routing_config.write_text(json.dumps({
            "contract_version": "1.0.0", "catalog_version": "1.0.0", "plugin_version": "0.1.0",
            "commands": [],
            "mappings": {
                "fake-a": {"class_selectors": {"economy": ["shared-name"]}},
                "fake-b": {"class_selectors": {"frontier": ["shared-name"]}},
            },
        }), encoding="utf-8")
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1", routing_config_path=routing_config)
        self.assertEqual(ctx.exception.field, "Routing")


class BundleLintTests(unittest.TestCase):
    """P2.6 F2/F4 — `bundle_lint` COMPUTES minimization/content-class evidence
    from actual bundle bytes instead of trusting a self-declared block."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bundle_dir = Path(self._tmp.name)
        self.manifest_path = self.bundle_dir / "manifest.json"
        self.verifier_path = self.bundle_dir / "verify.py"
        self.verifier_path.write_text("# stdlib-only verifier stub\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_manifest(self, files):
        self.manifest_path.write_text(json.dumps({"files": files}), encoding="utf-8")

    def test_missing_manifest_fails_closed(self):
        (self.bundle_dir / "a.txt").write_text("clean", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(self.bundle_dir, manifest_path=self.manifest_path,
                                      verifier_path=self.verifier_path,
                                      declared_privacy={"minimized": True, "excluded_classes": []}),
            task_contract.BUNDLE_ARTIFACT_MISSING)

    def test_missing_verifier_fails_closed(self):
        self._write_manifest(["a.txt"])
        (self.bundle_dir / "a.txt").write_text("clean", encoding="utf-8")
        self.verifier_path.unlink()
        self.assertEqual(
            task_contract.bundle_lint(self.bundle_dir, manifest_path=self.manifest_path,
                                      verifier_path=self.verifier_path,
                                      declared_privacy={"minimized": True, "excluded_classes": []}),
            task_contract.BUNDLE_ARTIFACT_MISSING)

    def test_clean_bundle_matching_declaration_allows(self):
        self._write_manifest(["a.txt"])
        (self.bundle_dir / "a.txt").write_text("clean committed content", encoding="utf-8")
        self.assertIsNone(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy={"minimized": True, "excluded_classes": ["secrets"]}))

    def test_extra_undeclared_file_breaks_minimization(self):
        self._write_manifest(["a.txt"])
        (self.bundle_dir / "a.txt").write_text("clean", encoding="utf-8")
        (self.bundle_dir / "extra.txt").write_text("undeclared", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(self.bundle_dir, manifest_path=self.manifest_path,
                                      verifier_path=self.verifier_path,
                                      declared_privacy={"minimized": True, "excluded_classes": []}),
            task_contract.BUNDLE_PRIVACY_MISMATCH)

    def test_secret_signature_found_despite_declared_exclusion(self):
        self._write_manifest(["creds.txt"])
        (self.bundle_dir / "creds.txt").write_text(
            "aws_secret_key: \"AKIAABCDEFGHIJKLMNOP\"", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(
                self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
                declared_privacy={"minimized": True, "excluded_classes": ["secrets"]}),
            task_contract.BUNDLE_PRIVACY_MISMATCH)

    def test_raw_transcript_body_needs_repeated_turn_markers_not_one_stray_line(self):
        self._write_manifest(["note.md"])
        (self.bundle_dir / "note.md").write_text(
            "See the incident where Human: reported the bug once.", encoding="utf-8")
        # One stray "Human:"-shaped line is not a transcript (false-positive guard).
        self.assertIsNone(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy={"minimized": True, "excluded_classes": ["raw-transcript-bodies"]}))

    def test_repeated_turn_markers_are_flagged_as_raw_transcript_bodies(self):
        self._write_manifest(["rollout.txt"])
        (self.bundle_dir / "rollout.txt").write_text(
            "Human: hi\nAssistant: hello\nHuman: again\nAssistant: sure\n", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(
                self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
                declared_privacy={"minimized": True, "excluded_classes": ["raw-transcript-bodies"]}),
            task_contract.BUNDLE_PRIVACY_MISMATCH)

    def test_undeclared_class_present_is_not_flagged(self):
        # The declaration only asserts what it claims excluded; a class present
        # but never claimed excluded is not this predicate's concern (it only
        # verifies the declared claims are true, never invents a stricter one).
        self._write_manifest(["rollout.txt"])
        (self.bundle_dir / "rollout.txt").write_text(
            "Human: hi\nAssistant: hello\nHuman: again\nAssistant: sure\n", encoding="utf-8")
        self.assertIsNone(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy={"minimized": True, "excluded_classes": []}))


if __name__ == "__main__":
    unittest.main()
