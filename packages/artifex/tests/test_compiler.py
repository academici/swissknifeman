from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from artifex import compiler
from support import clone, p2_1_pending_s3_fixture


PLAN_ID = "DEMO-PLAN"
ITEM = "P2.1"
CONTRACT_HASH = "a" * 64
FIELDS = {
    "Status": "⬜ Not started",
    "Files": "`src/out.py`",
    "Required Reads": "`docs/read.md`",
    "Validation": "check one",
    "Deliverables": "Deliverable text",
}


def _git_init(root: Path) -> None:
    for argv in (["git", "init", "-q"],
                 ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-q", "--allow-empty", "-m", "fixture"]):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)


class CompilerTests(unittest.TestCase):
    """Compile against small synthetic S1/S2/S3 sources in a throwaway repository."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        _git_init(self.root)
        self.plan = self.root / "work" / PLAN_ID
        (self.plan / "phases").mkdir(parents=True)
        (self.plan / "plan.md").write_text("# plan\n", encoding="utf-8")
        (self.plan / "phases/P2.md").write_text("# phase\n", encoding="utf-8")
        (self.plan / "handoff.md").write_text("# handoff\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs/read.md").write_text("required read\n", encoding="utf-8")
        policy = self.root / "packages/harness/configs/common/agent-packs/execution-policy.json"
        policy.parent.mkdir(parents=True)
        policy.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _sources(self):
        s1 = {"plans": {PLAN_ID: {"phases": {"P2": {"items": {ITEM: {"title": "Demo item", "fields": dict(FIELDS)}}}}}}}
        s2 = {"schema_version": "task-contract/v1", "version": {"content_hash": CONTRACT_HASH},
              "route": {"required": {"model_class": "implementation", "effort": "high"}},
              "evidence": [{"id": "E1", "path": "docs/read.md"}],
              "cold_start": {"reads": ["E1"]},
              "done": {"public_acceptance": [{"id": "A1", "check": "check one", "predicate": "Deliverable text"}]}}
        return s1, s2, p2_1_pending_s3_fixture()

    def _fields(self, s1):
        return s1["plans"][PLAN_ID]["phases"]["P2"]["items"][ITEM]["fields"]

    def test_manual_projection_is_deterministic(self):
        sources = self._sources()
        first = compiler.compile_slice(self.root, self.plan, ITEM, sources=clone(sources))
        second = compiler.compile_slice(self.root, self.plan, ITEM, sources=clone(sources))
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual("run", first["route"]["exec"])
        self.assertEqual("implementation", first["route"]["model_class"])
        self.assertEqual("high", first["route"]["effort"])
        self.assertEqual(first["task_contract"]["public_acceptance_ids"], first["scope"]["evidence_refs"])
        self.assertEqual(f"{PLAN_ID}:{ITEM}:r1", first["slice_id"])

    def test_source_drift_refuses_before_manifest(self):
        s1, s2, s3 = self._sources()
        next(row for row in s3["items"] if row["item_id"] == ITEM)["route"]["effort"] = "medium"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SOURCE_DRIFT"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(s1, s2, s3))

    def test_malformed_files_refuse(self):
        s1, s2, s3 = self._sources()
        self._fields(s1)["Files"] += " prose"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SLICE_INPUT_MISSING"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(s1, s2, s3))

    def test_external_file_refuses(self):
        s1, s2, s3 = self._sources()
        self._fields(s1)["Files"] = "`../escape.py`"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SLICE_INPUT_EXTERNAL"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(s1, s2, s3))

    def test_skeleton_item_refuses(self):
        s1, s2, s3 = self._sources()
        self._fields(s1)["Deliverables"] = "—"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SKELETON_ITEM"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(s1, s2, s3))


if __name__ == "__main__":
    unittest.main()
