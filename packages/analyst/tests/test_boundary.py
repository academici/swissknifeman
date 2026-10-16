"""analyst depends on the aicore foundation only: no `core` import, no monorepo-root path logic,
and no path of another module.

The scan reads the package files from disk, so it also runs in a standalone copy without Git.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
ZONES = ("lib", "bin", "scripts", "tests")
SUFFIXES = {".py", ".sh"}
CORE_IMPORT = re.compile(r"^\s*(from\s+core(\.|\s)|import\s+core\b)")
OTHER_MODULE_PATH = re.compile(r"packages/(maind|harness|skiller|planner|brain|orch|aicore)/")
SKIPPED_PARTS = {"__pycache__", "node_modules"}


def scanned_lines(path):
    """(number, line) of a file without the shared aicore locator fragment (a verbatim copy)."""
    inside = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("# --- aicore locator ---"):
            inside = True
        if not inside:
            yield number, line
        if line.startswith("# --- end aicore locator ---"):
            inside = False


def sources():
    for zone in ZONES:
        base = ROOT / zone
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or SKIPPED_PARTS & set(path.parts):
                continue
            # bin/analyst has no suffix; every other file is scanned by suffix.
            if path.suffix in SUFFIXES or path.parent.name == "bin":
                yield path


class BoundaryTests(unittest.TestCase):
    def scan(self, pattern):
        hits = []
        for path in sources():
            if path.resolve() == SELF:
                continue
            for number, line in scanned_lines(path):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        return hits

    def test_scan_covers_the_package(self):
        scanned = {path.relative_to(ROOT).as_posix() for path in sources()}
        self.assertIn("lib/analyst/common.py", scanned)
        self.assertIn("bin/analyst", scanned)
        self.assertIn("scripts/test.sh", scanned)

    def test_no_core_import(self):
        self.assertEqual(self.scan(CORE_IMPORT), [])

    def test_no_monorepo_root_path_logic(self):
        self.assertEqual(self.scan(re.compile(r"MONOREPO_ROOT|find_monorepo_root|monorepo_root")), [])

    def test_no_path_of_another_module(self):
        self.assertEqual(self.scan(OTHER_MODULE_PATH), [])

    def test_core_import_pattern_matches_import_forms(self):
        for line in ("import core", "from core import x", "from core.io import x", "  import core  # c"):
            self.assertTrue(CORE_IMPORT.search(line), line)
        for line in ("from aicore import x", "import coreutils", "from analyst.common import core_x",
                     "# import core"):
            self.assertFalse(CORE_IMPORT.search(line), line)


if __name__ == "__main__":
    unittest.main()
