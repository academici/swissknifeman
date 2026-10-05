from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from artifex import compiler
from support import PLAN_CLI, clone, make_plan, p2_1_pending_s3_fixture, plan_cli


ITEM = "P2.1"


def _git_init(root: Path) -> None:
    for argv in (["git", "init", "-q"],
                 ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-q", "--allow-empty", "-m", "fixture"]):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)


class CompilerTests(unittest.TestCase):
    """Compile against a real v3 plan (made through plan.py) and a synthetic harness queue."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        _git_init(self.root)
        self.plan = make_plan(self.root / "work")
        (self.root / "docs").mkdir()
        (self.root / "docs/read.md").write_text("required read\n", encoding="utf-8")
        policy = self.root / "packages/harness/configs/common/agent-packs/execution-policy.json"
        policy.parent.mkdir(parents=True)
        policy.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _sources(self):
        item = json.loads(plan_cli(self.root, "show", str(self.plan), ITEM, "--json"))
        return item, p2_1_pending_s3_fixture()

    def test_manual_projection_is_deterministic(self):
        sources = self._sources()
        first = compiler.compile_slice(self.root, self.plan, ITEM, sources=clone(sources))
        second = compiler.compile_slice(self.root, self.plan, ITEM, sources=clone(sources))
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual("run", first["route"]["exec"])
        self.assertEqual("implementation", first["route"]["model_class"])
        self.assertEqual("high", first["route"]["effort"])
        self.assertEqual(["V1"], first["scope"]["evidence_refs"])
        self.assertEqual(first["item"]["acceptance_ids"], first["scope"]["evidence_refs"])
        self.assertEqual(64, len(first["item"]["content_hash"]))
        self.assertEqual({"required_reads": ["docs/read.md"], "files": ["src/out.py"], "validation": ["check one"],
                          "deliverables": ["Deliverable text"], "evidence_refs": ["V1"]}, first["scope"])
        self.assertEqual(f"{self.plan.name}:{ITEM}:r1", first["slice_id"])
        self.assertEqual(set(compiler.SOURCE_KEYS), set(first["source_hashes"]))

    def test_observe_sources_reads_the_item_through_plan_py(self):
        item = json.loads(plan_cli(self.root, "show", str(self.plan), ITEM, "--json"))
        observed = compiler._run_json(["python3", str(PLAN_CLI), "show", str(self.plan), ITEM, "--json"],
                                      cwd=self.root, env=compiler._minimal_env())
        self.assertEqual(item, observed)

    def test_source_drift_refuses_before_manifest(self):
        item, queue = self._sources()
        next(row for row in queue["items"] if row["item_id"] == ITEM)["route"]["effort"] = "medium"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SOURCE_DRIFT"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(item, queue))

    def test_changed_item_status_drifts_from_the_queue(self):
        item, queue = self._sources()
        item["status"] = "in_progress"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SOURCE_DRIFT"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(item, queue))

    def test_duplicate_files_refuse(self):
        item, queue = self._sources()
        item["task_files"].append(dict(item["task_files"][0]))
        with self.assertRaisesRegex(compiler.CompileRefusal, "SLICE_INPUT_MISSING"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(item, queue))

    def test_external_file_refuses(self):
        item, queue = self._sources()
        item["task_files"][0]["path"] = "../escape.py"
        with self.assertRaisesRegex(compiler.CompileRefusal, "SLICE_INPUT_EXTERNAL"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(item, queue))

    def test_skeleton_item_refuses(self):
        item, queue = self._sources()
        item["deliverables"] = []
        with self.assertRaisesRegex(compiler.CompileRefusal, "SKELETON_ITEM"):
            compiler.compile_slice(self.root, self.plan, ITEM, sources=(item, queue))


if __name__ == "__main__":
    unittest.main()
