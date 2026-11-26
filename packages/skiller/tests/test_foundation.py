"""skiller depends on the aicore foundation only: no `core` import, no monorepo-root path logic.

The scan reads the package files from disk, so it also runs in a standalone copy without Git.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
ZONES = ("lib", "bin", "scripts", "tests")
TOP_FILES = ("install.sh",)
SUFFIXES = {".py", ".sh"}
CORE_IMPORT = re.compile(r"^\s*(from\s+core(\.|\s)|import\s+core\b)", re.MULTILINE)
SKIPPED_PARTS = {"__pycache__", "node_modules"}


def sources():
    for zone in ZONES:
        base = ROOT / zone
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or SKIPPED_PARTS & set(path.parts):
                continue
            # bin/skiller has no suffix; every other file is scanned by suffix.
            if path.suffix in SUFFIXES or path.parent.name == "bin":
                yield path
    for name in TOP_FILES:
        if (ROOT / name).is_file():
            yield ROOT / name


class FoundationTests(unittest.TestCase):
    def scan(self, pattern):
        hits = []
        for path in sources():
            if path.resolve() == SELF:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        return hits

    def test_scan_covers_the_package(self):
        scanned = {path.relative_to(ROOT).as_posix() for path in sources()}
        self.assertIn("lib/skiller/common.py", scanned)
        self.assertIn("bin/skiller", scanned)
        self.assertIn("scripts/test.sh", scanned)

    def test_no_core_import(self):
        self.assertEqual(self.scan(re.compile(CORE_IMPORT.pattern)), [])

    def test_no_monorepo_root_path_logic(self):
        self.assertEqual(self.scan(re.compile(r"MONOREPO_ROOT")), [])

    def test_no_reexport_layer(self):
        self.assertEqual(self.scan(re.compile(r"noqa: F401|re-export")), [])

    def test_removed_wrappers_stay_removed(self):
        for name in ("plugins.py", "native_codex.py"):
            self.assertFalse((ROOT / "lib/skiller" / name).exists(), name)

    def test_core_import_pattern_matches_import_forms(self):
        for line in ("import core", "from core import x", "from core.io import x", "  import core  # c"):
            self.assertTrue(CORE_IMPORT.search(line), line)
        for line in ("from aicore import x", "import coreutils", "from skiller.config import core_skill_tuples",
                     "# import core"):
            self.assertFalse(CORE_IMPORT.search(line), line)


if __name__ == "__main__":
    unittest.main()
