"""Command locale boundary: English canonical source, Russian overlay, and literal parity."""
from collections import Counter
from pathlib import Path
import unittest
from unittest.mock import patch

from task.command_locale import (command_locale_key, english_catalog, literal_inventory,
                                 verify_literal_inventory, resolve_command,
                                 _preserves_protected_literals)


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
OVERLAY_PATH = REPO_ROOT / "packages/task/locales/ru.json"


class CommandLocaleTests(unittest.TestCase):
    def test_frozen_preimage_inventory_needs_no_git_process(self):
        with patch("subprocess.run", side_effect=AssertionError("installed runtime must not call Git")):
            for command_id in ("plan-exec", "plan-run"):
                text = (COMMAND_ROOT / f"{command_id}.md").read_text()
                inventory = literal_inventory(text, command_id=command_id)
                self.assertEqual(inventory["preimage_commit"], "980ee79d")

    def test_english_is_the_canonical_default(self):
        result = resolve_command("plan-exec", command_root=COMMAND_ROOT)
        self.assertEqual(result["resolved_locale"], "en")
        self.assertTrue(result["fallback"])
        self.assertEqual(result["text"], (COMMAND_ROOT / "plan-exec.md").read_text(encoding="utf-8"))

    def test_russian_command_requests_use_sparse_english_fallback(self):
        for command_id in ("plan-exec", "plan-run"):
            with self.subTest(command_id=command_id):
                result = resolve_command(command_id, locale="ru", command_root=COMMAND_ROOT,
                                         overlay_path=OVERLAY_PATH)
                self.assertEqual(result["resolved_locale"], "en")
                self.assertTrue(result["fallback"])
                self.assertIsNone(result["overlay_sha256"])

    def test_complete_preimage_derived_inventory_matches_each_canonical_unit(self):
        catalog = english_catalog(COMMAND_ROOT)
        for command_id in ("plan-exec", "plan-run"):
            with self.subTest(command_id=command_id):
                inventory = verify_literal_inventory(catalog.units[command_locale_key(command_id)], command_id=command_id)
                self.assertEqual(inventory["preimage_commit"], "980ee79d")
                self.assertGreater(len(inventory["preimage_literals"]), 20)
                self.assertGreater(len(inventory["candidate_literals"]), 10)
                self.assertIn("inline-code", {kind for kind, _ in inventory["candidate_literals"]})
                self.assertIsInstance(inventory["protected_preimage_literals"], tuple)

    def test_inventory_rejects_omitted_reordered_multiplied_and_new_literals(self):
        text = (COMMAND_ROOT / "plan-run.md").read_text(encoding="utf-8")
        token = "task:plan-exec"
        reordered = text.replace("`task:plan-exec`", "`plan-exec`", 1)
        for label, candidate in (
            ("omitted", text.replace(token, "", 1)),
            ("reordered", reordered),
            ("multiplicity", text.replace(token, f"{token} {token}", 1)),
            ("new", text + "\n`NEW_MACHINE_LITERAL`\n"),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "CMD_LOCALE_LITERAL_INVENTORY_MISMATCH"):
                verify_literal_inventory(candidate, command_id="plan-run")

    def test_preimage_protection_rejects_a_removed_contract_atom(self):
        text = (COMMAND_ROOT / "plan-run.md").read_text(encoding="utf-8")
        inventory = literal_inventory(text, command_id="plan-run")
        self.assertTrue(inventory["candidate_literals"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
