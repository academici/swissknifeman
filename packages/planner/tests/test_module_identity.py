"""The module name lives in two constants; everything else derives from them or is a data file."""
import json
from pathlib import Path
import unittest

import planner
from planner.command_catalog import _COMMAND_ID_RE, build_command_catalog, package_command_path
from planner.plan import schema

PACKAGE = Path(__file__).resolve().parents[1]


def _json(relative):
    return json.loads((PACKAGE / relative).read_text(encoding="utf-8"))


class ModuleIdentityTests(unittest.TestCase):
    def test_constants_name_the_module(self):
        self.assertEqual(planner.MODULE_ID, "planner")
        self.assertEqual(planner.COMMAND_NAMESPACE, "planner")
        self.assertEqual(PACKAGE.name, planner.MODULE_ID)

    def test_package_files_carry_the_module_id(self):
        self.assertEqual(_json("unit.json")["id"], planner.MODULE_ID)
        self.assertEqual(_json(".claude-plugin/plugin.json")["name"], planner.MODULE_ID)
        self.assertEqual(_json(".codex-plugin/plugin.json")["name"], planner.MODULE_ID)
        self.assertEqual(_json("unit.json")["provides"]["plugins"][0]["name"], planner.MODULE_ID)

    def test_command_ids_use_the_namespace_and_follow_the_command_files(self):
        catalog = build_command_catalog(PACKAGE / "commands", PACKAGE / "configs/command-routing.json")
        prefix = f"{planner.COMMAND_NAMESPACE}:"
        self.assertEqual(sorted(record.command_id for record in catalog.records),
                         sorted(prefix + path.stem for path in (PACKAGE / "commands").glob("*.md")))
        for record in catalog.records:
            self.assertRegex(record.command_id, _COMMAND_ID_RE)
            self.assertEqual(record.source.path, f"packages/{planner.MODULE_ID}/commands/"
                             f"{record.command_id.removeprefix(prefix)}.md")

    def test_other_namespaces_are_not_commands(self):
        for command_id in ("task:plan-run", "plan-run", "planner:", "planner:Plan-run"):
            with self.subTest(command_id=command_id), self.assertRaisesRegex(ValueError, "CMD_ID_UNKNOWN"):
                package_command_path(command_id)

    def test_plan_urns_keep_their_original_prefix(self):
        self.assertEqual(schema.SCHEMA_URN_PREFIX, "urn:swissknifeman:task:plan:")
        self.assertEqual(_json("unit.json")["provides"]["contracts"][0]["id"], "urn:swissknifeman:task:plan")


if __name__ == "__main__":
    unittest.main()
