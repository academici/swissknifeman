#!/usr/bin/env python3
"""The Python floor of the hub has one source: aicore.MIN_PYTHON.

No module code names an older floor, and every module doctor that checks the interpreter reads the
constant instead of a literal version tuple.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
STALE = re.compile(r"version_info\s*>=\s*\(3,\s*8\)|python3\.8\+|python>=3\.8|python3\s*>=\s*3\.8")
DOCTORS = ("maind", "analyst", "harness", "skiller")


def module_sources():
    for lib in sorted(PACKAGES.glob("*/lib")):
        for path in sorted(lib.rglob("*.py")):
            yield path


class PythonFloorTests(unittest.TestCase):
    def test_aicore_floor_is_python_39(self):
        sys.path.insert(0, str(PACKAGES / "aicore" / "lib"))
        try:
            import aicore
        finally:
            sys.path.pop(0)
        self.assertEqual(tuple(aicore.MIN_PYTHON), (3, 9))

    def test_no_module_names_the_old_floor(self):
        hits = [str(p.relative_to(ROOT)) for p in module_sources() if STALE.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(hits, [])

    def test_module_doctors_read_the_constant(self):
        for module in DOCTORS:
            path = PACKAGES / module / "lib" / module / "doctor.py"
            text = path.read_text(encoding="utf-8")
            self.assertIn("MIN_PYTHON", text, f"{module} doctor does not use aicore.MIN_PYTHON")
            self.assertNotRegex(text, r"version_info\s*[<>]=?\s*\(3,\s*\d+\)", f"{module} doctor has a literal floor")


def _annotation_ids(tree):
    """ids of every node that sits inside an annotation (lazy under `from __future__ import annotations`)."""
    inside = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                if arg is not None and arg.annotation is not None:
                    annotations.append(arg.annotation)
            if node.returns is not None:
                annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        for annotation in annotations:
            inside.update(id(child) for child in ast.walk(annotation))
    return inside


class RuntimeUnionTests(unittest.TestCase):
    """`X | None` evaluated at runtime (an alias, a cast, a default) raises TypeError on Python 3.9."""

    def test_no_runtime_union_with_none(self):
        hits = []
        for path in module_sources():
            if "_vendor" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            inside = _annotation_ids(tree)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)) or id(node) in inside:
                    continue
                sides = (node.left, node.right)
                nones = [isinstance(side, ast.Constant) and side.value is None for side in sides]
                other = sides[nones.index(False)] if nones.count(True) == 1 else None
                if isinstance(other, (ast.Name, ast.Attribute, ast.Subscript)):
                    hits.append(f"{path.relative_to(ROOT)}:{node.lineno}: {ast.unparse(node)}")
        self.assertEqual(hits, [], "use Optional[...] in runtime expressions")


if __name__ == "__main__":
    unittest.main()
