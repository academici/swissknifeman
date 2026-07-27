#!/usr/bin/env python3
"""Тесты scripts/public-hygiene.py — синтетический список путей, без реального git ls-files."""
import importlib.util
import os
import sys
import unittest

_spec = importlib.util.spec_from_file_location(
    "public_hygiene",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-hygiene.py"),
)
public_hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(public_hygiene)


class TestPublicHygiene(unittest.TestCase):
    def test_forbidden_suffix(self):
        violations = public_hygiene.check(["dump.sqlite"])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], "dump.sqlite")

    def test_example_suffix_exempt(self):
        violations = public_hygiene.check([".env.example", "config.example"])
        self.assertEqual(violations, [])

    def test_dotenv_forbidden(self):
        violations = public_hygiene.check([".env", "packages/x/.env"])
        self.assertEqual(len(violations), 2)

    def test_clean_list_zero_violations(self):
        violations = public_hygiene.check(["README.md", "core/io.py", "docs/status.md"])
        self.assertEqual(violations, [])

    def test_component_rules(self):
        violations = public_hygiene.check(
            ["a/__pycache__/x.pyc", "a/.venv/bin/python", "a/node_modules/x/index.js"]
        )
        self.assertEqual(len(violations), 3)

    def test_reason_named_in_output(self):
        violations = public_hygiene.check(["secret.pem"])
        self.assertEqual(violations, [("secret.pem", "приватный ключ/сертификат")])


if __name__ == "__main__":
    unittest.main()
