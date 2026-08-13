"""Tests for `task.review_policy` — the P2.3 typed finding/review enforcement and
loop breaker over `root/contracts/risk-review-loop-budget-v1.md` (P2.1, frozen).

Covers the reopen predicate, seam-derived finding identity (split-ban), the
authority-profile-parameterized cap subject, the `same_finding_max = 2` loop budget
across every state the frozen machine declares a `typed-finding`/`same-finding-third`
transition for (`execution-state-machine-v1.md`, `state-transition-cases.json`), and
the historical `five-audit-loop` corpus scenario end to end
(`artifacts/source-evidence/precomputed/corpus.json`).

Run: cd packages/task && python3 -m unittest discover -s tests
"""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import fixtures  # noqa: F401,E402 — package invocation from repository root
except ImportError:  # pragma: no cover - discovery from packages/task
    import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
from task import journal, plan_gates, review_policy  # noqa: E402
from task.review_policy import (  # noqa: E402
    AUTHORITY_PROFILES, CAP_SUBJECT_BY_PROFILE, SAME_FINDING_MAX, LoopBudget,
    ReviewPolicyError, cap_subject, finding_id, identity_of, reopens_product,
    review_transition, same_finding_third, validation_cadence, classify_signal,
    audit_fixer_action,
)


def _finding(**overrides):
    base = {
        "type": "process",
        "severity": "minor",
        "file": "packages/task/lib/task/plan_lint.py",
        "rule_or_contract_locus": "plan-portability-v1.md §Classification rule",
        "defect_class": "tier-misclassification",
        "invalidates_acceptance": False,
    }
    base.update(overrides)
    return base


