#!/usr/bin/env python3
"""schema-types.py: the registry of the repository is sound, and --check / --write behave on a temporary repository."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "schema-types.py"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA = {
    "$schema": DRAFT, "$id": "urn:swissknifeman:x:c:thing:v1", "description": "Fixture.", "type": "object",
    "additionalProperties": False, "required": ["a"],
    "properties": {"a": {"description": "A.", "type": "string"}, "b": {"description": "B.", "type": "integer"}},
}


def run(*args):
    done = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)
    return done.returncode, done.stdout, done.stderr


class RepositoryRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "configs" / "schema-types.json").read_text(encoding="utf-8"))

    def test_every_root_is_a_schema_directory_and_every_out_lies_in_a_module_lib(self):
        self.assertEqual(1, self.registry["version"])
        for target in self.registry["targets"]:
            with self.subTest(out=target["out"]):
                self.assertTrue(list((ROOT / target["root"]).glob("*.schema.json")), target["root"])
                self.assertRegex(target["out"], r"^packages/[a-z]+/lib/[a-z_/]+\.py$")
                self.assertTrue((ROOT / target["out"]).is_file(), target["out"])

    def test_the_outs_are_unique_and_the_first_wave_is_registered(self):
        outs = [target["out"] for target in self.registry["targets"]]
        self.assertEqual(len(outs), len(set(outs)))
        self.assertEqual({"packages/orch/lib/orch/_types/records.py", "packages/orch/lib/orch/_types/conductor.py",
                          "packages/orch/lib/orch/_types/exec.py", "packages/orch/lib/orch/_types/work_source.py",
                          "packages/planner/lib/planner/plan/_types.py"}, set(outs))

    def test_the_generated_modules_of_the_repository_are_in_sync(self):
        code, _, err = run("--check")
        self.assertEqual((0, ""), (code, err))

    def test_the_generator_is_registered_in_golden(self):
        generation = json.loads((ROOT / "tests" / "golden" / "generation.json").read_text(encoding="utf-8"))
        entry = next(g for g in generation["generators"] if g["id"] == "schema-types")
        self.assertEqual(["python3", "scripts/schema-types.py", "--check"], entry["check_argv"])
        self.assertEqual({t["out"] for t in self.registry["targets"]}, set(entry["outputs"]))


class TemporaryRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "schemas" / "c" / "v1").mkdir(parents=True)
        (self.repo / "schemas" / "c" / "v1" / "thing.schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
        self.registry = self.repo / "types.json"
        self.registry.write_text(json.dumps({"version": 1, "targets": [
            {"root": "schemas/c/v1", "out": "lib/x/_types.py"}]}), encoding="utf-8")

    def call(self, mode):
        return run(mode, "--repo", str(self.repo), "--registry", str(self.registry))

    def test_write_creates_the_module_and_check_passes(self):
        self.assertEqual(1, self.call("--check")[0])  # nothing written yet: drift
        self.assertEqual(0, self.call("--write")[0])
        self.assertIn("class Thing(TypedDict):", (self.repo / "lib" / "x" / "_types.py").read_text(encoding="utf-8"))
        self.assertEqual(0, self.call("--check")[0])

    def test_a_schema_change_without_write_is_drift_and_names_the_module(self):
        self.call("--write")
        changed = dict(SCHEMA, required=["a", "b"])
        (self.repo / "schemas" / "c" / "v1" / "thing.schema.json").write_text(json.dumps(changed), encoding="utf-8")
        code, _, err = self.call("--check")
        self.assertEqual((1, "SCHEMA_CODEGEN_DRIFT: lib/x/_types.py\n"), (code, err))
        self.assertEqual(0, self.call("--write")[0])
        self.assertEqual(0, self.call("--check")[0])

    def test_a_bad_registry_is_refused(self):
        for body in ({"version": 2, "targets": []}, {"version": 1, "targets": [{"root": "nowhere", "out": "x.py"}]},
                     {"version": 1, "targets": [{"root": "schemas/c/v1", "out": "a.py"},
                                                {"root": "schemas/c/v1", "out": "a.py"}]}, []):
            with self.subTest(body=body):
                self.registry.write_text(json.dumps(body), encoding="utf-8")
                code, _, err = self.call("--check")
                self.assertNotEqual(0, code)
                self.assertIn("SCHEMA_TYPES_REGISTRY", err)


if __name__ == "__main__":
    unittest.main()
