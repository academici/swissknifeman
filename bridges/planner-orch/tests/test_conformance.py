"""Conformance of the bridge's ``brief`` with the orch exec/v1 contract, and of exec/v1 check-evidence with planner.

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
import partners

lifecycle, schema, store = partners.planner_engine("plan.lifecycle", "plan.schema", "plan.store")
ORCH = partners.find_orch_root()


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
            return partners.orch_validate("execution-input", _write(tmp, "input.json", doc))

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


@unittest.skipUnless(ORCH, "orch not found")
class EvidenceConformance(unittest.TestCase):
    """Valid exec/v1 check-evidence passes planner's field contract (D19) without conversion."""

    def test_orch_valid_check_evidence_is_accepted_by_task(self):
        fixtures = sorted((ORCH / "fixtures/exec/v1/valid/check-evidence").glob("*.json"))
        self.assertTrue(fixtures)
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = bridge_fixture.demo_plan(tmp)
            plan = store.load_plan(plan_dir)
            for fixture in fixtures:
                with self.subTest(fixture.name):
                    doc = json.loads(fixture.read_text(encoding="utf-8"))
                    self.assertTrue(doc["$schema"].startswith("urn:swissknifeman:orch:"))
                    doc["subject"] = f"{plan.plan['short_id']}.P2.1"  # only the subject names the test plan
                    target = plan_dir / "artifacts" / "evidence" / fixture.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(doc), encoding="utf-8")
                    path = f"@plan/artifacts/evidence/{fixture.name}"
                    proven = lifecycle.load_evidence(plan, "P2.1", {doc["check_id"]: path}, [doc["check_id"]])
                    expected = doc["exit"] if "exit" in doc else {"pass": 0, "fail": 1}[doc["verdict"]]
                    self.assertEqual(proven, {doc["check_id"]: expected})

    def test_task_schema_names_every_orch_field(self):
        orch = json.loads((ORCH / "schemas/exec/v1/check-evidence.schema.json").read_text(encoding="utf-8"))
        task = schema.load_registry().for_kind("check-evidence")[0]
        self.assertLessEqual(set(orch["properties"]), set(task["properties"]))
        self.assertLessEqual(set(task["required"]), set(orch["required"]))
        for name, node in orch["properties"].items():
            if "properties" in node:
                with self.subTest(field=name):
                    self.assertLessEqual(set(node["properties"]), set(task["properties"][name]["properties"]))


if __name__ == "__main__":
    unittest.main()
