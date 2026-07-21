"""Focused contract tests for the immutable semantic command catalog."""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from task.command_catalog import CommandCatalogError, build_command_catalog


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
FIXTURE = REPO_ROOT / "packages/task/tests/fixtures_data/codex-command-cases.json"


class CommandCatalogTests(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_exact_inventory_hashes_and_immutability(self):
        catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        self.assertEqual(catalog.contract_version, self.expected["contract_version"])
        self.assertEqual([record.command_id for record in catalog.records],
                         self.expected["command_ids"])
        self.assertEqual(len(catalog.records), 11)
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
