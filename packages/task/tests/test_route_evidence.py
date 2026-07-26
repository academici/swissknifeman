"""Tests for `task.route_evidence` — the P2.4 route/budget evidence layer over the
frozen `task.task_contract` route boundary (P2.2) and `task.command_catalog` (P1/P2.1).

Covers: deterministic REQUIRED derivation (`fixed` vs `inherited-plan` routing modes,
`command-routing.json` via a real `CommandCatalog`); ACTUAL capture with a named,
real source and a preserved timestamp; the four-way `exact/over/under/unknown`
classification where one axis never compensates the other; the two-code fail-closed
`dispatch_guard` that stands strictly upstream of `task_contract.pre_mutation` (an
`unknown` actual would crash that predicate's `.index()` lookup — this guard is what
prevents it from ever being called with one); capability support, route-change
boundary, the no-pricing usage/budget schema, the canonical `<model_class>/<effort>`
actor spelling (`findings/02` — 34 observed spellings), and the exact
`task-contract-v1.schema.json` `$defs/route` shape `build_task_contract_route`
assembles — proven end to end against the real committed P0.2 example contract.

Run: cd packages/task && python3 -m unittest discover -s tests
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401,E402 — puts lib/ on sys.path
from task import journal  # noqa: E402
from task import route_evidence as re  # noqa: E402
from task import task_contract  # noqa: E402
from task.command_catalog import build_command_catalog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
EXAMPLES_PATH = (REPO_ROOT / "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.2/"
                 "task-contract-examples.json")


def _load_base_contract():
    document = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    for example in document["examples"]:
        if example["id"] == "routine-continuation":
            return copy.deepcopy(example["contract"])
    raise AssertionError("fixture example 'routine-continuation' not found")


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
                    required["model_class"], required["effort"], source="self-attested")
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
    def test_valid_source_stamps_a_timestamp(self):
        evidence = re.capture_actual("implementation", "high", source="self-attested")
        self.assertEqual(evidence["source"], "self-attested")
        self.assertTrue(evidence["ts"])

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

    def test_unknown_actual_denies_as_undershoot_not_a_new_code(self):
        # Implementation Rules: "Missing actual effort is unknown and fails a
        # route-required dispatch" — reuses ROUTE_UNDERSHOOT, never mints a third code.
        unknown = {"model_class": "implementation", "effort": None}
        self.assertEqual(re.dispatch_guard(self.REQUIRED, unknown, self.CAPS_OK), "ROUTE_UNDERSHOOT")

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
        before = re.capture_actual("implementation", "high", source="self-attested", ts="t0")
        after = re.capture_actual("implementation", "high", source="self-attested", ts="t1")
        result = re.route_change_boundary(before, after)
        self.assertFalse(result["changed"])
        self.assertEqual(result["before"], before)
        self.assertEqual(result["after"], after)

    def test_switched_route_reports_changed(self):
        before = re.capture_actual("implementation", "high", source="self-attested")
        after = re.capture_actual("frontier", "high", source="self-attested")
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
        actual = re.capture_actual(required["model_class"], required["effort"], source="self-attested")
        caps = re.capability_support(
            [c["id"] for c in contract["route"]["capabilities"]],
            {c["id"]: c["support"] for c in contract["route"]["capabilities"]})
        self.assertIsNone(re.dispatch_guard(required, actual, caps))
        contract["route"] = re.build_task_contract_route(required, actual, caps)
        contract["version"]["content_hash"] = task_contract.content_hash(contract)
        self.assertIsNone(task_contract.pre_mutation(contract))

    def test_guard_denies_before_pre_mutation_ever_sees_an_unknown_actual(self):
        # `task_contract.pre_mutation` would raise ValueError on a `None` axis
        # (`.index()`); the guard is what stops that call from ever happening.
        contract = _load_base_contract()
        required = contract["route"]["required"]
        unknown_actual = re.capture_actual(required["model_class"], None, source="self-attested")
        caps = re.capability_support(
            [c["id"] for c in contract["route"]["capabilities"]],
            {c["id"]: c["support"] for c in contract["route"]["capabilities"]})
        self.assertEqual(re.dispatch_guard(required, unknown_actual, caps), "ROUTE_UNDERSHOOT")
        broken = copy.deepcopy(contract)
        broken["route"]["actual"]["effort"] = None
        broken["version"]["content_hash"] = task_contract.content_hash(broken)
        with self.assertRaises(ValueError):
            task_contract.pre_mutation(broken)


class JournalActorIntegrationTests(unittest.TestCase):
    """`task.journal append --route-evidence` (P2.4) — the canonical actor spelling
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
            re.capture_actual("implementation", "high", source="self-attested", model="sonnet"))
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--route-evidence", str(evidence_path),
            "--result", "closed-green",
        ])
        self.assertEqual(rc, 0)
        entry = json.loads((self.plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(entry["actor"], "sonnet/high")

    def test_historical_evidence_without_a_model_field_renders_the_literal_unknown(self):
        # Backward-compat (D72): an evidence blob predating this item's `model`
        # field must not crash the CLI — `.get("model")` renders `unknown`.
        evidence_path = self._write_evidence({"model_class": "implementation", "effort": "high"})
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--route-evidence", str(evidence_path),
            "--result", "closed-green",
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
            re.capture_actual("implementation", "high", source="self-attested"))
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
            re.capture_actual("implementation", None, source="self-attested", model="sonnet"))
        rc = journal.main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P2.4", "--command", "plan-run", "--route-evidence", str(evidence_path),
            "--result", "blocked",
        ])
        self.assertEqual(rc, 0)
        entry = json.loads((self.plan_dir / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(entry["actor"], "sonnet/unknown")


if __name__ == "__main__":
    unittest.main()
