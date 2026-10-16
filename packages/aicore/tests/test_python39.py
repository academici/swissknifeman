"""Python 3.9 syntax gate: every aicore module parses with the 3.9 grammar.

This catches syntax introduced after 3.9 (``match``, parenthesised ``with`` items, ``except*``).
It cannot catch library calls added later; the CI matrix runs the real interpreters.
"""
import ast
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib" / "aicore"


class TestPython39Syntax(unittest.TestCase):
    def test_every_module_parses_with_the_python_39_grammar(self):
        failures = []
        files = sorted(LIB.rglob("*.py"))
        self.assertTrue(files)
        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))
            except SyntaxError as exc:
                failures.append(f"{path.relative_to(LIB)}:{exc.lineno}: {exc.msg}")
        self.assertEqual(failures, [])

    def test_gate_rejects_newer_syntax(self):
        with self.assertRaises(SyntaxError):
            ast.parse("match x:\n    case 1:\n        pass\n", feature_version=(3, 9))

    def test_minimum_version_constant(self):
        import aicore
        self.assertEqual(aicore.MIN_PYTHON, (3, 9))


if __name__ == "__main__":
    unittest.main()
