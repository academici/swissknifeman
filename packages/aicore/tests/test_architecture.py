"""Architecture checks: aicore imports only itself and the standard library."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib" / "aicore"

# Python 3.9 has no sys.stdlib_module_names; this list covers the modules aicore uses.
_STDLIB_FALLBACK = frozenset({
    "__future__", "collections", "concurrent", "contextlib", "copy", "dataclasses",
    "datetime", "enum", "fcntl", "functools", "hashlib", "http", "inspect", "io",
    "itertools", "json", "math", "os", "pathlib", "re", "select", "shutil", "signal",
    "subprocess", "sys", "tempfile", "textwrap", "threading", "time", "types", "typing",
    "unittest", "urllib", "uuid",
})
STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) | _STDLIB_FALLBACK


def _imports(path):
    """Yield (top-level name, level, line) for every import statement in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], 0, node.lineno
        elif isinstance(node, ast.ImportFrom):
            yield (node.module or "").split(".")[0], node.level, node.lineno


class TestImportBoundary(unittest.TestCase):
    def test_lib_imports_only_stdlib_and_aicore(self):
        bad = []
        for path in sorted(LIB.rglob("*.py")):
            for name, level, line in _imports(path):
                if level == 0 and name not in STDLIB and name != "aicore":
                    bad.append(f"{path.relative_to(ROOT)}:{line} imports {name}")
        self.assertEqual(bad, [])

    def test_tests_import_only_stdlib_aicore_and_tests(self):
        bad = []
        for path in sorted((ROOT / "tests").rglob("*.py")):
            for name, level, line in _imports(path):
                if level == 0 and name not in STDLIB and name not in ("aicore", "tests"):
                    bad.append(f"{path.relative_to(ROOT)}:{line} imports {name}")
        self.assertEqual(bad, [])

    def test_core_is_never_imported(self):
        offenders = []
        for path in sorted(ROOT.joinpath("lib").rglob("*.py")) + sorted(ROOT.joinpath("tests").rglob("*.py")):
            for name, level, line in _imports(path):
                if level == 0 and name == "core":
                    offenders.append(f"{path.relative_to(ROOT)}:{line}")
        self.assertEqual(offenders, [])

    def test_usage_is_self_sufficient(self):
        for name, level, line in _imports(LIB / "usage.py"):
            self.assertEqual(level, 0, f"usage.py:{line} uses a relative import")
            self.assertNotEqual(name, "aicore", f"usage.py:{line} imports aicore")

    def test_subpackage_layering(self):
        """Layering: util imports no sibling subpackage; provider reaches only util and artifacts."""
        def aicore_targets(path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level >= 2:
                    yield (node.module or "").split(".")[0], node.lineno
        for path in sorted((LIB / "util").glob("*.py")):
            for target, line in aicore_targets(path):
                self.assertNotIn(target, ("provider", "artifacts"), f"{path.name}:{line}")
        for path in sorted((LIB / "provider").glob("*.py")):
            for target, line in aicore_targets(path):
                self.assertIn(target, ("util", "artifacts"), f"{path.name}:{line}")


if __name__ == "__main__":
    unittest.main()
