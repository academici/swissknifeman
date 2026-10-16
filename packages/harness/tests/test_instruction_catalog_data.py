"""The instruction catalog owns the scope list and the target paths per provider; the code reads them from it."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from harness.instructions import (  # noqa: E402
    CATALOG_VERSION, PROVIDERS, SCOPES, TARGETS, catalog_path, load_catalog, validate_catalog,
)


def codes(value):
    return {item.code for item in validate_catalog(value)}


class CatalogDataTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(catalog_path().read_text(encoding="utf-8"))

    def test_scopes_targets_and_version_come_from_the_catalog(self):
        self.assertEqual(SCOPES, tuple(scope["id"] for scope in self.raw["scopes"]))
        self.assertEqual(CATALOG_VERSION, self.raw["catalog_version"])
        for scope in self.raw["scopes"]:
            self.assertEqual(tuple(scope["targets"]), PROVIDERS)
            self.assertEqual(TARGETS[scope["id"]], scope["targets"])

    def test_scope_record_has_no_flat_target_fields(self):
        for scope in self.raw["scopes"]:
            self.assertEqual(set(scope), {"id", "targets", "sections"})

    def test_the_packaged_catalog_is_valid(self):
        self.assertEqual(codes(load_catalog()), set())

    def test_legacy_flat_target_fields_are_refused(self):
        legacy = copy.deepcopy(self.raw)
        legacy["scopes"][1]["claude_target"] = legacy["scopes"][1]["targets"]["claude-code"]
        self.assertIn("INSTRUCTION_SCOPE_INVALID", codes(legacy))

    def test_a_changed_target_path_is_refused(self):
        moved = copy.deepcopy(self.raw)
        moved["scopes"][1]["targets"]["codex"] = "elsewhere/AGENTS.md"
        self.assertIn("INSTRUCTION_TARGET_SET_MISMATCH", codes(moved))

    def test_an_unknown_provider_target_is_refused(self):
        extra = copy.deepcopy(self.raw)
        extra["scopes"][1]["targets"]["other"] = "x"
        self.assertIn("INSTRUCTION_SCOPE_INVALID", codes(extra))

    def test_a_reordered_scope_list_is_refused(self):
        reordered = copy.deepcopy(self.raw)
        reordered["scopes"].reverse()
        self.assertIn("INSTRUCTION_TARGET_SET_MISMATCH", codes(reordered))


if __name__ == "__main__":
    unittest.main()
