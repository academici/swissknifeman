"""Tests for `task.route_evidence` — the P2.4 route/budget evidence layer over the
frozen `task.task_contract` route boundary and `task.command_catalog`.

Covers: deterministic REQUIRED derivation (`fixed` vs `inherited-plan` routing modes,
`command-routing.json` via a real `CommandCatalog`); ACTUAL capture with a named,
real source and a preserved timestamp; the four-way `exact/over/under/unknown`
classification where one axis never compensates the other; the two-code fail-closed
`dispatch_guard` that stands strictly upstream of `task_contract.pre_mutation` (an
`unknown` actual denies EARLY, before the route ever reaches a contract — `pre_mutation`
itself also guards an out-of-ladder value on either axis/side as a defense-in-depth
typed `ROUTE_UNDERSHOOT`, P2.10/D78, rather than the raw `.index()` crash it used to
raise); capability support, route-change
boundary, the no-pricing usage/budget schema, the canonical `<model_class>/<effort>`
actor spelling (`findings/02` — 34 observed spellings), and the exact
`task-contract-v1.schema.json` `$defs/route` shape `build_task_contract_route`
assembles — proven end to end against the real committed P0.2 example contract.

Run: cd packages/task && python3 -m unittest discover -s tests
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fixtures  # noqa: F401,E402 — explicit root invocation fallback
from task import journal  # noqa: E402
from task import route_evidence as re  # noqa: E402
from task import task_contract  # noqa: E402
from task.command_catalog import build_command_catalog  # noqa: E402
from core.repo import resolve_plan_dir  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
EXAMPLES_PATH = Path(__file__).resolve().parent / "fixtures_data/task-contract-routine-continuation.json"


def _load_base_contract():
    return copy.deepcopy(json.loads(EXAMPLES_PATH.read_text(encoding="utf-8")))


class CodexInventoryRouteTests(unittest.TestCase):
    def test_explicit_astra_is_frontier_without_ambiguous_launch_default(self):
        from task import route_evidence_codex
        metadata = json.loads(ROUTING_PATH.read_text())
        self.assertEqual(metadata["mappings"]["codex"]["class_selectors"]["frontier"],
                         ["gpt-6-astra"])
        self.assertEqual(route_evidence_codex._selector_class("gpt-6-astra", ROUTING_PATH),
                         "frontier")
        self.assertEqual(route_evidence_codex._selector_class("gpt-6-sol", ROUTING_PATH),
                         "implementation")
        with self.assertRaises(re.RouteEvidenceError):
            route_evidence_codex._selector_class("unlisted-model", ROUTING_PATH)

    def test_overlapping_roles_admit_the_highest_class(self):
        from task import route_evidence_codex
        metadata = json.loads(ROUTING_PATH.read_text())
        metadata["mappings"]["codex"]["model_inventory"]["entries"].append(
            {"id": "overlap-model", "roles": ["implementation", "frontier", "review"]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "routing.json"
            path.write_text(json.dumps(metadata))
            self.assertEqual(route_evidence_codex._selector_class("overlap-model", path), "frontier")


class ModelPoolResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = json.loads(ROUTING_PATH.read_text())

    def resolve(self, provider, model):
        return re.resolve_model_class(provider, model, self.metadata)

    def test_family_patterns_and_versions_resolve_without_plan_edits(self):
        self.assertEqual(self.resolve("claude-code", "claude-sonnet-5-5"), "implementation")
        self.assertEqual(self.resolve("claude-code", "claude-opus-5-5"), "frontier")
        self.assertEqual(self.resolve("claude-code", "claude-fable-5-1"), "frontier")
        self.assertEqual(self.resolve("claude-code", "claude-haiku-4-5-20251001"), "economy")
        self.assertEqual(self.resolve("codex", "gpt-6.1-sol"), "frontier")
        self.assertEqual(self.resolve("codex", "gpt-6.2-sol"), "frontier")
        self.assertEqual(self.resolve("codex", "gpt-6-sol"), "implementation")
        self.assertEqual(self.resolve("cursor", "grok-4.7"), "frontier")
        self.assertEqual(self.resolve("cursor", "grok-4.8"), "frontier")
        self.assertEqual(self.resolve("grok", "grok-4.5"), "economy")
        self.assertEqual(self.resolve("grok", "grok-4.6"), "implementation")
        self.assertEqual(self.resolve("grok", "grok-4.7"), "frontier")

    def test_unknown_model_is_nonterminal_evidence_missing(self):
        for provider, model in (("codex", "unlisted-model"), ("cursor", "auto"),
                                ("claude-code", "claude-mystery-1"),
                                ("grok", "unlisted-model")):
            with self.assertRaises(re.RouteEvidenceError) as caught:
                self.resolve(provider, model)
            self.assertEqual(caught.exception.code, "ROUTE_MODEL_UNKNOWN")

    def test_retired_entry_leaves_the_pool(self):
        metadata = json.loads(json.dumps(self.metadata))
        for entry in metadata["mappings"]["codex"]["model_inventory"]["entries"]:
            if entry["id"] == "gpt-5.6-terra":
                entry["status"] = "retired"
        with self.assertRaises(re.RouteEvidenceError):
            re.resolve_model_class("codex", "gpt-5.6-terra", metadata)

    def test_stronger_actual_class_admits_and_weaker_stops(self):
        required = {"model_class": "implementation", "effort": "high"}
        stronger = re.capture_actual("frontier", "high", source="provider-thread-state", model="m")
        weaker = re.capture_actual("economy", "high", source="provider-thread-state", model="m")
        self.assertIsNone(re.dispatch_guard(required, stronger, ()))
        self.assertEqual(re.dispatch_guard(required, weaker, ()), "ROUTE_UNDERSHOOT")


class RequiredRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        cls.records = cls.catalog.by_id()

    def test_fixed_command_derives_from_command_routing_json(self):
        record = self.records["task:fix"]
        required = re.required_route(record)
        self.assertEqual(required["model_class"], "implementation")
        self.assertEqual(required["effort"], "medium")
        self.assertEqual(required["source"], "command-routing.json")

    def test_every_fixed_command_round_trips_through_classify_as_exact(self):
        for command_id, record in self.records.items():
            if record.routing.mode != "fixed":
                continue
            with self.subTest(command_id=command_id):
                required = re.required_route(record)
                actual = re.capture_actual(
                    required["model_class"], required["effort"], source="provider-doctor")
                self.assertEqual(re.classify(required, actual), "exact")
                self.assertIsNone(re.dispatch_guard(required, actual, ()))

    def test_inherited_plan_command_requires_the_plan_minimum(self):
        record = self.records["task:plan-run"]
        with self.assertRaises(re.RouteEvidenceError) as caught:
            re.required_route(record)
        self.assertEqual(caught.exception.code, "ROUTE_REQUIRED_UNRESOLVED")
        required = re.required_route(record, inherited_minimum=("implementation", "high"))
        self.assertEqual((required["model_class"], required["effort"]), ("implementation", "high"))

    def test_fixed_command_rejects_an_inherited_minimum(self):
        record = self.records["task:fix"]
        with self.assertRaises(re.RouteEvidenceError) as caught:
            re.required_route(record, inherited_minimum=("frontier", "xhigh"))
        self.assertEqual(caught.exception.code, "ROUTE_REQUIRED_UNRESOLVED")


class CaptureActualTests(unittest.TestCase):
    def test_self_attestation_cannot_turn_a_selector_into_actual_route_evidence(self):
        with self.assertRaises(re.RouteEvidenceError) as caught:
            re.capture_actual(
                "implementation", "high", source="self-attested", model="gpt-5.6-terra")
        self.assertEqual(caught.exception.code, "ROUTE_ACTUAL_SOURCE_UNDECLARED")

    def test_valid_source_stamps_a_timestamp(self):
        evidence = re.capture_actual("implementation", "high", source="provider-doctor")
        self.assertEqual(evidence["source"], "provider-doctor")
        self.assertTrue(evidence["ts"])

    def test_provider_config_source_is_declared(self):
        evidence = re.capture_actual("implementation", "high", source="provider-config",
                                     model="gpt-5.6-terra")
        self.assertEqual(evidence["source"], "provider-config")
        self.assertEqual(evidence["model"], "gpt-5.6-terra")

    def test_provider_thread_state_source_is_declared(self):
        evidence = re.capture_actual(
            "frontier", "high", source="provider-thread-state", model="gpt-5.6-sol")
        self.assertEqual(evidence["source"], "provider-thread-state")
        self.assertEqual(evidence["model"], "gpt-5.6-sol")

    def test_explicit_timestamp_is_preserved_verbatim(self):
        evidence = re.capture_actual(
            "frontier", "xhigh", source="provider-doctor", ts="2026-07-26T00:00:00Z")
        self.assertEqual(evidence["ts"], "2026-07-26T00:00:00Z")

    def test_unknown_axes_survive_as_none(self):
        evidence = re.capture_actual(None, None, source="self-attested")
        self.assertIsNone(evidence["model_class"])
        self.assertIsNone(evidence["effort"])

    def test_undeclared_source_fails_closed(self):
        with self.assertRaises(re.RouteEvidenceError) as caught:
            re.capture_actual("implementation", "high", source="requested-model")
        self.assertEqual(caught.exception.code, "ROUTE_ACTUAL_SOURCE_UNDECLARED")

    def test_off_ladder_axis_fails_closed(self):
        with self.assertRaises(re.RouteEvidenceError) as caught:
            re.capture_actual("sonnet", "high", source="self-attested")
        self.assertEqual(caught.exception.code, "ROUTE_ACTUAL_SOURCE_UNDECLARED")


class OwnerAttestationTests(unittest.TestCase):
    def _workflow_attestation(self):
        evidence = re.capture_actual(
            "implementation", "medium", source="provider-thread-state",
            model="gpt-5.6-terra", ts="2026-09-22T10:00:00Z")
        evidence.update({
            "thread_id": "thread-1", "source_version": "codex-turn-context-v1",
            "cwd": "/workspace/repo",
            "invocation": "$ task:plan-run PLAN P1.1",
            "owner_message_digest": "a" * 64,
        })
        return re.build_owner_attestation(
            evidence, provider="codex", plan_id="PLAN", item_id="P1.1",
            action_digest="b" * 64, audience="task.owner-authority",
            expires_at="2026-09-22T10:05:00Z", nonce="nonce-1")

    def _expected(self):
        return {"provider": "codex", "cwd": "/workspace/repo", "plan_id": "PLAN",
                "item_id": "P1.1", "action_digest": "b" * 64,
                "command": "task:plan-run", "arguments": "PLAN P1.1",
                "audience": "task.owner-authority", "session_id": "thread-1",
                "owner_message_digest": "a" * 64}

    def test_local_provider_state_is_workflow_guard_only(self):
        attestation = self._workflow_attestation()
        result = re.verify_owner_attestation(
            attestation, expected=self._expected(), protected=False,
            now=datetime(2026, 9, 22, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(result["boundary"], "workflow-guard")
        with self.assertRaisesRegex(re.RouteEvidenceError, "OWNER_ATTESTATION_UNSUPPORTED"):
            re.verify_owner_attestation(
                attestation, expected=self._expected(), protected=True,
                now=datetime(2026, 9, 22, 10, 1, tzinfo=timezone.utc))

    def test_exact_fields_binding_and_expiry_fail_closed(self):
        attestation = self._workflow_attestation()
        with self.assertRaisesRegex(re.RouteEvidenceError, "OWNER_ATTESTATION_INVALID"):
            re.verify_owner_attestation(
                {**attestation, "extra": True}, expected=self._expected(), protected=False,
                now=datetime(2026, 9, 22, 10, 1, tzinfo=timezone.utc))
        with self.assertRaisesRegex(re.RouteEvidenceError, "OWNER_ATTESTATION_INVALID"):
            re.verify_owner_attestation(
                {**attestation, "subject": {"audience": "task.owner-authority"}},
                expected=self._expected(), protected=False,
                now=datetime(2026, 9, 22, 10, 1, tzinfo=timezone.utc))
        with self.assertRaisesRegex(re.RouteEvidenceError, "OWNER_ATTESTATION_MISMATCH"):
            re.verify_owner_attestation(
                attestation, expected={**self._expected(), "item_id": "P1.2"},
                protected=False, now=datetime(2026, 9, 22, 10, 1, tzinfo=timezone.utc))
        with self.assertRaisesRegex(re.RouteEvidenceError, "OWNER_ATTESTATION_EXPIRED"):
            re.verify_owner_attestation(
                attestation, expected=self._expected(), protected=False,
                now=datetime(2026, 9, 22, 10, 6, tzinfo=timezone.utc))

    def test_security_boundary_requires_verifier_and_single_use_nonce(self):
        attestation = {**self._workflow_attestation(), "boundary": "security-boundary",
                       "issuer": "provider:codex", "proof": "opaque-provider-proof"}
        used = set()

        def consume(issuer, nonce, digest):
            key = (issuer, nonce, digest)
            if key in used:
                return False
            used.add(key)
            return True

        now = datetime(2026, 9, 22, 10, 1, tzinfo=timezone.utc)
        self.assertTrue(re.verify_owner_attestation(
            attestation, expected=self._expected(), verifier=lambda value: bool(value["proof"]),
            nonce_consumer=consume, protected=True, now=now)["verified"])
        with self.assertRaisesRegex(re.RouteEvidenceError, "OWNER_ATTESTATION_REPLAYED"):
            re.verify_owner_attestation(
                attestation, expected=self._expected(), verifier=lambda value: True,
                nonce_consumer=consume, protected=True, now=now)


class ClassifyTests(unittest.TestCase):
    REQUIRED = {"model_class": "implementation", "effort": "high"}

    def test_exact_match(self):
        actual = {"model_class": "implementation", "effort": "high"}
        self.assertEqual(re.classify(self.REQUIRED, actual), "exact")

    def test_overshoot_on_either_axis(self):
        self.assertEqual(
            re.classify(self.REQUIRED, {"model_class": "frontier", "effort": "high"}), "over")
        self.assertEqual(
            re.classify(self.REQUIRED, {"model_class": "implementation", "effort": "xhigh"}), "over")

    def test_undershoot_on_either_axis(self):
        self.assertEqual(
            re.classify(self.REQUIRED, {"model_class": "economy", "effort": "high"}), "under")
        self.assertEqual(
            re.classify(self.REQUIRED, {"model_class": "implementation", "effort": "medium"}), "under")

    def test_unknown_wins_over_a_generous_other_axis(self):
        # One axis never compensates the other: a frontier actual with unknown effort
        # is "unknown", never "over" on the strength of the model-class axis alone.
        actual = {"model_class": "frontier", "effort": None}
        self.assertEqual(re.classify(self.REQUIRED, actual), "unknown")

    def test_unknown_wins_over_an_undershooting_other_axis(self):
        actual = {"model_class": "economy", "effort": None}
        self.assertEqual(re.classify(self.REQUIRED, actual), "unknown")


class CapabilitySupportTests(unittest.TestCase):
    def test_bound_capability_reports_its_support_level(self):
        result = re.capability_support(
            ["command.subagents", "command.git-write"],
            {"command.subagents": "native", "command.git-write": "adapted"})
        self.assertEqual(result, (
            {"id": "command.subagents", "support": "native"},
            {"id": "command.git-write", "support": "adapted"},
        ))

    def test_missing_binding_is_unsupported_not_native_by_default(self):
        result = re.capability_support(["command.interactive-user-input"], {})
        self.assertEqual(result, ({"id": "command.interactive-user-input", "support": "unsupported"},))


class DispatchGuardTests(unittest.TestCase):
    REQUIRED = {"model_class": "implementation", "effort": "high"}
    CAPS_OK = ({"id": "command.subagents", "support": "native"},)

    def test_exact_and_overshoot_allow(self):
        exact = {"model_class": "implementation", "effort": "high"}
        over = {"model_class": "frontier", "effort": "xhigh"}
        self.assertIsNone(re.dispatch_guard(self.REQUIRED, exact, self.CAPS_OK))
        self.assertIsNone(re.dispatch_guard(self.REQUIRED, over, self.CAPS_OK))

    def test_undershoot_denies_with_the_frozen_p02_code(self):
        under = {"model_class": "economy", "effort": "high"}
        self.assertEqual(re.dispatch_guard(self.REQUIRED, under, self.CAPS_OK), "ROUTE_UNDERSHOOT")

    def test_unknown_actual_is_distinct_from_measured_undershoot(self):
        unknown = {"model_class": "implementation", "effort": None}
        self.assertEqual(
            re.dispatch_guard(self.REQUIRED, unknown, self.CAPS_OK), "ROUTE-UNVERIFIABLE")

    def test_unknown_actual_is_a_waiting_gate_not_config_recovery(self):
        actual = re.capture_actual(None, None, source="self-attested")
        self.assertEqual(
            re.dispatch_guard(self.REQUIRED, actual, self.CAPS_OK), "ROUTE-UNVERIFIABLE")

    def test_route_checked_before_capability(self):
        under = {"model_class": "economy", "effort": "high"}
        unsupported = ({"id": "command.subagents", "support": "unsupported"},)
        self.assertEqual(re.dispatch_guard(self.REQUIRED, under, unsupported), "ROUTE_UNDERSHOOT")

    def test_unsupported_capability_denies_once_route_is_fine(self):
        exact = {"model_class": "implementation", "effort": "high"}
        unsupported = ({"id": "command.subagents", "support": "unsupported"},)
        self.assertEqual(
            re.dispatch_guard(self.REQUIRED, exact, unsupported), "CAPABILITY_UNSUPPORTED")


class RouteChangeBoundaryTests(unittest.TestCase):
    def test_same_route_reports_unchanged(self):
        before = re.capture_actual("implementation", "high", source="provider-doctor", ts="t0")
        after = re.capture_actual("implementation", "high", source="provider-doctor", ts="t1")
        result = re.route_change_boundary(before, after)
        self.assertFalse(result["changed"])
        self.assertEqual(result["before"], before)
        self.assertEqual(result["after"], after)

    def test_switched_route_reports_changed(self):
        before = re.capture_actual("implementation", "high", source="provider-doctor")
        after = re.capture_actual("frontier", "high", source="provider-doctor")
        self.assertTrue(re.route_change_boundary(before, after)["changed"])


class CaptureBudgetTests(unittest.TestCase):
    def test_declared_axes_pass_through_omitted_as_none(self):
        budget = re.capture_budget(**{"in": 100, "out": 40})
        self.assertEqual(budget, {"in": 100, "out": 40, "cache_read": None,
                                 "cache_creation": None, "duration_ms": None, "tool_calls": None})

    def test_undeclared_axis_fails_closed(self):
        with self.assertRaises(re.RouteEvidenceError) as caught:
            re.capture_budget(cost_usd=1.5)
        self.assertEqual(caught.exception.code, "ROUTE_BUDGET_AXIS_UNKNOWN")

    def test_negative_or_boolean_count_fails_closed(self):
        with self.assertRaises(re.RouteEvidenceError):
            re.capture_budget(**{"in": -1})
        with self.assertRaises(re.RouteEvidenceError):
            re.capture_budget(tool_calls=True)


class CanonicalActorTests(unittest.TestCase):
    """D72/F8 repair: `canonical_actor` now carries the concrete MODEL
    (`sonnet/high`), never the route-evidence class — `model_class` stays a
    separate axis in `route.actual`/`capture_actual`'s own field."""

    def test_known_pair_formats_verbatim(self):
        self.assertEqual(re.canonical_actor("sonnet", "high"), "sonnet/high")

    def test_unknown_effort_renders_the_literal_unknown(self):
        self.assertEqual(re.canonical_actor("opus", None), "opus/unknown")
        self.assertEqual(re.canonical_actor("opus", "guessed"), "opus/unknown")

    def test_absent_model_renders_the_literal_unknown(self):
        self.assertEqual(re.canonical_actor(None, "high"), "unknown/high")

    def test_non_string_model_renders_the_literal_unknown(self):
        self.assertEqual(re.canonical_actor(123, "high"), "unknown/high")

    def test_model_class_is_a_separate_axis_never_substituted_for_model(self):
        # F8's exact defect: required/actual collapsing to the same class string.
        # A caller passing the CLASS instead of a concrete model gets it back
        # verbatim — canonical_actor never validates or maps it, it is free-form
        # provider evidence, not the frozen P0.2 route ladder.
        self.assertEqual(re.canonical_actor("implementation", "high"), "implementation/high")


