"""Package boundary: the core never names another package of the repository.

Knowledge of a partner lives only in ``bridges/<partner>/``. The aicore foundation is the shared base and
stays allowed, but only through ``lib/planner/integration`` and the projection renderer; the plan engine
runs without it. ``boundary_allowlist.json`` lists temporary violations by file with the owning plan
item; it may only shrink, so a stale entry fails the test as well.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
ALLOWLIST = ROOT / "tests" / "boundary_allowlist.json"

_NAMES = "orch|skiller|harness|maind|analyst|artifex"
FORBIDDEN = (
    re.compile(rf"packages/({_NAMES})\b"),
    re.compile(rf"^\s*(from|import)\s+({_NAMES})\b"),
    re.compile(rf"\b({_NAMES})\b"),
    re.compile(r"exec/v1"),
    re.compile(r"urn:swissknifeman:orch:"),
    re.compile(r"\b(general|quality|system|devops|oss-dev|repository-bootstrap)[/:][a-z][a-z0-9-]+"),
)
# skills/workflow-craft/ is workflow-authoring guidance moved verbatim from the skiller library (its content
# names the orchestration partners by design and is not edited); the code and commands stay checked.
SKIPPED_DIRS = ("bridges/", "docs/.vitepress/cache/", "docs/.vitepress/dist/", "skills/workflow-craft/")
SKIPPED_PARTS = {"__pycache__", "node_modules"}
SKIPPED_FILES = {"CHANGELOG.md", SELF}
REASON = re.compile(r"^P7\.[0-9]+: \S")


def core_files() -> list[str]:
    files = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT).as_posix()
        if (not path.is_file() or relative in SKIPPED_FILES or relative.startswith(SKIPPED_DIRS)
                or SKIPPED_PARTS & set(path.relative_to(ROOT).parts)
                or any(parts == (".claude", "runs") for parts in
                       zip(path.relative_to(ROOT).parts, path.relative_to(ROOT).parts[1:]))):
            continue
        files.append(relative)
    return files


def violations(relative: str) -> list[str]:
    try:
        text = (ROOT / relative).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []  # binary files carry no references
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            match = pattern.search(line)
            if match:
                found.append(f"{relative}:{number}: {match.group(0).strip()}")
                break
    return found


def allowlist() -> dict[str, str]:
    return json.loads(ALLOWLIST.read_text(encoding="utf-8")) if ALLOWLIST.exists() else {}


class BoundaryTests(unittest.TestCase):
    def test_core_names_no_other_package(self):
        allowed = allowlist()
        found = [hit for relative in core_files() if relative not in allowed for hit in violations(relative)]
        self.assertEqual(found, [], "core references another package; move it into bridges/<partner>/:\n"
                         + "\n".join(found))

    def test_allowlist_only_shrinks(self):
        stale = [f"{relative}: {reason}" for relative, reason in allowlist().items()
                 if not (ROOT / relative).is_file() or not violations(relative)]
        self.assertEqual(stale, [], "remove stale allowlist entries:\n" + "\n".join(stale))

    def test_allowlist_entries_name_their_owner(self):
        for relative, reason in allowlist().items():
            with self.subTest(relative):
                self.assertRegex(reason, REASON)
                self.assertFalse(relative.startswith(("/", "packages/")), "paths are relative to the package")

    def test_aicore_foundation_stays_allowed(self):
        for line in ("from aicore.provider import render", "import aicore", "packages/aicore/lib"):
            with self.subTest(line):
                self.assertFalse(any(p.search(line) for p in FORBIDDEN))

    def test_tokens_are_caught_and_longer_words_are_not(self):
        for line in ("see packages/maind/README.md", "import skiller.registry", "the orch runner",
                     "contract exec/v1", "urn:swissknifeman:orch:exec:brief:v1", "quality:code-review"):
            with self.subTest(line):
                self.assertTrue(any(p.search(line) for p in FORBIDDEN))
        for line in ("orchestration and the orchestrator", "harnessing", "planner:plan-run"):
            with self.subTest(line):
                self.assertFalse(any(p.search(line) for p in FORBIDDEN))


_FOUNDATION_IMPORT = re.compile(r"^\s*(from|import)\s+(core|aicore)\b")
_AICORE_USERS = ("lib/planner/integration/", "lib/planner/command_render.py")
_CLEAN_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT")


def _python_files(*parts: str) -> list[Path]:
    return sorted(path for path in ROOT.joinpath(*parts).rglob("*.py") if "__pycache__" not in path.parts)


class FoundationLayerTests(unittest.TestCase):
    def test_aicore_is_imported_only_by_integration_and_the_renderer(self):
        found = []
        for path in _python_files("lib", "planner"):
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith(_AICORE_USERS):
                continue
            found += [f"{relative}:{number}: {line.strip()}"
                      for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                      if _FOUNDATION_IMPORT.match(line)]
        self.assertEqual(found, [], "only planner.integration and command_render import the foundation")

    def test_engine_and_tests_import_no_core_package(self):
        found = []
        for path in _python_files("lib") + _python_files("tests") + _python_files("scripts"):
            if path.name == Path(__file__).name:
                continue
            found += [f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}"
                      for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                      if re.match(r"^\s*(from|import)\s+core\b", line)]
        self.assertEqual(found, [], "the transitional core package is not a planner dependency")

    def test_engine_names_neither_foundation_package(self):
        for path in _python_files("lib", "planner", "plan"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                with self.subTest(f"{path.name}:{number}"):
                    self.assertIsNone(_FOUNDATION_IMPORT.match(line), line)

    def test_integration_modules_import_aicore_lazily(self):
        for path in _python_files("lib", "planner", "integration"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                with self.subTest(f"{path.name}:{number}"):
                    self.assertFalse(re.match(r"^(from|import)\s+aicore\b", line), line)


class EngineWithoutAicoreTests(unittest.TestCase):
    """A copy of the module without a neighbouring aicore still runs the plan engine."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skm-planner-solo-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.copy = self.tmp / "planner"
        shutil.copytree(ROOT, self.copy, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        self.env = {key: os.environ[key] for key in _CLEAN_ENV_KEYS if key in os.environ}
        self.env.update(HOME=str(self.tmp / "home"), SKM_HOME=str(self.tmp / "skm"))

    def run_python(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *args], cwd=self.tmp, env=self.env, capture_output=True,
                              text=True, check=False)

    def make_plan(self) -> Path:
        script = ("import sys; from pathlib import Path\n"
                  f"sys.path[:0] = [{str(self.copy / 'lib')!r}, {str(self.copy / 'tests' / 'engine')!r}]\n"
                  f"import demo; print(demo.make_demo_plan(Path({str(self.tmp / 'plans')!r})))\n")
        result = self.run_python("-c", script)
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def test_check_and_next_work(self):
        plan = self.make_plan()
        launcher = str(self.copy / "scripts" / "plan.py")
        check = self.run_python(launcher, "check", str(plan))
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        step = self.run_python(launcher, "next", str(plan))
        self.assertEqual(step.returncode, 0, step.stderr)
        self.assertTrue(step.stdout.strip(), "next prints the next step")

    def test_integration_reports_the_missing_foundation(self):
        script = (f"import json, sys; sys.path.insert(0, {str(self.copy / 'lib')!r})\n"
                  "from planner import integration\n"
                  "print(json.dumps([integration.available(), integration.status()]))\n")
        result = self.run_python("-c", script)
        self.assertEqual(result.returncode, 0, result.stderr)
        available, status = json.loads(result.stdout)
        self.assertFalse(available)
        self.assertEqual(status["aicore"], "unavailable")
        self.assertIsNone(status["root"])
        self.assertTrue(status["reason"])

    def test_require_refuses_with_a_stable_code(self):
        script = (f"import sys; sys.path.insert(0, {str(self.copy / 'lib')!r})\n"
                  "from planner import integration\n"
                  "from planner.plan.model import PlanError\n"
                  "try:\n    integration.require('config')\nexcept PlanError as exc:\n    print(exc.code, exc.message)\n")
        result = self.run_python("-c", script)
        self.assertEqual(result.stdout.strip(), "AICORE_REQUIRED config needs the aicore foundation; set AICORE_ROOT")

    def test_renderer_refuses_without_aicore(self):
        result = self.run_python(str(self.copy / "scripts" / "render-provider-commands.py"),
                                 "--check", "--root", str(self.tmp))
        self.assertEqual(result.returncode, 2)
        self.assertIn("AICORE_NOT_FOUND", result.stderr)


if __name__ == "__main__":
    unittest.main()
