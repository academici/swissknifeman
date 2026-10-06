"""Conformance of Task's ``plan.py brief`` output with the orch execution-input contract (D10)."""
from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

from orch import contracts

from .task_fixture import TASK, brief_of_demo_plan

BRIEF_PY = TASK / "lib/task/plan/brief.py"


@unittest.skipUnless(TASK.is_dir() and BRIEF_PY.is_file(), "Task package is not next to orch")
class TaskBriefConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            cls.doc = brief_of_demo_plan(tmp, "P1.2")

    def test_document_is_a_valid_execution_input(self):
        errors = [i for i in contracts.validate(self.doc, "execution-input") if i.level == "error"]
        self.assertEqual(errors, [])

    def test_digest_matches_orch_canonical_digest(self):
        self.assertEqual(self.doc["digest"], contracts.canonical_digest(self.doc))
        self.assertTrue(self.doc["input_id"].endswith("@" + self.doc["digest"][:12]))

    def test_provenance_names_the_demo_plan(self):
        self.assertEqual(self.doc["provenance"]["kind"], "plan")
        self.assertEqual(self.doc["provenance"]["item"], "P1.2")
        self.assertTrue(self.doc["input_id"].startswith(f"{self.doc['provenance']['plan']}.P1.2@"))

    def test_lifecycle_phrases_match_task(self):
        tree = ast.parse(BRIEF_PY.read_text(encoding="utf-8"))
        found = [ast.literal_eval(n.value) for n in ast.walk(tree)
                 if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "LIFECYCLE_PHRASES" for t in n.targets)]
        self.assertEqual(found, [contracts.LIFECYCLE_PHRASES])


if __name__ == "__main__":
    unittest.main()