class BuildTaskContractRouteTests(unittest.TestCase):
    def test_shape_matches_the_frozen_schema_exactly(self):
        required = {"model_class": "implementation", "effort": "high", "source": "x", "ts": None}
        actual = {"model_class": "implementation", "effort": "high", "source": "y", "ts": "t"}
        caps = re.capability_support(["command.subagents"], {"command.subagents": "native"})
        route = re.build_task_contract_route(required, actual, caps)
        self.assertEqual(set(route), {"required", "actual", "capabilities"})
        self.assertEqual(set(route["required"]), {"model_class", "effort"})
        self.assertEqual(set(route["actual"]), {"model_class", "effort"})
        self.assertEqual(set(route["capabilities"][0]), {"id", "support"})

    def test_guard_allows_then_the_route_feeds_pre_mutation_unchanged(self):
        contract = _load_base_contract()
        self.assertIsNone(task_contract.pre_mutation(contract))
        required = contract["route"]["required"]
        actual = re.capture_actual(required["model_class"], required["effort"], source="provider-doctor")
        caps = re.capability_support(
            [c["id"] for c in contract["route"]["capabilities"]],
            {c["id"]: c["support"] for c in contract["route"]["capabilities"]})
        self.assertIsNone(re.dispatch_guard(required, actual, caps))
        contract["route"] = re.build_task_contract_route(required, actual, caps)
        contract["version"]["content_hash"] = task_contract.content_hash(contract)
        self.assertIsNone(task_contract.pre_mutation(contract))

    def test_guard_denies_before_pre_mutation_ever_sees_an_unknown_actual(self):
        # `dispatch_guard` denies EARLY, before a `None` axis ever reaches a compiled
        # contract. `task_contract.pre_mutation` itself also guards the same axis as
        # defense in depth: a caller that skips the guard and feeds
        # `pre_mutation` an unresolved actual gets the distinct nonterminal code,
        # never the raw `.index()` crash this predicate used to raise.
        contract = _load_base_contract()
        required = contract["route"]["required"]
        unknown_actual = re.capture_actual(required["model_class"], None, source="provider-doctor")
        caps = re.capability_support(
            [c["id"] for c in contract["route"]["capabilities"]],
            {c["id"]: c["support"] for c in contract["route"]["capabilities"]})
        self.assertEqual(
            re.dispatch_guard(required, unknown_actual, caps), "ROUTE-UNVERIFIABLE")
        broken = copy.deepcopy(contract)
        broken["route"]["actual"]["effort"] = None
        broken["version"]["content_hash"] = task_contract.content_hash(broken)
        self.assertEqual(task_contract.pre_mutation(broken), "ROUTE-UNVERIFIABLE")

    def test_run_receipt_survives_dialogue_and_rejects_route_change(self):
        evidence = re.capture_actual(
            "implementation", "high", source="provider-thread-state",
            model="gpt-5.6-terra")
        evidence.update({
            "thread_id": "session-1", "source_version": "fixture-v1",
            "cwd": "/workspace/repo", "invocation": "$ task:plan-run PLAN P1.1",
        })
        receipt = re.build_run_receipt(
            plan_id="PLAN", item_id="P1.1", attempt=1, session_id="session-1",
            run_id="run-1", evidence=evidence)
        self.assertTrue(re.verify_run_receipt(
            receipt, plan_id="PLAN", item_id="P1.1", run_id="run-1",
            current_evidence=dict(evidence)))
        changed = {**evidence, "effort": "medium"}
        with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_RECEIPT_MISMATCH"):
            re.verify_run_receipt(receipt, current_evidence=changed)

    def test_run_receipt_ttl_is_fail_closed(self):
        captured = datetime(2026, 8, 13, tzinfo=timezone.utc)
        evidence = re.capture_actual(
            "implementation", "high", source="provider-thread-state",
            model="gpt-5.6-terra", ts=captured.strftime("%Y-%m-%dT%H:%M:%SZ"))
        evidence.update({
            "thread_id": "session-1", "source_version": "fixture-v1",
            "cwd": "/workspace/repo", "invocation": "$ task:plan-run PLAN P1.1",
        })
        receipt = re.build_run_receipt(
            plan_id="PLAN", item_id="P1.1", attempt=1, session_id="session-1",
            run_id="run-1", evidence=evidence)
        with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_RECEIPT_EXPIRED"):
            re.verify_run_receipt(
                receipt, now=captured + timedelta(days=2), max_age_seconds=86400)

    def test_run_receipt_rejects_future_capture(self):
        captured = datetime(2026, 8, 13, 0, 0, 1, tzinfo=timezone.utc)
        evidence = re.capture_actual(
            "implementation", "high", source="provider-thread-state",
            model="gpt-5.6-terra", ts=captured.strftime("%Y-%m-%dT%H:%M:%SZ"))
        evidence.update({
            "thread_id": "session-1", "source_version": "fixture-v1",
            "cwd": "/workspace/repo", "invocation": "$ task:plan-run PLAN P1.1",
        })
        receipt = re.build_run_receipt(
            plan_id="PLAN", item_id="P1.1", attempt=1, session_id="session-1",
            run_id="run-1", evidence=evidence)
        with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_RECEIPT_INVALID"):
            re.verify_run_receipt(
                receipt, now=datetime(2026, 8, 13, tzinfo=timezone.utc))


