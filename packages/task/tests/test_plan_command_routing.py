"""Frozen provider-neutral plan routing and semantic Next contract tests."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

import fixtures  # noqa: F401,E402 — restores monorepo core/lib fallbacks
from task.command_catalog import EFFORTS, MODEL_CLASSES, build_command_catalog
from task.command_render import (PlanNextCarrier, mapping_from_catalog,
                                 parse_next_carrier, plan_provider_invocation,
                                 render_codex_launch)
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

    def test_terminal_audit_handoff_is_a_fresh_routed_session_boundary(self):
        audit = (COMMAND_ROOT / "plan-audit.md").read_text(encoding="utf-8")
        protocol = (REPO_ROOT / "packages/skiller/skills/general/plan-protocol/SKILL.md").read_text(
            encoding="utf-8")
        self.assertIn("AUDIT-ROOT-TERMINAL", audit)
        self.assertIn("fresh routed root", audit)
        self.assertIn("AUDIT-ROOT-TERMINAL", protocol)
        self.assertIn("must not execute the successor", protocol)

    def test_terminal_design_handoff_cannot_auto_execute_its_successor(self):
        design = (COMMAND_ROOT / "plan-design.md").read_text(encoding="utf-8")
        codex_design = (REPO_ROOT / "packages/task/adapters/codex/skills/task-plan-design/command.md"
                        ).read_text(encoding="utf-8")
        protocol = (REPO_ROOT / "packages/skiller/skills/general/plan-protocol/SKILL.md").read_text(
            encoding="utf-8")
        self.assertIn("DESIGN-ROOT-TERMINAL", design)
        self.assertIn("НЕ спавнит", design)
        self.assertIn("cold-start-root: design-root-terminal", design)
        self.assertIn("DESIGN-ROOT-TERMINAL", codex_design)
        self.assertIn("НЕ спавнит", codex_design)
        self.assertIn("DESIGN-ROOT-TERMINAL", protocol)
        self.assertIn("must not execute or spawn the successor", protocol)

    def test_new_plan_batch_is_mandatory_and_survives_every_handoff_writer(self):
        protocol = (REPO_ROOT / "packages/skiller/skills/general/plan-protocol/SKILL.md"
                    ).read_text(encoding="utf-8")
        template = (REPO_ROOT / "packages/skiller/skills/general/plan-protocol/snippets/plan-template.md"
                    ).read_text(encoding="utf-8")
        self.assertIn("| Batch | Items | Model class/effort | Exec | Review | Почему |", protocol)
        self.assertIn("For every new layout-v2 plan, `Batch` and `Review` are mandatory", protocol)
        self.assertIn("| Batch | Items | Model class/effort | Exec | Review | Почему |", template)
        for command in ("plan-design", "plan-exec", "plan-audit", "plan-close"):
            with self.subTest(command=command):
                body = (COMMAND_ROOT / f"{command}.md").read_text(encoding="utf-8")
                self.assertIn("Batch", body)

    def test_terminal_phase_handoff_uses_audit_policy_instead_of_probe_close(self):
        execution = (COMMAND_ROOT / "plan-exec.md").read_text(encoding="utf-8")
        close = (COMMAND_ROOT / "plan-close.md").read_text(encoding="utf-8")
        protocol = (REPO_ROOT / "packages/skiller/skills/general/plan-protocol/SKILL.md"
                    ).read_text(encoding="utf-8")
        for carrier in (execution, close, protocol):
            with self.subTest(carrier=carrier[:40]):
                self.assertIn("phase_audit_policy", carrier)
        self.assertNotIn(
            "Фаза терминальна → `/task:plan-close <PLAN-ID> Pn`", execution)
        self.assertIn("audit-phase: task:plan-audit", execution)
        self.assertIn("close: task:plan-close", execution)

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

    def test_codex_launch_pins_the_mapped_route_and_process_safety_flags(self):
        carrier = PlanNextCarrier(
            "run-items", "task:plan-run", "PLAN", ("PLAN", "P2.7"),
            context_kind="cold-start")
        mapping = mapping_from_catalog(self.catalog, "codex")
        plan = plan_provider_invocation(
            self.catalog, carrier, mapping, dict(mapping.capability_bindings),
            observed_class="implementation", observed_effort="high",
            inherited_minimum=("implementation", "high"))
        self.assertTrue(plan.ok, plan.diagnostics)
        expected = (
            "codex -C /workspace/repo -m gpt-5.6-terra "
            "-c 'model_reasoning_effort=\"high\"' -a never -s danger-full-access "
            "'$ task:plan-run PLAN P2.7'"
        )
        self.assertEqual(plan.codex_launch("/workspace/repo"), expected)
        self.assertEqual(
            render_codex_launch(plan.invocation or "", plan.model_selector or "",
                                plan.effort_selector or "", "/workspace/repo"),
            expected)
        with self.assertRaisesRegex(ValueError, "CMD_INVOCATION_INVALID"):
            render_codex_launch("task:plan-run PLAN P2.7", "gpt-5.6-terra", "high", "/repo")

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
