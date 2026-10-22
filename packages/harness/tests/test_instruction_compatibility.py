"""Independent P5.6 compatibility inventory against installed temp consumers."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from harness.instructions import (
    EXTENSION_IDS, PROVIDERS, ROOT_PINNED_COMMON_IDS, SCOPES, apply_instructions, default_request,
    load_catalog, operator_reference, plan_instructions,
)


DATA = Path(__file__).resolve().parent / "fixtures_data/instruction-compatibility-v1.json"


class InstructionCompatibilityTests(unittest.TestCase):
    def test_fixture_is_independent_pre_renderer_p5_6_inventory(self):
        expected = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(expected["provenance"], {"captured_before_renderer": True})
        self.assertEqual(len(expected["records"]), 97)
        self.assertTrue(all(item["assertions"] for item in expected["records"]))

    def test_every_record_anchor_exists_in_actual_installed_consumers(self):
        fixture = json.loads(DATA.read_text(encoding="utf-8"))
        records = {item["id"]: item for item in fixture["records"]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(default_request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            applied = apply_instructions(replace(
                default_request("apply", root), authorized_target_paths=targets))
            self.assertTrue(applied.green)
            lock = json.loads((root / ".swissknifeman/provider-artifacts.lock.json")
                              .read_text(encoding="utf-8"))
            self.assertTrue(all(record["contract_version"] == "1.1.0"
                                and record["semantic_metadata"]["artifact_kind"]
                                == "instruction-projection" for record in lock["records"]))
            for target in applied.targets:
                rendered = (root / target.target_path).read_text(encoding="utf-8")
                for semantic_id in target.ordered_semantic_ids:
                    self.assertIn(f"<!-- semantic:{semantic_id} -->", rendered)
                    for assertion in records[semantic_id]["assertions"]:
                        self.assertIn(assertion, rendered, semantic_id)

    def test_common_inventory_respects_provider_projection_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(default_request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            request = replace(default_request("apply", root), authorized_target_paths=targets)
            applied = apply_instructions(request)
            for scope in SCOPES:
                by_provider = {item.provider_id: item
                               for item in applied.targets if item.scope_id == scope}
                self.assertEqual(set(by_provider), set(PROVIDERS))
                # Root carries only the pinned common ids (to every provider); package common is
                # projected to Claude Code only.
                pinned = ROOT_PINNED_COMMON_IDS if scope == "root" else ()
                common_count = len(pinned) or sum(
                    record["kind"] == "common"
                    for record in next(item for item in load_catalog()["scopes"]
                                       if item["id"] == scope)["sections"])
                self.assertEqual(len(by_provider["claude-code"].ordered_semantic_ids),
                                 common_count + len(EXTENSION_IDS[(scope, "claude-code")]))
                self.assertEqual(by_provider["codex"].ordered_semantic_ids,
                                 pinned + EXTENSION_IDS[(scope, "codex")])
                self.assertEqual(by_provider["cursor"].ordered_semantic_ids,
                                 pinned + EXTENSION_IDS[(scope, "cursor")])
                self.assertEqual(by_provider["grok"].ordered_semantic_ids,
                                 pinned + EXTENSION_IDS[(scope, "grok")])

    def test_root_targets_carry_only_the_pinned_common_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(default_request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            applied = apply_instructions(replace(default_request("apply", root), authorized_target_paths=targets))
            root_common = [section["id"] for scope in load_catalog()["scopes"] if scope["id"] == "root"
                           for section in scope["sections"] if section["kind"] == "common"]
            on_demand = [sid for sid in root_common if sid not in ROOT_PINNED_COMMON_IDS]
            self.assertTrue(on_demand)
            for target in (item for item in applied.targets if item.scope_id == "root"):
                rendered = (root / target.target_path).read_text(encoding="utf-8")
                for pinned in ROOT_PINNED_COMMON_IDS:
                    self.assertIn(f"<!-- semantic:{pinned} -->", rendered, target.target_path)
                    self.assertIn(f"## {pinned}", rendered, target.target_path)
                for skipped in on_demand:
                    self.assertNotIn(f"## {skipped}", rendered, f"{target.target_path}: {skipped}")
                    self.assertNotIn(f"<!-- semantic:{skipped} -->", rendered, target.target_path)

    def test_p4_forbidden_claude_runtime_tokens_absent_from_codex_consumers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(default_request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            request = replace(default_request("apply", root), authorized_target_paths=targets)
            applied = apply_instructions(request)
            for target in (item for item in applied.targets if item.provider_id == "codex"):
                rendered = (root / target.target_path).read_text(encoding="utf-8")
                for token in ("/planner:", "PreToolUse", "enabledPlugins", ".claude/settings",
                              ".claude/skills", "outputStyle", "plansDirectory"):
                    self.assertNotIn(token, rendered, f"{target.target_path}: {token}")

    def test_generated_reference_matches_validated_catalog(self):
        reference = (Path(__file__).resolve().parents[1]
                     / "docs/reference/provider-instructions.md").read_text(encoding="utf-8")
        self.assertEqual(reference, operator_reference())

    def test_fixture_provider_ownership_matches_frozen_extension_sets(self):
        fixture = json.loads(DATA.read_text(encoding="utf-8"))
        catalog_records = {record["id"]: record for scope in load_catalog()["scopes"]
                           for record in scope["sections"]}
        for item in fixture["records"]:
            record = catalog_records[item["id"]]
            expected = (("claude-code", "codex") if record["kind"] == "common"
                        else (record["provider_id"],))
            self.assertEqual(tuple(item["provider_ids"]), expected)


if __name__ == "__main__":
    unittest.main()
