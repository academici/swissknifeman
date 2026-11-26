"""Recursive compatibility regressions ported from the donor, plus lock/generation integration."""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, ClassVar

import pytest

gen = import_module("tools.gen")
checker = import_module("tools.schema_check")
RULES, Change, Graph, RefError, compare = (
    checker.RULES,
    checker.Change,
    checker.Graph,
    checker.RefError,
    checker.compare,
)

URN = "urn:skm:compat:"
OPEN = {"type": "object"}
CLOSED = {"type": "object", "additionalProperties": False}


def registry(*documents):
    """A registry of schema documents; the first one is the root. Returns ``(registry, root id)``."""
    schemas = {}
    for body in documents:
        schemas[body["$id"]] = body
    return Graph(schemas), documents[0]["$id"]


def doc(body, name="t"):
    return {"$id": f"{URN}{name}:v1", **body}


def changes(old_body, new_body):
    old, old_id = registry(doc(old_body))
    new, new_id = registry(doc(new_body))
    found = compare(old, old_id, new, new_id)
    for change in found:
        if change.rule != "pattern-property-added":  # its grade depends on the schemas (see the tests)
            assert change.breaking is RULES[change.rule], change
    return found


def rules(old_body, new_body):
    return sorted(change.rule for change in changes(old_body, new_body))


def obj(properties=None, required=None, **extra):
    body = dict(CLOSED, **extra)
    body["properties"] = properties or {}
    if required is not None:
        body["required"] = required
    return body


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}


def directed(old_body, new_body, direction):
    old, old_id = registry(doc(old_body))
    new, new_id = registry(doc(new_body))
    return sorted((change.rule, change.breaking) for change in compare(old, old_id, new, new_id, direction))


class TestDirection(unittest.TestCase):
    """New outputs must stay valid under the consumer's old schema."""

    def test_a_new_property_breaks_an_output_contract_only(self):
        old, new = obj({"a": STR}), obj({"a": STR, "b": STR})
        assert directed(old, new, "input") == [("property-added", False)]
        assert directed(old, new, "output") == [("property-removed", True)]
        assert sorted([("property-added", False), ("property-removed", True)]) == directed(old, new, "both")

    def test_a_wider_enum_or_type_breaks_an_output_contract(self):
        assert directed({"enum": ["a"]}, {"enum": ["a", "b"]}, "output") == [("enum-narrowed", True)]
        assert directed(INT, {"type": "number"}, "output") == [("type-changed", True)]

    def test_a_removed_property_is_fine_for_an_output_contract(self):
        old, new = obj({"a": STR, "b": STR}), obj({"a": STR})
        assert directed(old, new, "input") == [("property-removed", True)]
        assert directed(old, new, "output") == [("property-added", False)]

    def test_messages_of_the_output_side_are_marked(self):
        old, old_id = registry(doc(obj({})))
        new, new_id = registry(doc(obj({"b": STR})))
        found = compare(old, old_id, new, new_id, "output")
        assert found[0].message.startswith("[output] ")

    def test_unknown_direction_is_a_programming_error(self):
        old, old_id = registry(doc(OPEN))
        with pytest.raises(ValueError, match="direction must be"):
            compare(old, old_id, old, old_id, "sideways")


