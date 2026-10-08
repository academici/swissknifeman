"""Tests of the closed-profile validator aicore.util.schema."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util import schema

PREFIX = "urn:test:"


def write_schema(directory: Path, kind: str, body: dict, version: str = "v1") -> None:
    doc = {"$schema": schema.DIALECT, "$id": f"{PREFIX}{kind}:{version}", **body}
    (directory / f"{kind}.schema.json").write_text(json.dumps(doc), encoding="utf-8")


class SchemaCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        schema.clear_registry_cache()
        self.addCleanup(schema.clear_registry_cache)

    def registry(self, body: dict, kind: str = "thing"):
        schema.clear_registry_cache()  # the same directory is rewritten within one test
        write_schema(self.dir, kind, body)
        return schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=(kind,))

    def codes(self, body: dict, doc: object, kind: str = "thing") -> list:
        return [issue.code for issue in schema.validate(doc, kind, self.registry(body, kind))]


class TestProfile(SchemaCase):
    def test_unsupported_keyword_fails_closed(self):
        write_schema(self.dir, "bad", {"type": "integer", "multipleOf": 2})
        with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword 'multipleOf'"):
            schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("bad",))

    def test_profile_rules(self):
        for body in ({"type": "bogus"}, {"additionalProperties": True}, {"required": "a"}, {"enum": []},
                     {"minItems": -1}, {"uniqueItems": 1}, {"pattern": "("}, {"$ref": 3}, {"oneOf": []},
                     {"properties": {"a": {"$schema": schema.DIALECT}}}):
            with self.subTest(body=body):
                schema.clear_registry_cache()
                write_schema(self.dir, "bad", body)
                with self.assertRaises(schema.SchemaProfileError):
                    schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("bad",))

    def test_empty_directory_and_unknown_kind(self):
        with self.assertRaises(schema.SchemaProfileError):
            schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("x",))
        registry = self.registry({"type": "string"})
        with self.assertRaises(schema.SchemaProfileError):
            registry.for_kind("other")

    def test_duplicate_id(self):
        write_schema(self.dir, "a", {})
        doc = {"$schema": schema.DIALECT, "$id": f"{PREFIX}a:v1"}
        (self.dir / "b.schema.json").write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(schema.SchemaProfileError, "duplicate"):
            schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("a",))

    def test_registry_is_cached_per_parameters(self):
        write_schema(self.dir, "thing", {"type": "string"})
        first = schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("thing",))
        self.assertIs(first, schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("thing",)))
        self.assertIsNot(first, schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=("thing",), version="v2"))


class TestValidation(SchemaCase):
    def test_type_enum_const(self):
        self.assertEqual(self.codes({"type": "integer"}, "x"), ["type"])
        self.assertEqual(self.codes({"type": "integer"}, True), ["type"])
        self.assertEqual(self.codes({"enum": ["a", "b"]}, "c"), ["enum"])
        self.assertEqual(self.codes({"enum": [1]}, True), ["enum"])
        self.assertEqual(self.codes({"const": "v"}, "w"), ["const"])
        self.assertEqual(self.codes({"type": ["string", "null"]}, None), [])

    def test_string_keywords(self):
        body = {"type": "string", "minLength": 2, "pattern": "^[a-z]+$"}
        self.assertEqual(self.codes(body, "ab"), [])
        self.assertEqual(self.codes(body, "A"), ["min_length", "pattern"])
        self.assertEqual(self.codes(body, "ab\n"), ["pattern"])  # "$" matches only at the very end

    def test_array_keywords(self):
        body = {"type": "array", "minItems": 2, "uniqueItems": True, "items": {"type": "integer"}}
        self.assertEqual(self.codes(body, [1, 2]), [])
        self.assertEqual(self.codes(body, [1]), ["min_items"])
        self.assertEqual(self.codes(body, [1, 1]), ["unique"])
        self.assertEqual(self.codes(body, [1, "a"]), ["type"])

    def test_object_keywords_and_pointer(self):
        body = {"type": "object", "required": ["a"], "additionalProperties": False,
                "properties": {"a": {"type": "string"}, "b/c": {"type": "integer"}}}
        self.assertEqual(self.codes(body, {"a": "x"}), [])
        self.assertEqual(self.codes(body, {}), ["required"])
        registry = self.registry(body)
        issues = schema.validate({"a": "x", "extra": 1, "b/c": "s"}, "thing", registry)
        self.assertEqual(sorted((issue.path, issue.code) for issue in issues),
                         [("/b~1c", "type"), ("/extra", "additional")])

    def test_one_of(self):
        body = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertEqual(self.codes(body, 1), [])
        self.assertEqual(self.codes(body, None), ["one_of"])
        self.assertEqual(self.codes({"oneOf": [{"type": "integer"}, {"type": "number"}]}, 1), ["one_of"])

    def test_ref_inside_registry_and_unresolved(self):
        body = {"type": "object", "properties": {"h": {"$ref": "#/$defs/hex"}, "z": {"$ref": "#/$defs/none"}},
                "$defs": {"hex": {"type": "string", "pattern": "^[0-9a-f]+$"}}}
        self.assertEqual(self.codes(body, {"h": "ab"}), [])
        self.assertEqual(self.codes(body, {"h": "zz"}), ["pattern"])
        self.assertEqual(self.codes(body, {"z": 1}), ["ref"])

    def test_validate_node(self):
        registry = self.registry({"$defs": {"n": {"type": "integer"}}})
        base = f"{PREFIX}thing:v1"
        self.assertEqual(schema.validate_node(registry, {"$ref": "#/$defs/n"}, base, 1), [])
        self.assertTrue(schema.validate_node(registry, {"$ref": "#/$defs/n"}, base, "s"))


class TestLoadContract(SchemaCase):
    def contract(self, name: str = "thing", version: str = "v1") -> Path:
        directory = self.dir / name / version
        directory.mkdir(parents=True)
        return directory

    def test_loads_kind_and_version(self):
        directory = self.contract("thing", "v2")
        write_schema(directory, "thing", {"type": "string"}, version="v2")
        registry, kind = schema.load_contract(directory, urn_prefix=PREFIX)
        self.assertEqual(kind, "thing")
        self.assertEqual(schema.validate("x", kind, registry), [])
        self.assertTrue(schema.validate(1, kind, registry))

    def test_rejects_wrong_layout(self):
        directory = self.contract("thing", "v1")
        write_schema(directory, "other", {})
        with self.assertRaises(schema.SchemaProfileError):
            schema.load_contract(directory, urn_prefix=PREFIX)
        bad_version = self.contract("thing2", "latest")
        write_schema(bad_version, "thing2", {}, version="latest")
        with self.assertRaises(schema.SchemaProfileError):
            schema.load_contract(bad_version, urn_prefix=PREFIX)

    def test_id_version_must_match_directory(self):
        directory = self.contract("thing", "v2")
        write_schema(directory, "thing", {}, version="v1")
        with self.assertRaises(schema.SchemaProfileError):
            schema.load_contract(directory, urn_prefix=PREFIX)


if __name__ == "__main__":
    unittest.main()
