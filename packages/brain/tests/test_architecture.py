"""Module boundary: lib/brain imports only the standard library, brain.* and aicore.*."""
import ast
import importlib.util
import re
import sys
import sysconfig
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib" / "brain"
FORBIDDEN = {"skiller", "maind", "core", "task", "planner", "orch", "analyst", "harness"}
ALLOWED_THIRD_PARTY = {"brain", "aicore", "__future__"}
STDLIB = Path(sysconfig.get_paths()["stdlib"]).resolve()


def is_stdlib(root: str) -> bool:
    if root in sys.builtin_module_names:
        return True
    spec = importlib.util.find_spec(root)
    origin = getattr(spec, "origin", None)
    if not origin or origin in ("built-in", "frozen"):
        return spec is not None
    path = Path(origin).resolve()
    return STDLIB in path.parents and "site-packages" not in path.parts


def imported_roots(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


class TestBoundary(unittest.TestCase):
    def test_sources_are_found(self):
        self.assertGreaterEqual(len(list(LIB.glob("*.py"))), 9)

    def test_no_forbidden_import(self):
        for path in sorted(LIB.glob("*.py")):
            with self.subTest(file=path.name):
                self.assertFalse(FORBIDDEN & set(imported_roots(path)))

    def test_only_stdlib_brain_and_aicore(self):
        for path in sorted(LIB.glob("*.py")):
            with self.subTest(file=path.name):
                extra = {root for root in imported_roots(path) if root not in ALLOWED_THIRD_PARTY and not is_stdlib(root)}
                self.assertEqual(set(), extra)

    def test_layers(self):
        # errors and frontmatter are the bottom layer: they import no sibling module.
        for name in ("errors.py", "frontmatter.py"):
            tree = ast.parse((LIB / name).read_text(encoding="utf-8"))
            relative = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level > 0]
            self.assertEqual([], relative, name)


WRITERS = {"notes.py", "docs.py"}
WRITES = re.compile(r"O_WRONLY|O_RDWR|O_CREAT|write_text|write_bytes|shutil\.(copy|move)|os\.(replace|rename|link|symlink|"
                    r"unlink|remove|rmdir|makedirs|mkdir|truncate|utime|chmod)|rmtree|\.(mkdir|touch|unlink|rmdir)\(|"
                    r"open\([^)]*['\"][wax+]")


class TestVaultWrites(unittest.TestCase):
    def test_only_notes_and_docs_write_files(self):
        """The vault is the person's data: the write paths are in two reviewed modules (notes.py, docs.py)."""
        for path in sorted(LIB.glob("*.py")):
            if path.name in WRITERS:
                continue
            with self.subTest(file=path.name):
                self.assertEqual([], WRITES.findall(path.read_text(encoding="utf-8")))

    def test_the_pattern_sees_writes(self):
        for sample in ("os.open(p, os.O_WRONLY)", "path.write_text('x')", "open(p, 'w')", "os.link(a, b)",
                       "shutil.copy2(a, b)", "p.mkdir()"):
            self.assertTrue(WRITES.search(sample), sample)
        self.assertFalse(WRITES.search("open(p, 'rb')"))

    def test_note_writes_stay_behind_the_lock(self):
        """Creating a note and touching the ledger take the lock object as an argument."""
        tree = ast.parse((LIB / "notes.py").read_text(encoding="utf-8"))
        functions = {n.name: [a.arg for a in n.args.args] for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for name in ("_create_new", "_append_ledger", "_read_ledger", "_write_once"):
            self.assertEqual("lock", functions[name][0], name)


if __name__ == "__main__":
    unittest.main()