class EvidenceFirstSignalTests(unittest.TestCase):
    def _candidate(self, *, statuses=("🟢 Done",), material_risks=(), files=("docs/x.md",)):
        return {
            "phase_id": "P1",
            "scope": [],
            "terminal_item_heads": [
                {"item_id": f"P1.{index}", "status": status}
                for index, status in enumerate(statuses, start=1)
            ],
            "material_risks": list(material_risks),
            "declared_files": list(files),
            "product_tree_sha256": "b" * 64,
        }

    def _plan_with_review(self, root, review, *, items="P1.1"):
        plan = Path(root) / "P"
        plan.mkdir()
        (plan / "plan.md").write_text(
            "## 3. Routing\n\n"
            "| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            f"| solo | {items} | implementation/high | manual | {review} | test |\n",
            encoding="utf-8",
        )
        return plan

    def test_phase_audit_policy_skips_separate_audit_for_low_risk_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan_with_review(tmp, "none")
            policy = plan_gates.phase_audit_policy(
                plan, "P1", candidate_snapshot=self._candidate())
            self.assertFalse(policy["audit_required"])
            self.assertEqual(policy["next_kind"], "close")
            self.assertEqual(policy["next_exact"], "close: task:plan-close P P1")

            snapshot = self._candidate()
            gate = plan_gates.phase_close_gate(
                plan, "P1",
                candidate_fingerprint=plan_gates._candidate_snapshot_fingerprint(snapshot),
                candidate_snapshot=snapshot)
            self.assertTrue(gate["allow"])
            self.assertEqual(gate["audit_policy"]["code"], "PHASE_DIRECT_CLOSE_LOW_RISK")

    def test_phase_audit_policy_uses_review_risk_and_phase_volume(self):
        cases = (
            ("full", ("🟢 Done",), (), True, "PHASE_AUDIT_REQUIRED_FULL_REVIEW"),
            ("light", ("🟢 Done",), (), False, "PHASE_DIRECT_CLOSE_LOW_RISK"),
            ("light", ("🟢 Done", "🟢 Done"), (), True, "PHASE_AUDIT_REQUIRED_MULTI_ITEM"),
            ("none", ("🟢 Done",), ("public contract",), True, "PHASE_AUDIT_REQUIRED_MATERIAL_RISK"),
            ("none", ("🟠 Done with deviations",), (), True, "PHASE_AUDIT_REQUIRED_NON_GREEN"),
        )
        for review, statuses, risks, required, code in cases:
            with self.subTest(review=review, statuses=statuses, risks=risks):
                with tempfile.TemporaryDirectory() as tmp:
                    items = "P1.1–P1.2" if len(statuses) == 2 else "P1.1"
                    plan = self._plan_with_review(tmp, review, items=items)
                    policy = plan_gates.phase_audit_policy(
                        plan, "P1", candidate_snapshot=self._candidate(
                            statuses=statuses, material_risks=risks))
                    self.assertEqual(policy["audit_required"], required)
                    self.assertEqual(policy["code"], code)

    def test_phase_audit_policy_fails_closed_when_routing_does_not_cover_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan_with_review(tmp, "none", items="P1.1")
            policy = plan_gates.phase_audit_policy(
                plan, "P1", candidate_snapshot=self._candidate(
                    statuses=("🟢 Done", "🟢 Done")))
            self.assertTrue(policy["audit_required"])
            self.assertEqual(policy["code"], "PHASE_AUDIT_REQUIRED_UNASSESSED")

    def test_phase_close_binds_policy_snapshot_to_candidate_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan_with_review(tmp, "none")
            gate = plan_gates.phase_close_gate(
                plan, "P1", candidate_fingerprint="a" * 64,
                candidate_snapshot=self._candidate())
            self.assertFalse(gate["allow"])
            self.assertEqual(gate["code"], "PHASE_CANDIDATE_SNAPSHOT_MISMATCH")

    def test_only_reproduced_acceptance_safety_authority_are_terminal(self):
        for signal in review_policy.SIGNAL_CLASSES:
            decision = classify_signal(
                signal, reproduced=True, scope_class="item", fingerprint=signal)
            self.assertEqual(
                decision["terminal"], signal in review_policy.TERMINAL_SIGNAL_CLASSES)

    def test_raw_acceptance_signal_requests_reproduction(self):
        decision = classify_signal(
            "acceptance", reproduced=False, scope_class="item", fingerprint="f1")
        self.assertFalse(decision["terminal"])
        self.assertEqual(decision["action"], "reproduce-impact")

    def test_future_carrier_and_unchanged_baseline_do_not_block(self):
        future = classify_signal(
            "dependency-not-ready", reproduced=True, scope_class="consumer", fingerprint="f2")
        self.assertFalse(future["terminal"])
        delta = plan_gates.baseline_delta(
            current_failures={"old"}, baseline_failures={"old"}, owned_failures={"old"})
        self.assertFalse(delta["blocks"])
        self.assertEqual(delta["pre_existing"], ("old",))

    def test_audit_fixer_repairs_safe_work_without_a_successor(self):
        self.assertEqual(
            audit_fixer_action(in_scope=True),
            {"action": "repair-inline", "terminal": False, "reason": "safe-in-scope"},
        )

    def test_audit_fixer_changes_tactic_then_allows_one_return(self):
        self.assertEqual(
            audit_fixer_action(in_scope=True, repeated_fingerprint=1)["action"],
            "change-tactic",
        )
        self.assertEqual(
            audit_fixer_action(in_scope=True, repeated_fingerprint=2)["action"],
            "isolated-child-return",
        )
        self.assertEqual(
            audit_fixer_action(in_scope=True, repeated_fingerprint=3, reviewer_returns=1)["action"],
            "repair-inline",
        )
        with self.assertRaisesRegex(ReviewPolicyError, "at most one reviewer return"):
            audit_fixer_action(in_scope=True, repeated_fingerprint=3, reviewer_returns=2)

    def test_audit_fixer_preserves_non_gating_and_authority_boundaries(self):
        self.assertEqual(
            audit_fixer_action(in_scope=False)["action"], "record-non-gating")
        self.assertEqual(
            audit_fixer_action(in_scope=True, boundary="authority"),
            {"action": "decision-request", "terminal": True, "reason": "authority-boundary"},
        )
        self.assertEqual(
            audit_fixer_action(in_scope=True, boundary="acceptance"),
            {"action": "decision-request", "terminal": True, "reason": "acceptance-boundary"},
        )

    def test_phase_close_requires_matching_green_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "P"
            plan.mkdir()
            fingerprint = "a" * 64
            missing = plan_gates.phase_close_gate(
                plan, "P1", candidate_fingerprint=fingerprint)
            self.assertEqual(missing["code"], "PHASE_AUDIT_MISSING")
            journal.append(plan, journal.new_entry(
                plan_id="P", item_id="P1", command="plan-audit", actor="model/high",
                result="audit-green", fingerprint=fingerprint))
            self.assertTrue(plan_gates.phase_close_gate(
                plan, "P1", candidate_fingerprint=fingerprint)["allow"])
            self.assertEqual(plan_gates.phase_close_gate(
                plan, "P1", candidate_fingerprint="b" * 64)["code"], "PHASE_AUDIT_STALE")

    def test_attention_is_a_distinct_close_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "P"
            plan.mkdir()
            journal.append(plan, journal.new_entry(
                plan_id="P", item_id="P1", command="plan-audit", actor="model/high",
                result="audit-attention", fingerprint="a" * 64))
            gate = plan_gates.phase_close_gate(
                plan, "P1", candidate_fingerprint="a" * 64)
            self.assertEqual(gate["code"], "PHASE_AUDIT_ATTENTION")

    def test_accepted_phase_scoped_decision_allows_direct_green_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "P"
            decisions = plan / "decisions"
            decisions.mkdir(parents=True)
            (decisions / "D26-direct-close.md").write_text(
                "---\n"
                "id: D26\n"
                "date: 2026-08-11\n"
                "status: accepted\n"
                "item: P3\n"
                "items: [P3, P3.2]\n"
                "supersedes: [D25]\n"
                "superseded_by: null\n"
                "---\n\n"
                "## Решение\n\n"
                "`phase-close: direct-green-validation`\n\n"
                "## Почему\n\n"
                "test\n\n"
                "## Consequences\n\n"
                "test\n",
                encoding="utf-8",
            )
            gate = plan_gates.phase_close_gate(
                plan, "P3", candidate_fingerprint="a" * 64, owner_decision="D26")
            self.assertTrue(gate["allow"])
            self.assertEqual(gate["code"], "allow")
            self.assertEqual(gate["owner_decision"], "D26")

    def test_audit_cap_remediation_uses_any_accepted_decision_id_for_the_whole_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "P"
            phase = plan / "phases" / "P5"
            decisions = plan / "decisions"
            phase.mkdir(parents=True)
            decisions.mkdir()
            (plan / "plan.md").write_text("| Layout | v2 |\n", encoding="utf-8")
            (phase / "P5.md").write_text("# P5\n", encoding="utf-8")
            for item_id in ("P5.1", "P5.2"):
                (phase / f"{item_id}.md").write_text(f"### {item_id}\n", encoding="utf-8")
            (decisions / "D91-audit-cap-remediation.md").write_text(
                "---\n"
                "id: D91\n"
                "date: 2026-08-11\n"
                "status: accepted\n"
                "item: P5.2\n"
                "items: [P5.1, P5.2]\n"
                "supersedes: []\n"
                "superseded_by: null\n"
                "---\n\n"
                "## Решение\n\n"
                "AUDIT-CAP: третьего Audit P5 нет; фаза закрывается штатным `task:plan-close`.\n\n"
                "## Почему\n\n"
                "test\n",
                encoding="utf-8",
            )
            gate = plan_gates.phase_close_gate(
                plan, "P5", candidate_fingerprint="a" * 64, owner_decision="D91")
            self.assertTrue(gate["allow"])
            self.assertEqual(gate["code"], "allow")
            self.assertEqual(gate["owner_decision"], "D91")

    def test_audit_cap_remediation_refuses_an_incomplete_phase_item_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "P"
            phase = plan / "phases" / "P5"
            decisions = plan / "decisions"
            phase.mkdir(parents=True)
            decisions.mkdir()
            (plan / "plan.md").write_text("| Layout | v2 |\n", encoding="utf-8")
            (phase / "P5.md").write_text("# P5\n", encoding="utf-8")
            for item_id in ("P5.1", "P5.2"):
                (phase / f"{item_id}.md").write_text(f"### {item_id}\n", encoding="utf-8")
            (decisions / "D91-incomplete-audit-cap.md").write_text(
                "---\n"
                "id: D91\n"
                "date: 2026-08-11\n"
                "status: accepted\n"
                "item: P5.2\n"
                "items: [P5.2]\n"
                "supersedes: []\n"
                "superseded_by: null\n"
                "---\n\n"
                "## Решение\n\n"
                "AUDIT-CAP: третьего Audit P5 нет; фаза закрывается штатным `task:plan-close`.\n\n"
                "## Почему\n\n"
                "test\n",
                encoding="utf-8",
            )
            gate = plan_gates.phase_close_gate(
                plan, "P5", candidate_fingerprint="a" * 64, owner_decision="D91")
            self.assertFalse(gate["allow"])
            self.assertEqual(gate["code"], "PHASE_OWNER_DECISION_ITEM_SET_MISMATCH")

    def test_invalid_owner_override_refuses_without_weakening_default_audit_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "P"
            decisions = plan / "decisions"
            decisions.mkdir(parents=True)
            (decisions / "D26-wrong-scope.md").write_text(
                "---\n"
                "id: D26\n"
                "date: 2026-08-11\n"
                "status: accepted\n"
                "item: P2\n"
                "items: [P2]\n"
                "supersedes: [D25]\n"
                "superseded_by: null\n"
                "---\n\n"
                "## Решение\n\n"
                "`phase-close: direct-green-validation`\n\n"
                "## Почему\n\n"
                "test\n\n"
                "## Consequences\n\n"
                "test\n",
                encoding="utf-8",
            )
            refused = plan_gates.phase_close_gate(
                plan, "P3", candidate_fingerprint="a" * 64, owner_decision="D26")
            self.assertEqual(refused["code"], "PHASE_OWNER_DECISION_SCOPE_MISMATCH")
            default = plan_gates.phase_close_gate(
                plan, "P3", candidate_fingerprint="a" * 64)
            self.assertEqual(default["code"], "PHASE_AUDIT_MISSING")


