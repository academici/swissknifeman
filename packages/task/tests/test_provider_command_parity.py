"""Independent exhaustive parity for the frozen task-command contract."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

try:
    from . import fixtures  # noqa: F401,E402 — package invocation
except ImportError:
    import fixtures  # noqa: F401,E402 — direct discovery
from task.command_catalog import CommandCatalogError, build_command_catalog
from task.command_render import (build_provider_command_parity_report,
                                 mapping_from_catalog, parse_next_carrier,
                                 plan_claude_command_render,
                                 plan_codex_command_render,
                                 plan_cursor_command_render,
                                 render_provider_commands_reference,
                                 render_provider_model_roles_reference,
                                 validate_route)
from core import ProviderManifestError


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
PLUGIN_PATH = REPO_ROOT / "packages/task/.claude-plugin/plugin.json"
CONTRACT_PATH = (REPO_ROOT / "plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/"
                 "provider-command-routing-contract.md")
FIXTURE_PATH = (REPO_ROOT / "packages/task/tests/fixtures_data/"
                "provider-command-parity.json")
REFERENCE_PATH = REPO_ROOT / "packages/task/docs/reference/provider-commands.md"
MODEL_ROLES_REFERENCE_PATH = REPO_ROOT / "packages/task/docs/reference/provider-model-roles.md"
_CODEX_RUNTIME_FORBIDDEN = (
    re.compile(r"(?i)\b(?:opus|sonnet|haiku|fable)\b"),
    re.compile(r"(?<![\w/])/task:"),
    re.compile(r"(?<![\w/])/(?:model|effort|clear)\b"),
    re.compile(r"Workflow\("),
)
_PLAN_STATUSES = (
    "⬜ Not started", "🟡 In progress", "🟢 Done", "🟠 Done with deviations",
    "🔴 Blocked", "⛔ Skipped by decision",
)
_PLAN_ITEM_FIELDS = (
    "Status", "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs",
    "Files", "Required Reads", "Implementation Rules", "Code Guidance",
    "Validation", "Deliverables", "Completion Notes", "Pending Work",
    "Known Deviations", "Escalation Needed",
)


def _contract_inventory():
    """Read the frozen Markdown inventory without consulting either renderer."""
    lines = CONTRACT_PATH.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Command inventory")
    end = next(index for index in range(start + 1, len(lines))
               if lines[index].startswith("## "))
    records = []
    for line in lines[start:end]:
        if not line.startswith("| `task:"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        records.append({
            "command_id": cells[0].strip("`"),
            "kind": cells[1],
            "source": cells[2].strip("`"),
            "routing": [cells[5], cells[6].strip("`"), cells[7].strip("`")],
        })
    return records


def _write_routing(root, mutation):
    value = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    mutation(value)
    path = root / "routing.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class ProviderCommandParityTests(unittest.TestCase):
    def test_canonical_and_both_provider_examples_execute_the_same_policy(self):
        import task.plan_lifecycle
        expected = {"plan-audit": "read-only", "plan-exec": "not-requested",
                    "plan-run": "not-requested", "plan-design": "not-requested"}
        for command, action in expected.items():
            paths = (COMMAND_ROOT / f"{command}.md",
                     REPO_ROOT / f"packages/task/adapters/codex/skills/task-{command}/command.md",
                     REPO_ROOT / f"packages/task/tests/fixtures_data/claude-command-golden/commands/{command}.md")
            results = []
            for path in paths:
                text = path.read_text()
                examples = re.findall(r"`(task\.plan_lifecycle\.select\([^`]+\))`", text)
                self.assertEqual(len(examples), 1, str(path))
                result = eval(examples[0], {"task": task, "__builtins__": {}})
                self.assertEqual(result.audit_action, action)
                self.assertEqual(result.validation, ("focused",))
                results.append(result)
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0], results[2])

    def test_mapping_support_is_manifest_derived_and_missing_manifest_fails_closed(self):
        manifest = json.loads((REPO_ROOT / "configs/provider-capabilities.json").read_text())
        expected = {item["id"]: item["support"]["codex"]["level"]
                    for item in manifest["capabilities"]}
        self.assertEqual(dict(self.mappings["codex"].capability_bindings),
                         {key: expected[key] for key in dict(
                             self.mappings["codex"].capability_bindings)})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProviderManifestError):
                mapping_from_catalog(self.catalog, "codex",
                                     manifest_path=Path(directory) / "missing.json")

    def test_manifest_derived_unsupported_level_blocks_before_results(self):
        support = dict(self.mappings["codex"].capability_bindings)
        support["skills.repository"] = "unsupported"
        plan = plan_codex_command_render(self.catalog, self.mappings["codex"], support)
        self.assertFalse(plan.ok)
        self.assertEqual(plan.results, ())
        self.assertIn("CMD_CAPABILITY_UNSUPPORTED",
                      {item.code for item in plan.diagnostics})

    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        cls.mappings = {
            provider_id: mapping_from_catalog(cls.catalog, provider_id)
            for provider_id in ("claude-code", "codex", "cursor")
        }
        cls.support = {
            provider_id: dict(mapping.capability_bindings)
            for provider_id, mapping in cls.mappings.items()
        }
        cls.claude_plan = plan_claude_command_render(
            cls.catalog, cls.mappings["claude-code"], cls.support["claude-code"],
            plugin_bytes=PLUGIN_PATH.read_bytes())
        cls.codex_plan = plan_codex_command_render(
            cls.catalog, cls.mappings["codex"], cls.support["codex"])
        cls.cursor_plan = plan_cursor_command_render(
            cls.catalog, cls.mappings["cursor"], cls.support["cursor"])
        cls.next_carriers = tuple(
            parse_next_carrier(case["valid"])
            for case in cls.expected["next_forms"])

    @classmethod
    def report(cls):
        return build_provider_command_parity_report(
            cls.catalog, cls.claude_plan, cls.codex_plan, cls.cursor_plan, cls.mappings,
            expected_command_ids=tuple(
                command["command_id"] for command in cls.expected["commands"]),
            next_carriers=cls.next_carriers)

    def test_contract_fixture_and_canonical_files_define_expected_set(self):
        contract = _contract_inventory()
        fixture = self.expected["commands"]
        self.assertEqual(
            [{key: row[key] for key in ("command_id", "kind", "source", "routing")}
             for row in fixture], contract)
        canonical = tuple(sorted(
            f"task:{path.stem}" for path in COMMAND_ROOT.glob("*.md") if path.is_file()))
        expected = tuple(sorted(row["command_id"] for row in fixture))
        self.assertEqual(canonical, expected)
        self.assertEqual(len(expected), len(set(expected)))

        records = self.catalog.by_id()
        for row in fixture:
            with self.subTest(command_id=row["command_id"]):
                record = records[row["command_id"]]
                source_bytes = (REPO_ROOT / row["source"]).read_bytes()
                self.assertEqual(record.source.content_hash,
                                 "sha256:" + sha256(source_bytes).hexdigest())
                self.assertEqual(record.kind, row["kind"])
                self.assertEqual(
                    [record.routing.mode, record.routing.model_class,
                     record.routing.effort], row["routing"])
                self.assertEqual(
                    [item.capability_id for item in record.capability_requirements],
                    row["capabilities"])

    def test_report_is_exhaustive_deterministic_and_projection_exact(self):
        first, second = self.report(), self.report()
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True))
        self.assertEqual(first["inventory"],
                         {"missing": [], "extra": [], "duplicates": []})
        for provider_id in ("claude-code", "codex", "cursor"):
            self.assertEqual(first["projections"][provider_id],
                             {"missing": [], "extra": [], "duplicates": []})
        self.assertEqual(
            [row["command_id"] for row in first["commands"]],
            [row["command_id"] for row in self.expected["commands"]])
        self.assertEqual(
            [row["carrier"]["kind"] for row in first["next_forms"]],
            [row["kind"] for row in self.expected["next_forms"]])

    def test_generated_operator_reference_matches_validated_report(self):
        first = render_provider_commands_reference(self.report())
        second = render_provider_commands_reference(self.report())
        self.assertEqual(first, second)
        self.assertEqual(REFERENCE_PATH.read_bytes(), first)

    def test_generated_model_roles_reference_is_deterministic(self):
        first = render_provider_model_roles_reference(self.catalog)
        second = render_provider_model_roles_reference(self.catalog)
        self.assertEqual(first, second)
        self.assertEqual(MODEL_ROLES_REFERENCE_PATH.read_bytes(), first)

    def test_codex_runtime_projection_is_provider_safe_and_semantically_complete(self):
        artifacts = {item.path: item.managed_bytes for item in self.codex_plan.artifacts}
        exact_copies = []
        unsafe = []
        projected = {}
        for record in self.catalog.records:
            name = record.command_id.removeprefix("task:")
            path = f"packages/task/adapters/codex/skills/task-{name}/command.md"
            runtime = artifacts[path]
            wrapper = artifacts[path.removesuffix("command.md") + "SKILL.md"]
            projected[record.command_id] = runtime.decode("utf-8")
            if runtime == self.catalog.content_for(record.command_id):
                exact_copies.append(record.command_id)
            if any(pattern.search(projected[record.command_id])
                   for pattern in _CODEX_RUNTIME_FORBIDDEN):
                unsafe.append(record.command_id)
            if any(pattern.search(wrapper.decode("utf-8"))
                   for pattern in _CODEX_RUNTIME_FORBIDDEN):
                unsafe.append(record.command_id + ":wrapper")

        self.assertEqual(exact_copies, [])
        self.assertEqual(unsafe, [])
        canonical_route_notation = []
        projected_route_notation = []
        canonical_clear_controls = 0
        projected_text = "\n".join(projected.values())
        for record in self.catalog.records:
            canonical = self.catalog.content_for(record.command_id).decode("utf-8")
            canonical_body = canonical.split("---\n", 2)[2]
            canonical_route_notation.extend(
                re.findall(r"[\w<>]+/effort", canonical_body))
            projected_route_notation.extend(
                re.findall(r"[\w<>]+/effort", projected[record.command_id]))
            canonical_clear_controls += len(
                re.findall(r"(?<![\w/])/clear\b", canonical_body))
        self.assertTrue(canonical_route_notation)
        self.assertEqual(projected_route_notation, canonical_route_notation)
        self.assertEqual(canonical_clear_controls, 0)
        self.assertIsNone(re.search(r"(?<![\w/])/clear\b", projected_text))
        # Audit P4 attempt 2 observed 32 corrupt replacements across the runtimes.
        self.assertNotIn("modelsession effort setting", projected_text)
        self.assertNotIn("session effort setting", projected_text)
        plan_text = "\n".join(
            projected[command_id] for command_id in projected
            if self.catalog.by_id()[command_id].kind == "plan-protocol")
        self.assertIn("plan_lifecycle", plan_text)
        self.assertIn("plan_lifecycle", plan_text)

    def test_qualified_item_reference_rule_survives_provider_rendering(self):
        literal = "runtime/plan-protocol/references/work-references.md"
        source = self.catalog.content_for("task:plan-design").decode("utf-8")
        self.assertIn(literal, source)
        self.assertIn("`PLAN1.D35`, `PLAN1.P2.3`; legacy: `<PLAN-ID> <local-ID>`", source)
        for provider_id, plan in (("claude-code", self.claude_plan), ("codex", self.codex_plan),
                                  ("cursor", self.cursor_plan)):
            with self.subTest(provider=provider_id):
                rendered = "\n".join(
                    artifact.managed_bytes.decode("utf-8")
                    for artifact in plan.artifacts
                    if artifact.path == "packages/task/commands/plan-design.md"
                    or "task-plan-design" in artifact.path
                )
                self.assertIn(literal, rendered)
                self.assertIn("`PLAN1.D35`, `PLAN1.P2.3`; legacy: `<PLAN-ID> <local-ID>`", rendered)

    def test_all_contract_diagnostics_have_fail_closed_negative_cases(self):
        observed = set()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commands = root / "commands"
            shutil.copytree(COMMAND_ROOT, commands)

            routing = _write_routing(
                root, lambda value: value["commands"][0].update(
                    {"command_id": "invalid"}))
            with self.assertRaises(CommandCatalogError) as caught:
                build_command_catalog(commands, routing)
            observed.add(caught.exception.diagnostic.code)

            routing = _write_routing(
                root, lambda value: value["commands"][0].update(
                    {"aliases": ["task:duplicate"]}))
            with self.assertRaises(CommandCatalogError) as caught:
                build_command_catalog(commands, routing)
            observed.add(caught.exception.diagnostic.code)

            (commands / "unexpected.md").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaises(CommandCatalogError) as caught:
                build_command_catalog(commands, ROUTING_PATH)
            observed.add(caught.exception.diagnostic.code)
            (commands / "unexpected.md").unlink()

            routing = _write_routing(
                root, lambda value: value.update({"contract_version": "2.0.0"}))
            with self.assertRaises(CommandCatalogError) as caught:
                build_command_catalog(commands, routing)
            observed.add(caught.exception.diagnostic.code)

            disabled = plan_codex_command_render(
                self.catalog, self.mappings["claude-code"],
                self.support["claude-code"])
            observed.update(item.code for item in disabled.diagnostics)

            unsupported = dict(self.support["codex"])
            unsupported.pop("skills.repository")
            plan = plan_codex_command_render(
                self.catalog, self.mappings["codex"], unsupported)
            observed.update(item.code for item in plan.diagnostics)

            classes = dict(self.mappings["codex"].class_selectors)
            classes["frontier"] = ()
            plan = plan_codex_command_render(
                self.catalog,
                replace(self.mappings["codex"], class_selectors=tuple(classes.items())),
                self.support["codex"])
            observed.update(item.code for item in plan.diagnostics)

            classes["frontier"] = ("gpt-5.6-sol", "gpt-5.6-sol-preview")
            plan = plan_codex_command_render(
                self.catalog,
                replace(self.mappings["codex"], class_selectors=tuple(classes.items())),
                self.support["codex"])
            observed.update(item.code for item in plan.diagnostics)

            plan = plan_codex_command_render(
                self.catalog, self.mappings["codex"], self.support["codex"],
                observed_routes={"task:plan-audit": ("implementation", "xhigh")})
            observed.update(item.code for item in plan.diagnostics)

            overshoot = validate_route(
                self.catalog.by_id()["task:fix"], "frontier", "high",
                self.mappings["codex"])
            observed.update(item.code for item in overshoot)

            with self.assertRaisesRegex(ValueError, "CMD_INVOCATION_INVALID"):
                parse_next_carrier("manual: opus/max")
            observed.add("CMD_INVOCATION_INVALID")

            plugin = json.loads(PLUGIN_PATH.read_text(encoding="utf-8"))
            plugin["commands"] = ["./other"]
            drift = plan_claude_command_render(
                self.catalog, self.mappings["claude-code"],
                self.support["claude-code"],
                plugin_bytes=(json.dumps(plugin) + "\n").encode())
            observed.update(item.code for item in drift.diagnostics)

        self.assertEqual(observed, set(self.expected["diagnostic_codes"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