class TestRules(unittest.TestCase):
    # rule -> (old schema, new schema) in which exactly that rule fires
    CASES: ClassVar = {
        "schema-widened": (obj({"x": False}), obj({"x": True})),
        "constraint-changed": ({}, {"format": "uuid"}),
        "property-removed": (obj({"a": STR}), obj({})),
        "property-added": (obj({"a": STR}), obj({"a": STR, "b": STR})),
        "required-added": (obj({"a": STR, "b": STR}, ["a"]), obj({"a": STR, "b": STR}, ["a", "b"])),
        "required-removed": (obj({"a": STR}, ["a"]), obj({"a": STR}, [])),
        "enum-narrowed": ({"enum": ["a", "b"]}, {"enum": ["a"]}),
        "enum-widened": ({"enum": ["a"]}, {"enum": ["a", "b"]}),
        "enum-added": (STR, {"type": "string", "enum": ["a"]}),
        "type-changed": (STR, INT),
        "type-widened": (INT, {"type": "number"}),
        "const-changed": ({"const": 1}, {"const": 2}),
        "pattern-changed": ({"pattern": "^a$"}, {"pattern": "^b$"}),
        "pattern-removed": ({"pattern": "^a$"}, {}),
        "bound-tightened": ({"minLength": 1}, {"minLength": 2}),
        "bound-relaxed": ({"minLength": 2}, {"minLength": 1}),
        "additional-closed": (OPEN, CLOSED),
        "pattern-property-removed": ({"patternProperties": {"^a": STR}}, {}),
        "pattern-property-added": (CLOSED, {"type": "object", "patternProperties": {"^a": STR}}),
        "property-names-changed": ({}, {"propertyNames": {"pattern": "^[a-z]+$"}}),
        "unique-added": ({"type": "array"}, {"type": "array", "uniqueItems": True}),
        "oneof-changed": ({"oneOf": [STR, INT]}, {"oneOf": [STR]}),
        "not-changed": ({"type": "object"}, {"type": "object", "not": {"required": ["a"]}}),
        "dependent-required-added": (OPEN, dict(OPEN, dependentRequired={"a": ["b"]})),
    }

    def test_conditions_only_break_when_they_narrow(self):
        deps = dict(OPEN, dependentRequired={"a": ["b"]})
        assert rules(deps, OPEN) == []
        assert rules(deps, deps) == []
        assert rules(deps, dict(OPEN, dependentRequired={"a": ["b", "c"]})) == ["dependent-required-added"]
        negated = dict(OPEN, **{"not": {"required": ["a"]}})
        assert rules(negated, OPEN) == []
        assert rules(negated, negated) == []

    def test_every_rule_has_a_case(self):
        assert set(RULES) == set(self.CASES) | {
            "ref-changed",
            "ref-sibling-conflict",
            "kind-removed",
            "kind-added",
        }  # the last two: TestMultiDocument

    def test_each_rule_fires_alone_with_its_breaking_flag(self):
        for rule, (old, new) in self.CASES.items():
            with self.subTest(rule=rule):
                found = changes(old, new)
                assert [rule] == [change.rule for change in found], found
                assert RULES[rule] is found[0].breaking  # a harmless pattern-property-added is False

    def test_identical_schemas_and_annotations_are_not_changes(self):
        base = obj({"a": dict(STR, minLength=1)}, ["a"])
        edited = json.loads(json.dumps(base))
        edited["title"] = "x"
        edited["description"] = "changed"
        edited["properties"]["a"]["description"] = "text"
        edited["properties"]["a"]["default"] = "d"
        edited["x-skm-layers"] = ["machine"]
        assert rules(base, base) == []
        assert rules(base, edited) == []

    def test_change_carries_path_and_message(self):
        found = changes(
            obj({"a": {"type": "array", "items": STR}}), obj({"a": {"type": "array", "items": INT}})
        )
        assert [Change("/properties/a/items", "type-changed", True, "type string is now integer")] == found

    def test_paths_escape_pointer_characters(self):
        found = changes(obj({"a/b": STR}), obj({"a/b": INT}))
        assert found[0].path == "/properties/a~1b"

    def test_property_removal_is_breaking_only_when_the_new_object_is_closed_and_does_not_cover_it(self):
        assert rules(obj({"a": STR}), dict(OPEN, properties={})) == []
        covered = obj({}, patternProperties={"^a": STR})
        assert rules(obj({"a": STR}), covered) == ["pattern-property-added"]

    def test_type_rules(self):
        assert rules({"type": "number"}, INT) == ["type-changed"]
        assert rules(INT, {"type": ["integer"]}) == []
        assert rules(INT, {"type": ["integer", "null"]}) == ["type-widened"]
        assert rules(STR, {}) == ["type-widened"]
        assert rules({}, STR) == ["type-changed"]
        assert rules({"type": ["string", "null"]}, STR) == ["type-changed"]

    def test_enum_values_compare_by_json_equality(self):
        assert rules({"enum": [1, "a"]}, {"enum": ["a", 1.0]}) == []
        assert rules({"enum": [1]}, {"enum": [True]}) == ["enum-narrowed", "enum-widened"]
        assert rules({"enum": ["a"]}, {}) == ["enum-widened"]
        assert rules({"enum": ["a", "b"]}, {"enum": ["b", "c"]}) == ["enum-narrowed", "enum-widened"]

    def test_bound_rules_for_every_keyword(self):
        for keyword, tight, loose in (
            ("minLength", 3, 1),
            ("minItems", 3, 1),
            ("minimum", 3, 1),
            ("maximum", 1, 3),
            ("maxLength", 1, 3),
            ("maxItems", 1, 3),
            ("minProperties", 3, 1),
            ("maxProperties", 1, 3),
        ):
            with self.subTest(keyword=keyword):
                assert rules({keyword: loose}, {keyword: tight}) == ["bound-tightened"]
                assert rules({keyword: tight}, {keyword: loose}) == ["bound-relaxed"]
                assert rules({}, {keyword: tight}) == ["bound-tightened"]
                assert rules({keyword: tight}, {}) == ["bound-relaxed"]

    def test_a_zero_minimum_length_or_item_count_is_no_bound(self):
        assert rules({}, {"minLength": 0, "minItems": 0}) == []

    def test_closing_an_object_and_opening_it(self):
        assert rules(CLOSED, OPEN) == []
        assert rules(CLOSED, CLOSED) == []
        assert rules(OPEN, CLOSED) == ["additional-closed"]

    def test_pattern_property_values_are_compared(self):
        old = {"patternProperties": {"^a": STR}}
        new = {"patternProperties": {"^a": INT}}
        assert rules(old, new) == ["type-changed"]
        assert rules(old, {"patternProperties": {"^b": STR}}) == [
            "pattern-property-added",
            "pattern-property-removed",
        ]
        graded = {c.rule: c.breaking for c in changes(old, {"patternProperties": {"^b": STR}})}
        assert graded["pattern-property-added"]  # the old object was open: ^b could meet any name

    def test_property_names_removed_or_equal_is_not_reported(self):
        names = {"propertyNames": {"pattern": "^a"}}
        assert rules(names, names) == []
        assert rules(names, {}) == []
        assert rules(names, {"propertyNames": {"pattern": "^b"}}) == ["property-names-changed"]

    def test_unique_items_dropped_is_not_reported(self):
        assert rules({"uniqueItems": True}, {"uniqueItems": False}) == []

    def test_added_const_and_changed_const(self):
        assert rules({}, {"const": "x"}) == ["const-changed"]
        assert rules({"const": "x"}, {"const": "x"}) == []
        assert rules({"const": "x"}, {}) == []

    def test_items_added_or_removed(self):
        assert rules({"type": "array"}, {"type": "array", "items": STR}) == ["type-changed"]
        assert rules({"type": "array", "items": STR}, {"type": "array"}) == ["type-widened"]

    def test_oneof_marks_a_changed_branch_once_and_hides_its_detail(self):
        old = {"oneOf": [obj({"a": STR}), obj({"b": STR})]}
        new = {"oneOf": [obj({"a": STR}), obj({"b": INT})]}
        found = changes(old, new)
        assert [(c.path, c.rule) for c in found] == [("/oneOf/1", "oneof-changed")]
        assert "type-changed" in found[0].message
        assert rules(old, old) == []
        assert rules({}, {"oneOf": [STR]}) == ["oneof-changed"]

    def test_oneof_branch_that_widened_and_shares_no_document_reports_its_own_changes(self):
        # branch 0 is closed and lacks "loaded", which branch 1 requires: no document matches both
        old = {"oneOf": [obj({"id": STR}, ["id"]), obj({"ref": STR, "loaded": BOOL}, ["ref", "loaded"])]}
        new = {"oneOf": [obj({"id": STR, "origin": STR}, ["id"]), old["oneOf"][1]]}
        found = changes(old, new)
        assert [(c.path, c.rule, c.breaking) for c in found] == [
            ("/oneOf/0/properties/origin", "property-added", False)
        ]

    def test_oneof_branch_that_widened_but_may_overlap_stays_oneof_changed(self):
        # branch 1 is open: {"id": "x", "origin": "y"} matched branch 1 only and now matches both
        old = {
            "oneOf": [
                obj({"id": STR}, ["id"]),
                {"type": "object", "properties": {"id": STR}, "required": ["id"]},
            ]
        }
        new = {"oneOf": [obj({"id": STR, "origin": STR}, ["id"]), old["oneOf"][1]]}
        assert [(c.path, c.rule) for c in changes(old, new)] == [("/oneOf/0", "oneof-changed")]

    def test_required_fields_prove_disjointness_from_bounded_empty_object(self):
        phase = obj({"id": STR}, ["id"])
        old = {"oneOf": [phase, {"type": "object", "maxProperties": 0}]}
        new = {"oneOf": [obj({"id": STR, "readiness": STR}, ["id"]), old["oneOf"][1]]}
        assert rules(old, new) == ["property-added"]
        # At the boundary the formerly unique {id, readiness} may now match both branches.
        for limit in (1, 2):
            before = {"oneOf": [phase, {"type": "object", "maxProperties": limit}]}
            after = {"oneOf": [new["oneOf"][0], before["oneOf"][1]]}
            assert rules(before, after) == ["oneof-changed"]

    def test_oneof_discriminator_and_types_prove_branches_apart(self):
        kind = {"kind": {"const": "a"}, "x": STR}
        old = {
            "oneOf": [
                {"type": "object", "properties": kind, "required": ["kind"]},
                {"type": "object", "properties": {"kind": {"enum": ["b", "c"]}}, "required": ["kind"]},
            ]
        }
        new = {
            "oneOf": [
                {
                    "type": "object",
                    "properties": dict(kind, x={"type": ["string", "null"]}),
                    "required": ["kind"],
                },
                old["oneOf"][1],
            ]
        }
        assert rules(old, new) == ["type-widened"]
        assert rules(
            {"oneOf": [{"type": "string", "maxLength": 3}, INT]}, {"oneOf": [{"type": "string"}, INT]}
        ) == ["bound-relaxed"]
        assert rules(
            {"oneOf": [{"type": "number", "maximum": 3}, INT]}, {"oneOf": [{"type": "number"}, INT]}
        ) == ["oneof-changed"]

    def test_oneof_branch_with_a_ref_sibling_conflict_proves_nothing(self):
        # A closed target {id, x} with sibling properties {note} would seem to forbid "id" after merging.
        # yet {"id": "v"} matched branch 0 only and, once the target stops requiring x, matches both
        body = {"oneOf": [obj({"id": STR}, ["id"]), {"$ref": f"{URN}target:v1", "properties": {"note": STR}}]}
        old, old_id = registry(doc(body), doc(obj({"id": STR, "x": STR}, ["id", "x"]), "target"))
        new, new_id = registry(doc(body), doc(obj({"id": STR, "x": STR}, ["id"]), "target"))
        found = compare(old, old_id, new, new_id)
        assert ("/oneOf/1", "oneof-changed") in [(c.path, c.rule) for c in found]

    def test_nested_changes_are_found_at_depth(self):
        old = obj({"a": obj({"b": {"type": "array", "items": obj({"c": STR}, ["c"])}})})
        new = obj({"a": obj({"b": {"type": "array", "items": obj({"c": STR}, [])}})})
        found = changes(old, new)
        assert [(c.path, c.rule) for c in found] == [("/properties/a/properties/b/items", "required-removed")]


