from __future__ import annotations

import ast
from pathlib import Path
import pkgutil
import sys
import sysconfig
import unittest


class BoundaryTests(unittest.TestCase):
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
