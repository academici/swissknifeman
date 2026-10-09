"""Parity of the closed schema profile: orch supports every keyword and error code planner's validator uses.

Both validators are read with ``ast``; neither package is imported.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import partner

PLANNER_SCHEMA = Path(__file__).resolve().parents[3] / "lib/planner/plan/schema.py"
ORCH = partner.find_orch_root()
NAMES = ("SUPPORTED_KEYWORDS", "ERROR_CODES")


def module_values(path: Path) -> dict:
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in NAMES:
                    value = node.value
                    if isinstance(value, ast.Call):
                        value = value.args[0]
                    values[target.id] = ast.literal_eval(value)
    return values


@unittest.skipUnless(ORCH, "orch not found")
class SchemaProfileParity(unittest.TestCase):
    def test_orch_profile_covers_task_profile(self):
        task, orch = module_values(PLANNER_SCHEMA), module_values(ORCH / "lib/orch/schema.py")
        self.assertEqual(set(task), set(NAMES))
        self.assertEqual(set(orch), set(NAMES))
        for name in NAMES:
            self.assertTrue(set(orch[name]).issuperset(task[name]), name)


if __name__ == "__main__":
    unittest.main()