class TestPatternPropertySoundness(unittest.TestCase):
    """A document valid by the old schema must stay valid when no breaking change is reported."""

    def breaking(self, old, new):
        return [c.rule for c in changes(old, new) if c.breaking]

    def test_a_pattern_that_also_matches_a_kept_property_is_breaking(self):
        old = obj({"id": STR})
        new = obj({"id": STR}, patternProperties={"^[a-z]+$": INT})
        assert self.breaking(old, new) == ["pattern-property-added"]

    def test_a_removed_property_covered_by_a_narrower_pattern_is_breaking(self):
        old = obj({"a": STR})
        new = obj({}, patternProperties={"^a$": INT})
        assert "type-changed" in self.breaking(old, new)

    def test_a_removed_property_covered_by_an_equal_pattern_is_compatible(self):
        old = obj({"a": STR})
        new = obj({}, patternProperties={"^a": STR})
        assert self.breaking(old, new) == []

    def test_a_pattern_added_to_an_open_object_is_breaking(self):
        assert self.breaking(OPEN, {"type": "object", "patternProperties": {"^ab": {"minLength": 5}}}) == [
            "pattern-property-added"
        ]

    def test_a_pattern_added_to_a_closed_object_with_other_names_is_compatible(self):
        assert self.breaking(obj({"a": STR}), obj({"a": STR}, patternProperties={"^z": STR})) == []

    def test_a_pattern_added_next_to_an_old_pattern_is_breaking(self):
        old = obj({}, patternProperties={"^a": STR})
        assert self.breaking(old, obj({}, patternProperties={"^a": STR, "^ab": INT})) == [
            "pattern-property-added"
        ]

    def test_a_property_added_under_an_old_pattern_is_compared_with_it(self):
        old = obj({}, patternProperties={"^a": STR})
        assert self.breaking(old, obj({"ab": INT}, patternProperties={"^a": STR})) == ["type-changed"]
        assert self.breaking(old, obj({"ab": STR}, patternProperties={"^a": STR})) == []


class TestRefSiblings(unittest.TestCase):
    def compare(self, old_defs, old_root, new_defs, new_root):
        old, old_id = registry(doc(dict(old_root, **{"$defs": old_defs})))
        new, new_id = registry(doc(dict(new_root, **{"$defs": new_defs})))
        return compare(old, old_id, new, new_id)

    def test_a_tightened_sibling_on_a_later_use_of_the_same_target_is_found(self):
        defs = {"s": STR}
        old_root = obj({"x": {"$ref": "#/$defs/s"}, "y": {"$ref": "#/$defs/s", "minLength": 1}})
        new_root = obj({"x": {"$ref": "#/$defs/s"}, "y": {"$ref": "#/$defs/s", "minLength": 5}})
        found = self.compare(defs, old_root, defs, new_root)
        assert [(c.path, c.rule, c.breaking) for c in found] == [("/properties/y", "bound-tightened", True)]

    def test_a_looser_sibling_does_not_relax_a_stricter_target(self):
        old = {"s": dict(STR, minLength=5)}
        new = {"s": dict(STR, minLength=100)}
        root = {"$ref": "#/$defs/s"}
        sibling = {"$ref": "#/$defs/s", "minLength": 0}
        found = self.compare(old, root, new, sibling)
        assert [c.rule for c in found] == ["bound-tightened"]
        assert found[0].breaking

    def test_siblings_that_cannot_be_merged_are_reported(self):
        old = {"s": {"type": "string", "pattern": "^a"}}
        new = {"s": {"type": "string", "pattern": "^a"}}
        found = self.compare(old, {"$ref": "#/$defs/s"}, new, {"$ref": "#/$defs/s", "pattern": "^b"})
        rules_found = sorted(c.rule for c in found)
        assert "ref-sibling-conflict" in rules_found
        assert all(c.breaking for c in found if c.rule == "ref-sibling-conflict")

    def test_a_conflict_present_in_both_versions_still_reports_a_changed_target(self):
        """The sibling keyword replaces nothing: target and sibling both apply, so a tighter target breaks."""
        sibling = {"$ref": "#/$defs/s", "properties": {"a": STR}}
        old = {"s": {"type": "object", "properties": {"a": dict(STR, minLength=1)}}}
        new = {"s": {"type": "object", "properties": {"a": dict(STR, minLength=5)}}}
        found = self.compare(old, sibling, new, sibling)
        assert [c.rule for c in found] == ["ref-sibling-conflict"]
        assert found[0].breaking
        assert self.compare(old, sibling, old, sibling) == []

    def test_an_empty_type_intersection_is_a_conflict_not_a_fallback(self):
        sibling = {"$ref": "#/$defs/s", "type": "integer"}
        old = {"s": {"type": ["string", "integer"]}}
        new = {"s": {"type": "string"}}
        found = self.compare(old, sibling, new, sibling)
        assert "ref-sibling-conflict" in [c.rule for c in found if c.breaking]

    def test_required_and_type_next_to_a_ref_are_merged(self):
        defs = {"s": obj({"a": STR, "b": STR}, ["a"])}
        found = self.compare(defs, {"$ref": "#/$defs/s"}, defs, {"$ref": "#/$defs/s", "required": ["b"]})
        assert [c.rule for c in found] == ["required-added"]


class TestRefs(unittest.TestCase):
    def test_refs_resolve_in_both_registries(self):
        old, old_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": obj({"a": STR}, ["a"])}}))
        new, new_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": obj({"a": STR}, [])}}))
        assert [c.rule for c in compare(old, old_id, new, new_id)] == ["required-removed"]

    def test_a_recursive_schema_terminates_and_reports_the_change_once(self):
        def tree(child_type):
            return doc(
                {
                    "$ref": "#/$defs/node",
                    "$defs": {
                        "node": obj(
                            {
                                "value": {"type": child_type},
                                "left": {"$ref": "#/$defs/node"},
                                "right": {"$ref": "#/$defs/node"},
                            }
                        )
                    },
                }
            )

        old, old_id = registry(tree("string"))
        new, new_id = registry(tree("integer"))
        found = compare(old, old_id, new, new_id)
        assert [c.rule for c in found] == ["type-changed"]
        assert compare(old, old_id, old, old_id) == []

    def test_a_ref_that_points_at_itself_is_an_error(self):
        loop = doc({"$ref": "#/$defs/a", "$defs": {"a": {"$ref": "#/$defs/a"}}})
        old, old_id = registry(loop)
        with pytest.raises(RefError, match="refers to itself"):
            compare(old, old_id, old, old_id)

    def test_an_unresolvable_ref_is_an_error(self):
        old, old_id = registry(doc({"$ref": "urn:skm:missing:x:v1"}))
        with pytest.raises(RefError):
            compare(old, old_id, old, old_id)

    def test_a_ref_to_another_document_is_followed_and_a_moved_target_is_informational(self):
        shared_a = doc({"$defs": {"x": STR}}, "a")
        shared_b = doc({"$defs": {"x": STR}}, "b")
        old, old_id = registry(doc({"$ref": f"{URN}a:v1#/$defs/x"}), shared_a)
        new, new_id = registry(doc({"$ref": f"{URN}b:v1#/$defs/x"}), shared_b)
        found = compare(old, old_id, new, new_id)
        assert [(c.path, c.rule, c.breaking) for c in found] == [("", "ref-changed", False)]
        changed, changed_id = registry(doc({"$ref": f"{URN}b:v1#/$defs/x"}), doc({"$defs": {"x": INT}}, "b"))
        assert sorted(c.rule for c in compare(old, old_id, changed, changed_id)) == [
            "ref-changed",
            "type-changed",
        ]

    def test_a_ref_on_one_side_only_compares_the_resolved_body(self):
        old, old_id = registry(doc(obj({"a": STR})))
        new, new_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": obj({"a": INT})}}))
        assert [c.rule for c in compare(old, old_id, new, new_id)] == ["type-changed"]

    def test_keywords_next_to_a_ref_win(self):
        old, old_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": {"minLength": 1}}}))
        new, new_id = registry(doc({"$ref": "#/$defs/x", "minLength": 4, "$defs": {"x": {"minLength": 1}}}))
        assert [c.rule for c in compare(old, old_id, new, new_id)] == ["bound-tightened"]


