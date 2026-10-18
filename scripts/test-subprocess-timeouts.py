#!/usr/bin/env python3
"""Every child process of the module libraries and bridges has a time limit, or says why it has none.

A `subprocess.run/call/check_output/check_call` in `packages/*/lib` and `bridges/*` must pass `timeout=`, or its line
(or the line above) must carry `# no-timeout: <reason>`: a hung `git` or partner CLI would otherwise hang the whole
pipeline (conductor, bridges, hooks). `aicore.util.proc.run` (and the bridge helper `run_bounded`) take the limit as a
required argument and turn a hang into exit status 124.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALLS = {"run", "call", "check_output", "check_call"}
MARK = "no-timeout:"


def sources():
    for base in [*sorted(ROOT.glob("packages/*/lib")), ROOT / "bridges"]:
        for path in sorted(base.rglob("*.py")):
            parts = path.relative_to(ROOT).parts
            if "_vendor" in parts or "tests" in parts or "skills" in parts:
                continue
            yield path


def unbounded(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for node in ast.walk(ast.parse(text)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CALLS
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
            continue
        if any(keyword.arg == "timeout" for keyword in node.keywords):
            continue
        near = " ".join(lines[max(0, node.lineno - 2):node.lineno])
        if MARK not in near:
            yield node.lineno


class SubprocessTimeoutTests(unittest.TestCase):
    def test_every_subprocess_call_has_a_limit_or_a_reason(self):
        found = [f"{path.relative_to(ROOT)}:{line}" for path in sources() for line in unbounded(path)]
        self.assertEqual(found, [], "pass timeout= (aicore.util.proc.run) or add '# no-timeout: <reason>'")


if __name__ == "__main__":
    unittest.main()
