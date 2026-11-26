#!/usr/bin/env python3
"""schema-compat-all on a temporary git repository: additive, breaking, uncovered, and the real subprocess wrapper."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "schema-compat-all.py"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "schema-compat-test", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "schema-compat-test", "GIT_COMMITTER_EMAIL": "t@example.com"}


def schema(required=("name",), extra=None):
    properties = {"name": {"type": "string", "description": "Name."}}
    if extra:
        properties.update(extra)
    return {
        "$schema": DRAFT,
        "$id": "urn:swissknifeman:x:c:v1",
        "type": "object",
        "additionalProperties": False,
        "description": "Fixture contract.",
        "required": list(required),
        "properties": properties,
    }


def unit(contracts):
    return {"id": "x", "stability": "beta", "provides": {"contracts": contracts}}


def contract(name, path):
    return {"id": f"urn:swissknifeman:x:{name}", "path": path, "version": "v1", "stability": "beta"}


class TemporaryRepo:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="skm-compat-all-"))
        self.git("init", "-q")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.email=t@example.com", "-c", "user.name=test", *args],
                       check=True, env=GIT_ENV, capture_output=True, text=True)

    def write(self, rel: str, doc) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = doc if isinstance(doc, str) else json.dumps(doc, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def run(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.root), *args],
                              capture_output=True, text=True)


class SchemaCompatAllTests(unittest.TestCase):
    def make(self) -> TemporaryRepo:
        repo = TemporaryRepo()
        self.addCleanup(shutil.rmtree, repo.root, True)
        return repo

    def test_additive_optional_field_is_ok_and_covers_the_contract(self):
        repo = self.make()
        repo.write("packages/x/unit.json", unit([contract("c", "schemas/c/v1")]))
        repo.write("packages/x/schemas/c/v1/c.schema.json", schema())
        repo.commit("base")
        document = schema(extra={"note": {"type": "string", "description": "Optional note."}})
        repo.write("packages/x/schemas/c/v1/c.schema.json", document)
        repo.commit("add optional note")
        result = repo.run("--base", "HEAD~1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"], data)
        contracts = data["units"][0]["contracts"]
        self.assertTrue(contracts)
        self.assertEqual(contracts[0]["contract"], "c")
        self.assertFalse(any(change["severity"] == "error" for change in contracts[0]["changes"]))

    def test_removing_a_required_field_of_a_beta_contract_exits_1(self):
        repo = self.make()
        repo.write("packages/x/unit.json", unit([contract("c", "schemas/c/v1")]))
        repo.write("packages/x/schemas/c/v1/c.schema.json", schema())
        repo.commit("base")
        dropped = schema(required=())
        dropped["properties"].pop("name")
        repo.write("packages/x/schemas/c/v1/c.schema.json", dropped)
        repo.commit("drop required name")
        result = repo.run("--base", "HEAD~1", "--json")
        self.assertEqual(result.returncode, 1, result.stdout)
        data = json.loads(result.stdout)
        self.assertFalse(data["ok"])
        changes = data["units"][0]["contracts"][0]["changes"]
        self.assertTrue(any(change["severity"] == "error" for change in changes), changes)

    def test_a_declared_contract_without_a_directory_is_uncovered(self):
        repo = self.make()
        repo.write("packages/x/unit.json", unit([
            contract("c", "schemas/c/v1"),
            contract("d", "schemas/d/v1"),
        ]))
        repo.write("packages/x/schemas/c/v1/c.schema.json", schema())
        repo.commit("base")
        repo.write("packages/x/schemas/c/v1/c.schema.json",
                   schema(extra={"note": {"type": "string", "description": "Optional note."}}))
        repo.commit("touch c so HEAD~1 exists")
        result = repo.run("--base", "HEAD~1", "--json")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("SCHEMA_COMPAT_UNCOVERED: x: d/v1", result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["units"][0]["uncovered"], ["d/v1"])
        self.assertTrue(data["units"][0]["contracts"])

    def test_the_wrapper_is_invoked_as_a_subprocess(self):
        """Scenario (d): the real command line, not an in-process call of the function alone."""
        repo = self.make()
        repo.write("packages/x/unit.json", unit([contract("c", "schemas/c/v1")]))
        repo.write("packages/x/schemas/c/v1/c.schema.json", schema())
        repo.commit("base")
        repo.write("packages/x/schemas/c/v1/c.schema.json",
                   schema(extra={"note": {"type": "string", "description": "Optional note."}}))
        repo.commit("add optional note")
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo.root), "--base", "HEAD~1", "--json"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"contract": "c"', result.stdout)


if __name__ == "__main__":
    unittest.main()
