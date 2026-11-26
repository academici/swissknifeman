#!/usr/bin/env python3
"""The Python floor of the hub has one source: aicore.MIN_PYTHON.

No module code names an older floor, and every module doctor that checks the interpreter reads the
constant instead of a literal version tuple.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
STALE = re.compile(
    r"version_info\s*>=\s*\(3,\s*(8|9|10)\)"
    r"|python3\.(8|9|10)\+"
    r"|python>=3\.(8|9|10)"
    r"|python3\s*>=\s*3\.(8|9|10)"
)
DOCTORS = ("maind", "analyst", "harness", "skiller")


def module_sources():
    for lib in sorted(PACKAGES.glob("*/lib")):
        for path in sorted(lib.rglob("*.py")):
            yield path


class PythonFloorTests(unittest.TestCase):
    def test_aicore_floor_is_python_311(self):
        sys.path.insert(0, str(PACKAGES / "aicore" / "lib"))
        try:
            import aicore
        finally:
            sys.path.pop(0)
        self.assertEqual(tuple(aicore.MIN_PYTHON), (3, 11))

    def test_no_module_names_the_old_floor(self):
        hits = [str(p.relative_to(ROOT)) for p in module_sources() if STALE.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(hits, [])

    def test_module_doctors_read_the_constant(self):
        for module in DOCTORS:
            path = PACKAGES / module / "lib" / module / "doctor.py"
            text = path.read_text(encoding="utf-8")
            self.assertIn("MIN_PYTHON", text, f"{module} doctor does not use aicore.MIN_PYTHON")
            self.assertNotRegex(text, r"version_info\s*[<>]=?\s*\(3,\s*\d+\)", f"{module} doctor has a literal floor")


if __name__ == "__main__":
    unittest.main()
