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
    "itertools", "json", "math", "os", "pathlib", "re", "select", "selectors", "shutil", "signal",
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
        """Layering: util -> nothing; state -> util; config -> util, state; provider -> util, artifacts;
        content -> util, provider, artifacts, config; release -> util, content;
        delivery -> everything below it; ext -> util, state, config, and nothing imports ext;
        project -> util, state, config."""
        def check(directory, allowed):
            for path in sorted((LIB / directory).glob("*.py")):
                for target, line in _aicore_targets(path):
                    self.assertIn(target, allowed, f"{directory}/{path.name}:{line} imports {target}")

        for path in sorted((LIB / "util").glob("*.py")):
            for target, line in _aicore_targets(path):
                self.assertNotIn(target, ("provider", "artifacts", "state", "config", "content", "delivery",
                                          "release"), f"{path.name}:{line}")
        check("state", ("util",))
        check("config", ("util", "state", "_vendor"))
        check("provider", ("util", "artifacts"))
        check("content", ("util", "provider", "artifacts", "config"))
        check("release", ("util", "content"))
        check("delivery", ("util", "state", "config", "provider", "artifacts", "content", "release"))
        check("ext", ("util", "state", "config"))
        check("project", ("util", "state", "config"))
        for directory in ("util", "state", "config", "provider", "artifacts", "content", "release", "delivery"):
            for path in sorted((LIB / directory).glob("*.py")):
                for target, line in _aicore_targets(path):
                    self.assertNotEqual(target, "ext", f"{directory}/{path.name}:{line}")
        for target, line in _aicore_targets(LIB / "usage.py"):
            self.assertNotEqual(target, "ext", f"usage.py:{line}")
        for path in sorted((LIB / "artifacts").glob("*.py")) + [LIB / "usage.py"]:
            for target, line in _aicore_targets(path):
                self.assertNotIn(target, ("state", "config"), f"{path.name}:{line}")
        for directory in ("state", "config", "provider", "artifacts"):
            for path in sorted((LIB / directory).glob("*.py")):
                for target, line in _aicore_targets(path):
                    self.assertNotIn(target, ("content", "delivery", "release"), f"{directory}/{path.name}:{line}")
        for target, line in _aicore_targets(LIB / "usage.py"):
            self.assertNotIn(target, ("content", "delivery", "release"), f"usage.py:{line}")

    def test_top_level_cli_imports_groups_lazily(self):
        """``aicore/cli.py`` names its group modules as strings and imports no subpackage statically."""
        self.assertEqual(list(_aicore_targets(LIB / "cli.py")), [])
        tree = ast.parse((LIB / "cli.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, f"cli.py:{node.lineno}")

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

    def test_content_primitives_are_defined_once(self):
        """The shared content primitives are defined in aicore only, never again in a sibling module."""
        owners = {
            "skill_content_hash": "lib/aicore/content/skill.py",
            "resolve_requires_bfs": "lib/aicore/content/skill.py",
            "estimate_tokens": "lib/aicore/content/budget.py",
            "skill_budget": "lib/aicore/content/budget.py",
            "measure_listing_budget": "lib/aicore/content/budget.py",
            "render_whole_file": "lib/aicore/content/publication.py",
            "codex_plugin_manifest": "lib/aicore/content/publication.py",
            "manifest_bytes": "lib/aicore/content/publication.py",
            "strict_frontmatter_fields": "lib/aicore/content/commands.py",
            "runtime_provenance": "lib/aicore/content/commands.py",
            "grade_assertion": "lib/aicore/content/eval.py",
            "build_benchmark": "lib/aicore/content/eval.py",
            "build_system_benchmark": "lib/aicore/content/eval.py",
            "run_case": "lib/aicore/content/eval.py",
            "compare_eval_context": "lib/aicore/content/eval.py",
            "enable_marketplace_plugins": "lib/aicore/delivery/claude.py",
            "connect_distribution_plan": "lib/aicore/delivery/distribution.py",
            "plan_selection": "lib/aicore/delivery/codex.py",
            "sync_skillset": "lib/aicore/delivery/materialize.py",
            "safe_copy_skill": "lib/aicore/delivery/materialize.py",
            "write_skill_manifest": "lib/aicore/delivery/materialize.py",
        }
        roots = [ROOT / "lib"]
        packages = ROOT.parent
        if (packages / "skiller").is_dir():  # a standalone run has no sibling modules
            roots = sorted(packages.glob("*/lib"))
        for name, owner in owners.items():
            pattern = re.compile(rf"^\s*def {name}\b", re.M)
            found = sorted(
                path.relative_to(packages).as_posix() for lib in roots for path in lib.rglob("*.py")
                if pattern.search(path.read_text(encoding="utf-8")))
            self.assertEqual(found, [f"aicore/{owner}"], name)

    def test_process_spawn_is_in_one_place(self):
        """Processes are started in ``ext/process.py`` only (the discipline of R08 lives there): no other
        module of ``ext`` calls ``subprocess.Popen|run|call|check_call|check_output`` or ``os.fork|posix_spawn``.
        The one exception is the detached background deliverer: ``subprocess.Popen`` inside
        ``delivery.spawn_background``."""
        spawning = {"Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
        forking = {"fork", "forkpty", "posix_spawn", "posix_spawnp", "system", "popen", "execv", "execve"}
        allowed = {"process.py"}
        exception = ("delivery.py", "spawn_background", "Popen")
        offenders, seen, background = [], False, 0
        for path in sorted((LIB / "ext").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

            def function_of(node, parents=parents):
                while node in parents:
                    node = parents[node]
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return node.name
                return None

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "os"):
                    names = {alias.name for alias in node.names}
                    bad = names & (spawning if node.module == "subprocess" else forking)
                    if bad and path.name not in allowed:
                        offenders.append(f"ext/{path.name}:{node.lineno} imports {sorted(bad)}")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and isinstance(node.func.value, ast.Name):
                    owner, name = node.func.value.id, node.func.attr
                    if (owner == "subprocess" and name in spawning) or (owner == "os" and name in forking):
                        if path.name in allowed:
                            seen = seen or (owner == "subprocess" and name == "Popen")
                        elif (path.name, function_of(node), name) == exception and owner == "subprocess":
                            background += 1
                        else:
                            offenders.append(f"ext/{path.name}:{node.lineno} calls {owner}.{name}")
        self.assertEqual(offenders, [])
        self.assertTrue(seen, "ext/process.py no longer spawns with subprocess.Popen")
        self.assertEqual(background, 1, "delivery.spawn_background starts the deliverer with one subprocess.Popen")

    def test_ext_has_no_mcp(self):
        """``aicore.ext`` is not an MCP bus (R24): no file of ``ext`` imports a module with ``mcp`` in its name
        or mentions ``mcp`` at all (checked on the whole text, case-insensitively)."""
        offenders = []
        for path in sorted((LIB / "ext").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(text, filename=str(path))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [alias.name for alias in node.names]
                if any("mcp" in name.lower() for name in names):
                    offenders.append(f"ext/{path.name}:{node.lineno} imports {names}")
            for number, line in enumerate(text.splitlines(), 1):
                if "mcp" in line.lower():
                    offenders.append(f"ext/{path.name}:{number} mentions mcp")
        self.assertEqual(offenders, [])

    def test_only_journal_writes_the_journal(self):
        """The name of the project event journal appears in ``ext/journal.py`` only (it is the one writer).
        ``provider/request_lifecycle.py`` keeps its own per-request ``events.jsonl`` in another directory."""
        own_file = {"provider/request_lifecycle.py"}
        offenders = [path.relative_to(LIB).as_posix() for path in sorted(LIB.rglob("*.py"))
                     if "events.jsonl" in path.read_text(encoding="utf-8")
                     and path.relative_to(LIB).as_posix() not in own_file | {"ext/journal.py"}]
        self.assertEqual(offenders, [])
        self.assertIn("events.jsonl", (LIB / "ext" / "journal.py").read_text(encoding="utf-8"))
        self.assertIn("events.jsonl", (LIB / "provider" / "request_lifecycle.py").read_text(encoding="utf-8"))

    def test_schema_validator_is_defined_once(self):
        defining = [path.relative_to(ROOT).as_posix() for path in sorted(LIB.rglob("*.py"))
                    if "def load_registry" in path.read_text(encoding="utf-8")]
        self.assertEqual(defining, ["lib/aicore/util/schema.py"])


if __name__ == "__main__":
    unittest.main()
