"""The Python 3.11 floor reads TOML with tomllib, so aicore ships no vendored parser."""
import ast
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib" / "aicore"


class TestNoVendoredLibraries(unittest.TestCase):
    def test_vendor_directory_is_absent(self):
        self.assertFalse((LIB / "_vendor").exists())

    def test_library_does_not_import_tomli(self):
        hits = []
        for path in sorted(LIB.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    if name.split(".")[0] == "tomli":
                        hits.append(f"{path.relative_to(LIB)}:{node.lineno}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