class FindingIdentityTests(unittest.TestCase):
    def test_same_seam_gives_same_id(self):
        a = finding_id(file="f.py", rule_or_contract_locus="rule:1", defect_class="bug")
        b = finding_id(file="f.py", rule_or_contract_locus="rule:1", defect_class="bug")
        self.assertEqual(a, b)

    def test_different_seam_gives_different_id(self):
        a = finding_id(file="f.py", rule_or_contract_locus="rule:1", defect_class="bug")
        b = finding_id(file="g.py", rule_or_contract_locus="rule:1", defect_class="bug")
        self.assertNotEqual(a, b)

    def test_split_ban_rewording_does_not_change_identity(self):
        """Splitting one seam into differently-worded reports must not create
        several identities — the id never reads report wording at all."""
        seam = dict(file="f.py", rule_or_contract_locus="rule:1", defect_class="bug")
        first = finding_id(**seam)
        second = finding_id(**seam)  # a second, differently-phrased report of the same seam
        self.assertEqual(first, second)

    def test_empty_seam_field_is_unstable(self):
        with self.assertRaises(ReviewPolicyError) as ctx:
            finding_id(file="", rule_or_contract_locus="rule:1", defect_class="bug")
        self.assertEqual(ctx.exception.code, "FINDING_IDENTITY_UNSTABLE")

    def test_identity_of_uses_reopen_of_as_the_stable_pair(self):
        original = _finding(finding_id="abc123")
        reopened = _finding(reopen_of="abc123")
        self.assertEqual(identity_of(original), "abc123")
        self.assertEqual(identity_of(reopened), "abc123")

    def test_identity_of_derives_when_no_explicit_id(self):
        f = _finding()
        expected = finding_id(file=f["file"], rule_or_contract_locus=f["rule_or_contract_locus"],
                              defect_class=f["defect_class"])
        self.assertEqual(identity_of(f), expected)


