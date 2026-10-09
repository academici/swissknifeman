"""Focused contract tests for the immutable semantic command catalog."""
from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from planner.command_catalog import CommandCatalogError, build_command_catalog, package_command_path


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/planner/commands"
ROUTING_PATH = REPO_ROOT / "packages/planner/configs/command-routing.json"
FIXTURE = REPO_ROOT / "packages/planner/tests/fixtures_data/codex-command-cases.json"


class CommandCatalogTests(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_exact_inventory_hashes_and_immutability(self):
        catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        self.assertEqual(catalog.contract_version, self.expected["contract_version"])
        self.assertEqual([record.command_id for record in catalog.records],
                         self.expected["command_ids"])
        self.assertEqual(len(catalog.records), 10)
        self.assertTrue(all(record.source.content_hash.startswith("sha256:") and
                            len(record.source.content_hash) == 71
                            for record in catalog.records))
        with self.assertRaises(FrozenInstanceError):
            catalog.catalog_version = "changed"
        with self.assertRaises(FrozenInstanceError):
            catalog.records[0].routing.effort = "low"

    def test_explicit_inputs_do_not_depend_on_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                import os
                os.chdir(temporary)
                catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
            finally:
                os.chdir(previous)
        self.assertEqual([record.command_id for record in catalog.records],
                         self.expected["command_ids"])

    def test_parent_command_resolves_in_source_and_installed_package_layouts(self):
        self.assertEqual(package_command_path("planner:plan-run"), COMMAND_ROOT / "plan-run.md")
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "planner" / "0.15.4"
            (installed / "lib" / "planner").mkdir(parents=True)
            shutil.copy2(
                REPO_ROOT / "packages/planner/lib/planner/command_catalog.py",
                installed / "lib" / "planner" / "command_catalog.py")
            shutil.copytree(COMMAND_ROOT, installed / "commands")
            spec = importlib.util.spec_from_file_location(
                "installed_task_command_catalog",
                installed / "lib" / "planner" / "command_catalog.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            self.addCleanup(sys.modules.pop, spec.name, None)
            spec.loader.exec_module(module)
            self.assertEqual(
                module.package_command_path("planner:plan-run"),
                installed / "commands" / "plan-run.md")

    def test_missing_extra_and_duplicate_fail_closed(self):
        cases = ("missing", "extra", "duplicate")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                commands = root / "commands"
                shutil.copytree(COMMAND_ROOT, commands)
                metadata = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
                if case == "missing":
                    (commands / "fix.md").unlink()
                elif case == "extra":
                    (commands / "unexpected.md").write_text("unexpected\n", encoding="utf-8")
                else:
                    metadata["commands"].append(dict(metadata["commands"][0]))
                routing = root / "routing.json"
                routing.write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaises(CommandCatalogError) as caught:
                    build_command_catalog(commands, routing)
                self.assertEqual(caught.exception.diagnostic.code, "CMD_CATALOG_MISMATCH")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
