"""Frozen provider-neutral plan routing and semantic Next contract tests."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

from task.command_catalog import EFFORTS, MODEL_CLASSES, build_command_catalog
from task.command_render import (PlanNextCarrier, mapping_from_catalog,
                                 parse_next_carrier, plan_provider_invocation)
from task.route_evidence import required_route


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
FIXTURE = REPO_ROOT / "packages/task/tests/fixtures_data/provider-plan-cases.json"
PARITY_FIXTURE = REPO_ROOT / "packages/task/tests/fixtures_data/provider-command-parity.json"


class ProviderPlanRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.parity = json.loads(PARITY_FIXTURE.read_text(encoding="utf-8"))
        cls.catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        cls.records = cls.catalog.by_id()

    def test_fixture_freezes_neutral_axes_plan_commands_and_next_kinds(self):
        self.assertEqual(list(MODEL_CLASSES), self.expected["model_classes"])
        self.assertEqual(list(EFFORTS), self.expected["efforts"])
        self.assertEqual(
            set(self.expected["plan_commands"]),
            {record.command_id for record in self.catalog.records
             if record.kind == "plan-protocol"},
        )
        for command_id, expected in self.expected["plan_commands"].items():
            record = self.records[command_id]
            self.assertEqual(record.routing.mode, expected["mode"])
            if expected["mode"] == "fixed":
                self.assertEqual(
                    [record.routing.model_class, record.routing.effort],
                    expected["minimum"],
                )
        self.assertEqual(
            set(self.expected["next_kinds"]), PlanNextCarrier.allowed_kinds())
        for kind, declaration in self.expected["next_declarations"].items():
            with self.subTest(kind=kind):
                self.assertEqual(parse_next_carrier(declaration).kind, kind)

    def test_each_plan_command_renders_from_one_semantic_carrier_for_both_providers(self):
        for command_id, expected in self.expected["plan_commands"].items():
            carrier = PlanNextCarrier(
                expected["kind"], command_id, "PLAN", tuple(expected["arguments"]))
            for provider_id, projection_key in (("claude-code", "claude"),
                                                ("codex", "codex")):
                with self.subTest(command_id=command_id, provider=provider_id):
                    mapping = mapping_from_catalog(self.catalog, provider_id)
                    self.assertEqual(set(dict(mapping.class_selectors)), set(MODEL_CLASSES))
                    self.assertEqual(set(dict(mapping.effort_selectors)), set(EFFORTS))
                    minimum = tuple(expected["minimum"])
                    plan = plan_provider_invocation(
                        self.catalog, carrier, mapping,
                        dict(mapping.capability_bindings),
                        observed_class=minimum[0], observed_effort=minimum[1],
                        inherited_minimum=(minimum if expected["mode"] == "inherited-plan"
                                           else None))
                    self.assertTrue(plan.ok, plan.diagnostics)
                    self.assertEqual(plan.invocation, expected[projection_key])

    def test_cold_start_next_is_semantic_and_renders_both_provider_invocations(self):
        expected = self.expected["cold_start_next"]
        carrier = parse_next_carrier(
            expected["declaration"],
            context_kind=expected["carrier"]["context_kind"],
            item_ids=expected["carrier"]["item_ids"],
            cold_start_scope=expected["carrier"]["cold_start_scope"],
        )
        self.assertEqual(carrier.as_dict(), expected["carrier"])
        for provider_id, invocation in expected["invocations"].items():
            mapping = mapping_from_catalog(self.catalog, provider_id)
            support = dict(mapping.capability_bindings)
            plan = plan_provider_invocation(
                self.catalog, carrier, mapping, support,
                observed_class="frontier", observed_effort="xhigh")
            self.assertTrue(plan.ok, plan.diagnostics)
            self.assertEqual(plan.invocation, invocation)
            self.assertIs(plan.carrier, carrier)

    def test_exact_overshoot_undershoot_and_unknown_routes_are_fail_closed(self):
        mapping = mapping_from_catalog(self.catalog, "codex")
        support = dict(mapping.capability_bindings)
        for case in self.expected["route_cases"]:
            with self.subTest(case=case["id"]):
                carrier = PlanNextCarrier(
                    kind=case["kind"],
                    command_id=case["command_id"], plan_id="PLAN",
                    arguments=("PLAN", "P4.4"), context_kind="same-session")
                minimum = tuple(case["minimum"]) if case["minimum"] else None
                plan = plan_provider_invocation(
                    self.catalog, carrier, mapping, support,
                    observed_class=case["observed"][0],
                    observed_effort=case["observed"][1],
                    inherited_minimum=minimum)
                self.assertEqual(plan.ok, case["ok"])
                self.assertEqual(
                    [item.code for item in plan.diagnostics], case["diagnostics"])
                self.assertEqual(plan.invocation is not None, case["ok"])

    def test_missing_and_ambiguous_provider_selectors_block_invocation(self):
        base = mapping_from_catalog(self.catalog, "codex")
        support = dict(base.capability_bindings)
        carrier = PlanNextCarrier(
            kind="audit-phase", command_id="task:plan-audit", plan_id="PLAN",
            arguments=("PLAN", "P4"), context_kind="cold-start")
        for case in self.expected["mapping_failures"]:
            pairs = dict(base.class_selectors)
            pairs["frontier"] = () if case["mutation"] == "missing" else (
                "gpt-5.6-sol", "gpt-5.6-sol-preview")
            mapping = replace(base, class_selectors=tuple(pairs.items()))
            plan = plan_provider_invocation(
                self.catalog, carrier, mapping, support,
                observed_class="frontier", observed_effort="xhigh")
            self.assertFalse(plan.ok)
            self.assertIsNone(plan.invocation)
            self.assertIn(case["diagnostic"], {item.code for item in plan.diagnostics})

    def test_orchestration_requires_both_semantic_capabilities(self):
        mapping = mapping_from_catalog(self.catalog, "codex")
        support = dict(mapping.capability_bindings)
        carrier = PlanNextCarrier(
            kind="run-items", command_id="task:plan-run", plan_id="PLAN",
            arguments=("PLAN", "P4.1-P4.3"), context_kind="cold-start",
            orchestration_capabilities=tuple(
                self.expected["orchestration"]["required_capabilities"]))
        for missing in carrier.orchestration_capabilities:
            with self.subTest(missing=missing):
                incomplete = dict(support)
                incomplete.pop(missing)
                plan = plan_provider_invocation(
                    self.catalog, carrier, mapping, incomplete,
                    observed_class="frontier", observed_effort="xhigh",
                    inherited_minimum=("implementation", "high"))
                self.assertFalse(plan.ok)
                self.assertIsNone(plan.invocation)
                self.assertIn(
                    self.expected["orchestration"]["missing_diagnostic"],
                    {item.code for item in plan.diagnostics})

    def test_every_next_form_has_positive_and_invalid_contract_cases(self):
        self.assertEqual(
            {case["kind"] for case in self.parity["next_forms"]},
            PlanNextCarrier.allowed_kinds())
        for case in self.parity["next_forms"]:
            with self.subTest(kind=case["kind"]):
                carrier = parse_next_carrier(case["valid"])
                self.assertEqual(carrier.kind, case["kind"])
                with self.assertRaisesRegex(ValueError, "CMD_INVOCATION_INVALID"):
                    parse_next_carrier(case["invalid"])
                if carrier.command_id is None:
                    continue
                record = self.records[carrier.command_id]
                inherited = (("implementation", "high")
                             if record.routing.mode == "inherited-plan" else None)
                observed_class = inherited[0] if inherited else record.routing.model_class
                observed_effort = inherited[1] if inherited else record.routing.effort
                for provider_id in ("claude-code", "codex"):
                    mapping = mapping_from_catalog(self.catalog, provider_id)
                    plan = plan_provider_invocation(
                        self.catalog, carrier, mapping,
                        dict(mapping.capability_bindings),
                        observed_class=observed_class,
                        observed_effort=observed_effort,
                        inherited_minimum=inherited)
                    self.assertTrue(plan.ok, plan.diagnostics)
                    self.assertIsNotNone(plan.invocation)

    def test_route_evidence_required_route_agrees_with_the_catalog_for_every_plan_command(self):
        # P2.4: route_evidence derives REQUIRED from the same CommandCatalog this
        # module already builds — never a second, independently-parsed reading of
        # `command-routing.json` that could silently drift from this one.
        for command_id, expected in self.expected["plan_commands"].items():
            with self.subTest(command_id=command_id):
                record = self.records[command_id]
                if expected["mode"] == "fixed":
                    required = required_route(record)
                    self.assertEqual(
                        [required["model_class"], required["effort"]], expected["minimum"])
                else:
                    required = required_route(
                        record, inherited_minimum=tuple(expected["minimum"]))
                    self.assertEqual(
                        [required["model_class"], required["effort"]], expected["minimum"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
