"""The vendored core (planner.plan._jsonschema_core, runs without aicore): size limits, dependentRequired and not; the profile check of the same keywords."""
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan._jsonschema_core import SchemaProfileError, ValidationIssue, _check, _check_profile


class Registry:
    def resolve(self, ref, base_id):  # no $ref in these schemas
        raise AssertionError(ref)


def issues(schema, value):
    out = []
    _check(Registry(), schema, "urn:test", value, "", out)
    return out


def codes(schema, value):
    return [issue.code for issue in issues(schema, value)]


class KeywordTests(unittest.TestCase):
    def test_max_length_counts_characters(self):
        schema = {"type": "string", "maxLength": 3}
        self.assertEqual(codes(schema, "abc"), [])
        self.assertEqual(codes(schema, "abcd"), ["max_length"])
        self.assertEqual(codes(schema, "жжж"), [])

    def test_max_items(self):
        schema = {"type": "array", "maxItems": 2}
        self.assertEqual(codes(schema, [1, 2]), [])
        self.assertEqual(codes(schema, [1, 2, 3]), ["max_items"])

    def test_property_counts(self):
        schema = {"type": "object", "minProperties": 1, "maxProperties": 2}
        self.assertEqual(codes(schema, {}), ["min_properties"])
        self.assertEqual(codes(schema, {"a": 1}), [])
        self.assertEqual(codes(schema, {"a": 1, "b": 2, "c": 3}), ["max_properties"])

    def test_dependent_required(self):
        schema = {"type": "object", "dependentRequired": {"argv": ["cwd"], "cmd": []}}
        self.assertEqual(codes(schema, {}), [])
        self.assertEqual(codes(schema, {"cmd": "x"}), [])
        self.assertEqual(codes(schema, {"argv": []}), ["dependent_required"])
        self.assertEqual(codes(schema, {"argv": [], "cwd": "."}), [])

    def test_not(self):
        schema = {"type": "object", "not": {"required": ["argv", "cmd"]}}
        self.assertEqual(codes(schema, {"argv": []}), [])
        self.assertEqual(codes(schema, {"argv": [], "cmd": "x"}), ["not"])
        enum_not = {"not": {"enum": ["root"]}}
        self.assertEqual(codes(enum_not, "root"), ["not"])
        self.assertEqual(codes(enum_not, "user"), [])

    def test_issue_shape(self):
        issue, = issues({"type": "string", "maxLength": 1}, "ab")
        self.assertIsInstance(issue, ValidationIssue)
        self.assertEqual((issue.path, issue.code), ("", "max_length"))


class ProfileTests(unittest.TestCase):
    def reject(self, schema):
        with self.assertRaises(SchemaProfileError):
            _check_profile(schema, "t.json", "", root=True)

    def test_accepts_the_new_keywords(self):
        _check_profile({"type": "object", "maxProperties": 3, "minProperties": 0,
                        "dependentRequired": {"a": ["b"]}, "not": {"required": ["c"]},
                        "properties": {"s": {"type": "string", "maxLength": 9}, "l": {"type": "array", "maxItems": 4}}},
                       "t.json", "", root=True)

    def test_rejects_malformed_values(self):
        for schema in ({"maxLength": -1}, {"maxItems": "3"}, {"maxProperties": True}, {"minProperties": 1.5},
                       {"dependentRequired": ["a"]}, {"dependentRequired": {"a": "b"}}, {"not": []},
                       {"not": {"format": "uri"}}):
            with self.subTest(schema=schema):
                self.reject(schema)

    def test_property_names_may_limit_the_length(self):
        _check_profile({"type": "object", "propertyNames": {"type": "string", "maxLength": 20}}, "t.json", "", root=True)


if __name__ == "__main__":
    unittest.main()
