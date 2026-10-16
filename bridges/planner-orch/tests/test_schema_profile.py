"""Parity of the closed schema profile: orch supports every keyword and error code planner's validator uses.

orch keeps no validator of its own: ``orch/schema.py`` re-exports the one of the foundation, so the profile orch
supports is the one of ``aicore/util/schema.py``. All sources are read with ``ast``; no package is imported.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import bridge_fixture
import partners

PLANNER_SCHEMA = bridge_fixture.PLANNER / "lib/planner/plan/schema.py"
ORCH = partners.find_orch_root()
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


def orch_profile_source() -> Path | None:
    """The file that defines the profile of orch: its own schema module, or the foundation one it re-exports."""
    own = ORCH / "lib/orch/schema.py"
    if module_values(own):
        return own
    lib = partners.aicore_lib()
    return lib / "aicore/util/schema.py" if lib else None


@unittest.skipUnless(ORCH, "orch not found")
class SchemaProfileParity(unittest.TestCase):
    def test_orch_profile_covers_task_profile(self):
        source = orch_profile_source()
        if source is None:
            self.skipTest("aicore not found (set AICORE_ROOT)")
        task, orch = module_values(PLANNER_SCHEMA), module_values(source)
        self.assertEqual(set(task), set(NAMES))
        self.assertEqual(set(orch), set(NAMES))
        for name in NAMES:
            self.assertTrue(set(orch[name]).issuperset(task[name]), name)


if __name__ == "__main__":
    unittest.main()