ROOT = Path(__file__).resolve().parents[3]
COMMAND = "urn:skm:demo:command:add-item:v1"
COMMAND_PATH = Path("src/skm/schemas/demo/commands/add-item.v1.json")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def scaffold(tmp_path):
    write_json(
        tmp_path / COMMAND_PATH,
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": COMMAND,
            "type": "object",
            "additionalProperties": False,
            "required": ["id"],
            "properties": {"id": {"type": "string", "format": "uuid"}},
            "x-skm-codegen": {
                "python": {
                    "module": "skm.modules.demo.generated.commands",
                    "class": "AddItem",
                    "kind": "dataclass",
                }
            },
        },
    )
    for relative in (gen.error_catalog.CATALOG_RELPATH, gen.error_catalog.SCHEMA_RELPATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="2.0.0.dev0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    gen.generate(tmp_path)
    assert checker.check(tmp_path, update_lock=True)["ok"]
    return tmp_path


def test_normalization_preserves_wire_names_and_literal_data():
    source = {
        "title": "annotation",
        "x-skm-codegen": {},
        "properties": {
            "description": {"description": "annotation", "type": "string"},
            "default": {"enum": [{"description": "literal", "x-skm": 1}]},
            "x-skm-data": {"const": {"title": "literal"}},
        },
        "required": ["description", "default"],
    }
    result = checker.normalize(source)
    assert "title" not in result
    assert "x-skm-codegen" not in result
    assert result["properties"]["description"] == STR
    assert result["properties"]["default"]["enum"] == [{"description": "literal", "x-skm": 1}]
    assert result["properties"]["x-skm-data"]["const"] == {"title": "literal"}
    assert "description" in source["properties"]["description"]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("command:add-item", "input"),
        ("query:get-item", "input"),
        ("settings:some-key", "input"),
        ("specification", "input"),
        ("defs", "both"),
        ("result:add-item", "output"),
        ("view:item", "output"),
        ("event:item-added", "output"),
        ("host-result:add-item", "output"),
        ("host:add-item", "input"),
        ("query:get-event", "input"),
        ("tool-output:some-tool", "output"),
    ],
)
def test_direction_uses_canonical_kind(kind, expected):
    assert checker.direction(f"urn:skm:demo:{kind}:v1") == expected


def test_extensions_and_open_outputs_allow_new_data():
    before = obj({"extensions": OPEN})
    after = obj({"extensions": {"type": "object", "properties": {"extra": STR}}})
    assert not any(c.breaking for c in compare(*registry(doc(before)), *registry(doc(after)), "output"))
    assert any(c.breaking for c in changes(OPEN, obj({})))
    assert not any(
        c.breaking
        for c in compare(*registry(doc(OPEN)), *registry(doc({**OPEN, "properties": {"x": STR}})), "output")
    )


@pytest.mark.parametrize(
    ("before", "after", "breaking"),
    [(False, True, False), (True, False, True), (True, STR, True), (False, STR, False), (STR, True, False)],
)
def test_boolean_subschemas(before, after, breaking):
    found = changes(obj({"x": before}), obj({"x": after}))
    assert any(c.breaking for c in found) is breaking


def test_nested_resources_keep_their_own_bases():
    def document(value):
        return doc(
            {
                "$defs": {
                    "local": STR,
                    "nested": {
                        "$id": "urn:skm:compat:nested:v1",
                        "$defs": {"local": {"type": value}},
                        "type": "object",
                        "properties": {"x": {"$ref": "#/$defs/local"}},
                    },
                },
                "properties": {"nested": {"$ref": "urn:skm:compat:nested:v1"}},
            }
        )

    found = compare(*registry(document("string")), *registry(document("integer")))
    assert [(c.path, c.rule) for c in found if c.breaking] == [
        ("/properties/nested/properties/x", "type-changed")
    ]


@pytest.mark.parametrize("ref", ["https://example.test/schema.json", "file:///tmp/schema.json"])
def test_network_and_file_refs_are_refused(ref):
    with pytest.raises(RefError, match="must be local"):
        registry(doc({"$ref": ref}))


def test_lock_round_trip_is_deterministic_and_contains_snapshots(scaffold):
    lock_path = scaffold / checker.LOCK_PATH
    original, timestamp = lock_path.read_bytes(), lock_path.stat().st_mtime_ns
    lock = checker.read_lock(scaffold)
    assert lock is not None
    assert lock["schema"] == checker.LOCK_URN
    assert lock["digest"] == checker.schema_digest({u: e["snapshot"] for u, e in lock["entries"].items()})
    assert list(lock["entries"]) == sorted(lock["entries"])
    entry = lock["entries"][COMMAND]
    assert entry["path"] == "demo/commands/add-item.v1.json"
    assert entry["direction"] == "input"
    assert entry["digest"] == checker.schema_digest(entry["snapshot"])
    assert "x-skm-codegen" not in entry["snapshot"]
    assert checker.check(scaffold)["ok"]
    assert checker.check(scaffold, update_lock=True)["ok"]
    assert lock_path.read_bytes() == original
    assert lock_path.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize(
    "relative",
    [
        "src/skm/modules/demo/generated/commands.py",
        "src/skm/kernel/generated/error_codes.py",
        "docs/reference/config.md",
        "docs/reference/errors.md",
        "docs/reference/events.md",
        "web/src/api/generated/kernel.ts",
    ],
)
def test_generated_drift_fails_without_writing_or_updating_lock(scaffold, relative):
    path = scaffold / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n# manual drift\n", encoding="utf-8")
    before, lock = path.read_bytes(), (scaffold / checker.LOCK_PATH).read_bytes()
    for update in (False, True):
        report = checker.check(scaffold, update_lock=update)
        assert not report["ok"]
        assert f"GEN_STALE {relative}" in report["errors"]
        assert path.read_bytes() == before
        assert (scaffold / checker.LOCK_PATH).read_bytes() == lock


def test_missing_generated_file_is_stale(scaffold):
    path = Path("docs/reference/config.md")
    (scaffold / path).unlink()
    assert f"GEN_STALE {path}" in checker.check(scaffold)["errors"]
    assert not (scaffold / path).exists()


def test_optional_input_requires_regeneration_then_can_update_lock(scaffold):
    path = scaffold / COMMAND_PATH
    document = json.loads(path.read_text())
    document["properties"]["note"] = STR
    write_json(path, document)
    assert any(e.startswith("GEN_STALE") for e in checker.check(scaffold)["errors"])
    gen.generate(scaffold)
    report = checker.check(scaffold)
    assert any(e.startswith("LOCK_STALE") for e in report["errors"])
    assert not any(c["breaking"] for c in report["changes"])
    assert checker.check(scaffold, update_lock=True)["ok"]
    assert checker.check(scaffold)["ok"]


@pytest.mark.parametrize("kind", ["result", "view", "event", "defs"])
def test_optional_output_addition_and_shared_defs_are_breaking(scaffold, kind):
    urn = f"urn:skm:demo:{kind}:item:v1" if kind != "defs" else "urn:skm:demo:defs:v1"
    path = scaffold / f"src/skm/schemas/demo/{kind}.v1.json"
    document = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": urn, **obj({"x": STR})}
    write_json(path, document)
    gen.generate(scaffold)
    assert checker.check(scaffold, update_lock=True)["ok"]
    original = (scaffold / checker.LOCK_PATH).read_bytes()
    document["properties"]["optional"] = STR
    write_json(path, document)
    gen.generate(scaffold)
    report = checker.check(scaffold, update_lock=True)
    assert not report["ok"]
    assert any(c["urn"] == urn and c["breaking"] for c in report["changes"])
    assert (scaffold / checker.LOCK_PATH).read_bytes() == original


def test_required_input_rejected_and_new_major_allowed(scaffold):
    path = scaffold / COMMAND_PATH
    document = json.loads(path.read_text())
    new_major = copy.deepcopy(document)
    new_major["$id"] = COMMAND.replace(":v1", ":v2")
    new_major.pop("x-skm-codegen")
    write_json(path.with_name("add-item.v2.json"), new_major)
    gen.generate(scaffold)
    assert checker.check(scaffold, update_lock=True)["ok"]
    document["properties"]["note"] = STR
    document["required"].append("note")
    write_json(path, document)
    gen.generate(scaffold)
    report = checker.check(scaffold, update_lock=True)
    assert not report["ok"]
    assert any(c["rule"] == "required-added" and c["breaking"] for c in report["changes"])


def test_schema_removal_is_breaking_and_addition_is_not():
    before = {COMMAND: {"snapshot": doc(STR)}}
    assert checker.compatibility(before, {})[0]["breaking"]
    assert not checker.compatibility({}, before)[0]["breaking"]


