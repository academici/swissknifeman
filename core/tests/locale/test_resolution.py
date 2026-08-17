import unittest
from pathlib import Path
from core.locale import resolve_locale


ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "core/locale/data/language-subtag-registry.txt"
BASE = {"contract_version": "1.0.0", "rank": 5, "kind": "built-in", "locale": {"response": "en", "plan": "en", "diagnostics": "en"}}


class ResolutionTests(unittest.TestCase):
    def test_surfaces_resolve_independently(self):
        result = resolve_locale(({"contract_version": "1.0.0", "rank": 1, "kind": "command-session", "locale": {"response": "ru-ru"}}, BASE), registry_path=REGISTRY)
        self.assertEqual(result.surfaces[0].as_dict()["canonical"], "ru-RU")
        self.assertEqual(result.surfaces[0].resolved, "ru")
        self.assertEqual(result.surfaces[1].resolved, "en")

    def test_each_surface_override_leaves_the_other_surfaces_byte_identical(self):
        baseline = resolve_locale((BASE,), registry_path=REGISTRY)
        baseline_rows = {row.surface: row.as_dict() for row in baseline.surfaces}

        for surface in ("response", "plan", "diagnostics"):
            with self.subTest(surface=surface):
                result = resolve_locale((
                    {"contract_version": "1.0.0", "rank": 1,
                     "kind": "command-session", "locale": {surface: "ru-RU"}},
                    BASE,
                ), registry_path=REGISTRY)
                rows = {row.surface: row.as_dict() for row in result.surfaces}
                self.assertEqual(rows[surface]["canonical"], "ru-RU")
                self.assertEqual(rows[surface]["resolved"], "ru")
                for untouched in {"response", "plan", "diagnostics"} - {surface}:
                    self.assertEqual(rows[untouched], baseline_rows[untouched])

    def test_private_use_is_not_malformed(self):
        result = resolve_locale(({"contract_version": "1.0.0", "rank": 1, "kind": "command-session", "locale": {"response": "en-x-acme"}}, BASE), registry_path=REGISTRY)
        self.assertIsNone(result.surfaces[0].resolved)
        self.assertEqual(result.surfaces[0].diagnostic, "LOCALE_UNSUPPORTED_PRIVATE_USE")
