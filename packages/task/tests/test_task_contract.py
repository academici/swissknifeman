"""Tests for `task.task_contract` — the P2.2 Task Contract v1 compiler.

Exercises every one of the twelve pre-mutation and three pre-final reason codes declared
by the frozen `root/contracts/task-contract-v1.md`, plus the portability tier
classification/lint layer added by `plan-portability-v1.md` (P2.1,
`PORTABILITY_TIER_MISCLASSIFIED`). A base contract is copied from the committed P0.2
example (.json` example `routine-continuation`) so
every mutation starts from a schema-valid, allow/allow baseline — one mutated field per
test, never a hand-authored contract that could silently satisfy the wrong branch.
"""
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path

try:
    from . import fixtures  # noqa: F401,E402 — package invocation from repository root
except ImportError:  # pragma: no cover - discovery from packages/task
    import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
from task import (journal, plan_authority, plan_item_state, plan_layout, task_contract,
                  terminal_policy)  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_PATH = Path(__file__).resolve().parent / "fixtures_data/task-contract-routine-continuation.json"


def _load_base_contract():
    return copy.deepcopy(json.loads(EXAMPLES_PATH.read_text(encoding="utf-8")))


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
    ::portability_cases` — the compiler and the
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
            {"path": "plans/2026.07.24-DEMO-PLAN/artifacts/P2.2/base-sha.txt",
             "kind": "produced-by-predecessor", "producer": None})
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "PORTABILITY_INPUT_MISSING")

    def test_predecessor_input_with_producer_allows(self):
        base = _load_base_contract()
        base["portability"]["execution_inputs"].append(
            {"path": "plans/2026.07.24-DEMO-PLAN/artifacts/P2.2/base-sha.txt",
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

    def test_unresolved_actual_route_is_distinct_from_measured_undershoot(self):
        # D74/D78 root: `_rank(MODEL_CLASS_ORDER, None)` used to raise
        # `ValueError: tuple.index(x): x not in tuple` instead of a typed code.
        base = _load_base_contract()
        base["route"]["actual"]["model_class"] = None
        base["route"]["actual"]["effort"] = None
        contract = _rehashed(base)
        self.assertEqual(task_contract.pre_mutation(contract), "ROUTE-UNVERIFIABLE")

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
    def test_audit_cap_remediation_requires_an_accepted_item_scoped_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            decision = plan / "decisions" / "D76.md"
            decision.parent.mkdir()
            decision.write_text(
                "---\nstatus: accepted\nitem: P5.6\n---\n"
                "AUDIT-CAP: P5.6 обязан закрыть без waiver; третьего Audit P5 нет.\n",
                encoding="utf-8")
            self.assertTrue(task_contract._has_audit_cap_remediation_grant(plan, "P5.6"))
            self.assertFalse(task_contract._has_audit_cap_remediation_grant(plan, "P5.5"))

    def test_audit_cap_recovery_allows_only_explicit_validation_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            decision = plan / "decisions" / "D79.md"
            decision.parent.mkdir()
            decision.write_text(
                "---\nstatus: accepted\nitem: P6.7\n"
                "items: [P6.1, P6.2, P6.3, P6.4, P6.5, P6.6, P6.7]\n---\n"
                "AUDIT-CAP P6 закрывается bounded recovery без третьего Audit P6. "
                "Владелец разрешает повторить исходные Validation для P6.1/P6.3/P6.5, "
                "P6.6 и P6.7 только в fresh native roots с provider-attested маршрутами; "
                "новых terminal attempts недостаточно без route evidence.\n",
                encoding="utf-8",
            )
            for item_id in ("P6.1", "P6.3", "P6.5", "P6.6", "P6.7"):
                self.assertTrue(task_contract._has_audit_cap_remediation_grant(plan, item_id))
            for item_id in ("P6.2", "P6.4"):
                self.assertFalse(task_contract._has_audit_cap_remediation_grant(plan, item_id))

    def test_first_audit_leaves_one_repair_round(self):
        base = _load_base_contract()
        base["authority"]["observed_rounds"] = 1
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))

    def test_final_allowed_audit_preserves_repair_authority(self):
        base = _load_base_contract()
        base["authority"]["observed_rounds"] = 2
        contract = _rehashed(base)
        self.assertIsNone(task_contract.pre_mutation(contract))

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
        from task.session_context import SessionContext
        session = patch("task.session_context.resolve", return_value=SessionContext("codex", "owner-thread", "test"))
        session.start()
        self.addCleanup(session.stop)
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
        self._replace_decision_rows(decision_rows)
        (self.plan_dir / "brief" / "00-brief.md").write_text(
            "# Owner message\n\n"
            "[REPOSITORY-OWNER-MESSAGE:grant-g-test] [OWNER-GRANT:G-TEST] "
            "branch=`go-branch`; scope=`finite-scope`; provenance=`repository-owner`\n",
            encoding="utf-8")
        spec = fixtures.item_spec_md().replace(
            "**Implementation Rules:** stdlib-only.",
            "**Implementation Rules:** [OWNER-GRANT:G-TEST] protects this transition.")
        fixtures.write_v2_carriers(self.plan_dir, item_spec=spec)
        request = {"gate_id": "G-TEST", "branch": "go-branch", "scope": "finite-scope"}
        action = {"plan_id": self.plan_dir.name, "item_id": "P1.1", "gate": request,
                  "command": f"task:plan-run {self.plan_dir.name} P1.1",
                  "cwd": str(self.plan_dir.parent.parent)}
        action_digest = hashlib.sha256(json.dumps(
            action, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        plan_authority.DurableAuthorityStore.for_plan(self.plan_dir).activate(
            f"{self.plan_dir.name}\0P1.1\0G-TEST",
            {"schema_version": "owner-activation/v1", "plan_id": self.plan_dir.name,
             "item_id": "P1.1", "gate_id": "G-TEST", "decision_id": "D65",
             "owner_message": "brief/00-brief.md#grant-g-test",
             "action_digest": action_digest, "attestation_sha256": "a" * 64,
             "boundary": "security-boundary"})

    def tearDown(self):
        self._tmp.cleanup()

    def _actual_route(self):
        from task import route_evidence
        return route_evidence.capture_actual("implementation", "medium",
                                             source="provider-doctor", ts="t", model="test")

    def _protected(self, **overrides):
        request = {"gate_id": "G-TEST", "branch": "go-branch", "scope": "finite-scope"}
        request.update(overrides)
        return task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route(),
                                   protected_transition=request)

    def _security_evidence(self):
        from task import route_evidence
        now = datetime.now(timezone.utc).replace(microsecond=0)
        request = {"gate_id": "G-TEST", "branch": "go-branch", "scope": "finite-scope"}
        action = {"plan_id": self.plan_dir.name, "item_id": "P1.1", "gate": request,
                  "command": f"task:plan-run {self.plan_dir.name} P1.1",
                  "cwd": str(self.plan_dir.parent.parent)}
        digest = hashlib.sha256(json.dumps(
            action, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        evidence = {**self._actual_route(), "source": "provider-thread-state",
                    "thread_id": "owner-thread", "source_version": "codex-provider-v1",
                    "cwd": str(self.plan_dir.parent.parent),
                    "invocation": f"$ task:plan-run {self.plan_dir.name} P1.1",
                    "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "owner_message_digest": "b" * 64}
        workflow = route_evidence.build_owner_attestation(
            evidence, provider="codex", plan_id=self.plan_dir.name, item_id="P1.1",
            action_digest=digest, audience="task.owner-authority",
            expires_at=(now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            nonce="nonce-provider-1")
        evidence["owner_attestation"] = {
            **workflow, "boundary": "security-boundary", "issuer": "provider:codex",
            "proof": "opaque-provider-proof"}
        return evidence

    @staticmethod
    def _decision_rows(*tail, prefix_count=64):
        """A checked D1…Dn Decision Log; tail cases mutate only its final carrier."""
        prefix = [f"| D{number} | 2026-08-03 | ordinary decision {number} | test |"
                  for number in range(1, prefix_count + 1)]
        return "\n".join([*prefix, *tail])

    def _replace_decision_rows(self, rows):
        decisions = self.plan_dir / "decisions"
        for path in decisions.glob("D*.md"):
            path.unlink()
        for raw in rows.splitlines():
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            if len(cells) < 3 or not re.fullmatch(r"D\d+", cells[0]):
                continue
            target = decisions / f"{cells[0]}-fixture.md"
            if target.exists():
                duplicate = decisions / f"{cells[0]}-duplicate.md"
                duplicate.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
                continue
            fixtures.write_decision_record(
                self.plan_dir, cells[0], decision=cells[2], date=cells[1])

    def test_routine_authority_uses_the_current_item_carrier(self):
        contract = task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())
        self.assertEqual(contract["authority"]["class"], "routine")
        self.assertTrue(contract["authority"]["granted"])
        self.assertEqual(contract["authority"]["granted_by"], "phases/P1/P1.1.md:P1.1")
        self.assertEqual(task_contract.evaluate(contract)["pre_mutation"], "allow")

    def test_local_owner_grant_cannot_activate_protected_transition(self):
        contract = self._protected()
        self.assertEqual(contract["authority"]["class"], "owner-gate")
        self.assertFalse(contract["authority"]["granted"])
        self.assertEqual(task_contract.evaluate(contract)["pre_mutation"],
                         "block:AUTHORITY_BOUNDARY")

    def _declare_gate(self):
        path = fixtures.item_spec_path(self.plan_dir)
        path.write_text(path.read_text() + "\n**Authority:** [OWNER-GATE:G-TEST] "
                        "branch=`go-branch`; scope=`finite-scope`\n", encoding="utf-8")

    def test_declared_gate_is_discovered_without_caller_kwargs(self):
        self._declare_gate()
        contract = task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())
        self.assertEqual(contract["authority"]["class"], "owner-gate")
        self.assertFalse(contract["authority"]["granted"])

    def test_migration_prose_gap_is_closed_even_when_routine_is_declared(self):
        path = fixtures.item_spec_path(self.plan_dir)
        path.write_text(path.read_text() + "\n**Authority:** routine\n"
                        "Requires durable owner authorization.\n", encoding="utf-8")
        with self.assertRaisesRegex(task_contract.TaskContractBuildError, "AUTHORITY_CONTRACT_GAP"):
            task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())

    def test_unresolved_clarification_cannot_fall_through_to_routine_authority(self):
        path = fixtures.item_spec_path(self.plan_dir)
        path.write_text(path.read_text().replace(
            "**Code Guidance:** ручная проверка dict-ключей.",
            "**Code Guidance:** [NEEDS CLARIFICATION: consumer owner and paths]."),
            encoding="utf-8")
        with self.assertRaisesRegex(task_contract.TaskContractBuildError, "AUTHORITY_CONTRACT_GAP"):
            task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())

    def test_live_owner_invocation_materializes_only_the_declared_gate(self):
        self._declare_gate()
        self._replace_decision_rows(self._decision_rows(prefix_count=64))
        store = plan_authority.DurableAuthorityStore.for_plan(self.plan_dir)
        store.path.unlink()
        evidence = self._security_evidence()
        with patch("task.route_evidence.capture_launch", return_value=evidence) as capture, \
                patch("task.route_evidence.provider_owner_verification",
                      return_value=(lambda value: True, lambda issuer, nonce, digest: True)):
            result = task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
            self.assertFalse(result["granted"])
            self.assertTrue(result["prepared"])
            capture.assert_called_once_with(expected_invocation=f"task:plan-run {self.plan_dir.name} P1.1",
                                            expected_cwd=self.plan_dir.parent.parent,
                                            require_current_owner_invocation=True)
        self.assertFalse(task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])
        self.assertFalse(self._protected(scope="other-scope")["authority"]["granted"])
        with patch("task.route_evidence.capture_launch", return_value={**evidence, "invocation": "$ task:plan-run OTHER P1.1"}), \
                patch("task.route_evidence.provider_owner_verification",
                      return_value=(lambda value: True, lambda issuer, nonce, digest: True)):
            with self.assertRaisesRegex(task_contract.TaskContractBuildError, "UNATTESTED"):
                task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
        with self.assertRaises(TypeError):
            task_contract.materialize_owner_invocation(self.plan_dir, "P1.1", evidence=evidence)

    def test_materialization_failure_never_activates_partial_grant(self):
        self._declare_gate()
        self._replace_decision_rows(self._decision_rows(prefix_count=64))
        store = plan_authority.DurableAuthorityStore.for_plan(self.plan_dir)
        store.path.unlink()
        evidence = self._security_evidence()
        with patch("task.route_evidence.capture_launch", return_value=evidence), \
                patch("task.route_evidence.provider_owner_verification",
                      return_value=(lambda value: True, lambda issuer, nonce, digest: True)), \
                patch("task.plan_decisions.build_views", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
        self.assertFalse(task_contract.build(
            self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])

    def _declare_local_gate(self, environment="checkout"):
        self._declare_gate()
        path = fixtures.item_spec_path(self.plan_dir)
        path.write_text(path.read_text().replace("scope=`finite-scope`\n",
            f"scope=`finite-scope`; boundary=`owner-session`; effect=`local-source`; environment=`{environment}`\n"), encoding="utf-8")
        self._replace_decision_rows(self._decision_rows(prefix_count=64))
        plan_authority.DurableAuthorityStore.for_plan(self.plan_dir).path.unlink()
        state = path.with_name(path.stem + ".state.md")
        state.write_text(state.read_text().replace("🟢 Done", "🟡 In progress"), encoding="utf-8")

    def test_local_grant_is_narrow_session_bound_and_idempotent(self):
        self._declare_local_gate("corex_test")
        evidence = self._security_evidence()
        evidence.pop("owner_attestation")
        with patch("task.route_evidence.capture_launch", return_value=evidence):
            first = task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
            second = task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
            self.assertTrue(first["granted"])
            self.assertEqual(first["boundary"], "workflow-guard")
            self.assertTrue(second["reused"])
            self.assertEqual(len(list((self.plan_dir / "decisions").glob("D*.md"))), 65)
            self.assertTrue(task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])
        with patch("task.route_evidence.capture_launch", return_value={**evidence, "thread_id": "other"}):
            self.assertFalse(task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])
        path = fixtures.item_spec_path(self.plan_dir)
        path.write_text(path.read_text().replace("finite-scope", "wider-scope"), encoding="utf-8")
        with patch("task.route_evidence.capture_launch", return_value=evidence):
            self.assertFalse(task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])

    def test_provider_unavailable_precedes_owner_prompt_capture(self):
        self._declare_gate()
        with patch("task.route_evidence.capture_launch") as capture:
            with self.assertRaisesRegex(ValueError, "AUTHORITY_PROVIDER_UNAVAILABLE"):
                task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
            capture.assert_not_called()

    def test_local_grant_retry_after_runtime_failure_and_completion(self):
        self._declare_local_gate()
        evidence = self._security_evidence()
        evidence.pop("owner_attestation")
        with patch("task.route_evidence.capture_launch", return_value=evidence):
            with patch("task.plan_bundle.build", side_effect=RuntimeError("transport")):
                with self.assertRaisesRegex(RuntimeError, "transport"):
                    task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")
            self.assertEqual(len(list((self.plan_dir / "decisions").glob("D*.md"))), 64)
            self.assertTrue(task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")["granted"])
            path = fixtures.item_spec_path(self.plan_dir)
            original = path.read_text()
            path.write_text(original.replace("lib/pkg/config.py", "lib/pkg/other.py"), encoding="utf-8")
            self.assertFalse(task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])
            path.write_text(original, encoding="utf-8")
            state = path.with_name(path.stem + ".state.md")
            state.write_text(state.read_text().replace("🟡 In progress", "🟢 Done"), encoding="utf-8")
            self.assertFalse(task_contract.build(self.plan_dir, "P1.1", actual_route=self._actual_route())["authority"]["granted"])
            with self.assertRaisesRegex(task_contract.TaskContractBuildError, "run уже завершён"):
                task_contract.materialize_owner_invocation(self.plan_dir, "P1.1")

    def test_local_boundary_rejects_external_targets_and_effects(self):
        for environment, effect in (("production", "local-source"), ("checkout", "deploy"),
                                    ("checkout", "release"), ("checkout", "secrets"), ("checkout", "fleet")):
            with self.subTest(environment=environment, effect=effect):
                declaration = f"[OWNER-GATE:G-TEST] branch=`go`; scope=`finite`; boundary=`owner-session`; effect=`{effect}`; environment=`{environment}`"
                with self.assertRaisesRegex(task_contract.TaskContractBuildError, "AUTHORITY_BOUNDARY"):
                    task_contract.declared_authority("P1.1", {"Authority": declaration})

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

    def test_explicit_owner_message_cannot_replace_provider_authority(self):
        plan = (self.plan_dir / "plan.md").read_text(encoding="utf-8").replace(
            "| Approval Owner | dv |", "| Approval Owner | copied-display-name |")
        (self.plan_dir / "plan.md").write_text(plan, encoding="utf-8")
        self.assertEqual(task_contract.evaluate(self._protected())["pre_mutation"],
                         "block:AUTHORITY_BOUNDARY")

    def test_legacy_manual_authority_kwargs_are_refused_by_the_api(self):
        with self.assertRaises(TypeError):
            task_contract.build(self.plan_dir, "P1.1", authority_granted_by="D50 (foreign)")


class AuthorityCommandBoundaryTests(unittest.TestCase):
    """Both write-sites consume the compiler; plan-run is the single execution command."""

    def test_plan_run_boundaries_use_the_checked_compiler(self):
        run_text = (REPO_ROOT / "packages/task/commands/plan-run.md").read_text(encoding="utf-8")
        self.assertIn("task_contract", run_text)
        self.assertNotIn("authority_granted", run_text)
        self.assertNotIn("authority_granted_by", run_text)


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
        base["cold_start"]["carrier"] = "task:plan-run 2026.07.24-DEMO-PLAN P9.9"
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


class RuntimeValidationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.contract = _load_base_contract()
        evidence = self.contract["evidence"][0]
        evidence.update(path="python3 -m unittest", proof_class="declared",
                        algorithm="shell-command")
        self.contract["done"]["public_acceptance"][0].update(
            check="python3 -m unittest", evidence_ref=evidence["id"])
        self.contract = _rehashed(self.contract)
        self.context = {
            "schema_version": "validation-context/v1",
            "spec_sha256": "a" * 64,
            "head": "b" * 40,
            "tree": "c" * 40,
            "environment_sha256": "d" * 64,
        }

    def _receipt(self, exit_code=0):
        return task_contract.build_validation_receipt(
            self.contract, "E1", exit_code=exit_code,
            context=self.context, executed_at="2026-09-22T00:00:00Z",
        )

    def test_declared_validation_without_runtime_receipt_blocks(self):
        self.assertEqual(
            task_contract.pre_final(self.contract, validation_context=self.context),
            "VALIDATION_RECEIPT_MISSING",
        )

    def test_nonzero_runtime_receipt_blocks(self):
        self.assertEqual(
            task_contract.pre_final(
                self.contract, validation_receipts=[self._receipt(1)],
                validation_context=self.context,
            ),
            "VALIDATION_RECEIPT_NONZERO",
        )

    def test_changed_product_tree_blocks(self):
        changed = {**self.context, "tree": "e" * 40}
        self.assertEqual(
            task_contract.pre_final(
                self.contract, validation_receipts=[self._receipt()],
                validation_context=changed,
            ),
            "VALIDATION_RECEIPT_STALE",
        )

    def test_commit_without_product_change_keeps_receipt_fresh(self):
        moved = {**self.context, "head": "e" * 40}
        self.assertIsNone(task_contract.pre_final(
            self.contract, validation_receipts=[self._receipt()], validation_context=moved))

    def test_successful_bound_runtime_receipt_allows(self):
        self.assertIsNone(task_contract.pre_final(
            self.contract, validation_receipts=[self._receipt()],
            validation_context=self.context,
        ))


class AuditRoundCountingTests(unittest.TestCase):
    def test_only_fingerprinted_candidate_audits_consume_the_phase_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            phase_lines = [
                "# P1", "## Audit P1 — legacy", "**Вердикт: RED**",
                "## Audit P1 — candidate", "**Вердикт: RED**",
            ]
            events = [
                {"command": "plan-audit", "item_id": "P1", "result": "audit-red"},
                {"command": "plan-audit", "item_id": "P1", "result": "audit-red",
                 "fingerprint": "a" * 64},
            ]
            (plan / "journal.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
            self.assertEqual(task_contract._count_audit_rounds(plan, phase_lines, "P1"), 1)

    def test_base_fixture_pre_final_allows(self):
        base = _load_base_contract()
        self.assertIsNone(task_contract.pre_final(base))


class EvaluateTests(unittest.TestCase):
    def test_base_fixture_evaluates_allow_allow(self):
        base = _load_base_contract()
        result = task_contract.evaluate(base)
        self.assertEqual(result["pre_mutation"], "allow")
        self.assertEqual(result["pre_final"], "allow")
        self.assertEqual(result["reason_codes"], {
            "pre_mutation": None, "pre_final": None})
        self.assertEqual(result["content_hash"], base["version"]["content_hash"])

    def test_blocked_pre_mutation_reports_pre_final_as_not_applicable(self):
        base = _load_base_contract()
        base["authority"]["class"] = "owner-gate"
        base["authority"]["granted"] = False
        contract = _rehashed(base)
        result = task_contract.evaluate(contract)
        self.assertEqual(result["pre_mutation"], "block:AUTHORITY_BOUNDARY")
        self.assertEqual(result["pre_final"], "n/a")
        self.assertEqual(result["reason_codes"]["pre_mutation"]["code"],
                         "policy-denied")
        self.assertIsNone(result["reason_codes"]["pre_final"])

    def test_public_reason_taxonomy_keeps_internal_diagnostics(self):
        expected = {
            "PLAN_CONTEXT_TRUNCATED": "evidence-missing",
            "PLAN_CONTEXT_DIGEST_MISMATCH": "evidence-forged",
            "VALIDATION_RECEIPT_STALE": "evidence-stale",
            "OWNER_ATTESTATION_FORGED": "evidence-forged",
            "AUTHORITY_BOUNDARY": "policy-denied",
            "JOURNAL_CONFLICT": "conflict",
            "JOURNAL_CORRUPT": "corrupt-state",
            "JOURNAL_DURABILITY_FAILED": "durability-failed",
            "PORTABILITY_INPUT_INVALID": "schema-invalid",
        }
        for internal, public in expected.items():
            with self.subTest(internal=internal):
                reason = task_contract.public_reason(internal)
                self.assertEqual(reason["code"], public)
                self.assertEqual(reason["internal_code"], internal)
                self.assertTrue(reason["message"])
        for unknown in ("UNKNOWN_MISSING", "UNKNOWN_ATTESTATION", "UNKNOWN_CONFLICT"):
            with self.subTest(unknown=unknown):
                self.assertEqual(task_contract.public_reason(unknown)["code"],
                                 "policy-denied")


class CliGateTests(unittest.TestCase):
    def _check(self, contract):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join((str(REPO_ROOT / "packages/task/lib"),
                                                  str(REPO_ROOT)))
            return subprocess.run(
                (sys.executable, "-m", "task.task_contract", "check",
                 "--contract", str(path)),
                cwd=REPO_ROOT, env=env, text=True, capture_output=True,
            )

    def test_full_check_exits_nonzero_when_final_gate_blocks(self):
        contract = _load_base_contract()
        contract["done"]["public_acceptance"][0]["scope"] = "internal"
        result = self._check(_rehashed(contract))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["pre_mutation"], "allow")
        self.assertEqual(payload["pre_final"], "block:ACCEPTANCE_NOT_PUBLIC")
        self.assertEqual(payload["reason_codes"]["pre_final"]["code"],
                         "schema-invalid")

    def test_full_check_keeps_allow_allow_exit_zero_and_json_shape(self):
        result = self._check(_load_base_contract())
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["pre_mutation"], "allow")
        self.assertEqual(payload["pre_final"], "allow")
        self.assertEqual(payload["reason_codes"], {
            "pre_mutation": None, "pre_final": None})


class EvaluateFindingHookTests(unittest.TestCase):
    """`evaluate_finding` — the ONE new call-site this compiler gains for
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


def _routing_row(model_effort="implementation/medium"):
    return (f"\n\n| Items | Model class/effort | Exec | Почему |\n"
           f"|:--|:--|:--|:--|\n"
           f"| P1.1 | {model_effort} | run | test |\n")


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
        self.assertEqual(contract["next"]["context"], "continue-root")

    def test_built_contract_has_nonempty_required_arrays_and_matching_hash(self):
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertGreaterEqual(len(contract["must"]), 1)
        self.assertGreaterEqual(len(contract["never"]), 1)
        self.assertGreaterEqual(len(contract["evidence"]), 1)
        self.assertGreaterEqual(len(contract["done"]["public_acceptance"]), 1)
        self.assertEqual(contract["version"]["content_hash"], task_contract.content_hash(contract))

    def test_build_is_byte_deterministic_across_two_calls(self):
        first = json.dumps(task_contract.build(self.plan_dir, "P1.1"), sort_keys=True)
        second = json.dumps(task_contract.build(self.plan_dir, "P1.1"), sort_keys=True)
        self.assertEqual(first, second)

    def test_default_actual_route_is_unresolved_and_dispatch_guard_denies_it(self):
        from task import route_evidence as re_
        contract = task_contract.build(self.plan_dir, "P1.1")
        required, actual = contract["route"]["required"], contract["route"]["actual"]
        self.assertIsNone(actual["model_class"])
        self.assertEqual(re_.dispatch_guard(required, actual, contract["route"]["capabilities"]),
                         "ROUTE-UNVERIFIABLE")

    def test_live_actual_route_matching_required_allows_mutation_but_needs_runtime_validation(self):
        from task import route_evidence as re_
        contract = task_contract.build(self.plan_dir, "P1.1")
        required = contract["route"]["required"]
        actual = re_.capture_actual(required["model_class"], required["effort"],
                                    source="provider-doctor", ts="t", model="sonnet")
        caps = re_.capability_support(["command.subagents"], {"command.subagents": "native"})
        contract["route"] = re_.build_task_contract_route(required, actual, caps)
        contract["version"]["content_hash"] = task_contract.content_hash(contract)
        self.assertIsNone(task_contract.pre_mutation(contract))
        self.assertEqual(task_contract.pre_final(contract), "VALIDATION_RECEIPT_MISSING")

    def test_unknown_item_id_fails_closed(self):
        with self.assertRaises(task_contract.TaskContractBuildError):
            task_contract.build(self.plan_dir, "P1.999")

    def test_v2_phase_carrier_builds_through_layout_resolver(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = fixtures.write_valid_plan(Path(tmp), "DEMO-V2", layout="v2")
            text = (plan / "plan.md").read_text(encoding="utf-8").replace(
                "## 3. Routing\n\n", "## 3. Routing" + _routing_row())
            (plan / "plan.md").write_text(text, encoding="utf-8")
            contract = task_contract.build(plan, "P1.1")
            self.assertEqual(contract["route"]["required"],
                             {"model_class": "implementation", "effort": "medium"})
            self.assertEqual(contract["goal"]["outcome"], "Добавить проверку.")
            self.assertEqual(contract["next"]["context"], "continue-root")

    def test_validation_bullets_keep_product_checks_distinct_from_external_tooling(self):
        path = fixtures.item_spec_path(self.plan_dir)
        path.write_text(path.read_text(encoding="utf-8").replace(
            "**Validation:** bash scripts/test.sh — зелёный.",
            "**Validation:**\n- bash scripts/test.sh — зелёный.\n"
            "- python3 <task>/scripts/plan-lint.py plans/DEMO-1 — зелёный."),
            encoding="utf-8")
        contract = task_contract.build(self.plan_dir, "P1.1")
        acceptance = contract["done"]["public_acceptance"]
        self.assertEqual([entry["scope"] for entry in acceptance], ["public", "internal"])
        self.assertEqual(task_contract.pre_final(contract), "VALIDATION_RECEIPT_MISSING")
        context = {
            "schema_version": "validation-context/v1",
            "spec_sha256": "a" * 64, "head": "b" * 40, "tree": "c" * 40,
            "environment_sha256": "d" * 64,
        }
        receipt = task_contract.build_validation_receipt(
            contract, acceptance[0]["evidence_ref"], exit_code=0, context=context)
        self.assertIsNone(task_contract.pre_final(
            contract, validation_receipts=[receipt], validation_context=context))
        receipt["exit_code"] = 1
        self.assertEqual(task_contract.pre_final(
            contract, validation_receipts=[receipt], validation_context=context),
            "VALIDATION_RECEIPT_NONZERO")

    def test_build_preserves_external_input_until_portability_gate(self):
        phase_path = fixtures.item_spec_path(self.plan_dir)
        phase_path.write_text(
            phase_path.read_text(encoding="utf-8").replace(
                "**Required Reads:** 1) lib/pkg/config.py",
                "**Required Reads:** 1) lib/pkg/config.py 2) `/tmp/secret.json`"),
            encoding="utf-8",
        )
        contract = task_contract.build(self.plan_dir, "P1.1")
        external = next(entry for entry in contract["portability"]["execution_inputs"]
                        if entry["original"] == "/tmp/secret.json")
        self.assertEqual(external["path_kind"], "external")
        self.assertEqual(task_contract.pre_mutation(contract), "PORTABILITY_EXTERNAL_INPUT")

    def test_path_classifier_is_platform_neutral_and_does_not_expand_ambient_state(self):
        cases = {
            "nested/file.md": "internal",
            "C:\\temp\\file.md": "external",
            "\\\\server\\share\\file.md": "external",
            "file:///tmp/file.md": "external",
            "~/file.md": "external",
            "$HOME/file.md": "external",
            "nested/../file.md": "invalid",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    task_contract.classify_execution_input(value)["path_kind"], expected)

    def test_contract_ignores_a_mapping_table_before_the_executable_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = fixtures.write_valid_plan(Path(tmp), "DEMO-ROUTING", layout="v2")
            routing = (
                "| Provider | Model | Selector |\n"
                "|:--|:--|:--|\n"
                "| Codex | gpt-5.6-terra | implementation |\n\n"
                "| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
                "|:--|:--|:--|:--|:--|:--|\n"
                "| solo | P1.1 | implementation/high | run | full | test |\n")
            plan_md = (plan / "plan.md").read_text(encoding="utf-8").replace(
                "## 3. Routing\n\n", "## 3. Routing\n\n" + routing)
            (plan / "plan.md").write_text(plan_md, encoding="utf-8")
            contract = task_contract.build(plan, "P1.1")
            self.assertEqual(contract["route"]["required"],
                             {"model_class": "implementation", "effort": "high"})

    def test_empty_validation_field_refuses_to_fabricate_an_acceptance_entry(self):
        phase_path = fixtures.item_spec_path(self.plan_dir)
        phase_path.write_text(
            phase_path.read_text(encoding="utf-8").replace(
                "**Validation:** bash scripts/test.sh — зелёный.", "**Validation:** —"),
            encoding="utf-8")
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Validation")
        self.assertEqual(ctx.exception.item_id, "P1.1")

    def test_missing_routing_row_fails_closed(self):
        # fixtures.plan_md() leaves §3 Routing empty; P1.1's default row was added in
        # setUp only for THIS plan.md, so an item absent from it has no row.
        fixtures.write_v2_carriers(self.plan_dir, item_id="P1.2", refresh_views=False)
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
           f"| {items} | {model_effort} | run | test |\n")


class RoutingFormTests(unittest.TestCase):
    """P2.10/D78 — §3 Routing form coverage: canonical header only, provider model
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

    def test_legacy_routing_header_fails_closed(self):
        self._write_plan(_routing_row_with_header("Model/effort", "implementation/high"))
        with self.assertRaises(task_contract.TaskContractBuildError) as ctx:
            task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(ctx.exception.field, "Routing")

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
        self._write_plan(_routing_row_with_header("Model class/effort", "opus/high"))
        contract = task_contract.build(self.plan_dir, "P1.1")
        self.assertEqual(contract["route"]["required"],
                         {"model_class": "frontier", "effort": "high"})

    def test_unknown_model_name_fails_closed(self):
        self._write_plan(_routing_row_with_header("Model class/effort", "gpt-9-nonexistent/high"))
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
        fixtures.write_v2_carriers(self.plan_dir, item_id=item_id, refresh_views=False)

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
        # The live shape (`P4.1–P4.2, P4.4`): a range AND a list in one
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
        self._write_plan(_routing_row_with_header("Model class/effort", "shared-name/high"))
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
                                      declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_ARTIFACT_MISSING)

    def test_missing_verifier_fails_closed(self):
        self._write_manifest(["a.txt"])
        (self.bundle_dir / "a.txt").write_text("clean", encoding="utf-8")
        self.verifier_path.unlink()
        self.assertEqual(
            task_contract.bundle_lint(self.bundle_dir, manifest_path=self.manifest_path,
                                      verifier_path=self.verifier_path,
                                      declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_ARTIFACT_MISSING)

    def test_clean_bundle_matching_declaration_allows(self):
        self._write_manifest(["a.txt"])
        (self.bundle_dir / "a.txt").write_text("clean committed content", encoding="utf-8")
        self.assertIsNone(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()))

    def test_clean_nested_minimized_bundle_allows(self):
        self._write_manifest(["nested/a.txt"])
        (self.bundle_dir / "nested").mkdir()
        (self.bundle_dir / "nested/a.txt").write_text("clean committed content", encoding="utf-8")
        self.assertIsNone(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()))

    def test_extra_undeclared_file_breaks_minimization(self):
        self._write_manifest(["a.txt"])
        (self.bundle_dir / "a.txt").write_text("clean", encoding="utf-8")
        (self.bundle_dir / "extra.txt").write_text("undeclared", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(self.bundle_dir, manifest_path=self.manifest_path,
                                      verifier_path=self.verifier_path,
                                      declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_PRIVACY_MISMATCH)

    def test_secret_signature_found_despite_declared_exclusion(self):
        self._write_manifest(["creds.txt"])
        (self.bundle_dir / "creds.txt").write_text(
            "aws_secret_key: \"AKIAABCDEFGHIJKLMNOP\"", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(
                self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
                declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_POLICY_DENIED)

    def test_raw_transcript_body_needs_repeated_turn_markers_not_one_stray_line(self):
        self._write_manifest(["note.md"])
        (self.bundle_dir / "note.md").write_text(
            "See the incident where Human: reported the bug once.", encoding="utf-8")
        # One stray "Human:"-shaped line is not a transcript (false-positive guard).
        self.assertIsNone(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()))

    def test_repeated_turn_markers_are_flagged_as_raw_transcript_bodies(self):
        self._write_manifest(["rollout.txt"])
        (self.bundle_dir / "rollout.txt").write_text(
            "Human: hi\nAssistant: hello\nHuman: again\nAssistant: sure\n", encoding="utf-8")
        self.assertEqual(
            task_contract.bundle_lint(
                self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
                declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_POLICY_DENIED)

    def test_caller_cannot_remove_a_policy_forbidden_class(self):
        self._write_manifest(["rollout.txt"])
        (self.bundle_dir / "rollout.txt").write_text(
            "Human: hi\nAssistant: hello\nHuman: again\nAssistant: sure\n", encoding="utf-8")
        self.assertEqual(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy={"minimized": True, "excluded_classes": []}),
            task_contract.BUNDLE_POLICY_DENIED)

    def test_duplicate_normalized_manifest_names_reject(self):
        self._write_manifest(["nested/a.txt", "nested/./a.txt"])
        (self.bundle_dir / "nested").mkdir()
        (self.bundle_dir / "nested/a.txt").write_text("clean", encoding="utf-8")
        self.assertEqual(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_MEMBER_DUPLICATE)

    def test_external_and_traversing_manifest_names_reject(self):
        for value, code in (("/tmp/a.txt", task_contract.BUNDLE_PATH_EXTERNAL),
                            ("../a.txt", task_contract.BUNDLE_PATH_INVALID),
                            ("C:\\temp\\a.txt", task_contract.BUNDLE_PATH_EXTERNAL),
                            ("file:///tmp/a.txt", task_contract.BUNDLE_PATH_EXTERNAL)):
            with self.subTest(value=value):
                self._write_manifest([value])
                self.assertEqual(task_contract.bundle_lint(
                    self.bundle_dir, manifest_path=self.manifest_path,
                    verifier_path=self.verifier_path,
                    declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()), code)

    def test_symlink_escape_rejects_without_reading_target(self):
        outside = self.bundle_dir.with_name(self.bundle_dir.name + "-outside.txt")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.write_text("clean", encoding="utf-8")
        (self.bundle_dir / "escape.txt").symlink_to(outside)
        self._write_manifest(["escape.txt"])
        self.assertEqual(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_MEMBER_UNSAFE)

    def test_broken_symlink_rejects_without_following_it(self):
        (self.bundle_dir / "broken.txt").symlink_to(self.bundle_dir / "missing.txt")
        self._write_manifest(["broken.txt"])
        self.assertEqual(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_MEMBER_UNSAFE)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX mkfifo")
    def test_special_file_rejects_without_opening_it(self):
        os.mkfifo(self.bundle_dir / "pipe")
        self._write_manifest(["pipe"])
        self.assertEqual(task_contract.bundle_lint(
            self.bundle_dir, manifest_path=self.manifest_path, verifier_path=self.verifier_path,
            declared_privacy=task_contract.BUNDLE_INPUT_POLICY.privacy()),
            task_contract.BUNDLE_MEMBER_UNSAFE)

class BatchRoutingAdmissionTests(unittest.TestCase):
    """P1.2: batch authority is enforced before a caller can create an attempt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan_dir = fixtures.write_valid_plan(Path(self.tmp.name), "BATCH-DEMO", layout="v2")
        for item in ("P1.2", "P1.3"):
            fixtures.write_v2_carriers(self.plan_dir, item_id=item, refresh_views=False)
        routing = (
            "\n\n| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| B1 | P1.1–P1.3 | implementation/high | run | full | test |\n")
        plan = fixtures.plan_md("BATCH-DEMO").replace("## 3. Routing\n\n", "## 3. Routing" + routing)
        (self.plan_dir / "plan.md").write_text(plan, encoding="utf-8")
        (self.plan_dir / "journal.jsonl").write_text("", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_exec_spellings_resolve_to_one_mode_route_and_admission(self):
        path = self.plan_dir / "plan.md"
        baseline = task_contract.compile_batch_routing(self.plan_dir)
        self.assertEqual(baseline["batches"]["B1"]["exec"], "run")
        path.write_text(path.read_text().replace("| run |", "| plan-run |"))
        compiled = task_contract.compile_batch_routing(self.plan_dir)
        self.assertEqual(compiled["batches"]["B1"]["exec"], "run")
        self.assertEqual(compiled["items"]["P1.1"]["declared_exec"], "plan-run")
        self.assertEqual(compiled["batches"]["B1"]["route"], baseline["batches"]["B1"]["route"])
        self.assertNotEqual(compiled["routing_digest"], baseline["routing_digest"])
        self.assertEqual(task_contract.admit_batch(self.plan_dir, "P1.1–P1.3")["verdict"], "ALLOW")
        self.assertEqual(task_contract.admit_batch(self.plan_dir, "P1.1")["verdict"], "BATCH_REQUIRED")
        path.write_text(path.read_text().replace("| plan-run |", "| plan-rnu |"))
        with self.assertRaisesRegex(task_contract.TaskContractBuildError, "invalid Exec"):
            task_contract.compile_batch_routing(self.plan_dir)

    def test_direct_first_item_is_refused_and_exact_range_is_allowed(self):
        partial = task_contract.admit_batch(self.plan_dir, "P1.1")
        exact = task_contract.admit_batch(self.plan_dir, "P1.1–P1.3")
        self.assertEqual(partial["verdict"], "BATCH_REQUIRED")
        self.assertEqual(exact["verdict"], "ALLOW")
        self.assertEqual(exact["batch"]["route"],
                         {"model_class": "implementation", "effort": "high"})

    def test_checkpoint_bound_suffix_and_stale_spec_refusal(self):
        batch = task_contract.compile_batch_routing(self.plan_dir)["batches"]["B1"]
        receipt = task_contract.build_batch_receipt(batch, completed_prefix=("P1.1",))
        self.assertEqual(task_contract.admit_batch(self.plan_dir, ("P1.2", "P1.3"),
                                                   receipt=receipt)["verdict"], "BATCH_STALE")
        decision = terminal_policy.build_decision(
            self.plan_dir, "P1.1", result="closed-green",
            validation=[{"carrier": "fixture", "status": "green",
                         "evidence_ids": ["test:terminal"]}],
        )
        journal.append(self.plan_dir, journal.new_entry(
            plan_id=self.plan_dir.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green", decision=decision,
        ))
        plan_item_state.build_states(self.plan_dir, item_id="P1.1",
                                     materialize_successor=False)
        self.assertEqual(task_contract.admit_batch(self.plan_dir, ("P1.2", "P1.3"),
                                                   receipt=receipt)["verdict"], "ALLOW")
        spec = fixtures.item_spec_path(self.plan_dir, "P1.2")
        spec.write_text(spec.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        self.assertEqual(task_contract.admit_batch(self.plan_dir, ("P1.2", "P1.3"),
                                                   receipt=receipt)["verdict"], "BATCH_STALE")

    def test_recommended_batch_admits_only_ready_frontier_and_returns_empty_prefix_receipt(self):
        path = self.plan_dir / "plan.md"
        path.write_text(path.read_text().replace("| test |", "| recommended: sequential |"),
                        encoding="utf-8")
        successor = fixtures.item_spec_path(self.plan_dir, "P1.2")
        successor.write_text(successor.read_text().replace(
            "**Inputs:** `lib/pkg/config.py`.",
            "**Inputs:** `phases/P1/P1.1.state.md` (producer: P1.1)."), encoding="utf-8")
        (self.plan_dir / "journal.jsonl").write_text("", encoding="utf-8")
        for item in ("P1.1", "P1.2", "P1.3"):
            from task import plan_item_state
            plan_item_state.build_states(self.plan_dir, item_id=item,
                                         materialize_successor=False)
        verdict = task_contract.admit_batch(self.plan_dir, ("P1.1", "P1.2"))
        self.assertEqual(verdict["verdict"], "ALLOW")
        self.assertEqual(verdict["batch_receipt"]["membership"], ["P1.1", "P1.2"])
        self.assertEqual(verdict["batch_receipt"]["completed_prefix"], [])

    def test_recommended_batch_rejects_reversed_membership_order(self):
        path = self.plan_dir / "plan.md"
        path.write_text(path.read_text().replace("| test |", "| recommended: ordered |"),
                        encoding="utf-8")
        verdict = task_contract.admit_batch(self.plan_dir, ("P1.2", "P1.1"))
        self.assertEqual(verdict["verdict"], "BATCH_REQUIRED")
        self.assertEqual(verdict["canonical"], ["P1.1", "P1.2"])

    def test_recommended_batch_rejects_caller_fabricated_completed_prefix(self):
        path = self.plan_dir / "plan.md"
        path.write_text(path.read_text().replace("| test |", "| recommended: ordered |"),
                        encoding="utf-8")
        batch = task_contract.compile_batch_routing(self.plan_dir)["batches"]["B1"]
        receipt = task_contract.build_batch_receipt(
            batch, membership=("P1.1", "P1.2"), completed_prefix=("P1.1",),
        )
        verdict = task_contract.admit_batch(self.plan_dir, "P1.2", receipt=receipt)
        self.assertEqual(verdict["verdict"], "BATCH_STALE")

    def test_receipt_binds_plan_spec_routing_and_handoff_identity(self):
        batch = task_contract.compile_batch_routing(self.plan_dir)["batches"]["B1"]
        receipt = task_contract.build_batch_receipt(batch)
        for field in ("routing_digest", "spec_digest", "handoff_digest"):
            with self.subTest(field=field):
                tampered = copy.deepcopy(receipt)
                tampered[field] = "0" * 64
                verdict = task_contract.admit_batch(
                    self.plan_dir, ("P1.2", "P1.3"), receipt=tampered)
                self.assertEqual(verdict["verdict"], "BATCH_STALE")

        plan_path = self.plan_dir / "plan.md"
        original = plan_path.read_text(encoding="utf-8")
        plan_path.write_text(original.replace("implementation/high", "frontier/high"),
                             encoding="utf-8")
        try:
            verdict = task_contract.admit_batch(
                self.plan_dir, ("P1.2", "P1.3"), receipt=receipt)
            self.assertEqual(verdict["verdict"], "BATCH_STALE")
        finally:
            plan_path.write_text(original, encoding="utf-8")

        handoff = self.plan_dir / "handoff.md"
        original_handoff = handoff.read_text(encoding="utf-8")
        handoff.write_text(original_handoff + "\nchanged\n", encoding="utf-8")
        try:
            verdict = task_contract.admit_batch(
                self.plan_dir, ("P1.2", "P1.3"), receipt=receipt)
            self.assertEqual(verdict["verdict"], "BATCH_STALE")
        finally:
            handoff.write_text(original_handoff, encoding="utf-8")

    def test_request_across_groups_is_ambiguous(self):
        plan = (self.plan_dir / "plan.md").read_text(encoding="utf-8").replace(
            "| B1 | P1.1–P1.3 | implementation/high | run | full | test |",
            "| solo | P1.1 | implementation/high | run | full | test |\n"
            "| B1 | P1.2–P1.3 | implementation/high | run | full | test |")
        (self.plan_dir / "plan.md").write_text(plan, encoding="utf-8")
        self.assertEqual(task_contract.admit_batch(self.plan_dir, ("P1.1", "P1.2"))["verdict"],
                         "BATCH_AMBIGUOUS")

    def test_admission_route_uses_batch_maximum_for_the_first_item(self):
        path = self.plan_dir / "plan.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "| B1 | P1.1–P1.3 | implementation/high | run | full | test |",
            "| B1 | P1.1 | implementation/medium | run | none | recommended: shared |\n"
            "| B1 | P1.2 | frontier/high | run | full | recommended: hard seam |\n"
            "| B1 | P1.3 | implementation/high | run | light | recommended: shared |"),
            encoding="utf-8")
        compiled = task_contract.compile_batch_routing(self.plan_dir)
        batch_route = compiled["batches"]["B1"]["route"]
        self.assertEqual(batch_route, {"model_class": "frontier", "effort": "high"})
        contract = task_contract.build(self.plan_dir, "P1.1", admission_route=batch_route)
        self.assertEqual(contract["route"]["required"], batch_route)
        with self.assertRaisesRegex(task_contract.TaskContractBuildError,
                                    "BATCH_ROUTE_MISMATCH"):
            task_contract.build(
                self.plan_dir, "P1.1",
                admission_route={"model_class": "implementation", "effort": "medium"})


class ExecutableRoutingTableTests(unittest.TestCase):
    """P3.2/D6: only the exact executable header is a Routing carrier."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan_dir = fixtures.write_valid_plan(
            Path(self.tmp.name), "ROUTING-TABLE", layout="v2")
        self.routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/high | run | light | test |\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_routing(self, suffix=""):
        path = self.plan_dir / "plan.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "## 3. Routing\n\n", "## 3. Routing\n\n" + self.routing + suffix),
            encoding="utf-8")

    def test_pinned_bounded_route_accepts_stronger_model_and_records_over(self):
        from task import route_evidence
        self._write_routing()
        actual = route_evidence.capture_actual("frontier", "xhigh", source="provider-thread-state", model="gpt-test")
        task_contract.build(self.plan_dir, "P1.1", actual_route=actual)
        contract = task_contract.build(self.plan_dir, "P1.1", actual_route=actual,
            carrier=f"task:plan-run {self.plan_dir.name} P1.1")
        self.assertEqual(contract["route"]["actual"]["model_class"], "frontier")

    def test_declared_frontier_route_has_no_economy_ceiling(self):
        from task import route_evidence
        self.routing = self.routing.replace("implementation/high", "frontier/high")
        self._write_routing()
        actual = route_evidence.capture_actual("frontier", "xhigh", source="provider-thread-state", model="gpt-test")
        task_contract.build(self.plan_dir, "P1.1", actual_route=actual)

    def test_recommended_batch_accepts_a_stronger_route(self):
        from task import route_evidence
        self.routing = self.routing.replace("| test |", "| recommended: test |")
        self._write_routing()
        actual = route_evidence.capture_actual("frontier", "xhigh", source="provider-thread-state", model="gpt-test")
        task_contract.build(self.plan_dir, "P1.1", actual_route=actual)

    def test_adjacent_mapping_table_does_not_change_compiled_route_or_digest(self):
        self._write_routing(
            "\n| Provider | Model | Selector |\n"
            "|:--|:--|:--|\n"
            "| Codex | gpt-5.6-terra | implementation |\n")
        table = task_contract.executable_routing_table(self.plan_dir)
        compiled = task_contract.compile_batch_routing(self.plan_dir)
        self.assertEqual(table["rows"][0][0]["Review"], "light")
        self.assertEqual(compiled["items"]["P1.1"]["review"], "light")
        self.assertEqual(compiled["routing_digest"], table["digest"])

    def test_duplicate_executable_header_refuses_before_admission(self):
        self._write_routing("\n" + self.routing)
        with self.assertRaisesRegex(task_contract.TaskContractBuildError,
                                    "duplicate executable Routing tables"):
            task_contract.admit_batch(self.plan_dir, "P1.1")

    def test_duplicate_item_refuses_from_the_same_compiler(self):
        self._write_routing(
            "| solo | P1.1 | implementation/high | run | full | duplicate |\n")
        with self.assertRaisesRegex(task_contract.TaskContractBuildError,
                                    "item is assigned more than once"):
            task_contract.compile_batch_routing(self.plan_dir)


if __name__ == "__main__":
    unittest.main()
