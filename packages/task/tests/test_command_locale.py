"""Command locale boundary: English canonical source, Russian overlay, and literal parity."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from task.command_locale import (catalog_sha256, command_locale_key, english_catalog,
                                 immutable_tokens, resolve_command)


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
OVERLAY_PATH = REPO_ROOT / "packages/task/locales/ru.json"


class CommandLocaleTests(unittest.TestCase):
    def test_english_is_the_canonical_default(self):
        result = resolve_command("plan-exec", command_root=COMMAND_ROOT)
        self.assertEqual(result["resolved_locale"], "en")
        self.assertTrue(result["fallback"])
        self.assertEqual(result["text"], (COMMAND_ROOT / "plan-exec.md").read_text(encoding="utf-8"))

    def test_russian_overlay_renders_both_migrated_commands(self):
        for command_id in ("plan-exec", "plan-run"):
            with self.subTest(command_id=command_id):
                result = resolve_command(command_id, locale="ru", command_root=COMMAND_ROOT,
                                         overlay_path=OVERLAY_PATH)
                self.assertEqual(result["resolved_locale"], "ru")
                self.assertFalse(result["fallback"])
                self.assertIn("---", result["text"])

    def test_missing_russian_unit_falls_back_to_english(self):
        source = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        source["units"].pop(command_locale_key("plan-run"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ru.json"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            # A sparse overlay may omit a unit and must use its English source unchanged.
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = resolve_command("plan-run", locale="ru", command_root=COMMAND_ROOT,
                                     overlay_path=path)
            self.assertEqual(result["text"], (COMMAND_ROOT / "plan-run.md").read_text(encoding="utf-8"))
            self.assertTrue(result["fallback"])

    def test_overlay_literals_match_the_english_unit(self):
        catalog = english_catalog(COMMAND_ROOT)
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(overlay["source_catalog_sha256"], catalog_sha256(catalog))
        for command_id in ("plan-exec", "plan-run"):
            key = command_locale_key(command_id)
            unit = overlay["units"][key]
            tokens = immutable_tokens(catalog.units[key])
            self.assertEqual(unit["source_sha256"], "sha256:" + sha256(catalog.units[key].encode()).hexdigest())
            self.assertEqual(unit["immutable_tokens"], list(tokens))
            self.assertTrue(all(unit["text"].count(token) == catalog.units[key].count(token)
                                for token in tokens))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