class ReopensProductPredicateTests(unittest.TestCase):
    def test_product_type_reopens(self):
        self.assertTrue(reopens_product(_finding(type="product", severity="nit")))

    def test_security_blocker_reopens(self):
        self.assertTrue(reopens_product(_finding(type="process", severity="blocker")))

    def test_evidence_invalidating_acceptance_reopens(self):
        self.assertTrue(reopens_product(
            _finding(type="evidence", severity="minor", invalidates_acceptance=True)))

    def test_plain_evidence_does_not_reopen(self):
        self.assertFalse(reopens_product(
            _finding(type="evidence", severity="minor", invalidates_acceptance=False)))

    def test_plain_process_nit_does_not_reopen(self):
        self.assertFalse(reopens_product(_finding(type="process", severity="nit")))

    def test_unknown_type_is_unstable(self):
        with self.assertRaises(ReviewPolicyError) as ctx:
            reopens_product(_finding(type="cosmetic"))
        self.assertEqual(ctx.exception.code, "FINDING_IDENTITY_UNSTABLE")

    def test_unknown_severity_is_unstable(self):
        with self.assertRaises(ReviewPolicyError) as ctx:
            reopens_product(_finding(severity="urgent"))
        self.assertEqual(ctx.exception.code, "FINDING_IDENTITY_UNSTABLE")


