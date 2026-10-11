#!/usr/bin/env python3
"""Tests of scripts/ecosystem-units.py: unit/v1 and check-result/v1 schemas, caret ranges, manifest checks,
ownership map, repository schemas, boundaries with the baseline, render.

Checks run on temporary git trees (``--root``); only the last class touches the real repository.
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

    def test_validator_is_the_foundation_one(self):
        self.assertEqual(self.schema.__name__, "aicore.util.schema")

    def registry(self, kind: str):
        return self.schema.load_contract(AICORE_SCHEMAS / kind / "v1")[0]  # with the contracts it references

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
        self.write_json("packages/alpha/schemas/data/v1/data.schema.json", {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:swissknifeman:alpha:data:v1"})
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

    def add_module(self, name: str, requires_foundation: bool = False):
        """A second module with no cli and no plugins; it requires the foundation only on request."""
        self.write_json(f"packages/{name}/unit.json", {
            "$schema": "urn:swissknifeman:aicore:unit:v1", "id": name, "title": name.title(), "kind": "capability",
            "version": "0.1.0", "stability": "alpha", "destination": "hub",
            "requires": [{"unit": "aicore", "range": "^0.1"}] if requires_foundation else [], "provides": {}})
        self.write_json(f"packages/{name}/package.json", {"name": name, "version": "0.1.0"})
        self.write(f"packages/{name}/lib/{name}/__init__.py", "")
        self.config["version_sources"][name] = {"path": f"packages/{name}/package.json", "read": "json:version"}

    def add_bridge(self, name: str, requires=("aicore", "alpha"), **overrides):
        """A bridge unit in ``bridges/<name>/`` that requires the given units (the foundation range is ``^0.1``)."""
        ranges = {"aicore": "^0.1", "alpha": "^1.2"}
        doc = {"$schema": "urn:swissknifeman:aicore:unit:v1", "id": name, "title": name, "kind": "bridge",
               "version": "0.1.0", "stability": "alpha", "destination": "hub",
               "requires": [{"unit": unit, "range": ranges.get(unit, "^0.1")} for unit in requires],
               "provides": {}, "protocol": {"min": "1", "max": "1"}}
        doc.update(overrides)
        self.write_json(f"bridges/{name}/unit.json", doc)
        return doc

    def use_boundary_config(self):
        """The path patterns and suffixes of the real configuration."""
        real = json.loads((ROOT / "configs/ecosystem-units.json").read_text(encoding="utf-8"))
        self.config["path_patterns"] = real["path_patterns"]
        self.config["path_suffixes"] = real["path_suffixes"]

    def set_baseline(self, violations: dict, standalone=None):
        self.write("configs/ecosystem-baseline.json", eu.baseline_text(violations, standalone or {}))


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

    def test_events_must_start_with_the_module_id(self):
        self.tree.alpha["provides"]["events"] = ["alpha.item.done", "alpha.plan.closed"]
        self.assertEqual(self.tree.check().returncode, 0)
        self.tree.alpha["provides"]["events"] = ["alpha.item.done", "beta.item.done"]
        result = self.assertFails("UNIT_EVENTS_PREFIX")
        self.assertIn("'beta.item.done' must start with the module id 'alpha'", result.stderr)
        self.assertNotIn("alpha.item.done'", result.stderr)

    def test_event_names_have_three_segments(self):
        self.tree.alpha["provides"]["events"] = ["alpha.done"]
        result = self.assertFails("UNIT_INVALID")
        self.assertIn("pattern", result.stderr)

    def test_a_subscription_needs_its_program_in_the_module(self):
        self.tree.alpha["subscribes"] = [{"id": "notify", "on": ["alpha.item.*"], "run": ["bin/alpha", "--event"]}]
        self.assertEqual(self.tree.check().returncode, 0)
        self.tree.alpha["subscribes"][0]["run"] = ["bin/missing"]
        result = self.assertFails("UNIT_SUBSCRIBES_RUN")
        self.assertIn("subscribes[notify].run: 'bin/missing' does not exist", result.stderr)
        self.tree.alpha["subscribes"][0]["run"] = ["../aicore/unit.json"]
        self.assertIn("must stay inside the module", self.assertFails("UNIT_SUBSCRIBES_RUN").stderr)
        (self.tree.root / "packages/alpha/bin/alpha").chmod(0o644)
        self.tree.alpha["subscribes"][0]["run"] = ["bin/alpha"]
        self.assertIn("is not executable", self.assertFails("UNIT_SUBSCRIBES_RUN").stderr)

    def test_a_subscription_without_run_is_invalid(self):
        self.tree.alpha["subscribes"] = [{"id": "notify", "on": ["alpha.item.*"]}]
        self.assertFails("UNIT_INVALID")

    def test_permissions_follow_the_shared_contract(self):
        self.tree.alpha["permissions"] = {"filesystem": ["project"], "env": ["PATH"], "profile": "read-only"}
        self.assertEqual(self.tree.check().returncode, 0)
        self.tree.alpha["permissions"]["env"] = ["path"]
        self.assertFails("UNIT_INVALID")

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

    def test_broken_digest_contract_fails_profile(self):
        path = "packages/aicore/schemas/digest/v1/digest.schema.json"
        schema = json.loads((self.tree.root / path).read_text(encoding="utf-8"))
        schema["multipleOf"] = 2
        self.tree.write_json(path, schema)
        result = self.assertFails("SCHEMA_PROFILE")
        self.assertIn("unsupported keyword 'multipleOf'", result.stderr)

    def test_contract_id_must_match_its_directory(self):
        path = "packages/aicore/schemas/digest/v1/digest.schema.json"
        schema = json.loads((self.tree.root / path).read_text(encoding="utf-8"))
        schema["$id"] = "urn:swissknifeman:aicore:digest:v2"
        self.tree.write_json(path, schema)
        self.assertFails("SCHEMA_PROFILE")

    def test_config_shape(self):
        self.tree.config["module_aliases"] = {"alpha": "nowhere"}
        self.tree.config["version_sources"]["alpha"]["read"] = "yaml:version"
        result = self.assertFails("CONFIG")
        self.assertIn("module_aliases", result.stderr)
        self.assertIn("version_sources", result.stderr)


class ConfigShapeTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)

    def test_path_pattern_needs_reason_and_target_group(self):
        self.tree.config["path_patterns"] = [{"id": "a", "regex": "x(?P<target>y)"}]
        result = self.tree.check()
        self.assertIn("ECOSYSTEM_CONFIG", codes(result))
        self.assertIn("reason", result.stderr)
        self.tree.config["path_patterns"] = [{"id": "a", "regex": "xy", "reason": "why"}]
        self.assertIn("named group", self.tree.check().stderr)
        self.tree.config["path_patterns"] = [{"id": "a", "regex": "x(", "reason": "why"}]
        self.assertIn("invalid regex", self.tree.check().stderr)

    def test_transitional_roots_and_suffixes_shape(self):
        self.tree.config["transitional_roots"] = ["core"]
        self.tree.config["path_suffixes"] = ["py"]
        result = self.tree.check()
        self.assertIn("transitional_roots", result.stderr)
        self.assertIn("path_suffixes", result.stderr)

    def test_standalone_foundation_free_shape(self):
        self.assertEqual(self.tree.check().returncode, 0)
        self.tree.config["standalone"] = {"foundation_free": ["alpha"]}
        self.assertEqual(self.tree.check().returncode, 0)
        for value, word in (("alpha", "list of module folders"), ([1], "list of module folders"),
                            (["nowhere"], "not a module folder")):
            self.tree.config["standalone"] = {"foundation_free": value}
            result = self.tree.check()
            self.assertIn("ECOSYSTEM_CONFIG", codes(result))
            self.assertIn(word, result.stderr)


class MapCheckTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)
        self.tree.config["transitional_roots"] = ["legacy/"]
        self.tree.write("legacy/a.py", "")
        self.tree.write("legacy/sub/b.py", "")
        self.tree.config["ownership"] = [
            {"path": "legacy/", "target": "hub", "phase": "P3", "confidence": "fixed"},
        ]

    def assertFails(self, code: str):
        result = self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"ECOSYSTEM_{code}", codes(result), result.stderr)
        return result

    def test_covered_tree_passes(self):
        result = self.tree.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_uncovered_file_in_transitional_root(self):
        self.tree.config["ownership"] = [
            {"path": "legacy/a.py", "target": "hub", "phase": "P3", "confidence": "fixed"}]
        result = self.assertFails("MAP_UNCOVERED")
        self.assertIn("legacy/sub/b.py", result.stderr)
        self.assertNotIn("legacy/a.py:", result.stderr)

    def test_stale_entry(self):
        self.tree.config["ownership"].append(
            {"path": "legacy/gone.py", "target": "hub", "phase": "P3", "confidence": "fixed"})
        result = self.assertFails("MAP_STALE")
        self.assertIn("legacy/gone.py", result.stderr)

    def test_stale_directory_entry(self):
        self.tree.config["ownership"].append(
            {"path": "nothing/", "target": "hub", "phase": "P3", "confidence": "fixed"})
        self.assertFails("MAP_STALE")

    def test_directory_entry_needs_trailing_slash(self):
        self.tree.config["ownership"].append(
            {"path": "legacy/sub", "target": "hub", "phase": "P3", "confidence": "fixed"})
        result = self.assertFails("MAP_STALE")
        self.assertIn("end the path with '/'", result.stderr)

    def test_entry_fields_are_validated(self):
        bad = [({"target": "nowhere"}, "target"), ({"phase": "P2"}, "phase"), ({"phase": "P14"}, "phase"),
               ({"confidence": "sure"}, "confidence"), ({"note": ""}, "note"), ({"extra": 1}, "unknown keys")]
        for change, word in bad:
            with self.subTest(change=change):
                entry = {"path": "legacy/a.py", "target": "hub", "phase": "P3", "confidence": "fixed", **change}
                self.tree.config["ownership"] = [{"path": "legacy/", "target": "hub", "phase": "P3",
                                                  "confidence": "fixed"}, entry]
                self.assertIn(word, self.assertFails("MAP_ENTRY").stderr)

    def test_duplicate_and_unsafe_paths(self):
        entry = {"path": "legacy/", "target": "hub", "phase": "P3", "confidence": "fixed"}
        self.tree.config["ownership"] = [entry, dict(entry)]
        self.assertIn("duplicate", self.assertFails("MAP_ENTRY").stderr)
        self.tree.config["ownership"] = [entry, {**entry, "path": "../legacy/"}]
        self.assertIn("inside the repository", self.assertFails("MAP_ENTRY").stderr)

    def test_longest_prefix_wins(self):
        entries = [{"path": "legacy/", "target": "hub"}, {"path": "legacy/sub/", "target": "alpha"},
                   {"path": "legacy/sub/b.py", "target": "retired"}]
        self.assertEqual(eu.owner_entry("legacy/a.py", entries)["target"], "hub")
        self.assertEqual(eu.owner_entry("legacy/sub/c.py", entries)["target"], "alpha")
        self.assertEqual(eu.owner_entry("legacy/sub/b.py", entries)["target"], "retired")
        self.assertIsNone(eu.owner_entry("other/a.py", entries))
        self.assertIsNone(eu.owner_entry("legacy", entries))


class SchemaCheckTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)
        self.draft = "https://json-schema.org/draft/2020-12/schema"

    def schema(self, rel: str, **fields):
        self.tree.write_json(rel, {"$schema": self.draft, "$id": "urn:x:thing:v1", "type": "object", **fields})

    def assertFails(self, code: str):
        result = self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"ECOSYSTEM_{code}", codes(result), result.stderr)
        return result

    def test_valid_schemas_pass(self):
        self.schema("packages/alpha/schemas/thing/v1/thing.schema.json")
        self.schema("packages/alpha/schema/flat.schema.json", **{"$schema": "http://json-schema.org/draft-07/schema#"})
        self.assertEqual(self.tree.check().returncode, 0)

    def test_missing_or_unknown_draft(self):
        self.tree.write_json("packages/alpha/schemas/a.schema.json", {"$id": "urn:x:a:v1"})
        self.assertIn("$schema", self.assertFails("SCHEMA_ID").stderr)
        self.schema("packages/alpha/schemas/a.schema.json", **{"$schema": "http://json-schema.org/draft-04/schema#"})
        self.assertIn("$schema", self.assertFails("SCHEMA_ID").stderr)

    def test_missing_or_unversioned_id(self):
        self.tree.write_json("packages/alpha/schemas/a.schema.json", {"$schema": self.draft})
        self.assertIn("$id", self.assertFails("SCHEMA_ID").stderr)
        for bad in ("urn:x:a", "https://example.com/a.json", "urn:x:a:v", "urn:X:a:v1", "urn:x:a:1"):
            with self.subTest(bad=bad):
                self.schema("packages/alpha/schemas/a.schema.json", **{"$id": bad})
                self.assertFails("SCHEMA_ID")

    def test_folder_version_must_match_id(self):
        self.schema("packages/alpha/schemas/thing/v2/thing.schema.json")
        result = self.assertFails("SCHEMA_VERSION")
        self.assertIn("v2", result.stderr)
        self.schema("packages/alpha/schemas/thing/v2/thing.schema.json", **{"$id": "urn:x:thing:v2"})
        self.assertEqual(self.tree.check().returncode, 0)

    def test_aicore_schemas_must_be_2020_12(self):
        self.schema("packages/aicore/schemas/extra/v1/extra.schema.json",
                    **{"$schema": "http://json-schema.org/draft-07/schema#"})
        self.assertIn("aicore schemas", self.assertFails("SCHEMA_ID").stderr)

    def test_unparsable_schema(self):
        self.tree.write("packages/alpha/schemas/a.schema.json", "{nope")
        self.assertFails("PARSE")

    def test_fixture_test_and_example_schemas_are_skipped(self):
        for folder in ("tests", "fixtures", "examples"):
            self.tree.write_json(f"packages/alpha/{folder}/bad.schema.json", {"type": "object"})
        self.assertEqual(self.tree.check().returncode, 0)


class ConfigExampleTests(unittest.TestCase):
    SCHEMA = {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:swissknifeman:alpha:config:v1",
        "type": "object", "additionalProperties": False, "description": "Alpha settings.",
        "properties": {"level": {"type": "integer", "minimum": 1, "default": 3, "description": "How deep."}}}

    def setUp(self):
        self.tree = Tree(self)
        self.tree.alpha["provides"]["config"] = "configs/config.schema.json"
        self.tree.write_json("packages/alpha/configs/config.schema.json", self.SCHEMA)

    def expected(self) -> str:
        sys.path.insert(0, str(ROOT / "packages/aicore/lib"))
        try:
            from aicore.config import example, model
        finally:
            sys.path.pop(0)
        schema = model.load_module_schema(self.tree.root / "packages/alpha/configs/config.schema.json", "alpha")
        return example.render(schema, "configs/config.schema.json")

    def test_missing_example_is_drift(self):
        result = self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ECOSYSTEM_CONFIG_EXAMPLE_DRIFT", codes(result))
        self.assertIn("aicore config example packages/alpha --write", result.stderr)

    def test_matching_example_passes(self):
        self.tree.write("packages/alpha/config.example.toml", self.expected())
        result = self.tree.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_edited_example_is_drift(self):
        self.tree.write("packages/alpha/config.example.toml", self.expected().replace("= 3", "= 4"))
        result = self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ECOSYSTEM_CONFIG_EXAMPLE_DRIFT", codes(result))

    def test_invalid_schema_is_reported(self):
        bad = dict(self.SCHEMA, required=["level"])
        self.tree.write_json("packages/alpha/configs/config.schema.json", bad)
        result = self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ECOSYSTEM_CONFIG_SCHEMA", codes(result))

    def test_module_without_config_needs_no_example(self):
        self.assertEqual(Tree(self).check().returncode, 0)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)
        self.tree.add_module("beta")
        self.tree.use_boundary_config()
        self.tree.set_baseline({})

    def violations(self, *flags: str) -> dict:
        data = json.loads(self.tree.check("--json", *flags).stdout)
        return {v["key"]: v["count"] for v in data["violations"]}

    def assertFails(self, code: str, *flags: str):
        result = self.tree.check(*flags)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"ECOSYSTEM_{code}", codes(result), result.stderr)
        return result

    def test_clean_tree_has_no_violations(self):
        self.assertEqual(self.violations(), {})
        self.assertEqual(self.tree.check().returncode, 0)

    def test_import_of_neighbour_is_a_new_violation(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\nfrom beta.sub import thing\n")
        result = self.assertFails("BOUNDARY_NEW")
        self.assertIn("packages/alpha/lib/alpha/use.py", result.stderr)
        self.assertEqual(self.violations(), {"import|packages/alpha/lib/alpha/use.py|beta": 2})

    def test_violation_in_baseline_passes(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        self.tree.set_baseline({"import|packages/alpha/lib/alpha/use.py|beta": 1})
        result = self.tree.check()
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_more_occurrences_than_baseline_fail(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\nimport beta.x\n")
        self.tree.set_baseline({"import|packages/alpha/lib/alpha/use.py|beta": 1})
        self.assertIn("baseline allows 1", self.assertFails("BOUNDARY_NEW").stderr)

    def test_removed_violation_is_an_improvement(self):
        self.tree.set_baseline({"import|packages/alpha/lib/alpha/use.py|beta": 2, "path|packages/alpha/x.py|beta": 1})
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        result = self.tree.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("improvement: import|packages/alpha/lib/alpha/use.py|beta: 2 -> 1", result.stderr)
        self.assertIn("improvement: path|packages/alpha/x.py|beta: 1 -> 0", result.stderr)
        data = json.loads(self.tree.check("--json").stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(sorted((i["key"], i["count"]) for i in data["improvements"]),
                         [("import|packages/alpha/lib/alpha/use.py|beta", 1), ("path|packages/alpha/x.py|beta", 0)])

    def test_strict_ignores_the_baseline(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        self.tree.set_baseline({"import|packages/alpha/lib/alpha/use.py|beta": 1})
        self.assertEqual(self.tree.check().returncode, 0)
        result = self.assertFails("BOUNDARY", "--strict")
        self.assertNotIn("BOUNDARY_NEW", result.stderr)

    def test_strict_on_clean_tree_passes(self):
        self.assertEqual(self.tree.check("--strict").returncode, 0)

    def test_key_has_no_line_numbers(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        self.tree.set_baseline({"import|packages/alpha/lib/alpha/use.py|beta": 1})
        self.tree.write("packages/alpha/lib/alpha/use.py", "# moved down\n\n\nimport beta\n")
        self.assertEqual(self.tree.check().returncode, 0)

    def test_imports_are_found_anywhere_in_the_file(self):
        self.tree.write("packages/alpha/lib/alpha/use.py",
                        "def f():\n    try:\n        from beta import x\n    except ImportError:\n        pass\n")
        self.assertEqual(self.violations(), {"import|packages/alpha/lib/alpha/use.py|beta": 1})

    def test_own_package_stdlib_and_relative_imports_are_fine(self):
        self.tree.write("packages/alpha/lib/alpha/use.py",
                        "import os\nimport alpha\nfrom alpha import x\nfrom . import y\nfrom .z import w\n")
        self.assertEqual(self.violations(), {})

    def test_tests_and_scripts_are_scanned_too(self):
        self.tree.write("packages/alpha/tests/test_x.py", "import beta\n")
        self.tree.write("packages/alpha/scripts/tool.py", "from beta import x\n")
        self.assertEqual(sorted(self.violations()),
                         ["import|packages/alpha/scripts/tool.py|beta", "import|packages/alpha/tests/test_x.py|beta"])

    def test_foundation_import_needs_requires(self):
        self.tree.write("packages/beta/lib/beta/use.py", "import core\nfrom core.io import read\nimport aicore\n")
        self.tree.write("packages/alpha/lib/alpha/use.py", "import core\nfrom aicore import x\n")
        self.assertEqual(self.violations(), {"undeclared|packages/beta/lib/beta/use.py|aicore": 3})
        self.assertIn("does not require it", self.assertFails("BOUNDARY_NEW").stderr)

    def test_foundation_may_import_itself_but_not_its_old_alias(self):
        self.tree.write("packages/aicore/lib/aicore/use.py", "import aicore\nfrom aicore.util import io\nimport core\n")
        self.assertEqual(self.violations(), {"undeclared|packages/aicore/lib/aicore/use.py|aicore": 1})

    def test_path_allow_exempts_a_file_from_path_patterns_only(self):
        self.tree.use_boundary_config()
        self.tree.write("packages/alpha/data.json", '{"source": "packages/beta/doc.md"}\n')
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\nP = 'packages/beta/x'\n")
        self.tree.config["path_allow"] = [{"path": "packages/alpha/data.json", "reason": "pointers as data"},
                                          {"path": "packages/alpha/lib/alpha/use.py", "reason": "fixture"}]
        self.assertEqual(self.violations(), {"import|packages/alpha/lib/alpha/use.py|beta": 1})

    def test_path_allow_needs_a_reason(self):
        self.tree.config["path_allow"] = [{"path": "packages/alpha/data.json"}]
        result = self.tree.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("path_allow", result.stderr)

    def test_retired_folder_is_not_scanned(self):
        self.tree.write("packages/old/lib/old/use.py", "import beta\nPATH = 'packages/beta/x'\n")
        self.assertEqual(self.violations(), {})

    def test_retired_folder_name_is_still_a_module_name(self):
        self.tree.write("packages/old/lib/old/__init__.py", "")
        self.tree.write("packages/alpha/lib/alpha/use.py", "import old\n")
        self.assertEqual(self.violations(), {"import|packages/alpha/lib/alpha/use.py|old": 1})

    def test_unparsable_python_is_an_error_not_a_violation(self):
        self.tree.write("packages/alpha/lib/alpha/broken.py", "def (:\n")
        result = self.assertFails("PARSE")
        self.assertIn("broken.py", result.stderr)
        self.assertEqual(self.violations(), {})

    def test_sibling_path_in_python_and_shell(self):
        self.tree.write("packages/alpha/lib/alpha/p.py", "ROOT = 'packages/beta/data'\nOTHER = 'packages/beta/x'\n")
        self.tree.write("packages/alpha/scripts/run.sh", "cd packages/beta/bin\n")
        self.tree.write("packages/alpha/bin/tool", "#!/bin/sh\nexec packages/beta/bin/b\n", mode=0o755)
        self.assertEqual(self.violations(), {
            "path|packages/alpha/lib/alpha/p.py|beta": 2, "path|packages/alpha/scripts/run.sh|beta": 1,
            "path|packages/alpha/bin/tool|beta": 1})
        self.assertFails("BOUNDARY_NEW")

    def test_markdown_and_docs_are_not_scanned(self):
        self.tree.write("packages/alpha/README.md", "see packages/beta/x\n")
        self.tree.write("packages/alpha/docs/guide.txt", "packages/beta/x\n")
        self.tree.write("packages/alpha/docs/guide.json", '{"p": "packages/beta/x"}\n')
        self.tree.write("packages/alpha/notes.txt", "packages/beta/x\n")
        self.assertEqual(self.violations(), {})

    def test_own_path_and_unknown_folder_are_not_violations(self):
        self.tree.write("packages/alpha/lib/alpha/p.py",
                        "A = 'packages/alpha/x'\nB = 'packages/unknown/x'\nC = 'packages/<id>/x'\nD = 'packages/'\n")
        self.assertEqual(self.violations(), {})

    def test_climb_leaving_the_module_is_an_escape(self):
        self.tree.write("packages/alpha/package.json", '{"scripts": {"s": "bash ../../scripts/x.sh"}}\n')
        self.tree.write("packages/alpha/lib/alpha/p.py", "A = '../../../../configs/x'\n")
        self.assertEqual(self.violations(), {"path|packages/alpha/package.json|scripts": 1,
                                             "path|packages/alpha/lib/alpha/p.py|configs": 1})

    def test_climb_inside_the_module_is_not_an_escape(self):
        self.tree.write("packages/alpha/scripts/run.sh", 'DIR="$HERE/../configs/x"\n')
        self.tree.write("packages/alpha/tests/t.py", "A = '../bin/x'\nB = '../../bin/x'\n")
        self.assertEqual(self.violations(), {})

    def test_foundation_path_is_allowed_only_with_requires(self):
        self.tree.write("packages/alpha/scripts/loc.sh", "# see packages/aicore/scripts/x.sh\n")
        self.tree.write("packages/beta/scripts/loc.sh", "# see packages/aicore/scripts/x.sh\n")
        self.assertEqual(self.violations(), {"path|packages/beta/scripts/loc.sh|aicore": 1})

    def test_climb_to_a_sibling_module(self):
        self.tree.write("packages/alpha/package.json", '{"p": "../scripts/x"}\n')
        self.tree.write("packages/beta/lib/beta/p.py", "A = '../scripts/x'\n")  # inside the module, no escape
        self.tree.write("packages/scripts/lib/scripts/__init__.py", "")
        result = json.loads(self.tree.check("--json").stdout)
        self.assertEqual({v["key"] for v in result["violations"]}, {"path|packages/alpha/package.json|scripts"})

    def test_files_without_scanned_suffix_are_skipped(self):
        self.tree.write("packages/alpha/data.bin", "packages/beta/x\n")
        self.tree.write("packages/alpha/data.txt", "packages/beta/x\n")
        self.assertEqual(self.violations(), {})

    def test_baseline_file_errors(self):
        self.tree.write("configs/ecosystem-baseline.json", "{nope")
        result = self.tree.check()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ecosystem-baseline.json", result.stderr)
        self.tree.write("configs/ecosystem-baseline.json", '{"violations": {"k": "x"}}')
        self.assertEqual(self.tree.check().returncode, 2)

    def test_missing_baseline_means_empty_baseline(self):
        (self.tree.root / "configs/ecosystem-baseline.json").unlink()
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        self.assertFails("BOUNDARY_NEW")


class BaselineCommandTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)
        self.tree.add_module("beta")
        self.tree.use_boundary_config()
        self.tree.flush()

    def baseline(self):
        return run(self.tree.root, "baseline", "--update")

    def read(self) -> dict:
        return json.loads((self.tree.root / "configs/ecosystem-baseline.json").read_text(encoding="utf-8"))

    def test_update_writes_sorted_violations_and_prints_diff(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        self.tree.write("packages/alpha/a.json", '{"p": "packages/beta/x"}\n')
        result = self.baseline()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("+ import|packages/alpha/lib/alpha/use.py|beta: 0 -> 1", result.stdout)
        doc = self.read()
        self.assertEqual(doc["schema_version"], "ecosystem-baseline/v1")
        self.assertEqual(list(doc["violations"]), sorted(doc["violations"]))
        self.assertEqual(doc["violations"], {"import|packages/alpha/lib/alpha/use.py|beta": 1,
                                             "path|packages/alpha/a.json|beta": 1})
        self.assertEqual(doc["standalone"], {})
        text = (self.tree.root / "configs/ecosystem-baseline.json").read_text(encoding="utf-8")
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(self.tree.check().returncode, 0)

    def test_update_is_reproducible_and_reports_removals(self):
        self.tree.write("packages/alpha/lib/alpha/use.py", "import beta\n")
        self.baseline()
        first = (self.tree.root / "configs/ecosystem-baseline.json").read_bytes()
        self.assertNotIn("->", self.baseline().stdout.split("configs/")[0])
        self.assertEqual((self.tree.root / "configs/ecosystem-baseline.json").read_bytes(), first)
        self.tree.write("packages/alpha/lib/alpha/use.py", "")
        result = self.baseline()
        self.assertIn("- import|packages/alpha/lib/alpha/use.py|beta: 1 -> 0", result.stdout)
        self.assertEqual(self.read()["violations"], {})

    def test_update_keeps_the_standalone_section(self):
        self.tree.set_baseline({}, {"alpha": "pass"})
        self.baseline()
        self.assertEqual(self.read()["standalone"], {"alpha": "pass"})

    def test_update_refuses_on_parse_errors(self):
        self.tree.write("packages/alpha/lib/alpha/broken.py", "def (:\n")
        result = self.baseline()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ECOSYSTEM_PARSE", result.stderr)
        self.assertFalse((self.tree.root / "configs/ecosystem-baseline.json").exists())

    def test_update_flag_is_required(self):
        result = run(self.tree.root, "baseline")
        self.assertEqual(result.returncode, 2, result.stderr)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tree = Tree(self)
        self.tree.config["ownership"] = [
            {"path": "packages/alpha/lib/alpha/__init__.py", "target": "aicore", "subsystem": "util",
             "phase": "P10", "confidence": "hypothesis", "note": "a | pipe"},
            {"path": "packages/alpha/bin/alpha", "target": "hub", "phase": "P9", "confidence": "fixed"},
            {"path": "packages/aicore/unit.json", "target": "aicore", "phase": "P9", "confidence": "fixed"},
        ]
        self.tree.flush()
        self.doc = self.tree.root / "docs/architecture/ownership.md"

    def render(self, *flags):
        return run(self.tree.root, "render", *flags)

    def test_render_writes_modules_and_map(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.doc.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<!-- generated by scripts/ecosystem-units.py render; do not edit -->"))
        self.assertIn("| alpha | capability | 1.2.0 | hub | beta | aicore |", text)
        self.assertIn("| aicore | foundation | 0.1.0 | own-repo | development | - |", text)
        self.assertIn("| `packages/alpha/bin/alpha` | alpha | hub | - | P9 | fixed | - |", text)
        self.assertIn("a \\| pipe", text)

    def test_map_is_sorted_by_numeric_phase_then_path(self):
        self.render()
        rows = [line for line in self.doc.read_text(encoding="utf-8").splitlines() if line.startswith("| `")]
        self.assertEqual([r.split("`")[1] for r in rows],
                         ["packages/aicore/unit.json", "packages/alpha/bin/alpha", "packages/alpha/lib/alpha/__init__.py"])

    def test_alias_is_shown(self):
        self.tree.config["module_aliases"] = {"alpha": "aicore"}
        self.tree.flush()
        self.render()
        self.assertIn("| alpha (renamed to aicore) |", self.doc.read_text(encoding="utf-8"))

    def test_render_is_deterministic_and_free_of_absolute_paths(self):
        self.render()
        first = self.doc.read_bytes()
        self.render()
        self.assertEqual(self.doc.read_bytes(), first)
        self.assertNotIn(str(self.tree.root), first.decode("utf-8"))
        self.assertNotIn("/home/", first.decode("utf-8"))

    def test_check_passes_when_current_and_fails_when_stale_or_missing(self):
        missing = self.render("--check")
        self.assertEqual(missing.returncode, 1, missing.stderr)
        self.assertIn("ECOSYSTEM_RENDER_STALE", missing.stderr)
        self.render()
        self.assertEqual(self.render("--check").returncode, 0)
        self.doc.write_text(self.doc.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
        stale = self.render("--check")
        self.assertEqual(stale.returncode, 1)
        self.assertIn("ECOSYSTEM_RENDER_STALE", stale.stderr)

    def test_check_does_not_write(self):
        self.render("--check")
        self.assertFalse(self.doc.exists())


class BridgeUnitTests(unittest.TestCase):
    """Bridges are units of the hub: ``bridges/<id>/unit.json``."""

    def setUp(self):
        self.tree = Tree(self)
        self.tree.use_boundary_config()
        self.tree.set_baseline({})

    def assertFails(self, code: str):
        result = self.tree.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"ECOSYSTEM_{code}", codes(result), result.stderr)
        return result

    def assertPasses(self):
        result = self.tree.check()
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_bridge_may_require_a_capability_and_needs_no_version_source(self):
        self.tree.add_bridge("alpha-beta")
        self.assertPasses()

    def test_bridge_is_listed_and_rendered_under_its_folder(self):
        self.tree.add_bridge("alpha-beta")
        self.tree.flush()
        listed = json.loads(run(self.tree.root, "list", "--json").stdout)["modules"]
        self.assertIn(("alpha-beta", "bridge"), [(row["id"], row["kind"]) for row in listed])
        self.assertEqual(run(self.tree.root, "render").returncode, 0)
        text = (self.tree.root / eu.OWNERSHIP_DOC).read_text(encoding="utf-8")
        self.assertIn("| alpha-beta | bridge | 0.1.0 | hub | alpha | aicore, alpha |", text)

    def test_current_module_of_a_bridge_path(self):
        self.assertEqual(eu.current_module("bridges/alpha-beta/brief.py"), "bridges/alpha-beta")
        self.assertEqual(eu.current_module("packages/alpha/lib/alpha/x.py"), "alpha")
        self.assertEqual(eu.current_module("bridges/README.md"), "bridges (hub root)")

    def test_capability_requires_only_the_foundation(self):
        self.tree.write_json("packages/beta/unit.json", {**self.tree.alpha, "id": "beta", "requires": [
            {"unit": "alpha", "range": "^1.2"}], "provides": {}})
        self.tree.write("packages/beta/package.json", json.dumps({"version": "1.2.0"}))
        self.tree.config["version_sources"]["beta"] = {"path": "packages/beta/package.json", "read": "json:version"}
        self.assertFails("UNIT_REQUIRES")

    def test_a_bridge_is_required_by_nobody(self):
        self.tree.add_bridge("alpha-beta", requires=("aicore",))
        self.tree.alpha["requires"].append({"unit": "alpha-beta", "range": "^0.1"})
        self.assertFails("UNIT_REQUIRES")

    def test_bridge_requires_no_other_bridge(self):
        self.tree.add_bridge("first", requires=("aicore",))
        self.tree.add_bridge("second", requires=("aicore", "first"))
        self.assertFails("UNIT_REQUIRES")

    def test_kind_bridge_in_packages_is_refused(self):
        self.tree.alpha["kind"] = "bridge"
        self.assertFails("UNIT_KIND")

    def test_capability_in_bridges_is_refused(self):
        self.tree.add_bridge("alpha-beta", kind="capability")
        self.assertFails("UNIT_KIND")

    def test_bridge_belongs_to_the_hub(self):
        self.tree.add_bridge("alpha-beta", destination="own-repo")
        self.assertFails("UNIT_KIND")

    def test_bridge_folder_without_unit_json_is_refused(self):
        self.tree.write("bridges/alpha-beta/README.md", "no manifest\n")
        self.assertFails("UNIT_MISSING")

    def test_bridge_id_must_equal_its_folder(self):
        self.tree.add_bridge("alpha-beta", id="other")
        self.assertFails("UNIT_ID")

    def test_bridge_folder_named_like_a_module_is_refused(self):
        self.tree.add_bridge("alpha")
        self.assertFails("UNIT_ID")

    def test_bridge_cli_must_exist_in_the_bridge(self):
        self.tree.add_bridge("alpha-beta", provides={"cli": ["brief.py"]})
        self.assertFails("UNIT_PATH")
        self.tree.write("bridges/alpha-beta/brief.py", "print(1)\n")
        self.assertPasses()

    def test_port_must_name_an_extension_point_of_a_required_module(self):
        self.tree.alpha["provides"]["extension_points"] = [{"id": "source", "description": "Work source."}]
        self.tree.add_bridge("alpha-beta", provides={"ports": [{"id": "alpha:source", "bridge": "alpha-beta"}]})
        self.assertPasses()
        self.tree.add_bridge("alpha-beta", provides={"ports": [{"id": "alpha:missing", "bridge": "alpha-beta"}]})
        self.assertFails("UNIT_PORT")

    def test_port_of_a_module_the_bridge_does_not_require_is_refused(self):
        self.tree.alpha["provides"]["extension_points"] = [{"id": "source", "description": "Work source."}]
        self.tree.add_bridge("alpha-beta", requires=("aicore",),
                             provides={"ports": [{"id": "alpha:source", "bridge": "alpha-beta"}]})
        self.assertFails("UNIT_PORT")

    def test_port_must_name_its_own_bridge(self):
        self.tree.alpha["provides"]["extension_points"] = [{"id": "source", "description": "Work source."}]
        self.tree.add_bridge("alpha-beta", provides={"ports": [{"id": "alpha:source", "bridge": "elsewhere"}]})
        self.assertFails("UNIT_PORT")

    def test_import_of_a_partner_from_a_bridge_is_a_violation(self):
        self.tree.add_bridge("alpha-beta")
        self.tree.write("bridges/alpha-beta/use.py", "import alpha\nfrom alpha.sub import thing\n")
        result = self.assertFails("BOUNDARY_NEW")
        self.assertIn("bridges/alpha-beta/use.py", result.stderr)
        data = json.loads(self.tree.check("--json").stdout)
        self.assertEqual({v["key"]: v["count"] for v in data["violations"]},
                         {"import|bridges/alpha-beta/use.py|alpha": 2})

    def test_import_of_the_foundation_needs_requires_in_a_bridge(self):
        self.tree.add_bridge("alpha-beta", requires=("alpha",))
        self.tree.write("bridges/alpha-beta/use.py", "import aicore\n")
        self.assertFails("BOUNDARY_NEW")

    def test_the_path_of_a_neighbour_package_is_a_violation_in_a_bridge(self):
        self.tree.add_bridge("alpha-beta")
        self.tree.write("bridges/alpha-beta/where.py", "ROOT = 'packages/alpha/lib'\n")
        self.assertFails("BOUNDARY_NEW")

    def test_the_foundation_locator_path_is_allowed_in_a_bridge_that_requires_it(self):
        self.tree.add_bridge("alpha-beta")
        self.tree.write("bridges/alpha-beta/where.py", "LIB = HUB / 'packages' / 'aicore'  # packages/aicore/lib\n")
        self.assertPasses()

    def test_a_bridge_has_no_standalone_run(self):
        self.tree.add_bridge("alpha-beta", dev={"test": ["true"]})
        self.tree.flush()
        result = run(self.tree.root, "standalone", "alpha-beta")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone alpha-beta: n/a", result.stdout)


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

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT)

    def test_baseline_is_current_and_strict_fails(self):
        self.assertEqual(self.run_script("check").returncode, 0)
        self.assertEqual(self.run_script("check", "--strict").returncode, 1)
        baseline = json.loads((ROOT / "configs/ecosystem-baseline.json").read_text(encoding="utf-8"))["violations"]
        self.assertTrue(any(k.startswith("import|packages/maind/") and k.endswith("|harness") for k in baseline))
        # analyst stays inside its boundaries since P11.2: no violation of its own is in the baseline
        self.assertFalse(any(k.split("|")[1].startswith("packages/analyst/") for k in baseline))

    def test_ownership_doc_is_current(self):
        self.assertEqual(self.run_script("render", "--check").returncode, 0)

    def test_map_covers_transitional_roots(self):
        data = json.loads(self.run_script("check", "--json").stdout)
        self.assertEqual([e for e in data["errors"] if e["code"].startswith("ECOSYSTEM_MAP")], [])

    def test_modules_and_aliases(self):
        data = json.loads(subprocess.run([sys.executable, str(SCRIPT), "list", "--json"], capture_output=True,
                                         text=True, cwd=ROOT).stdout)
        self.assertEqual(sorted(m["id"] for m in data["modules"] if m["kind"] != "bridge"),
                         ["aicore", "analyst", "brain", "harness", "maind", "orch", "planner", "skiller"])
        self.assertEqual(sorted(m["id"] for m in data["modules"] if m["kind"] == "bridge"),
                         ["orch-harness", "orch-skiller", "planner-orch"])
        self.assertFalse((ROOT / "packages/artifex/unit.json").exists())


class StandaloneTests(unittest.TestCase):
    """standalone runs dev commands in a copy of the module with HOME inside a temporary directory."""

    def setUp(self):
        self.tree = Tree(self)
        self.tree.config["standalone"] = {"foundation_paths": ["shared"], "unset_env": ["SKM_LEAK"],
                                          "timeout_s": 5}
        self.tree.write("shared/data.txt", "foundation\n")

    def dev(self, **dev):
        self.tree.alpha["dev"] = dev

    def standalone(self, *args, env=None):
        self.tree.flush()
        merged = {**__import__("os").environ, **(env or {})}
        return subprocess.run([sys.executable, str(SCRIPT), "standalone", *args, "--root", str(self.tree.root)],
                              capture_output=True, text=True, env=merged)

    def baseline(self) -> dict:
        return json.loads((self.tree.root / "configs/ecosystem-baseline.json").read_text(encoding="utf-8"))

    def test_pass(self):
        self.dev(test=["python3", "-c", "import sys; sys.exit(0)"])
        result = self.standalone("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone alpha: pass", result.stdout)

    def test_fail_prints_the_tail(self):
        self.dev(test=["python3", "-c", "import sys; print('boom-marker'); sys.exit(1)"])
        result = self.standalone("alpha")
        self.assertEqual(result.returncode, 1)
        self.assertIn("standalone alpha: fail", result.stdout)
        self.assertIn("boom-marker", result.stderr)

    def test_without_dev_is_not_applicable(self):
        result = self.standalone("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone alpha: n/a", result.stdout)

    def test_setup_runs_before_tests_and_validate_after(self):
        self.dev(standalone_setup=[["python3", "-c", "open('order','a').write('s')"]],
                 test=["python3", "-c", "open('order','a').write('t')"],
                 validate=["python3", "-c", "import sys; sys.exit(0 if open('order').read()=='st' else 1)"])
        self.assertEqual(self.standalone("alpha").returncode, 0)

    def test_layout_home_and_environment(self):
        script = ("import os, pathlib, sys; home = pathlib.Path(os.environ['HOME']).resolve(); "
                  "tmp = pathlib.Path.cwd().resolve().parents[1]; "
                  "ok = tmp in home.parents and os.environ['XDG_CONFIG_HOME'].startswith(str(home)) "
                  "and 'SKM_LEAK' not in os.environ and pathlib.Path('../../shared/data.txt').is_file() "
                  "and pathlib.Path('../aicore/unit.json').is_file() and not pathlib.Path('../../packages').exists(); "
                  "open('home.txt','w').write(str(home)); sys.exit(0 if ok else 1)")
        self.dev(test=["python3", "-c", script])
        result = self.standalone("alpha", env={"SKM_LEAK": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_foundation_free_module_gets_no_foundation_paths(self):
        script = ("import pathlib, sys; "
                  "sys.exit(0 if not pathlib.Path('../../shared').exists() "
                  "and pathlib.Path('../aicore/unit.json').is_file() else 1)")
        self.dev(test=["python3", "-c", script])
        self.assertEqual(self.standalone("alpha").returncode, 1)
        self.tree.config["standalone"]["foundation_free"] = ["alpha"]
        result = self.standalone("alpha")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_timeout_is_a_failure_and_temp_is_removed(self):
        self.tree.config["standalone"]["timeout_s"] = 1
        self.dev(test=["python3", "-c", "import time; time.sleep(30)"])
        before = set(Path(tempfile.gettempdir()).glob("skm-standalone-alpha.*"))
        result = self.standalone("alpha")
        self.assertEqual(result.returncode, 1)
        self.assertIn("timeout", result.stderr)
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("skm-standalone-alpha.*")), before)

    def test_update_baseline_records_results_and_keeps_violations(self):
        self.tree.set_baseline({"import|x.py|beta": 2})
        self.dev(test=["python3", "-c", "import sys; sys.exit(0)"])
        self.tree.add_module("beta")
        self.tree.write_json("packages/beta/unit.json", {**json.loads(
            (self.tree.root / "packages/beta/unit.json").read_text(encoding="utf-8")),
            "dev": {"test": ["python3", "-c", "import sys; sys.exit(1)"]}})
        self.tree.add_module("gamma")
        result = self.standalone("--all", "--update-baseline")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = self.baseline()
        self.assertEqual(doc["standalone"], {"aicore": "n/a", "alpha": "pass", "beta": "fail", "gamma": "n/a"})
        self.assertEqual(doc["violations"], {"import|x.py|beta": 2})

    def test_baseline_runs_only_recorded_passes(self):
        self.tree.add_module("beta")
        self.tree.write_json("packages/beta/unit.json", {**json.loads(
            (self.tree.root / "packages/beta/unit.json").read_text(encoding="utf-8")),
            "dev": {"test": ["python3", "-c", "import sys; sys.exit(1)"]}})
        self.dev(test=["python3", "-c", "import sys; sys.exit(0)"])
        self.tree.set_baseline({}, {"alpha": "pass", "beta": "fail"})
        result = self.standalone("--baseline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone alpha: pass", result.stdout)
        self.assertNotIn("beta", result.stdout)

    def test_baseline_fails_when_a_recorded_pass_regresses(self):
        self.dev(test=["python3", "-c", "import sys; sys.exit(1)"])
        self.tree.set_baseline({}, {"alpha": "pass"})
        self.assertEqual(self.standalone("--baseline").returncode, 1)

    def test_usage_errors(self):
        self.assertEqual(self.standalone().returncode, 2)
        self.assertEqual(self.standalone("nope").returncode, 2)


class RepositoryStandaloneTests(unittest.TestCase):
    def test_recorded_states(self):
        doc = json.loads((ROOT / "configs/ecosystem-baseline.json").read_text(encoding="utf-8"))["standalone"]
        self.assertEqual(set(doc), {"aicore", "analyst", "brain", "harness", "maind", "orch", "planner", "skiller"})
        self.assertEqual(doc["skiller"], "pass")
        self.assertTrue(set(doc.values()) <= set(eu.STANDALONE_STATES))


if __name__ == "__main__":
    unittest.main()
