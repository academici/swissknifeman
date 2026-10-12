"""harness depends on the aicore foundation only: no `core` import, no monorepo-root path logic in
the wrappers and no path of another module.

The instruction catalog and its fixtures name module files as data (hub path_allow entries); they are
JSON and are not scanned. The scan reads the package files from disk, so it also runs in a standalone
copy without Git.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
ZONES = ("lib", "bin", "scripts", "tests")
SUFFIXES = {".py", ".sh"}
CORE_IMPORT = re.compile(r"^\s*(from\s+core(\.|\s)|import\s+core\b)")
# built from parts: the acceptance grep for the old wrapper variable also reads compiled bytecode of this file
MONOREPO_PATH_LOGIC = re.compile("|".join(("_".join(("MONOREPO", "ROOT")), "(?<!find_)monorepo_root")))
OTHER_MODULE_PATH = re.compile(r"packages/(maind|analyst|skiller|planner|brain|orch|aicore|artifex)\b")
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
            # bin/harness has no suffix; every other file is scanned by suffix.
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
        self.assertIn("lib/harness/common.py", scanned)
        self.assertIn("bin/harness", scanned)
        self.assertIn("scripts/test.sh", scanned)
        self.assertIn("tests/test_run_worker.py", scanned)

    def test_no_core_import(self):
        self.assertEqual(self.scan(CORE_IMPORT), [])

    def test_no_monorepo_root_path_logic(self):
        self.assertEqual(self.scan(MONOREPO_PATH_LOGIC), [])

    def test_no_path_of_another_module(self):
        self.assertEqual(self.scan(OTHER_MODULE_PATH), [])

    def test_core_import_pattern_matches_import_forms(self):
        for line in ("import core", "from core import x", "from core.io import x", "  import core  # c"):
            self.assertTrue(CORE_IMPORT.search(line), line)
        for line in ("from aicore import x", "import coreutils", "from harness.common import core_x",
                     "# import core"):
            self.assertFalse(CORE_IMPORT.search(line), line)

    def test_monorepo_pattern_spares_the_aicore_helper_name(self):
        self.assertTrue(MONOREPO_PATH_LOGIC.search("monorepo_root=root"))
        self.assertFalse(MONOREPO_PATH_LOGIC.search("find_monorepo_root(env.root)"))


if __name__ == "__main__":
    unittest.main()