class JournalActorIntegrationTests(unittest.TestCase):
    """`task.journal append --route-evidence` — the canonical actor spelling
    derives from captured route evidence instead of being hand-typed at the call
    site (`findings/02` — 34 observed spellings). Exercised here, not in
    `test_journal.py`, since it is this item's own new call path, not journal's."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plan_dir = self.root / "P"
        self.plan_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write_evidence(self, evidence):
        path = self.root / "route.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        return path

    def test_route_evidence_flag_derives_the_canonical_actor(self):
        evidence_path = self._write_evidence(
            re.capture_actual("implementation", "high", source="provider-doctor", model="sonnet"))
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--route-evidence", str(evidence_path),
            "--result", "in-progress",
        ])
        self.assertEqual(rc, 0)
        entry = json.loads((self.plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(entry["actor"], "sonnet/high")

    def test_historical_evidence_without_a_model_field_renders_the_literal_unknown(self):
        # Backward-compat: an evidence blob predating this item's `model`
        # field must not crash the CLI — `.get("model")` renders `unknown`.
        evidence_path = self._write_evidence({"model_class": "implementation", "effort": "high"})
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--route-evidence", str(evidence_path),
            "--result", "in-progress",
        ])
        self.assertEqual(rc, 0)
        entry = json.loads((self.plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(entry["actor"], "unknown/high")

    def test_actor_and_route_evidence_are_mutually_exclusive(self):
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--result", "closed-green",
        ])
        self.assertEqual(rc, 1)
        self.assertFalse((self.plan_dir / "journal.jsonl").exists())
        evidence_path = self._write_evidence(
            re.capture_actual("implementation", "high", source="provider-doctor"))
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--actor", "implementation/high",
            "--route-evidence", str(evidence_path), "--result", "closed-green",
        ])
        self.assertEqual(rc, 1)

    def test_unreadable_route_evidence_fails_closed(self):
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run",
            "--route-evidence", str(self.root / "missing.json"), "--result", "closed-green",
        ])
        self.assertEqual(rc, 1)
        self.assertFalse((self.plan_dir / "journal.jsonl").exists())

    def test_unknown_effort_in_evidence_still_derives_a_canonical_unknown_actor(self):
        evidence_path = self._write_evidence(
            re.capture_actual("implementation", None, source="provider-doctor", model="sonnet"))
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--route-evidence", str(evidence_path),
            "--result", "in-progress",
        ])
        self.assertEqual(rc, 0)
        entry = json.loads((self.plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(entry["actor"], "sonnet/unknown")


class CodexLaunchEvidenceTests(unittest.TestCase):
    def test_plan_run_reviewer_spelling_matches_typed_scope_and_preserves_owner_line(self):
        from task import route_evidence_codex
        raw = "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.7/500K/high/"
        equivalent = ("$ task:plan-run PLAN P1.1 P1.2 --reviewer grok/grok-4.7/500000 --review-effort high",
                      "$ task:plan-run PLAN P1.1–P1.2 --review-effort=high --reviewer=grok/grok-4.7/500k",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer grok/grok-4.7/500k/hight/")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_thread_state(root, thread_id="typed-reviewer", model="gpt-6.1-sol",
                                            effort="high", prompt=raw)
            source = path.read_bytes()
            for expected in equivalent:
                evidence = route_evidence_codex.capture_current(expected_invocation=expected,
                    expected_cwd="/workspace/repo", thread_id="typed-reviewer", state_root=root)
                self.assertEqual(evidence["invocation"], raw)
                self.assertEqual(evidence["model"], "gpt-6.1-sol")
            self.assertEqual(path.read_bytes(), source)

    def test_typed_plan_run_scope_and_reviewer_mismatches_stay_closed(self):
        from task import route_evidence_codex
        expected = "$ task:plan-run PLAN P1.1 P1.2 --reviewer grok/grok-4.7/500k --review-effort high"
        mismatches = ("$ task:plan-run OTHER P1.1 P1.2 --reviewer=grok/grok-4.7/500k",
                      "$ task:plan-run PLAN P1.2 P1.1 --reviewer=grok/grok-4.7/500k",
                      "$ task:plan-run PLAN P1 --reviewer=grok/grok-4.7/500k",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=codex/grok-4.7/500k",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.6/500k",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.7/256k",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.7/500k/low",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.7/500k/high --review-effort=low",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.7/500k --reviewer=grok/grok-4.7/500k",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer=grok/grok-4.7/500k --unknown=high",
                      "$ task:plan-run PLAN P1.1 P1.2 --reviewer='grok/grok-4.7/500k",
                      "$ task:plan-run PLAN P1.1 P1.2 --review-effort=high")
        for actual in mismatches:
            self.assertFalse(route_evidence_codex._contains_invocation(actual, expected), actual)

    def test_local_owner_invocation_survives_addition_but_not_revoke(self):
        from task import route_evidence_codex
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = "$ task:plan-run PLAN P0.3"
            path = self._write_thread_state(root, thread_id="owner-local", model="gpt-5.6-terra",
                                            effort="high", prompt=prompt)
            options = dict(expected_invocation=prompt, expected_cwd="/workspace/repo",
                           thread_id="owner-local", state_root=root,
                           require_current_owner_invocation=True, allow_additive_owner_followup=True)
            original = route_evidence_codex.capture_current(**options)
            for message in ("Also explain the result", "revoke this grant"):
                with path.open("a") as stream:
                    stream.write(json.dumps({"type": "response_item", "payload": {
                        "type": "message", "role": "user", "content": [{"type": "input_text", "text": message}]}}) + "\n")
                if message.startswith("revoke"):
                    with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_LAUNCH_MISMATCH"):
                        route_evidence_codex.capture_current(**options)
                else:
                    self.assertEqual(route_evidence_codex.capture_current(**options)["owner_message_digest"], original["owner_message_digest"])

    def _write_thread_state(self, root, *, thread_id, model, effort, prompt,
                            cwd="/workspace/repo"):
        path = root / "2026" / "08" / "12" / f"rollout-{thread_id}.jsonl"
        path.parent.mkdir(parents=True)
        turn_context = {"type": "turn_context", "payload": {
            "turn_id": f"turn-{thread_id}", "model": model, "effort": effort,
            "cwd": cwd, "approval_policy": "never",
            "sandbox_policy": {"type": "danger-full-access"},
        }}
        events = (
            {"type": "session_meta", "payload": {
                "id": thread_id, "cwd": cwd, "model_provider": "openai",
            }},
            turn_context,
            {"type": "event_msg", "payload": {
                "type": "item_completed", "turn_id": f"turn-{thread_id}",
                "item": {"type": "UserMessage", "content": [
                    {"type": "text", "text": prompt},
                ]},
            }},
            # Compaction may re-emit the same turn context after the user event.
            turn_context,
        )
        path.write_text(
            "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
            encoding="utf-8",
        )
        return path

    def test_interactive_thread_state_proves_current_route_without_launch_selectors(self):
        from task import route_evidence_codex

        prompt = "$ task:plan-run PLAN P0.3"
        prompt_with_payload = prompt + "\n\nMODE: bounded audit repair-forward"
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            self._write_thread_state(
                state_root, thread_id="thread-after-clear", model="gpt-5.6-terra",
                effort="high", prompt=prompt_with_payload,
            )
            process_table = {
                200: (100, ("python3", "-m", "task.route_evidence_codex", "capture")),
                100: (1, (
                    "codex", "-c", 'approval_policy="never"',
                    "-s", "danger-full-access",
                )),
            }

            evidence = route_evidence_codex.capture_current(
                expected_invocation=prompt,
                expected_cwd="/workspace/repo",
                thread_id="thread-after-clear",
                start_pid=200,
                process_table=process_table,
                state_root=state_root,
            )

        self.assertEqual(evidence["model"], "gpt-5.6-terra")
        self.assertEqual(evidence["model_class"], "implementation")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["source"], "provider-thread-state")
        self.assertEqual(evidence["thread_id"], "thread-after-clear")
        self.assertEqual(evidence["source_version"], "codex-turn-context-v1")

    def test_current_thread_state_wins_over_stale_native_launch_route(self):
        from task import route_evidence_codex

        prompt = "$ task:plan-run PLAN P0.3"
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            self._write_thread_state(
                state_root, thread_id="thread-123", model="gpt-5.6-terra",
                effort="medium", prompt=prompt,
            )
            process_table = {
                200: (100, ("python3", "-m", "task.route_evidence_codex", "capture")),
                100: (1, (
                    "codex", "-C", "/workspace/repo", "-m", "gpt-5.6-sol",
                    "-c", 'model_reasoning_effort="high"', "-a", "never",
                    "-s", "danger-full-access", prompt,
                )),
            }

            evidence = route_evidence_codex.capture_current(
                expected_invocation=prompt,
                expected_cwd="/workspace/repo",
                thread_id="thread-123",
                start_pid=200,
                process_table=process_table,
                state_root=state_root,
            )

        self.assertEqual(evidence["model"], "gpt-5.6-terra")
        self.assertEqual(evidence["effort"], "medium")
        self.assertEqual(evidence["source"], "provider-thread-state")

    def test_thread_state_keeps_the_latest_task_invocation_through_a_follow_up_turn(self):
        from task import route_evidence_codex

        prompt = "$ task:plan-run PLAN P0.3"
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            path = self._write_thread_state(
                state_root, thread_id="thread-follow-up", model="gpt-5.6-terra",
                effort="medium", prompt=prompt,
            )
            follow_up_context = {"type": "turn_context", "payload": {
                "turn_id": "turn-follow-up-2", "model": "gpt-5.6-terra", "effort": "medium",
                "cwd": "/workspace/repo", "approval_policy": "never",
                "sandbox_policy": {"type": "danger-full-access"},
            }}
            follow_up_message = {"type": "event_msg", "payload": {
                "type": "item_completed", "turn_id": "turn-follow-up-2",
                "item": {"type": "UserMessage", "content": [
                    {"type": "text", "text": "Continue execution."},
                ]},
            }}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(follow_up_context, ensure_ascii=False) + "\n")
                handle.write(json.dumps(follow_up_message, ensure_ascii=False) + "\n")

            evidence = route_evidence_codex.capture_current(
                expected_invocation=prompt,
                expected_cwd="/workspace/repo",
                thread_id="thread-follow-up",
                state_root=state_root,
            )

        self.assertEqual(evidence["model_class"], "implementation")
        self.assertEqual(evidence["effort"], "medium")

    def test_thread_state_accepts_semantic_task_invocation_without_shell_prompt_marker(self):
        from task import route_evidence_codex

        expected = "$ task:plan-run PLAN P5.6"
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            self._write_thread_state(
                state_root, thread_id="thread-natural-invocation", model="gpt-5.6-sol",
                effort="high", prompt="task:plan-run PLAN P5.6",
            )

            evidence = route_evidence_codex.capture_current(
                expected_invocation=expected,
                expected_cwd="/workspace/repo",
                thread_id="thread-natural-invocation",
                state_root=state_root,
            )

        self.assertEqual(evidence["invocation"], expected)
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "high")

    def test_thread_state_rejects_a_prompt_from_an_older_turn(self):
        from task import route_evidence_codex

        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            self._write_thread_state(
                state_root, thread_id="thread-123", model="gpt-5.6-sol",
                effort="high", prompt="$ task:plan-run PLAN P0.2",
            )
            with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_LAUNCH_MISMATCH"):
                route_evidence_codex.capture_current(
                    expected_invocation="$ task:plan-run PLAN P0.3",
                    expected_cwd="/workspace/repo",
                    thread_id="thread-123",
                    state_root=state_root,
                )

    def test_owner_grant_cannot_reuse_old_invocation_after_new_user_turn(self):
        from task import route_evidence_codex
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = "$ task:plan-run PLAN P0.3"
            path = self._write_thread_state(root, thread_id="owner-current", model="gpt-5.6-terra",
                                            effort="high", prompt=prompt)
            evidence = route_evidence_codex.capture_current(expected_invocation=prompt,
                expected_cwd="/workspace/repo", thread_id="owner-current", state_root=root,
                require_current_owner_invocation=True)
            self.assertIn("owner_message_digest", evidence)
            with path.open("a") as stream:
                stream.write(json.dumps({"type": "response_item", "payload": {
                    "type": "message", "role": "user", "content": [{"type": "input_text", "text": "Review only"}]}}) + "\n")
            with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_LAUNCH_MISMATCH"):
                route_evidence_codex.capture_current(expected_invocation=prompt,
                    expected_cwd="/workspace/repo", thread_id="owner-current", state_root=root,
                    require_current_owner_invocation=True)

    def test_exact_native_launch_is_captured_from_the_current_ancestor_chain(self):
        from task import route_evidence_codex

        process_table = {
            300: (200, ("python3", "-m", "task.route_evidence_codex", "capture")),
            200: (100, ("/bin/bash", "-c", "python3 -m task.route_evidence_codex capture")),
            100: (1, (
                "codex", "-C", "/workspace/repo", "-m", "gpt-5.6-sol",
                "-c", 'model_reasoning_effort="high"', "-a", "never",
                "-s", "danger-full-access",
                "$ task:plan-run 2026.08.12-№1-DEMO-PLAN P0.3",
            )),
        }

        with tempfile.TemporaryDirectory() as directory:
            evidence = route_evidence_codex.capture_current(
                expected_invocation="$ task:plan-run 2026.08.12-№1-DEMO-PLAN P0.3",
                expected_cwd="/workspace/repo",
                thread_id="thread-123",
                start_pid=300,
                process_table=process_table,
                state_root=Path(directory),
            )

        self.assertEqual(evidence["model"], "gpt-5.6-sol")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["source"], "cli-flag")
        self.assertEqual(evidence["thread_id"], "thread-123")
        self.assertEqual(evidence["source_version"], "codex-ancestor-argv-v1")

    def test_wrong_prompt_is_rejected_instead_of_reusing_a_stale_codex_session(self):
        from task import route_evidence_codex

        process_table = {
            200: (100, ("python3", "-m", "task.route_evidence_codex", "capture")),
            100: (1, (
                "codex", "-C", "/workspace/repo", "-m", "gpt-5.6-sol",
                "-c", 'model_reasoning_effort="high"', "-a", "never",
                "-s", "danger-full-access", "$ task:plan-run PLAN P0.2",
            )),
        }

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(re.RouteEvidenceError, "ROUTE_LAUNCH_MISMATCH"):
                route_evidence_codex.capture_current(
                    expected_invocation="$ task:plan-run PLAN P0.3",
                    expected_cwd="/workspace/repo",
                    thread_id="thread-123",
                    start_pid=200,
                    process_table=process_table,
                    state_root=Path(directory),
                )


if __name__ == "__main__":
    unittest.main()
