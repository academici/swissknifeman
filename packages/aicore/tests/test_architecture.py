"""Architecture checks: aicore imports only itself and the standard library."""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib" / "aicore"

# Python 3.9 has no sys.stdlib_module_names; this list covers the modules aicore uses.
_STDLIB_FALLBACK = frozenset({
    "__future__", "ast", "collections", "concurrent", "contextlib", "copy", "dataclasses",
    "datetime", "enum", "fcntl", "functools", "hashlib", "http", "inspect", "io",
    "itertools", "json", "math", "os", "pathlib", "re", "select", "shutil", "signal",
    "subprocess", "sys", "tempfile", "textwrap", "threading", "time", "tomllib", "types",
    "typing",
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


def _aicore_targets(path):
    """Yield (sibling subpackage, line) for every import of another aicore subpackage in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level >= 2:
            if node.module:
                yield node.module.split(".")[0], node.lineno
            else:  # ``from .. import util``
                for alias in node.names:
                    yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split(".")  # ``from aicore.provider import x``
            if parts[0] == "aicore" and len(parts) > 1:
                yield parts[1], node.lineno
        elif isinstance(node, ast.Import):
            for alias in node.names:  # ``import aicore.provider``
                parts = alias.name.split(".")
                if parts[0] == "aicore" and len(parts) > 1:
                    yield parts[1], node.lineno


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
        """Layering: util -> nothing; state -> util; config -> util, state; provider -> util, artifacts."""
        def check(directory, allowed):
            for path in sorted((LIB / directory).glob("*.py")):
                for target, line in _aicore_targets(path):
                    self.assertIn(target, allowed, f"{directory}/{path.name}:{line} imports {target}")

        for path in sorted((LIB / "util").glob("*.py")):
            for target, line in _aicore_targets(path):
                self.assertNotIn(target, ("provider", "artifacts", "state", "config"), f"{path.name}:{line}")
        check("state", ("util",))
        check("config", ("util", "state", "_vendor"))
        check("provider", ("util", "artifacts"))
        for path in sorted((LIB / "artifacts").glob("*.py")) + [LIB / "usage.py"]:
            for target, line in _aicore_targets(path):
                self.assertNotIn(target, ("state", "config"), f"{path.name}:{line}")

    def test_config_modules_do_not_depend_on_the_model(self):
        """toml, toml_edit and secrets are below the model and must not import it."""
        for name in ("toml.py", "toml_edit.py", "secrets.py"):
            tree = ast.parse((LIB / "config" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1:
                    self.assertNotEqual(node.module, "model", f"config/{name}:{node.lineno}")

    def test_toml_is_imported_in_one_place_only(self):
        """``tomllib`` and ``tomli`` are imported only by ``config/toml.py`` (and inside ``_vendor``)."""
        offenders = []
        for path in sorted(LIB.rglob("*.py")):
            where = path.relative_to(LIB).as_posix()
            if where.startswith("_vendor/") or where == "config/toml.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [alias.name for alias in node.names]
                for name in names:
                    if {"tomllib", "tomli"} & set(name.split(".")):
                        offenders.append(f"{where}:{node.lineno} imports {name}")
        self.assertEqual(offenders, [])
        imports = {name for name, _level, _line in _imports(LIB / "config" / "toml.py")}
        self.assertIn("tomllib", imports)

    def test_one_canonical_json_and_one_digest_implementation(self):
        """Canonical JSON and tagged SHA-256 of JSON live in util/digest.py only."""
        definitions, hashing = [], []
        for path in sorted(LIB.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            where = path.relative_to(LIB).as_posix()
            if re.search(r"^\s*def canonical_json_bytes\b", text, re.M):
                definitions.append(where)
            if re.search(r"sha256\(\s*json\.dumps\(", text):
                hashing.append(where)
        self.assertEqual(definitions, ["util/digest.py"])
        self.assertEqual(hashing, [])

    def test_provider_layer_has_no_waiting_or_retry(self):
        """The provider layer states facts; waiting and repeating belong to the run engine."""
        offenders = []
        for path in sorted((LIB / "provider").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.search(
                        r"retry|backoff", node.name, re.I):
                    offenders.append(f"{path.name}:{node.lineno} defines {node.name}")
                elif isinstance(node, ast.Call):
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    if name == "sleep":
                        offenders.append(f"{path.name}:{node.lineno} calls sleep")
        self.assertEqual(offenders, [])

    def test_schema_validator_is_defined_once(self):
        defining = [path.relative_to(ROOT).as_posix() for path in sorted(LIB.rglob("*.py"))
                    if "def load_registry" in path.read_text(encoding="utf-8")]
        self.assertEqual(defining, ["lib/aicore/util/schema.py"])


if __name__ == "__main__":
    unittest.main()
