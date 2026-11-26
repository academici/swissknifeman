from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aicore.util import schema as foundation

from orch import contracts, schema


class SchemaProfileTests(unittest.TestCase):
    def test_unsupported_keyword_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "bad.schema.json").write_text(json.dumps({
                "$id": "urn:test:bad:v1", "type": "string", "format": "uri",
            }))
            with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword 'format'"):
                schema.load_registry(Path(directory), urn_prefix="urn:test:", kinds=("bad",))

    def test_profile_is_the_aicore_profile(self):
        self.assertIs(schema.validate, foundation.validate)
        self.assertIs(schema.load_registry, foundation.load_registry)
        self.assertIs(schema.Registry, foundation.Registry)
        self.assertIs(schema.SchemaProfileError, foundation.SchemaProfileError)
        self.assertEqual(schema.SUPPORTED_KEYWORDS, foundation.SUPPORTED_KEYWORDS)
        self.assertEqual(schema.ERROR_CODES, foundation.ERROR_CODES)
        self.assertFalse(hasattr(schema, "_check_array") or hasattr(schema, "_check_object"))

    def test_digest_matches_every_signed_fixture(self):
        signed = []
        for path in sorted((Path(contracts.__file__).resolve().parents[2] / "fixtures/exec/v1/valid").glob("*/*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc.get("digest"), str):
                signed.append(path.name)
                legacy = json.dumps({k: v for k, v in doc.items() if k != "digest"} if "input_id" not in doc else
                                    {**{k: v for k, v in doc.items() if k != "digest"},
                                     "input_id": doc["input_id"].rsplit("@", 1)[0]},
                                    sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                self.assertEqual(contracts.canonical_digest(doc), sha256(legacy.encode("utf-8")).hexdigest(), path.name)
                self.assertEqual(doc["digest"], contracts.canonical_digest(doc), path.name)
        self.assertTrue(signed)

    def test_float_document_is_reported_not_raised(self):
        doc = {"contract_version": "exec/v1", "digest": "a" * 64, "input_id": "x@" + "a" * 12, "n": 1.5}
        issues = contracts.semantic_checks(doc, "execution-input")
        self.assertIn(("/digest", "DIGEST_MISMATCH"), [(i.path, i.code) for i in issues])
        with self.assertRaises(TypeError):
            contracts.canonical_digest(doc)

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
            "support": "unknown", "binding": "cao", "roleId": "reviewer", "commitRole": "fix",
            "section": {"id": "x", "title": "X", "text": ""},
            "submissionId": "sub-abc", "attemptId": "att-run-1-primary-1", "callId": "call-1",
            "eventId": "evt-run-1-3", "moduleVersion": {"id": "orch", "version": "0.1.0"},
            "reasonCode": "PRECONDITION_CHANGED",
            "skillRef": {"name": "x", "digest": "sha256:" + "a" * 64},
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
                            ("route", {"class": "economy"}), ("submissionId", "att-1"),
                            ("attemptId", "sub-1"), ("callId", "evt-1"), ("eventId", "call-1"),
                            ("moduleVersion", {"id": "orch"}), ("reasonCode", "lower"),
                            ("skillRef", {"name": "x", "digest": "a" * 64}),
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