@pytest.mark.parametrize("version", ["2.0.0", "2.0.1.dev0", "3.0.0", "invalid"])
def test_allow_breaking_refused_at_or_after_release(scaffold, version):
    (scaffold / "pyproject.toml").write_text(f'[project]\nversion="{version}"\n')
    (scaffold / "CHANGELOG.md").write_text("## [Unreleased]\n- BREAKING: explained\n")
    with pytest.raises(ValueError, match="ALLOW_BREAKING_REFUSED"):
        checker.breaking_permission(scaffold)


@pytest.mark.parametrize(
    "changelog",
    [
        "## [Unreleased]\n- BREAKING:\n",
        "## [Unreleased]\n\n## 1.0.0\n- BREAKING: old release\n",
        "## 1.0.0\n- BREAKING: historical\n",
    ],
)
def test_allow_breaking_requires_explanation_in_unreleased(scaffold, changelog):
    (scaffold / "CHANGELOG.md").write_text(changelog)
    with pytest.raises(ValueError, match="explain BREAKING"):
        checker.breaking_permission(scaffold)


def test_allow_breaking_is_explicit_and_still_checks_freshness(scaffold):
    path = scaffold / COMMAND_PATH
    document = json.loads(path.read_text())
    document["properties"]["id"] = INT
    write_json(path, document)
    (scaffold / "CHANGELOG.md").write_text(
        "## 2.0.0.dev0 — Unreleased\n- BREAKING: change id representation before release\n"
    )
    with pytest.raises(ValueError, match="requires --update-lock"):
        checker.check(scaffold, allow_breaking=True)
    assert not checker.check(scaffold, update_lock=True, allow_breaking=True)["ok"]
    gen.generate(scaffold)
    assert checker.check(scaffold, update_lock=True, allow_breaking=True)["ok"]
    assert checker.check(scaffold)["ok"]


def test_json_cli_reports_failure_without_traceback(scaffold, capsys):
    (scaffold / checker.LOCK_PATH).write_text("invalid json")
    assert checker.main(["--json"], root=scaffold) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["errors"]


def test_lock_rejects_tampered_digest_and_direction(scaffold):
    path = scaffold / checker.LOCK_PATH
    original = json.loads(path.read_text())
    for key, value in (("digest", "sha256:wrong"), ("direction", "output")):
        altered = copy.deepcopy(original)
        altered["entries"][COMMAND][key] = value
        write_json(path, altered)
        with pytest.raises(ValueError, match="LOCK_INVALID"):
            checker.read_lock(scaffold)


def test_docs_mode_and_check_share_identical_reference_outputs(scaffold):
    rendered = gen.outputs(scaffold, only="docs")
    assert set(rendered) == {Path(f"docs/reference/{name}.md") for name in ("config", "errors", "events")}
    assert all(text.startswith("<!-- generated by tools/gen.py") for text in rendered.values())
    assert gen.generate(scaffold, check=True, only="docs") == []
    path = scaffold / "docs/reference/errors.md"
    path.write_text("manual edit")
    assert gen.generate(scaffold, check=True, only="docs") == [Path("docs/reference/errors.md")]
    assert path.read_text() == "manual edit"


def test_reference_metadata_and_event_class_stream_kind(scaffold):
    settings = {
        "$id": "urn:skm:settings:demo:v1",
        "x-skm-section": {"id": "demo"},
        "properties": {
            "group": {
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "default": True,
                        "description": "enable | disable",
                        "x-skm": {
                            "chain": "work",
                            "levels": ["instance"],
                            "merge": "replace",
                            "reload": "live",
                            "override": True,
                            "sensitivity": "public",
                        },
                    }
                }
            }
        },
    }
    event = {"$id": "urn:skm:demo:event:item-added:v1", "title": "ItemAdded", **obj({"id": STR}, ["id"])}
    model = gen.load(scaffold / "src/skm/schemas")
    model.documents.update({settings["$id"]: settings, event["$id"]: event})
    path = scaffold / "src/skm/modules/demo/domain/events.py"
    path.parent.mkdir(parents=True)
    path.write_text('class ItemAdded:\n    stream_kind: str = "workspace"\n')
    rendered = gen.reference_outputs(scaffold, model)
    config = rendered[Path("docs/reference/config.md")]
    assert "demo.group.enabled | boolean | true | work" in config
    assert "enable \\| disable" in config
    assert "| workspace |" in rendered[Path("docs/reference/events.md")]
    assert "SCHEMA_INVALID" in rendered[Path("docs/reference/errors.md")]


def test_make_targets_are_real_and_schema_check_is_a_check_prerequisite():
    makefile = (ROOT / "Makefile").read_text()
    assert "schema-check" in next(line for line in makefile.splitlines() if line.startswith("check:"))
    assert "$(PY) tools/schema_check.py\n" in makefile
    assert "$(PY) tools/schema_check.py --update-lock" in makefile
    assert "skip: schema-check" not in makefile
    assert "skip: schema-lock" not in makefile


def test_exported_defs_are_compared_even_without_current_references():
    urn = "urn:skm:demo:defs:v1"

    def entry(value):
        return {urn: {"snapshot": {"$id": urn, "$defs": {"unused": value}}}}

    found = checker.compatibility(entry(STR), entry(INT))
    assert any(c["breaking"] and c["path"] == "/$defs/unused" for c in found)
    removed = {urn: {"snapshot": {"$id": urn, "$defs": {}}}}
    assert any(c["breaking"] for c in checker.compatibility(entry(STR), removed))
    assert not any(c["breaking"] for c in checker.compatibility(removed, entry(STR)))


def test_removed_property_is_checked_against_new_additional_schema():
    assert any(c.breaking for c in changes(obj({"a": STR}), {"type": "object", "additionalProperties": INT}))
    assert not any(
        c.breaking for c in changes(obj({"a": STR}), {"type": "object", "additionalProperties": STR})
    )


def test_header_drift_is_detected(scaffold):
    relative = Path("src/skm/modules/demo/generated/commands.py")
    path = scaffold / relative
    text = path.read_text()
    assert text.startswith("# generated by tools/gen.py from ")
    path.write_text(text.split("\n", 1)[1])
    assert f"GEN_STALE {relative}" in checker.check(scaffold)["errors"]


def test_catalog_emitter_is_still_the_only_errorcode_owner(scaffold):
    path = scaffold / gen.error_catalog.CATALOG_RELPATH
    catalog = json.loads(path.read_text())
    catalog["codes"][0]["description"] = "A changed description."
    write_json(path, catalog)
    gen.generate(scaffold, only="docs")
    errors = checker.check(scaffold)["errors"]
    assert "GEN_STALE src/skm/kernel/generated/error_codes.py" in errors
    gen.generate(scaffold, only="python")
    assert checker.check(scaffold)["ok"]


def test_missing_lock_is_reported_without_being_created(scaffold):
    path = scaffold / checker.LOCK_PATH
    path.unlink()
    assert any(e.startswith("LOCK_STALE") for e in checker.check(scaffold)["errors"])
    assert not path.exists()


def test_unchanged_refs_in_applicators_follow_changed_targets():
    for keyword in ("anyOf", "allOf", "prefixItems"):

        def body(value, keyword=keyword):
            return doc({"$defs": {"value": value}, keyword: [{"$ref": "#/$defs/value"}]})

        found = compare(*registry(body(STR)), *registry(body(INT)))
        assert any(c.breaking for c in found), keyword


