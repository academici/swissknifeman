"""Conformance of the bridge's ``brief`` and of Task's check-evidence with the orch exec/v1 contract.

orch is never imported: documents are checked with ``orch.py validate <kind> <file>``; orch's lifecycle phrases are
read from its source with ``ast``.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

import bridge_fixture
import brief
import partner

ORCH = partner.find_orch_root()
EVIDENCE_FIXTURES = bridge_fixture.TASK / "tests/engine/fixtures/evidence"


def _write(directory: str, name: str, doc: dict) -> Path:
    path = Path(directory) / name
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


@unittest.skipUnless(ORCH, "orch not found")
class BriefConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            cls.doc = bridge_fixture.brief_of_demo_plan(tmp, "P1.2")

    def validate(self, doc: dict) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            return partner.orch_validate("execution-input", _write(tmp, "input.json", doc))

    def test_document_is_a_valid_execution_input(self):
        code, out = self.validate(self.doc)
        self.assertEqual(code, 0, out)

    def test_digest_is_canonical_and_checked_by_orch(self):
        self.assertEqual(self.doc["digest"], brief.canonical_digest(self.doc))
        self.assertTrue(self.doc["input_id"].endswith("@" + self.doc["digest"][:12]))
        code, out = self.validate({**self.doc, "digest": "0" * 64})
        self.assertEqual(code, 1, out)

    def test_provenance_names_the_demo_plan(self):
        self.assertEqual(self.doc["provenance"]["kind"], "plan")
        self.assertEqual(self.doc["provenance"]["item"], "P1.2")
        self.assertTrue(self.doc["input_id"].startswith(f"{self.doc['provenance']['plan']}.P1.2@"))

    def test_bridge_lifecycle_phrases_cover_orch(self):
        tree = ast.parse((ORCH / "lib/orch/contracts.py").read_text(encoding="utf-8"))
        found = [ast.literal_eval(n.value) for n in ast.walk(tree)
                 if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "LIFECYCLE_PHRASES" for t in n.targets)]
        self.assertEqual(len(found), 1)
        self.assertTrue(set(brief.LIFECYCLE_PHRASES) >= set(found[0]))


@unittest.skipUnless(ORCH and EVIDENCE_FIXTURES.is_dir(), "orch or Task evidence fixtures not found")
class EvidenceConformance(unittest.TestCase):
    """Every check-evidence file Task accepts in its tests is valid exec/v1 check-evidence."""

    def test_task_evidence_fixtures_are_valid_check_evidence(self):
        fixtures = sorted(EVIDENCE_FIXTURES.glob("*.json"))
        self.assertTrue(fixtures)
        for fixture in fixtures:
            with self.subTest(fixture.name):
                code, out = partner.orch_validate("check-evidence", fixture)
                self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