class CapSubjectTests(unittest.TestCase):
    def test_owner_gated_subject_is_owner(self):
        self.assertEqual(cap_subject("owner-gated"), "owner")

    def test_self_host_subject_is_agent(self):
        self.assertEqual(cap_subject("self-host"), "agent")

    def test_all_declared_profiles_resolve(self):
        for profile in AUTHORITY_PROFILES:
            self.assertIn(cap_subject(profile), CAP_SUBJECT_BY_PROFILE.values())

    def test_undeclared_profile_fails_closed(self):
        with self.assertRaises(ReviewPolicyError) as ctx:
            cap_subject("owner-decides-by-vibe")
        self.assertEqual(ctx.exception.code, "AUTHORITY_PROFILE_UNDECLARED")


class LoopBudgetTests(unittest.TestCase):
    def test_occurrences_start_at_zero(self):
        budget = LoopBudget()
        self.assertEqual(budget.occurrences(_finding()), 0)

    def test_record_fix_round_increments_per_identity(self):
        budget = LoopBudget()
        f = _finding(type="product")
        self.assertEqual(budget.record_fix_round(f), 1)
        self.assertEqual(budget.record_fix_round(f), 2)
        self.assertEqual(budget.occurrences(f), 2)

    def test_different_identities_track_independently(self):
        budget = LoopBudget()
        a = _finding(type="product", file="a.py")
        b = _finding(type="product", file="b.py")
        budget.record_fix_round(a)
        self.assertEqual(budget.occurrences(a), 1)
        self.assertEqual(budget.occurrences(b), 0)

    def test_reopen_of_pair_counts_as_one_identity(self):
        budget = LoopBudget()
        first = _finding(type="product", finding_id="stable-1")
        second = _finding(type="product", reopen_of="stable-1")
        budget.record_fix_round(first)
        budget.record_fix_round(second)
        self.assertEqual(budget.occurrences(first), 2)
        self.assertEqual(budget.occurrences(second), 2)