def test_invalid_errorcode_is_reported_before_any_kernel_import(scaffold):
    path = scaffold / "src/skm/kernel/generated/error_codes.py"
    path.write_text("invalid Python !!!")
    script = """
import sys
from pathlib import Path
class RejectKernelImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'skm' or fullname.startswith('skm.'):
            raise AssertionError('ErrorCode must be checked before importing the kernel')
sys.meta_path.insert(0, RejectKernelImports())
from tools.schema_check import main
raise SystemExit(main(['--json'], root=Path(sys.argv[1])))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(scaffold)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert "GEN_STALE src/skm/kernel/generated/error_codes.py" in report["errors"]
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("urn", ["bad", "urn:skm:demo:defs:v0", "https://example.test/schema"])
def test_invalid_lock_urn_has_a_controlled_error(urn):
    with pytest.raises(ValueError, match="LOCK_INVALID"):
        checker.direction(urn)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({"oneOf": [False, STR]}, {"oneOf": [True, STR]}),
        ({"oneOf": [{"const": "a"}, {"const": "b"}]}, {"oneOf": [{}, {"const": "b"}]}),
    ],
)
def test_relaxing_oneof_branch_can_break_by_introducing_overlap(before, after):
    assert any(c.breaking for c in changes(before, after))


def test_const_removal_behind_unchanged_oneof_ref_is_checked_for_overlap():
    def body(first):
        return doc({"$defs": {"first": first}, "oneOf": [{"$ref": "#/$defs/first"}, {"const": "b"}]})

    found = compare(*registry(body({"const": "a"})), *registry(body({})))
    assert any(c.rule == "oneof-changed" and c.breaking for c in found)
    assert not any(c.breaking for c in changes({"oneOf": [False, STR]}, {"oneOf": [INT, STR]}))


SENSITIVE_CASES = (
    "not",
    "propertyNames",
    "contains_min",
    "contains_max",
    "contains_both",
    "if_then",
    "if_else",
    "if_general",
)


def sensitive_ref_case(case):
    """Each instance is accepted before the change and rejected afterwards."""
    before, after = ["a"], ["a", "b"]
    body: dict[str, Any] = {"type": "string"}
    instance: Any = "b"
    ref = {"$ref": "#/$defs/p"}
    if case == "not":
        body["not"] = ref
    elif case == "propertyNames":
        body, instance = {"type": "object", "propertyNames": ref}, {"b": 1}
        before, after = after, before
    elif case.startswith("contains"):
        body = {"type": "array", "contains": ref}
        if case == "contains_min":
            before, after = after, before
            instance = ["b"]
        elif case == "contains_max":
            body.update(minContains=0, maxContains=1)
            instance = ["b", "b"]
        else:
            body["maxContains"] = 1
            instance = ["a", "b"]
    elif case == "if_else":
        body.update({"if": ref, "else": False})
        before, after = after, before
    elif case == "if_then":
        body.update({"if": ref, "then": False})
    else:
        body.update({"if": ref, "then": {"enum": ["a"]}})
    return (
        doc({**body, "$defs": {"p": {"enum": before}}}),
        doc({**body, "$defs": {"p": {"enum": after}}}),
        instance,
    )


@pytest.mark.parametrize("case", SENSITIVE_CASES)
@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_sensitive_unchanged_refs_reject_breaking_changes(case, direction):
    from jsonschema import Draft202012Validator

    old, new, instance = sensitive_ref_case(case)
    assert Draft202012Validator(old).is_valid(instance)
    assert not Draft202012Validator(new).is_valid(instance)
    if direction == "output":
        old, new = new, old
    found = compare(*registry(old), *registry(new), direction)
    assert any(c.breaking for c in found), (case, direction, found)


@pytest.mark.parametrize("case", SENSITIVE_CASES)
@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_sensitive_ref_changes_cannot_update_lock(scaffold, case, direction):
    old, new, _ = sensitive_ref_case(case)
    if direction == "output":
        old, new = new, old
    kind = {"input": "command:constraint-probe", "output": "result:constraint-probe", "both": "defs"}[
        direction
    ]
    urn = f"urn:skm:demo:{kind}:v1"
    path = scaffold / "src/skm/schemas/demo/constraint-probe.v1.json"
    for document in (old, new):
        document.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": urn})
    write_json(path, old)
    gen.generate(scaffold)
    assert checker.check(scaffold, update_lock=True)["ok"]
    lock = scaffold / checker.LOCK_PATH
    contents, modified = lock.read_bytes(), lock.stat().st_mtime_ns
    write_json(path, new)
    gen.generate(scaffold)
    for update in (False, True):
        report = checker.check(scaffold, update_lock=update)
        assert not report["ok"]
        assert "SCHEMA_BREAKING use a new major + migration" in report["errors"]
        assert lock.read_bytes() == contents
        assert lock.stat().st_mtime_ns == modified


@pytest.mark.parametrize(
    "case", ["not", "propertyNames", "contains_min", "contains_max", "if_then", "if_else"]
)
def test_sensitive_ref_polarity_preserves_compatible_input_direction(case):
    old, new, _ = sensitive_ref_case(case)
    # Reverse a proven input narrowing: it is safe for input, but expands outputs.
    assert not any(c.breaking for c in compare(*registry(new), *registry(old), "input"))
    assert any(c.breaking for c in compare(*registry(new), *registry(old), "output"))
    assert any(c.breaking for c in compare(*registry(new), *registry(old), "both"))


@pytest.mark.parametrize("case", SENSITIVE_CASES)
@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_unchanged_sensitive_ref_graph_is_not_a_change(case, direction):
    old, _, _ = sensitive_ref_case(case)
    assert compare(*registry(old), *registry(copy.deepcopy(old)), direction) == []


@pytest.mark.parametrize("keyword", ["not", "propertyNames", "contains", "if"])
@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_consuming_recursive_sensitive_refs_terminate(keyword, direction):
    def recursive(values):
        predicate = {
            "type": "object",
            "properties": {"tag": {"enum": values}, "child": {"$ref": "#/$defs/p"}},
            "required": ["tag"],
        }
        body = {"type": "object", keyword: {"$ref": "#/$defs/p"}, "$defs": {"p": predicate}}
        if keyword == "propertyNames":
            # A recursive schema can also have object-only assertions while applied
            # to property-name strings. Those assertions must still terminate.
            predicate["type"] = "string"
            predicate["enum"] = values
            predicate.pop("required")
        elif keyword == "contains":
            body["type"] = "array"
        elif keyword == "if":
            body["then"] = False
        return doc(body)

    old, new = recursive(["a"]), recursive(["a", "b"])
    assert compare(*registry(old), *registry(copy.deepcopy(old)), direction) == []
    found = compare(*registry(old), *registry(new), direction)
    assert found
    assert len(found) <= 8
    assert any(c.breaking for c in compare(*registry(old), *registry(new), "both"))


@pytest.mark.parametrize("case", ["not", "propertyNames", "contains", "if", "if_general"])
@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_shared_ref_dedup_keeps_distinct_applicator_contexts(case, direction):
    from jsonschema import Draft202012Validator

    ref = {"$ref": "#/$defs/p"}
    special = {"not": ref}
    before, after = ["a"], ["a", "b"]
    value = "b"
    if case == "propertyNames":
        special, value = {"type": "object", "propertyNames": ref}, {"b": 1}
        before, after = after, before
    elif case == "contains":
        special, value = {"type": "array", "contains": ref, "minContains": 0, "maxContains": 0}, ["b"]
    elif case.startswith("if"):
        special = {"if": ref, "then": False if case == "if" else {"enum": ["a"]}}

    def body(values):
        return doc({**obj({"regular": ref, "constrained": special}), "$defs": {"p": {"enum": values}}})

    old, new = body(before), body(after)
    instance = {"regular": "a", "constrained": value}
    assert Draft202012Validator(old).is_valid(instance)
    assert not Draft202012Validator(new).is_valid(instance)
    if direction == "output":
        old, new = new, old
    found = compare(*registry(old), *registry(new), direction)
    assert any(c.breaking and c.path.startswith("/properties/constrained/") for c in found), found


@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_if_predicate_is_irrelevant_when_branches_are_identical(direction):
    old, new, _ = sensitive_ref_case("if_then")
    for body in (old, new):
        body["then"] = STR
        body["else"] = STR
    assert compare(*registry(old), *registry(new), direction) == []
    for body in (old, new):
        body.pop("then")
        body.pop("else")
    assert compare(*registry(old), *registry(new), direction) == []


@pytest.mark.parametrize(
    "old_then",
    [
        {"required": ["a", "b", "c"]},
        {"anyOf": [{"required": ["a", "b"]}, {"required": ["b", "c"]}]},
    ],
)
def test_weakening_conditional_required_alternatives_preserves_inputs(old_then):
    predicate = {"properties": {"verdict": {"const": "edit"}}}
    old = {**OPEN, "if": predicate, "then": old_then}
    new = {**old, "then": {"anyOf": [{"required": ["a"]}, {"required": ["b"]}, {"required": ["c"]}]}}
    assert directed(old, new, "input") == [("schema-widened", False)]
    assert directed(old, new, "output") == [("constraint-changed", True)]
    assert directed(old, new, "both") == [("constraint-changed", True), ("schema-widened", False)]


@pytest.mark.parametrize(
    "new_then",
    [
        {"anyOf": [{"required": ["a"]}, {"required": ["d"]}]},
        {"anyOf": [{"required": ["b"], "properties": {"b": {"const": "new"}}}]},
    ],
)
def test_conditional_widening_must_preserve_each_old_alternative(new_then):
    from jsonschema import Draft202012Validator

    old = {**OPEN, "if": True, "then": {"anyOf": [{"required": ["a"]}, {"required": ["b", "c"]}]}}
    new = {**old, "then": new_then}
    instance = {"b": "old", "c": True}
    assert Draft202012Validator(old).is_valid(instance)
    assert not Draft202012Validator(new).is_valid(instance)
    assert directed(old, new, "input") == [("constraint-changed", True)]


@pytest.mark.parametrize("referenced", [False, True])
def test_weaker_then_can_break_inputs_when_the_predicate_changes(referenced):
    from jsonschema import Draft202012Validator

    def schema(predicate, then):
        if referenced:
            return doc(
                {**OPEN, "$defs": {"predicate": predicate}, "if": {"$ref": "#/$defs/predicate"}, "then": then}
            )
        return doc({**OPEN, "if": predicate, "then": then})

    old = schema({"required": ["flag"]}, {"required": ["a", "b"]})
    new = schema(True, {"anyOf": [{"required": ["a"]}, {"required": ["b"]}]})
    assert Draft202012Validator(old).is_valid({})
    assert not Draft202012Validator(new).is_valid({})
    assert any(change.breaking for change in compare(*registry(old), *registry(new)))


def test_widening_proof_requires_if_and_then_in_the_same_schema():
    from jsonschema import Draft202012Validator

    old = doc({"$defs": {"branch": {"then": {"required": ["a", "b"]}}}, "$ref": "#/$defs/branch", "if": True})
    new = doc(
        {"$defs": {"branch": {"if": True, "then": {"required": ["a"]}}}, "$ref": "#/$defs/branch", "if": True}
    )
    assert Draft202012Validator(old).is_valid({})
    assert not Draft202012Validator(new).is_valid({})
    assert any(change.breaking for change in compare(*registry(old), *registry(new)))


@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_contains_with_zero_minimum_and_no_upper_bound_ignores_predicate_changes(direction):
    old, new, _ = sensitive_ref_case("contains_min")
    for body in (old, new):
        body["minContains"] = 0
    assert compare(*registry(old), *registry(new), direction) == []


def test_removing_zero_min_contains_restores_the_default_minimum():
    from jsonschema import Draft202012Validator

    old, new, _ = sensitive_ref_case("contains_min")
    new = copy.deepcopy(old)
    old["minContains"] = 0
    assert Draft202012Validator(old).is_valid([])
    assert not Draft202012Validator(new).is_valid([])
    assert any(c.rule == "bound-tightened" and c.breaking for c in compare(*registry(old), *registry(new)))
    assert not any(c.breaking for c in compare(*registry(new), *registry(old)))


def test_recursive_negation_distinguishes_both_polarities():
    def recursive(values):
        return doc(
            {
                "not": {"$ref": "#/$defs/p"},
                "$defs": {
                    "p": {
                        "type": "object",
                        "properties": {"tag": {"enum": values}, "child": {"not": {"$ref": "#/$defs/p"}}},
                    }
                },
            }
        )

    old, new = recursive(["a"]), recursive(["a", "b"])
    assert compare(*registry(old), *registry(copy.deepcopy(old))) == []
    found = compare(*registry(old), *registry(new))
    assert any(c.breaking for c in found)
    assert len(found) <= 8


@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_introducing_if_activates_even_identical_previously_ignored_branches(direction):
    from jsonschema import Draft202012Validator

    old = doc({"$defs": {"p": {"enum": ["a"]}}, "then": False, "else": False})
    new = {**old, "if": {"$ref": "#/$defs/p"}}
    assert Draft202012Validator(old).is_valid("b")
    assert not Draft202012Validator(new).is_valid("b")
    if direction == "output":
        old, new = new, old
    assert any(c.breaking for c in compare(*registry(old), *registry(new), direction))


@pytest.mark.parametrize("direction", ["input", "output", "both"])
def test_introducing_bare_if_without_branches_adds_no_constraint(direction):
    old = doc({"$defs": {"p": {"enum": ["a"]}}})
    new = {**old, "if": {"$ref": "#/$defs/p"}}
    assert compare(*registry(old), *registry(new), direction) == []


# Wider than the default int-to-text limit (4300 digits): json.loads and json.dumps refuse these literals.
WIDE = 10**5000 - 1
WIDE_TEXT = "9" * 5000
NEGATIVE = -(10**4999)
NEGATIVE_TEXT = "-1" + "0" * 4999
WIDE_SCHEMA = "urn:skm:demo:command:wide:v1"
MARKER_TEXT = "skm-wide-int-0-0"  # the first marker the writer tries; a schema string must survive it


@pytest.fixture
def wide_scaffold(tmp_path):
    path = tmp_path / "src/skm/schemas/demo/commands/wide.v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "' + WIDE_SCHEMA + '",'
        ' "type": "object", "properties": {'
        f' "n": {{"type": "integer", "maximum": {WIDE_TEXT}, "minimum": {NEGATIVE_TEXT}}},'
        f' "k": {{"enum": [{WIDE_TEXT}, 1]}}, "s": {{"const": "{MARKER_TEXT}"}}}}}}\n',
        encoding="utf-8",
    )
    for relative in (gen.error_catalog.CATALOG_RELPATH, gen.error_catalog.SCHEMA_RELPATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    gen.generate(tmp_path)
    return tmp_path


def test_wide_integer_literals_reach_the_lock_with_exact_digits(wide_scaffold):
    snapshot = checker.entries(wide_scaffold)[WIDE_SCHEMA]["snapshot"]
    assert snapshot["properties"]["n"] == {"type": "integer", "maximum": WIDE, "minimum": NEGATIVE}
    assert snapshot["properties"]["k"]["enum"] == [WIDE, 1]
    assert checker.check(wide_scaffold, update_lock=True)["ok"]
    lock_path = wide_scaffold / checker.LOCK_PATH
    text = lock_path.read_text(encoding="utf-8")
    assert f'"maximum": {WIDE_TEXT},' in text
    assert f'"minimum": {NEGATIVE_TEXT}' in text
    assert text.count("skm-wide-int-") == 1  # only the schema's own string
    lock = checker.read_lock(wide_scaffold)
    assert lock is not None
    assert lock["entries"][WIDE_SCHEMA]["snapshot"] == snapshot
    assert lock["entries"][WIDE_SCHEMA]["path"] == "demo/commands/wide.v1.json"
    original, timestamp = lock_path.read_bytes(), lock_path.stat().st_mtime_ns
    report = checker.check(wide_scaffold)
    assert report["ok"]
    assert report["lock_stale"] is False
    assert checker.check(wide_scaffold, update_lock=True)["ok"]
    assert lock_path.read_bytes() == original
    assert lock_path.stat().st_mtime_ns == timestamp


def test_wide_integer_snapshot_change_is_compared_against_the_lock(wide_scaffold):
    assert checker.check(wide_scaffold, update_lock=True)["ok"]
    path = wide_scaffold / "src/skm/schemas/demo/commands/wide.v1.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace(WIDE_TEXT, WIDE_TEXT[:-1] + "8", 1), encoding="utf-8"
    )
    report = checker.check(wide_scaffold)
    assert not report["ok"]
    assert [(c["path"], c["rule"], c["message"]) for c in report["changes"]] == [
        ("/properties/n", "bound-tightened", f"maximum is now {WIDE_TEXT[:-1]}8 (was {WIDE_TEXT})")
    ]


def test_canonical_text_of_wide_integers_is_exact_and_keeps_marker_like_strings():
    value = {"b": [WIDE, MARKER_TEXT], "a": NEGATIVE, "c": {"d": 1, "e": True}}
    expected = f'{{"a":{NEGATIVE_TEXT},"b":[{WIDE_TEXT},"{MARKER_TEXT}"],"c":{{"d":1,"e":true}}}}'
    assert checker.canonical(value) == expected
    assert checker.schema_digest(value) == "sha256:" + hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert checker._loads(expected) == value


def test_lock_writer_keeps_the_bytes_of_the_repository_lock():
    text = (ROOT / checker.LOCK_PATH).read_text(encoding="utf-8")
    assert checker._dumps(checker._loads(text), ensure_ascii=False, indent=2) + "\n" == text
    assert checker.read_lock(ROOT) is not None


@pytest.mark.parametrize(
    "number",
    [0, 7, -7, 10**512 - 1, 10**512, -(10**512), 10**640 - 1, 10**640, 10**1024 + 1, WIDE, NEGATIVE],
    ids=lambda number: f"{'-' if number < 0 else ''}{abs(number).bit_length()}bits",
)
def test_integer_text_round_trips_at_any_width(number):
    text = checker._digits(number)
    assert checker._loads(text) == number
    assert text == "0" or not text.removeprefix("-").startswith("0")
    if -(10**640) < number < 10**640:
        assert text == str(number)


def test_wide_integer_messages_and_ref_siblings_compare_without_text_limits():
    assert [c.message for c in changes(obj({"n": {"maximum": WIDE}}), obj({"n": {"maximum": WIDE - 1}}))] == [
        f"maximum is now {WIDE_TEXT[:-1]}8 (was {WIDE_TEXT})"
    ]
    assert [c.message for c in changes({"enum": [WIDE, 1]}, {"enum": [1]})] == [f"enum lost [{WIDE_TEXT}]"]
    assert [c.message for c in changes({"const": 1}, {"const": NEGATIVE})] == [
        f"const is now {NEGATIVE_TEXT}"
    ]
    ref = {"$defs": {"t": {"type": "integer"}}, "$ref": "#/$defs/t"}
    assert rules({**ref, "maximum": WIDE}, {**ref, "maximum": WIDE - 1}) == ["bound-tightened"]


@contextmanager
def int_text_limit(limit):
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(before)


def write_lock(root, snapshot):
    """A lock of one snapshot with correct digests, written compactly (``indent`` takes the recursive
    pure-Python encoder, which bounds the nesting of the repository writer before and after)."""
    urn = snapshot["$id"]
    entry = {
        "path": "demo/x.v1.json",
        "direction": checker.direction(urn),
        "digest": checker.schema_digest(snapshot),
        "snapshot": snapshot,
    }
    document = {
        "schema": checker.LOCK_URN,
        "digest": checker.schema_digest({urn: snapshot}),
        "updated_at": "2026-01-01T00:00:00Z",
        "entries": {urn: entry},
    }
    path = root / checker.LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(checker._dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# json.dumps and json.loads (C) take this nesting; Python recursion at the default limit of 1000 does not.
DEPTH = 1100


def nested(leaf):
    for _ in range(DEPTH):
        leaf = [leaf]
    return leaf


@pytest.mark.parametrize(("leaf", "leaf_text"), [(0, "0"), (WIDE, WIDE_TEXT)], ids=["normal", "wide"])
def test_deep_nesting_is_written_and_read_as_json_writes_and_reads_it(leaf, leaf_text, tmp_path):
    expected = "[" * DEPTH + leaf_text + "]" * DEPTH
    assert checker.canonical(nested(leaf)) == expected
    snapshot = {"$id": WIDE_SCHEMA, "const": nested(leaf)}
    path = write_lock(tmp_path, snapshot)
    lock = checker.read_lock(tmp_path)
    assert lock is not None
    assert checker.canonical(lock["entries"][WIDE_SCHEMA]["snapshot"]["const"]) == expected
    # the nesting does not hide a digest mismatch
    path.write_text(path.read_text(encoding="utf-8").replace('"const"', '"enum"'), encoding="utf-8")
    with pytest.raises(ValueError, match=f"LOCK_INVALID {WIDE_SCHEMA}: direction or snapshot digest"):
        checker.read_lock(tmp_path)


def test_writer_refuses_a_circular_value_like_json_dumps():
    value: list[Any] = [WIDE]
    value.append({"self": value})
    with pytest.raises(ValueError, match="Circular reference"):
        checker.canonical(value)


def counting_dumps(monkeypatch):
    calls = []
    original = json.dumps

    def dumps(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(checker.json, "dumps", dumps)
    return calls


@pytest.mark.parametrize("where", ["values", "keys"])
def test_marker_collisions_cost_a_bounded_number_of_writes(where, monkeypatch):
    taken = [f"skm-wide-int-{n}-0" for n in range(1024)]
    taken += ['a"skm-wide-int-1024-0', "skm-wide-int-" + "9" * 5000 + "-", "skm-wide-int-01-0"]
    strings = taken if where == "values" else dict.fromkeys(taken, 1)
    value = {"n": WIDE, "s": strings}
    expected = (
        '{"n":' + WIDE_TEXT + ',"s":' + json.dumps(strings, sort_keys=True, separators=(",", ":")) + "}"
    )
    calls = counting_dumps(monkeypatch)
    with int_text_limit(4300):
        assert checker.canonical(value) == expected
    assert len(calls) <= 3  # each occupied marker cost a whole write of the value before


def test_a_value_json_dumps_can_write_is_written_once(monkeypatch):
    calls = counting_dumps(monkeypatch)
    assert checker.canonical({"a": [10**700, "skm-wide-int-0-0"]}) == (
        '{"a":[' + checker._digits(10**700) + ',"skm-wide-int-0-0"]}'
    )
    assert len(calls) == 1


BOUND = 65536  # the registry's _INT_DIGITS_MAX


def test_lock_integers_follow_the_registry_bound():
    registry = import_module("skm.platform.schema.registry")
    assert registry._INT_DIGITS_MAX == BOUND


@pytest.mark.parametrize("limit", [640, 4300], ids=["lowest", "default"])
def test_past_an_enabled_limit_lock_integers_are_read_up_to_the_registry_bound(limit, tmp_path):
    widest = 10**BOUND - 1
    write_lock(tmp_path, {"$id": WIDE_SCHEMA, "const": [widest, -widest]})
    with int_text_limit(limit):
        lock = checker.read_lock(tmp_path)
        assert lock is not None
        assert lock["entries"][WIDE_SCHEMA]["snapshot"]["const"] == [widest, -widest]
        write_lock(tmp_path, {"$id": WIDE_SCHEMA, "const": -(10**BOUND)})  # 65537 digits, correct digests
        with pytest.raises(ValueError, match="65537 digits is wider than 65536") as error:
            checker.read_lock(tmp_path)
        assert len(str(error.value)) < 300
        assert sys.get_int_max_str_digits() == limit


def test_a_lock_token_past_the_bound_is_refused_before_the_envelope_is_checked(tmp_path):
    path = tmp_path / checker.LOCK_PATH
    path.parent.mkdir(parents=True)
    path.write_text('{"schema": "x", "noise": ' + "9" * 100001 + "}", encoding="utf-8")
    with int_text_limit(4300), pytest.raises(ValueError, match="100001 digits is wider than 65536"):
        checker.read_lock(tmp_path)


@pytest.mark.parametrize("limit", [0, 100000], ids=["off", "wider"])
def test_a_lock_integer_past_the_bound_is_read_when_the_limit_admits_it(limit, tmp_path):
    past = 10**70000 - 1
    write_lock(tmp_path, {"$id": WIDE_SCHEMA, "const": past})
    with int_text_limit(limit):
        lock = checker.read_lock(tmp_path)
        assert sys.get_int_max_str_digits() == limit
    assert lock is not None
    assert lock["entries"][WIDE_SCHEMA]["snapshot"]["const"] == past
