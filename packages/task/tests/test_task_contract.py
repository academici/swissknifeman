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
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
from task import task_contract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_PATH = (REPO_ROOT / "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.2/"
                 "task-contract-examples.json")
PLAN_ROOT = REPO_ROOT / "plans/2026.07.24-AGENT-RELIABILITY"


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
