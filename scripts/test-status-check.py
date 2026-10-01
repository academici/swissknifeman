#!/usr/bin/env python3
"""Tests scripts/status-check.py — synthetic markdown-fixtures in tmpdir (P8.5)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "status_check", os.path.join(os.path.dirname(os.path.abspath(__file__)), "status-check.py")
)
status_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(status_check)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VALID = """# Status

## Matrix

| Package | Opportunity | Maturity | Evidence / boundary |
|:--|:--|:--|:--|
| skiller | budget | available | `skiller status` prints budget |
| core | io | available | `unittest discover -s core/tests` |

## Known limitations
"""


def _write(tmpdir, content):
    path = os.path.join(tmpdir, "status.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestStatusCheck(unittest.TestCase):
    def test_valid_matrix_zero_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, VALID)
            rows, errors = status_check.check(path, REPO_ROOT)
            self.assertEqual(errors, [])
            self.assertEqual(len(rows), 2)

    def test_maturity_outside_dictionary(self):
        bad = VALID.replace("available", "works", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, bad)
            _, errors = status_check.check(path, REPO_ROOT)
            self.assertEqual(len(errors), 1)
            self.assertIn("not from the dictionary", errors[0])

    def test_empty_evidence(self):
        bad = VALID.replace("`skiller status` prints budget", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, bad)
            _, errors = status_check.check(path, REPO_ROOT)
            self.assertEqual(len(errors), 1)
            self.assertIn("Evidence empty", errors[0])

    def test_unknown_package(self):
        bad = VALID.replace("| skiller |", "| non-existent-package |")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, bad)
            _, errors = status_check.check(path, REPO_ROOT)
            self.assertEqual(len(errors), 1)
            self.assertIn("unknown", errors[0])

    def test_duplicate_package_capability(self):
        dup = VALID.replace(
            "## Known limitations",
            "| skiller | budget | experimental | another line |\n\n## Known limitations",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, dup)
            _, errors = status_check.check(path, REPO_ROOT)
            self.assertEqual(len(errors), 1)
            self.assertIn("take", errors[0])

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = _write(tmp, VALID)
            self.assertEqual(status_check.main(["status-check.py", good]), 0)
            bad = _write(tmp, VALID.replace("available", "works", 1))
            self.assertEqual(status_check.main(["status-check.py", bad]), 1)


if __name__ == "__main__":
    unittest.main()
