#!/usr/bin/env python3
"""Tests of scripts/ecosystem-units.py: unit/v1 and check-result/v1 schemas, caret ranges, manifest checks.

Manifest checks run on temporary git trees (``--root``); only one test touches the real repository.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ecosystem-units.py"
AICORE_SCHEMAS = ROOT / "packages" / "aicore" / "schemas"

spec = importlib.util.spec_from_file_location("ecosystem_units", SCRIPT)
eu = importlib.util.module_from_spec(spec)
sys.modules["ecosystem_units"] = eu
spec.loader.exec_module(eu)


def run(root: Path, *args: str):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--root", str(root)],
                          capture_output=True, text=True)


def codes(result) -> list:
    return sorted({line.split(":", 1)[0] for line in result.stderr.splitlines() if line.startswith("ECOSYSTEM_")})


class SchemaFixtureTests(unittest.TestCase):
    """Every fixture of the two aicore schemas validates (valid) or is rejected (invalid)."""

    @classmethod
    def setUpClass(cls):
        cls.schema = eu.schema_validator()

    def registry(self, kind: str):
        return self.schema.load_registry(AICORE_SCHEMAS / kind / "v1", urn_prefix=eu.AICORE_SCHEMA_URN_PREFIX,
                                         kinds=(kind,))

    def fixtures(self, kind: str, group: str) -> list:
        return sorted((AICORE_SCHEMAS / kind / "v1" / "examples" / group).glob("*.json"))

    def test_fixture_counts(self):
        for kind in ("unit", "check-result"):
            self.assertGreaterEqual(len(self.fixtures(kind, "valid")), 1, kind)
            self.assertGreaterEqual(len(self.fixtures(kind, "invalid")), 3, kind)

    def test_valid_fixtures_pass(self):
        for kind in ("unit", "check-result"):
            registry = self.registry(kind)
            for path in self.fixtures(kind, "valid"):
                with self.subTest(fixture=f"{kind}/{path.name}"):
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(self.schema.validate(doc, kind, registry), [])

    def test_invalid_fixtures_fail(self):
        for kind in ("unit", "check-result"):
            registry = self.registry(kind)
            for path in self.fixtures(kind, "invalid"):
                with self.subTest(fixture=f"{kind}/{path.name}"):
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    self.assertNotEqual(self.schema.validate(doc, kind, registry), [])

    def test_invalid_fixture_reasons(self):
        expected = {"extra-field": "additional", "bad-enum": "enum", "missing-required": "required"}
        for kind in ("unit", "check-result"):
            registry = self.registry(kind)
            for name, code in expected.items():
                doc = json.loads((AICORE_SCHEMAS / kind / "v1" / "examples" / "invalid" / f"{name}.json")
                                 .read_text(encoding="utf-8"))
                self.assertIn(code, {i.code for i in self.schema.validate(doc, kind, registry)}, f"{kind}/{name}")

    def test_schemas_are_closed_and_described(self):
        def walk(node, where):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object" and "properties" in node:
                self.assertIs(node.get("additionalProperties"), False, where)
            for name, child in node.get("properties", {}).items():
                self.assertIn("description", child, f"{where}/{name}")
                walk(child, f"{where}/{name}")
            for name, child in node.get("$defs", {}).items():
                walk(child, f"{where}/$defs/{name}")
            if isinstance(node.get("items"), dict):
                walk(node["items"], f"{where}/items")

        for kind in ("unit", "check-result"):
            path = AICORE_SCHEMAS / kind / "v1" / f"{kind}.schema.json"
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$id"], f"urn:swissknifeman:aicore:{kind}:v1")
            walk(schema, kind)


class CaretTests(unittest.TestCase):
    def test_ranges(self):
        cases = [
            ("0.1.0", "^0.1", True), ("0.1.9", "^0.1", True), ("0.2.0", "^0.1", False),
            ("0.0.9", "^0.1", False), ("1.4.2", "^1.2", True), ("1.1.9", "^1.2", False),
            ("2.0.0", "^1.2", False), ("1.2.3", "^1.2.3", True), ("1.2.2", "^1.2.3", False),
            ("1.9.0", "^1.2.3", True), ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
            ("0.1.0-rc.1", "^0.1", False), ("0.1.1-rc.1", "^0.1.0", True), ("1.0.0-rc.1", "^0.9", False),
        ]
        for version, rng, ok in cases:
            self.assertIs(eu.satisfies(version, rng), ok, f"{version} vs {rng}")

    def test_malformed(self):
        self.assertFalse(eu.satisfies("0.1", "^0.1"))
        self.assertFalse(eu.satisfies("0.1.0", ">=0.1"))
        self.assertIsNone(eu.caret_bounds("0.1"))


class Tree:
    """A minimal valid hub: foundation aicore plus one capability, in a temporary git repository."""

    def __init__(self, test: unittest.TestCase):
        self.root = Path(tempfile.mkdtemp(prefix="skm-eu-test-")).resolve()
        test.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        shutil.copytree(AICORE_SCHEMAS, self.root / "packages/aicore/schemas")
        self.config = {
            "schema_version": "ecosystem-units/v1",
            "targets": ["aicore", "alpha", "hub", "retired"],
            "module_aliases": {},
            "retired": ["old"],
            "foundation": {"id": "aicore", "aliases": ["core"]},
            "transitional_roots": [],
            "version_sources": {"alpha": {"path": "packages/alpha/package.json", "read": "json:version"}},
            "path_patterns": [], "path_suffixes": [], "standalone": {}, "ownership": [],
        }
        self.write_json("packages/aicore/unit.json", {
            "$schema": "urn:swissknifeman:aicore:unit:v1", "id": "aicore", "title": "Foundation",
            "kind": "foundation", "version": "0.1.0", "stability": "development", "destination": "own-repo",
            "requires": [], "provides": {}})
        self.alpha = {
            "$schema": "urn:swissknifeman:aicore:unit:v1", "id": "alpha", "title": "Alpha", "kind": "capability",
            "version": "1.2.0", "stability": "beta", "destination": "hub",
            "requires": [{"unit": "aicore", "range": "^0.1"}],
            "provides": {
                "cli": ["bin/alpha", "scripts/alpha.py"],
                "plugins": [{"name": "alpha", "manifest": ".claude-plugin/plugin.json"}],
                "contracts": [{"id": "urn:swissknifeman:alpha:data", "path": "schemas/data/v1",
                               "version": "v1", "stability": "alpha"}],
                "doctor": [{"id": "alpha.environment", "category": "environment",
                            "probe": ["bin/alpha", "doctor"], "output": "text"}]}}
        self.write_json("packages/alpha/package.json", {"name": "alpha", "version": "1.2.0"})
        self.write("packages/alpha/bin/alpha", "#!/bin/sh\n", mode=0o755)
        self.write("packages/alpha/scripts/alpha.py", "print(1)\n")
        self.write_json("packages/alpha/.claude-plugin/plugin.json", {"name": "alpha", "version": "1.2.0"})
        self.write("packages/alpha/schemas/data/v1/data.schema.json", "{}\n")
        self.write("packages/alpha/lib/alpha/__init__.py", "")
        self.flush()

    def write(self, rel: str, text: str, mode: int = 0o644):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)

    def write_json(self, rel: str, doc):
        self.write(rel, json.dumps(doc, indent=2) + "\n")

    def flush(self):
        self.write_json("configs/ecosystem-units.json", self.config)
        self.write_json("packages/alpha/unit.json", self.alpha)

    def check(self, *flags: str):
        self.flush()
        return run(self.root, "check", *flags)


class ManifestCheckTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)

    def assertFails(self, code: str, result=None):
        result = result or self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"ECOSYSTEM_{code}", codes(result), result.stderr)
        return result

    def test_clean_tree_passes(self):
        result = self.tree.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_json_output(self):
        ok = json.loads(self.tree.check("--json").stdout)
        self.assertEqual(ok, {"ok": True, "errors": [], "violations": [], "improvements": []})
        self.tree.alpha["id"] = "beta"
        result = self.tree.check("--json")
        data = json.loads(result.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(data["errors"][0]["code"], "ECOSYSTEM_UNIT_ID")
        self.assertEqual(data["errors"][0]["path"], "packages/alpha/unit.json")

    def test_missing_unit(self):
        (self.tree.root / "packages/alpha/unit.json").unlink()
        run_ = run(self.tree.root, "check")
        self.assertFails("UNIT_MISSING", run_)

    def test_retired_folder_is_skipped(self):
        self.tree.write("packages/old/lib/old/__init__.py", "")
        result = self.tree.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_unit(self):
        self.tree.alpha["unexpected"] = 1
        result = self.assertFails("UNIT_INVALID")
        self.assertIn("additional", result.stderr)

    def test_unparsable_unit(self):
        self.tree.flush()
        self.tree.write("packages/alpha/unit.json", "{not json")
        self.assertFails("UNIT_INVALID", run(self.tree.root, "check"))

    def test_id_differs_from_folder(self):
        self.tree.alpha["id"] = "beta"
        self.assertFails("UNIT_ID")

    def test_lib_with_wrong_or_extra_package(self):
        self.tree.write("packages/alpha/lib/extra/__init__.py", "")
        self.assertFails("UNIT_LIB")
        shutil.rmtree(self.tree.root / "packages/alpha/lib/extra")
        shutil.rmtree(self.tree.root / "packages/alpha/lib/alpha")
        self.tree.write("packages/alpha/lib/other/__init__.py", "")
        self.assertFails("UNIT_LIB")

    def test_version_differs_from_source(self):
        self.tree.alpha["version"] = "9.9.9"
        result = self.assertFails("UNIT_VERSION")
        self.assertIn("1.2.0", result.stderr)

    def test_version_source_missing(self):
        del self.tree.config["version_sources"]["alpha"]
        self.assertFails("UNIT_VERSION")

    def test_version_source_unreadable(self):
        self.tree.config["version_sources"]["alpha"]["path"] = "packages/alpha/nothing.json"
        self.assertFails("UNIT_VERSION")

    def test_python_version_source(self):
        self.tree.write("packages/alpha/lib/alpha/__init__.py", '"""doc"""\n__version__ = "1.2.0"\n')
        self.tree.config["version_sources"]["alpha"] = {"path": "packages/alpha/lib/alpha/__init__.py",
                                                       "read": "python:__version__"}
        result = self.tree.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.tree.alpha["version"] = "1.2.1"
        self.assertFails("UNIT_VERSION")

    def test_unknown_required_unit(self):
        self.tree.alpha["requires"].append({"unit": "ghost", "range": "^1.0"})
        self.assertFails("UNIT_REQUIRES")

    def test_capability_may_require_only_foundation(self):
        self.tree.write_json("packages/beta/unit.json", {**self.tree.alpha, "id": "beta", "requires": [
            {"unit": "alpha", "range": "^1.0"}], "provides": {}})
        self.tree.write("packages/beta/package.json", json.dumps({"version": "1.2.0"}))
        self.tree.config["version_sources"]["beta"] = {"path": "packages/beta/package.json", "read": "json:version"}
        self.assertFails("UNIT_REQUIRES")

    def test_foundation_requires_nothing(self):
        doc = json.loads((self.tree.root / "packages/aicore/unit.json").read_text(encoding="utf-8"))
        doc["requires"] = [{"unit": "alpha", "range": "^1.0"}]
        self.tree.write_json("packages/aicore/unit.json", doc)
        self.assertFails("UNIT_REQUIRES")

    def test_self_and_duplicate_requires(self):
        self.tree.alpha["requires"] = [{"unit": "alpha", "range": "^1.0"}]
        self.assertFails("UNIT_REQUIRES")
        self.tree.alpha["requires"] = [{"unit": "aicore", "range": "^0.1"}, {"unit": "aicore", "range": "^0.1"}]
        self.assertFails("UNIT_REQUIRES")

    def test_range_not_satisfied(self):
        self.tree.alpha["requires"] = [{"unit": "aicore", "range": "^0.2"}]
        self.assertFails("UNIT_RANGE")

    def test_cli_missing_or_not_executable(self):
        (self.tree.root / "packages/alpha/bin/alpha").chmod(0o644)
        result = self.assertFails("UNIT_PATH")
        self.assertIn("not executable", result.stderr)
        (self.tree.root / "packages/alpha/bin/alpha").unlink()
        result = self.assertFails("UNIT_PATH")
        self.assertIn("does not exist", result.stderr)

    def test_python_cli_needs_no_exec_bit(self):
        self.assertEqual(self.tree.check().returncode, 0)
        self.assertTrue((self.tree.root / "packages/alpha/scripts/alpha.py").stat().st_mode & 0o111 == 0)

    def test_plugin_name_mismatch(self):
        self.tree.write_json("packages/alpha/.claude-plugin/plugin.json", {"name": "other"})
        self.assertFails("UNIT_PATH")

    def test_contract_directory_missing(self):
        shutil.rmtree(self.tree.root / "packages/alpha/schemas")
        self.assertFails("UNIT_PATH")

    def test_doctor_probe_missing(self):
        self.tree.alpha["provides"]["doctor"][0]["probe"] = ["bin/missing", "doctor"]
        self.assertFails("UNIT_PATH")

    def test_path_escaping_module_is_rejected(self):
        self.tree.alpha["provides"]["cli"] = ["../aicore/unit.json"]
        result = self.assertFails("UNIT_PATH")
        self.assertIn("inside the module", result.stderr)

    def test_broken_aicore_schema_fails_profile(self):
        path = self.tree.root / "packages/aicore/schemas/unit/v1/unit.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema["properties"]["id"]["format"] = "uri"
        self.tree.write_json("packages/aicore/schemas/unit/v1/unit.schema.json", schema)
        self.assertFails("SCHEMA_PROFILE")

    def test_config_shape(self):
        self.tree.config["module_aliases"] = {"alpha": "nowhere"}
        self.tree.config["version_sources"]["alpha"]["read"] = "yaml:version"
        result = self.assertFails("CONFIG")
        self.assertIn("module_aliases", result.stderr)
        self.assertIn("version_sources", result.stderr)


class EnvironmentTests(unittest.TestCase):
    def test_not_a_git_tree(self):
        tmp = Path(tempfile.mkdtemp(prefix="skm-eu-test-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        result = run(tmp, "check")
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_missing_config(self):
        tree = Tree(self)
        (tree.root / "configs/ecosystem-units.json").unlink()
        result = run(tree.root, "check")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ecosystem-units.json", result.stderr)

    def test_does_not_write_into_root(self):
        tree = Tree(self)
        tree.flush()
        before = sorted(p for p in tree.root.rglob("*") if p.is_file() and ".git" not in p.parts)
        run(tree.root, "check")
        run(tree.root, "list")
        after = sorted(p for p in tree.root.rglob("*") if p.is_file() and ".git" not in p.parts)
        self.assertEqual(before, after)


class ListTests(unittest.TestCase):
    def test_list_json_and_text(self):
        tree = Tree(self)
        tree.flush()
        data = json.loads(run(tree.root, "list", "--json").stdout)
        self.assertEqual([m["id"] for m in data["modules"]], ["aicore", "alpha"])
        alpha = data["modules"][1]
        self.assertEqual((alpha["kind"], alpha["version"], alpha["destination"], alpha["stability"],
                          alpha["requires"]), ("capability", "1.2.0", "hub", "beta", ["aicore"]))
        text = run(tree.root, "list").stdout
        self.assertIn("alpha", text)
        self.assertIn("capability", text)

    def test_list_skips_retired(self):
        tree = Tree(self)
        tree.write_json("packages/old/unit.json", {"id": "old"})
        data = json.loads(run(tree.root, "list", "--json").stdout)
        self.assertNotIn("old", [m["id"] for m in data["modules"]])


class RealRepositoryTests(unittest.TestCase):
    def test_check_passes(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "check"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_modules_and_aliases(self):
        data = json.loads(subprocess.run([sys.executable, str(SCRIPT), "list", "--json"], capture_output=True,
                                         text=True, cwd=ROOT).stdout)
        self.assertEqual(sorted(m["id"] for m in data["modules"]),
                         ["aicore", "analyst", "harness", "maind", "orch", "skiller", "task"])
        self.assertFalse((ROOT / "packages/artifex/unit.json").exists())


if __name__ == "__main__":
    unittest.main()
