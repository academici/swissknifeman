"""Instruction routing regressions: discovery cannot select a plan workflow."""
from pathlib import Path
import unittest

import fixtures  # noqa: F401 — repository import fallback
from task.command_catalog import build_command_catalog
from task.command_render import mapping_from_catalog, plan_codex_command_render


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages/task"


class IntentOptInTests(unittest.TestCase):
    def test_ordinary_requests_do_not_activate_any_task_route(self):
        contract = (PACKAGE / "references/intent-routing.md").read_text()
        self.assertIn("only when the owner explicitly invokes", contract)
        self.assertIn("existing plan files, and old handoffs do not activate it", contract)
        self.assertIn("without loading Task commands, runtime references, workflow rules, or plan gates", contract)

    def test_single_contract_covers_direct_and_explicit_plan_requests(self):
        contract = (PACKAGE / "references/intent-routing.md").read_text()
        scenarios = (
            ("Narrow correction", "task:fix"),
            ("Ordinary implementation, including large bounded work", "task:dev"),
            ("Research only", "task:research"),
            ("Explicit design/specification request", "task:design"),
            ("Explicit creation/refinement of an executable plan", "task:plan-design"),
            ("Explicit execution of an existing plan/item", "task:plan-run"),
            ("Review", "task:review"),
        )
        for intent, route in scenarios:
            with self.subTest(intent=intent):
                self.assertIn(f"| {intent} | `{route}`", contract)
        self.assertIn("latest explicit owner instruction", contract)
        self.assertIn("without a plan overrides older embedded successor-plan", contract)
        self.assertIn("explicit request to create a plan and execute it authorizes both", contract)
        self.assertIn("Size, risk, cross-module scope, portability needs", contract)
        self.assertIn("Loading relevant guidance is distinct from selecting its workflow", contract)

    def test_direct_commands_have_no_plan_prerequisite_for_either_provider(self):
        catalog = build_command_catalog(PACKAGE / "commands", PACKAGE / "configs/command-routing.json")
        mapping = mapping_from_catalog(catalog, "codex")
        plan = plan_codex_command_render(catalog, mapping, dict(mapping.capability_bindings))
        self.assertTrue(plan.ok, plan.diagnostics)
        artifacts = {artifact.path: artifact.managed_bytes.decode() for artifact in plan.artifacts}
        for command in ("dev", "fix"):
            record = catalog.by_id()[f"task:{command}"]
            self.assertEqual(record.plan_semantics, ())
            canonical = catalog.content_for(record.command_id).decode()
            runtime = artifacts[f"packages/task/adapters/codex/skills/task-{command}/command.md"]
            for text in (canonical, runtime):
                self.assertIn("references/intent-routing.md", text)
                for dependency in ("task-design", "task:plan-design", "task:plan-audit",
                                   "task:plan-close"):
                    self.assertNotIn(dependency, text)
            wrapper = artifacts[f"packages/task/adapters/codex/skills/task-{command}/SKILL.md"]
            self.assertIn("Activate only when the owner explicitly invokes this Task command or skill", wrapper)
            self.assertIn("automatic workflow for development", wrapper)
            reference = (PACKAGE / f"adapters/codex/skills/task-{command}" /
                         "../../../../references/intent-routing.md").resolve()
            self.assertEqual(reference, PACKAGE / "references/intent-routing.md")


if __name__ == "__main__":
    unittest.main()
