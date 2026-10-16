from __future__ import annotations

import ast
import os
from pathlib import Path
import pkgutil
import re
import sys
import sysconfig
import unittest


ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
_NAMES = "planner|skiller|harness|maind|analyst"
FORBIDDEN = (
    re.compile(rf"packages/({_NAMES})\b"),
    re.compile(rf"^\s*(from|import)\s+({_NAMES})\b"),
    re.compile(r"\b(skiller|harness|maind|analyst)\b"),
    re.compile(r"plan\.py"),
    re.compile(r"\bplanner:[a-z][a-z-]*"),
    re.compile(r"planner/(lib|plan|scripts|commands|skills)\b"),
    # The native provider event is not a skill identity.
    re.compile(r"\b(?!system/init(?![a-z0-9-]))(general|quality|system|devops|oss-dev|repository-bootstrap)[/:][a-z][a-z0-9-]+"),
)
# docs/research/ is a verbatim historical record of the design research; it names partners by nature.
# dev-skills/ are agent skills for operating the hub (they name the commands of the other packages, like the dev-skills of
# every module); they are not module code.
SKIPPED_DIRS = ("docs/research/", "docs/.vitepress/cache/", "docs/.vitepress/dist/", "dev-skills/")
SKIPPED_PARTS = {"__pycache__", "node_modules"}
# Generated instruction projections (harness instruction catalog); their boundary sentence names the partners once.
GENERATED_INSTRUCTIONS = {"CLAUDE.md", "AGENTS.md", ".cursor-instructions.mdc", ".grok-instructions.md"}


def _names_artifacts(node) -> bool:
    """Whether an expression names the artifact folder of a piece: ``item.artifacts``, a name ``artifacts``, an
    ``artifacts_dir`` key or attribute, or the ``orch-artifacts`` fallback folder."""
    for part in ast.walk(node):
        if isinstance(part, ast.Attribute) and part.attr in ("artifacts", "artifacts_dir"):
            return True
        if isinstance(part, ast.Name) and part.id in ("artifacts", "artifacts_dir"):
            return True
        if isinstance(part, ast.Constant) and isinstance(part.value, str) \
                and (part.value == "artifacts_dir" or "orch-artifacts" in part.value):
            return True
    return False


class BoundaryTests(unittest.TestCase):
    def test_core_names_no_other_package(self):
        found = []
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT).as_posix()
            parts = path.relative_to(ROOT).parts
            if (not path.is_file() or relative in GENERATED_INSTRUCTIONS | {"CHANGELOG.md", SELF}
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
        for line in ("packages/" + "planner", "from planner.plan import store", "skiller resolve",
                     "plan" + ".py finish", "planner:" + "plan-run", "planner/commands/dev.md",
                     "quality/code-review", "system/agent-packs", "system/initial", "system/init-extra", "general/verify-claims"):
            with self.subTest(line=line):
                self.assertTrue(any(pattern.search(line) for pattern in FORBIDDEN))
        for line in ("task failures", "plan store", "system/init", "orchestration", "harnessing"):
            with self.subTest(line=line):
                self.assertFalse(any(pattern.search(line) for pattern in FORBIDDEN))

    def test_runtime_imports_are_stdlib_orch_or_aicore(self):
        allowed = getattr(sys, "stdlib_module_names", None)
        if allowed is None:  # Python 3.9 CI; stdlib_module_names was added in 3.10.
            paths = {sysconfig.get_path("stdlib"), sysconfig.get_path("platstdlib"),
                     sysconfig.get_config_var("DESTSHARED")}
            allowed = set(sys.builtin_module_names) | {
                info.name for info in pkgutil.iter_modules([p for p in paths if p])
            }
        allowed = set(allowed) | {"orch", "aicore"}
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

    def test_plan_artifacts_and_transitions_only_in_the_work_source_module(self):
        """knowledge/p11-refactor#fs: inside the conductor, only ``infrastructure/work_source.py`` builds a path into the
        artifact folder of a piece (``item.artifacts``, ``artifacts_dir``, ``orch-artifacts``), builds an ``orch.py source``
        command line or runs one; nobody runs the plan command line (``test_core_names_no_other_package`` bans its name)."""
        conductor = ROOT / "lib" / "orch" / "conductor"
        allowed = conductor / "infrastructure" / "work_source.py"
        self.assertTrue(allowed.is_file())
        found = []
        for path in sorted(conductor.rglob("*.py")):
            if path == allowed:
                continue
            relative = path.relative_to(conductor).as_posix()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) \
                        and any(_names_artifacts(side) for side in (node.left, node.right)):
                    found.append(f"{relative}:{node.lineno}: a path into the artifacts")
                elif isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) > 1 \
                        and all(isinstance(elt, ast.Constant) and isinstance(elt.value, str) for elt in node.elts[:2]) \
                        and node.elts[0].value == "source":
                    found.append(f"{relative}:{node.lineno}: an orch.py source command line")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr in ("_orch", "run_orch"):
                    found.append(f"{relative}:{node.lineno}: a call of orch.py source")
        self.assertEqual(found, [], "outside infrastructure/work_source.py:\n" + "\n".join(found))

    def test_the_work_source_rule_sees_each_form(self):
        for text in ('item.artifacts / "x.json"', 'Path(".swissknifeman") / "orch-artifacts"', 'root / brief["artifacts_dir"]',
                     'artifacts / "evidence"'):
            with self.subTest(text=text):
                node = ast.parse(text, mode="eval").body
                self.assertTrue(any(_names_artifacts(side) for side in (node.left, node.right)))
        for text in ('self.project / "x"', 'item.directory / "reports"'):
            with self.subTest(text=text):
                node = ast.parse(text, mode="eval").body
                self.assertFalse(any(_names_artifacts(side) for side in (node.left, node.right)))

    def test_no_mcp_imports(self):
        """MCP is a tool surface, not the event bus: neither orch nor the aicore extension layer imports it."""
        aicore = Path(os.environ.get("AICORE_ROOT") or ROOT.parent / "aicore")
        extension = aicore / "lib" / "aicore" / "ext"
        self.assertTrue(extension.is_dir(), f"aicore extension layer not found at {extension}")
        found = []
        for base in (ROOT / "lib" / "orch", extension):
            for path in sorted(base.rglob("*.py")):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        modules = [node.module or ""] + [alias.name for alias in node.names]
                    else:
                        continue
                    found += [f"{path.name}:{node.lineno}: {module}" for module in modules if "mcp" in module.lower()]
        self.assertEqual(found, [])

