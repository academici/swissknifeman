"""The configuration extension of the schema profile: minimum, maximum and the x-skm-* annotations."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util import schema

PREFIX = "urn:test:"


class ProfileCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        schema.clear_registry_cache()
        self.addCleanup(schema.clear_registry_cache)

    def load(self, body, kind="thing"):
        schema.clear_registry_cache()
        doc = {"$schema": schema.DIALECT, "$id": f"{PREFIX}{kind}:v1", **body}
        (self.dir / f"{kind}.schema.json").write_text(json.dumps(doc), encoding="utf-8")
        return schema.load_registry(self.dir, urn_prefix=PREFIX, kinds=(kind,))

    def codes(self, body, value):
        return [issue.code for issue in schema.validate(value, "thing", self.load(body))]


class TestMinimumMaximum(ProfileCase):
    def test_minimum_and_maximum_bound_numbers(self):
        body = {"type": "integer", "minimum": 1, "maximum": 10}
        self.assertEqual(self.codes(body, 1), [])
        self.assertEqual(self.codes(body, 10), [])
        self.assertEqual(self.codes(body, 0), ["minimum"])
        self.assertEqual(self.codes(body, 11), ["maximum"])

    def test_bounds_apply_to_floats(self):
        body = {"type": "number", "minimum": 0, "maximum": 1}
        self.assertEqual(self.codes(body, 0.5), [])
        self.assertEqual(self.codes(body, -0.1), ["minimum"])
        self.assertEqual(self.codes(body, 1.5), ["maximum"])

    def test_booleans_and_strings_are_not_bounded(self):
        body = {"minimum": 5}
        self.assertEqual(self.codes(body, True), [])
        self.assertEqual(self.codes(body, "0"), [])

    def test_wrong_type_stops_before_the_bound(self):
        self.assertEqual(self.codes({"type": "integer", "minimum": 1}, "0"), ["type"])

    def test_bound_must_be_a_finite_number(self):
        for body in ({"minimum": "1"}, {"maximum": True}, {"minimum": None}, {"maximum": float("inf")}):
            with self.subTest(body=body):
                with self.assertRaises(schema.SchemaProfileError):
                    self.load(body)

    def test_error_codes_list_the_new_codes(self):
        self.assertIn("minimum", schema.ERROR_CODES)
        self.assertIn("maximum", schema.ERROR_CODES)


class TestAnnotations(ProfileCase):
    def test_annotations_are_accepted_and_ignored(self):
        body = {"type": "string", "x-skm-secret": True, "x-skm-layers": ["defaults", "machine"]}
        self.assertEqual(self.codes(body, "anything"), [])
        self.assertEqual(self.codes(body, 1), ["type"])

    def test_annotations_are_accepted_in_nested_nodes(self):
        body = {"type": "object", "properties": {"a": {"type": "string", "x-skm-secret": True}}}
        self.assertEqual(self.codes(body, {"a": "x"}), [])

    def test_other_x_keywords_are_rejected(self):
        for keyword in ("x-skm-other", "x-custom", "x-skm-secrets"):
            with self.subTest(keyword=keyword):
                with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword"):
                    self.load({"type": "string", keyword: True})

    def test_annotation_values_are_checked(self):
        for body in ({"x-skm-secret": "yes"}, {"x-skm-layers": "machine"}, {"x-skm-layers": []},
                     {"x-skm-layers": [1]}, {"x-skm-layers": [""]}):
            with self.subTest(body=body):
                with self.assertRaises(schema.SchemaProfileError):
                    self.load(body)

    def test_existing_keywords_keep_failing_closed(self):
        with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword 'format'"):
            self.load({"type": "string", "format": "uri"})


if __name__ == "__main__":
    unittest.main()