class ReviewTransitionVerifyingTests(unittest.TestCase):
    """`state-transition-cases.json` cells for `state=VERIFYING event=typed-finding`
    and `same-finding-third` — the load-bearing bounded-repair path."""

    def test_non_reopening_finding_stays_in_verifying(self):
        result = review_transition("VERIFYING", _finding(type="process"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "continue-next")
        self.assertEqual(result["to_state"], "VERIFYING")
        self.assertFalse(result["reopened"])

    def test_first_reopening_finding_enters_fixing(self):
        result = review_transition("VERIFYING", _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "retry-fix")
        self.assertEqual(result["to_state"], "FIXING")
        self.assertEqual(result["occurrence"], 1)

    def test_second_reopening_finding_still_retries(self):
        budget = LoopBudget()
        f = _finding(type="product", finding_id="dup-1")
        review_transition("VERIFYING", f, budget=budget, profile="self-host")
        result = review_transition("VERIFYING", f, budget=budget, profile="self-host")
        self.assertEqual(result["decision"], "retry-fix")
        self.assertEqual(result["occurrence"], 2)

    def test_third_occurrence_of_same_finding_is_incident(self):
        budget = LoopBudget()
        f = _finding(type="product", finding_id="dup-2")
        review_transition("VERIFYING", f, budget=budget, profile="self-host")
        review_transition("VERIFYING", f, budget=budget, profile="self-host")
        result = review_transition("VERIFYING", f, budget=budget, profile="self-host")
        self.assertEqual(result["decision"], "incident")
        self.assertEqual(result["to_state"], "INCIDENT")
        self.assertEqual(result["journal"], "blocked")
        self.assertEqual(result["occurrence"], SAME_FINDING_MAX + 1)

    def test_third_occurrence_cap_subject_is_profile_parameterized(self):
        budget_owner = LoopBudget()
        budget_self = LoopBudget()
        f = _finding(type="product", finding_id="dup-3")
        for _ in range(SAME_FINDING_MAX):
            review_transition("VERIFYING", f, budget=budget_owner, profile="owner-gated")
            review_transition("VERIFYING", f, budget=budget_self, profile="self-host")
        owner_result = review_transition("VERIFYING", f, budget=budget_owner, profile="owner-gated")
        self_result = review_transition("VERIFYING", f, budget=budget_self, profile="self-host")
        self.assertEqual(owner_result["cap_subject"], "owner")
        self.assertEqual(self_result["cap_subject"], "agent")

    def test_third_occurrence_without_declared_profile_fails_closed(self):
        budget = LoopBudget()
        f = _finding(type="product", finding_id="dup-4")
        for _ in range(SAME_FINDING_MAX):
            review_transition("VERIFYING", f, budget=budget, profile="self-host")
        with self.assertRaises(ReviewPolicyError) as ctx:
            review_transition("VERIFYING", f, budget=budget, profile="undeclared")
        self.assertEqual(ctx.exception.code, "AUTHORITY_PROFILE_UNDECLARED")

    def test_reopen_of_pair_counts_toward_the_same_cap(self):
        budget = LoopBudget()
        first = _finding(type="product", finding_id="seam-x")
        second = _finding(type="product", reopen_of="seam-x")
        third = _finding(type="product", reopen_of="seam-x")
        review_transition("VERIFYING", first, budget=budget, profile="self-host")
        review_transition("VERIFYING", second, budget=budget, profile="self-host")
        result = review_transition("VERIFYING", third, budget=budget, profile="self-host")
        self.assertEqual(result["decision"], "incident")


class ReviewTransitionOtherStatesTests(unittest.TestCase):
    def test_ready_reopening_finding_escalates_to_design(self):
        result = review_transition("READY", _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "escalate-design")
        self.assertEqual(result["to_state"], "ESCALATED")
        self.assertEqual(result["journal"], "escalated")

    def test_ready_non_reopening_finding_is_a_no_op(self):
        result = review_transition("READY", _finding(type="process"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "continue-next")
        self.assertEqual(result["to_state"], "READY")
        self.assertEqual(result["journal"], "no-op")

    def test_done_reopening_finding_escalates_to_design(self):
        result = review_transition("DONE", _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "escalate-design")
        self.assertEqual(result["to_state"], "ESCALATED")

    def test_done_non_reopening_finding_is_a_no_op(self):
        result = review_transition("DONE", _finding(type="evidence"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "continue-next")
        self.assertEqual(result["to_state"], "DONE")

    def test_executing_absorbs_any_finding_inline(self):
        for finding in (_finding(type="product"), _finding(type="process")):
            result = review_transition("EXECUTING", finding, budget=LoopBudget(),
                                       profile="self-host")
            self.assertEqual(result["decision"], "continue-next")
            self.assertEqual(result["to_state"], "EXECUTING")

    def test_fixing_absorbs_any_finding_inline(self):
        result = review_transition("FIXING", _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "continue-next")
        self.assertEqual(result["to_state"], "FIXING")

    def test_incident_records_further_findings_without_a_second_incident(self):
        result = review_transition("INCIDENT", _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "continue-next")
        self.assertEqual(result["to_state"], "INCIDENT")

    def test_reopen_evaluated_outside_a_guarded_state_is_refused(self):
        with self.assertRaises(ReviewPolicyError) as ctx:
            review_transition("OWNER_BOUNDARY", _finding(type="product"),
                              budget=LoopBudget(), profile="self-host")
        self.assertEqual(ctx.exception.code, "REOPEN_WITHOUT_PRODUCT_FINDING")


class SameFindingThirdEventTests(unittest.TestCase):
    """`state-transition-cases.json` cells for `event = same-finding-third`."""

    def test_incident_from_every_open_loop_state(self):
        for state in ("EXECUTING", "VERIFYING", "FIXING", "DONE", "OWNER_BOUNDARY", "ESCALATED"):
            result = same_finding_third(state, _finding(type="product"),
                                        budget=LoopBudget(), profile="self-host")
            self.assertEqual(result["decision"], "incident")
            self.assertEqual(result["to_state"], "INCIDENT")
            self.assertEqual(result["journal"], "blocked")

    def test_incident_state_self_loops_without_a_second_incident(self):
        result = same_finding_third("INCIDENT", _finding(type="product"),
                                    budget=LoopBudget(), profile="self-host")
        self.assertEqual(result["decision"], "continue-next")
        self.assertEqual(result["to_state"], "INCIDENT")

    def test_ready_and_skipped_carry_no_fix_round_to_close(self):
        for state in ("READY", "SKIPPED"):
            with self.assertRaises(ReviewPolicyError) as ctx:
                same_finding_third(state, _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
            self.assertEqual(ctx.exception.code, "REOPEN_WITHOUT_PRODUCT_FINDING")

    def test_cap_subject_is_profile_parameterized_here_too(self):
        owner = same_finding_third("VERIFYING", _finding(type="product"),
                                   budget=LoopBudget(), profile="owner-gated")
        agent = same_finding_third("VERIFYING", _finding(type="product"),
                                   budget=LoopBudget(), profile="self-host")
        self.assertEqual(owner["cap_subject"], "owner")
        self.assertEqual(agent["cap_subject"], "agent")


class ValidationCadenceTests(unittest.TestCase):
    def test_terminal_item_gets_full_validation(self):
        self.assertEqual(validation_cadence(is_phase_terminal_item=True), "full")

    def test_non_terminal_item_gets_targeted_validation(self):
        self.assertEqual(validation_cadence(is_phase_terminal_item=False), "targeted")


class FiveAuditLoopHistoricalScenarioTests(unittest.TestCase):
    """Machine form of the corpus case `five-audit-loop`
    (`artifacts/source-evidence/precomputed/corpus.json`): a product-blocking
    finding raised repeatedly past the declared cap must become an INCIDENT
    routed to a bounded next action instead of a fourth audit round — the exact
    field failure this plan exists to enforce as a runtime transition."""

    def test_third_audit_round_of_the_same_finding_becomes_incident_not_a_fourth_loop(self):
        budget = LoopBudget()
        recurring_finding = _finding(
            type="product", severity="blocker",
            file="packages/task/commands/plan-audit.md",
            rule_or_contract_locus="plan-audit.md:45-58 audit cap",
            defect_class="premature-stop-recurrence",
        )
        outcomes = []
        for _round in range(3):
            outcomes.append(review_transition("VERIFYING", recurring_finding,
                                               budget=budget, profile="self-host"))
        first, second, third = outcomes
        self.assertEqual(first["decision"], "retry-fix")
        self.assertEqual(second["decision"], "retry-fix")
        self.assertEqual(third["decision"], "incident")
        self.assertEqual(third["to_state"], "INCIDENT")
        self.assertEqual(third["cap_subject"], "agent")
        # A fifth audit attempt over the same finding stays inside the incident —
        # it never reopens a fourth independent fix loop.
        fourth = same_finding_third("INCIDENT", recurring_finding, budget=budget,
                                    profile="self-host")
        self.assertEqual(fourth["decision"], "continue-next")
        self.assertEqual(fourth["to_state"], "INCIDENT")

    def test_cosmetically_reworded_recurrence_still_trips_the_cap(self):
        """Split-ban in situ: re-filing the same seam under different wording must
        not reset the counter — the whole reason `finding_id` reads the seam."""
        budget = LoopBudget()
        seam = dict(file="packages/task/commands/plan-audit.md",
                   rule_or_contract_locus="plan-audit.md:45-58 audit cap",
                   defect_class="premature-stop-recurrence")
        wordings = ("stops before evidence is complete", "returns early on partial evidence",
                   "exits the loop before the cap")
        outcomes = [review_transition("VERIFYING",
                                      _finding(type="product", **seam, note=wording),
                                      budget=budget, profile="owner-gated")
                   for wording in wordings]
        self.assertEqual([o["decision"] for o in outcomes],
                         ["retry-fix", "retry-fix", "incident"])
        self.assertEqual(outcomes[-1]["cap_subject"], "owner")


class LoopBudgetFromCommittedTests(unittest.TestCase):
    """P2.6 F5 — `LoopBudget.from_committed` reconstructs a finding's
    cross-session occurrence count from `journal.jsonl` + `## Audit Pn`
    blocks instead of always starting a fresh in-process counter at zero."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plan_dir = Path(self._tmp.name)
        (self.plan_dir / "phases").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _finding(self, locus="lib/foo.py:10-20"):
        return {"type": "product", "severity": "blocker", "file": "lib/foo.py",
               "rule_or_contract_locus": locus, "defect_class": "no-persistence"}

    def test_missing_phase_file_is_unknown_not_zero(self):
        budget, count = LoopBudget.from_committed(self.plan_dir, "P9", self._finding())
        self.assertEqual(count, "unknown")
        self.assertIsInstance(budget, LoopBudget)

    def test_v2_missing_phase_carrier_refuses_instead_of_unknown(self):
        (self.plan_dir / "plan.md").write_text(
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n",
            encoding="utf-8")
        with self.assertRaises(ReviewPolicyError) as ctx:
            LoopBudget.from_committed(self.plan_dir, "P9", self._finding())
        self.assertEqual(ctx.exception.code, "CARRIER_UNRESOLVED")

    def test_no_matching_audit_block_is_a_real_verified_zero(self):
        (self.plan_dir / "phases" / "P2.md").write_text(
            "## Phase Status\n\n## Audit P2 — 2026-01-01\n\nno findings here\n",
            encoding="utf-8")
        budget, count = LoopBudget.from_committed(self.plan_dir, "P2", self._finding())
        self.assertEqual(count, 0)

    def test_finding_locus_repeated_across_two_audit_blocks_counts_both(self):
        (self.plan_dir / "phases" / "P2.md").write_text(
            "## Phase Status\n\n"
            "## Audit P2 — 2026-01-01\n\nFinding at lib/foo.py:10-20 still present.\n\n"
            "## Audit P2 — 2026-01-08\n\nFinding at lib/foo.py:10-20 STILL present.\n",
            encoding="utf-8")
        budget, count = LoopBudget.from_committed(self.plan_dir, "P2", self._finding())
        self.assertEqual(count, 2)
        self.assertEqual(budget.occurrences(self._finding()), 2)

    def test_journal_plan_audit_notes_are_also_counted(self):
        (self.plan_dir / "phases" / "P2.md").write_text(
            "## Phase Status\n\n## Audit P2 — 2026-01-01\n\nno findings here\n",
            encoding="utf-8")
        entries = [
            {"command": "plan-audit", "note": "recurring: lib/foo.py:10-20 unresolved"},
            {"command": "plan-audit", "note": "recurring: lib/foo.py:10-20 unresolved (2)"},
            {"command": "plan-exec", "note": "lib/foo.py:10-20 mentioned in passing"},
        ]
        with open(self.plan_dir / "journal.jsonl", "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e) + "\n")
        budget, count = LoopBudget.from_committed(self.plan_dir, "P2", self._finding())
        self.assertEqual(count, 2)

    def test_reconstructed_budget_reaches_the_incident_cap_on_the_next_round(self):
        (self.plan_dir / "phases" / "P2.md").write_text(
            "## Phase Status\n\n"
            "## Audit P2 — 2026-01-01\n\nlib/foo.py:10-20\n\n"
            "## Audit P2 — 2026-01-08\n\nlib/foo.py:10-20\n",
            encoding="utf-8")
        finding = self._finding()
        budget, count = LoopBudget.from_committed(self.plan_dir, "P2", finding)
        self.assertEqual(count, SAME_FINDING_MAX)
        result = review_transition("VERIFYING", finding, budget=budget, profile="self-host")
        self.assertEqual(result["decision"], "incident")

    def test_empty_locus_is_unstable(self):
        with self.assertRaises(ReviewPolicyError) as ctx:
            LoopBudget.from_committed(self.plan_dir, "P2", self._finding(locus=""))
        self.assertEqual(ctx.exception.code, "FINDING_IDENTITY_UNSTABLE")


class ReviewPolicyErrorMessageTests(unittest.TestCase):
    def test_error_message_carries_its_code(self):
        try:
            cap_subject("nonsense")
        except ReviewPolicyError as error:
            self.assertIn("AUTHORITY_PROFILE_UNDECLARED", str(error))
        else:
            self.fail("expected ReviewPolicyError")


if __name__ == "__main__":
    unittest.main()
