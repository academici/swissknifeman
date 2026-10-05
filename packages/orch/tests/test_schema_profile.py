from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orch import contracts, schema

TASK_SCHEMA = Path(__file__).resolve().parents[2] / "task/lib/task/plan/schema.py"


class SchemaProfileTests(unittest.TestCase):
    def test_unsupported_keyword_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "bad.schema.json").write_text(json.dumps({
                "$id": "urn:test:bad:v1", "type": "integer", "minimum": 0,
            }))
            with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword 'minimum'"):
                schema.load_registry(Path(directory), urn_prefix="urn:test:", kinds=("bad",))

    @unittest.skipUnless(TASK_SCHEMA.is_file(), "Task source not present in standalone checkout")
    def test_task_profile_parity_without_importing_task(self):
        tree = ast.parse(TASK_SCHEMA.read_text(encoding="utf-8"))
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ("SUPPORTED_KEYWORDS", "ERROR_CODES"):
                        value = node.value
                        if isinstance(value, ast.Call):
                            value = value.args[0]
                        values[target.id] = ast.literal_eval(value)
        self.assertEqual(set(values), {"SUPPORTED_KEYWORDS", "ERROR_CODES"})
        for name, expected in values.items():
            self.assertTrue(set(getattr(schema, name)).issuperset(expected), name)

    def test_digest_canonical_bytes_and_no_mutation(self):
        original = {"digest": "old", "z": "привет", "a": {"digest": "nested", "n": 1}}
        reordered = {"a": {"n": 1, "digest": "nested"}, "z": "привет", "digest": "new"}
        expected = sha256('{"a":{"digest":"nested","n":1},"z":"привет"}'.encode()).hexdigest()
        self.assertEqual(contracts.canonical_digest(original), expected)
        self.assertEqual(contracts.canonical_digest(reordered), expected)
        self.assertEqual(original["digest"], "old")
        self.assertNotEqual(contracts.canonical_digest({"a": {"n": 1}, "z": "привет"}), expected)

    def test_shared_definitions(self):
        registry = contracts.load_registry()
        base = contracts.URN_PREFIX + "defs:v1"
        valid = {
            "id": "PLAN2.P1.1/U1@run", "sha256": "a" * 64, "gitSha": "abc1234",
            "ts": "2026-10-05T17:00:00.123Z", "text": "x", "path": "@plan/knowledge/a.json",
            "provider": "codex", "modelClass": "implementation", "effort": "high",
            "route": {"class": "implementation", "effort": "high"},
            "actor": {"provider": "codex", "model": "gpt-6.1-sol"},
            "check": {"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"},
            "support": "unknown", "binding": "cao", "roleId": "reviewer",
            "section": {"id": "x", "title": "X", "text": ""},
        }
        root, _ = registry.resolve(base, base)
        self.assertEqual(set(root["$defs"]), set(valid))
        for name, value in valid.items():
            with self.subTest(name=name):
                node = {"$ref": "#/$defs/" + name}
                self.assertEqual(schema.validate_node(registry, node, base, value), [])
                self.assertTrue(schema.validate_node(registry, node, base, None))
        for name, value in (("id", "x" * 161), ("id", "abc\n"), ("sha256", "A" * 64),
                            ("path", "/absolute"), ("path", "has space"), ("provider", "Codex"),
                            ("route", {"class": "economy"}),
                            ("actor", {"provider": "codex", "model": "x", "extra": 1})):
            with self.subTest(name=name, value=value):
                self.assertTrue(schema.validate_node(registry, {"$ref": "#/$defs/" + name}, base, value))
        for definition in root["$defs"].values():
            for prop in definition.get("properties", {}).values():
                self.assertTrue(prop.get("description"))

    def test_registry_cache_includes_route_parameters(self):
        directory = Path(contracts.__file__).resolve().parents[2] / "schemas/exec/v1"
        first = contracts.load_registry()
        self.assertIs(first, contracts.load_registry())
        other = schema.load_registry(directory, urn_prefix="urn:other:", kinds=("defs",))
        self.assertIsNot(first, other)
        with self.assertRaises(schema.SchemaProfileError):
            other.for_kind("execution-input")

    def test_schema_and_semantic_dispatch(self):
        kind = "execution-input"
        registry = schema.Registry({contracts.URN_PREFIX + kind + ":v1": {
            "type": "object", "required": ["goal"],
        }}, urn_prefix=contracts.URN_PREFIX, kinds=contracts.KINDS)
        semantic = contracts.Issue("/goal", "TEST_SEMANTIC", "test issue")
        with patch.dict(contracts.SEMANTIC, {kind: lambda doc: [semantic]}):
            issues = contracts.validate({"contract_version": "exec/v1"}, kind, registry)
        self.assertEqual([issue.code for issue in issues], ["required", "TEST_SEMANTIC"])
        self.assertTrue(all(issue.level == "error" for issue in issues))
        with self.assertRaises(schema.SchemaProfileError):
            contracts.validate({"contract_version": "exec/v1"}, "unknown", registry)
