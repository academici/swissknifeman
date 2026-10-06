from __future__ import annotations

import ast
from pathlib import Path
import pkgutil
import re
import sys
import sysconfig
import unittest


ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
_NAMES = "task|skiller|harness|maind|analyst|artifex"
FORBIDDEN = (
    re.compile(rf"packages/({_NAMES})\b"),
    re.compile(rf"^\s*(from|import)\s+({_NAMES})\b"),
    re.compile(r"\b(skiller|harness|maind|analyst|artifex)\b"),
    re.compile(r"plan\.py"),
    re.compile(r"\btask:[a-z][a-z-]*"),
    re.compile(r"task/(lib|plan|scripts|commands|skills)\b"),
    # The native provider event is not a skill identity.
    re.compile(r"\b(?!system/init(?![a-z0-9-]))(general|quality|system|devops|oss-dev|repository-bootstrap)[/:][a-z][a-z0-9-]+"),
)
SKIPPED_DIRS = ("bridges/", "docs/.vitepress/cache/", "docs/.vitepress/dist/")
SKIPPED_PARTS = {"__pycache__", "node_modules"}


class BoundaryTests(unittest.TestCase):
    def test_core_names_no_other_package(self):
        found = []
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT).as_posix()
            parts = path.relative_to(ROOT).parts
            if (not path.is_file() or relative in {"CHANGELOG.md", SELF}
                    or relative.startswith(SKIPPED_DIRS) or SKIPPED_PARTS & set(parts)
                    or any(pair == (".claude", "runs") for pair in zip(parts, parts[1:]))):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                for pattern in FORBIDDEN:
                    match = pattern.search(line)
                    if match:
                        found.append(f"{relative}:{number}: {match.group(0).strip()}")
                        break
        self.assertEqual(found, [], "core references another package:\n" + "\n".join(found))

    def test_boundary_tokens_and_provider_event(self):
        for line in ("packages/" + "task", "from task.plan import store", "skiller resolve",
                     "plan" + ".py finish", "task:" + "plan-run", "task/commands/dev.md",
                     "quality/code-review", "system/agent-packs", "system/initial", "system/init-extra", "general/verify-claims"):
            with self.subTest(line=line):
                self.assertTrue(any(pattern.search(line) for pattern in FORBIDDEN))
        for line in ("task failures", "plan store", "system/init", "orchestration", "harnessing"):
            with self.subTest(line=line):
                self.assertFalse(any(pattern.search(line) for pattern in FORBIDDEN))

    def test_runtime_imports_are_stdlib_or_orch(self):
        allowed = getattr(sys, "stdlib_module_names", None)
        if allowed is None:  # Python 3.9 CI; stdlib_module_names was added in 3.10.
            paths = {sysconfig.get_path("stdlib"), sysconfig.get_path("platstdlib"),
                     sysconfig.get_config_var("DESTSHARED")}
            allowed = set(sys.builtin_module_names) | {
                info.name for info in pkgutil.iter_modules([p for p in paths if p])
            }
        allowed = set(allowed) | {"orch"}
        root = Path(__file__).resolve().parents[1] / "lib/orch"
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    modules = [node.module]
                for module in modules:
                    with self.subTest(file=path.name, line=node.lineno, module=module):
                        self.assertIn(module.split(".")[0], allowed)
