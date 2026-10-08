#!/usr/bin/env python3
"""Tests scripts/verify-tag.py — synthetic CHANGELOG in tmpdir."""
import importlib.util
import os
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location(
    "verify_tag", os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-tag.py")
)
verify_tag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_tag)

WITH_RELEASE = """# Changelog

## [Unreleased]

### Added

- something

## [1.2.0] - 2026-07-01

### Added

- previous

## [1.1.0] - 2026-06-01
"""

ONLY_UNRELEASED = """# Changelog

## [Unreleased]

### Added

- something
"""

MALFORMED = """# Changelog

## [Unreleased]

## [1.2.0 no date]
"""


def _changelog(tmp, text):
    path = os.path.join(tmp, "CHANGELOG.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class TestVerifyTag(unittest.TestCase):
    def test_tag_matches_top_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _changelog(tmp, WITH_RELEASE)
            code, _ = verify_tag.verify("v1.2.0", path)
            self.assertEqual(code, 0)

    def test_tag_without_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _changelog(tmp, WITH_RELEASE)
            code, _ = verify_tag.verify("v9.9.9", path)
            self.assertEqual(code, 1)

    def test_tag_against_unreleased_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _changelog(tmp, ONLY_UNRELEASED)
            code, _ = verify_tag.verify("v1.0.0", path)
            self.assertEqual(code, 1)

    def test_tag_not_topmost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _changelog(tmp, WITH_RELEASE)
            code, _ = verify_tag.verify("v1.1.0", path)
            self.assertEqual(code, 1)

    def test_malformed_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _changelog(tmp, MALFORMED)
            code, message = verify_tag.verify("v1.2.0", path)
            self.assertEqual(code, 2)
            self.assertIn("released view header not found", message)

    def test_missing_changelog_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = verify_tag.verify("v1.0.0", os.path.join(tmp, "nope.md"))
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
