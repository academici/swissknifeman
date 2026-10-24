"""Compatibility rules of aicore.util.schemacompat and the ``aicore schema compat`` command."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from aicore import cli
from aicore.util.schema import RefError, Registry
from aicore.util.schemacompat import RULES, Change, compare

URN = "urn:swissknifeman:aicore:"
OPEN = {"type": "object"}
CLOSED = {"type": "object", "additionalProperties": False}


def registry(*documents):
    """A registry of schema documents; the first one is the root. Returns ``(registry, root id)``."""
    schemas = {}
    for body in documents:
        schemas[body["$id"]] = body
    return Registry(schemas, urn_prefix=URN, kinds=()), documents[0]["$id"]


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
    """An output contract is checked from the consumer side: new documents must stay valid by the old schema."""

    def test_a_new_property_breaks_an_output_contract_only(self):
        old, new = obj({"a": STR}), obj({"a": STR, "b": STR})
        self.assertEqual([("property-added", False)], directed(old, new, "input"))
        self.assertEqual([("property-removed", True)], directed(old, new, "output"))
        self.assertEqual(sorted([("property-added", False), ("property-removed", True)]), directed(old, new, "both"))

    def test_a_wider_enum_or_type_breaks_an_output_contract(self):
        self.assertEqual([("enum-narrowed", True)], directed({"enum": ["a"]}, {"enum": ["a", "b"]}, "output"))
        self.assertEqual([("type-changed", True)], directed(INT, {"type": "number"}, "output"))

    def test_a_removed_property_is_fine_for_an_output_contract(self):
        old, new = obj({"a": STR, "b": STR}), obj({"a": STR})
        self.assertEqual([("property-removed", True)], directed(old, new, "input"))
        self.assertEqual([("property-added", False)], directed(old, new, "output"))

    def test_messages_of_the_output_side_are_marked(self):
        old, old_id = registry(doc(obj({})))
        new, new_id = registry(doc(obj({"b": STR})))
        found = compare(old, old_id, new, new_id, "output")
        self.assertTrue(found[0].message.startswith("[output] "))

    def test_unknown_direction_is_a_programming_error(self):
        old, old_id = registry(doc(OPEN))
        with self.assertRaises(ValueError):
            compare(old, old_id, old, old_id, "sideways")


class TestRules(unittest.TestCase):
    # rule -> (old schema, new schema) in which exactly that rule fires
    CASES = {
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
        self.assertEqual([], rules(deps, OPEN))
        self.assertEqual([], rules(deps, deps))
        self.assertEqual(["dependent-required-added"], rules(deps, dict(OPEN, dependentRequired={"a": ["b", "c"]})))
        negated = dict(OPEN, **{"not": {"required": ["a"]}})
        self.assertEqual([], rules(negated, OPEN))
        self.assertEqual([], rules(negated, negated))

    def test_every_rule_has_a_case(self):
        self.assertEqual(set(RULES), set(self.CASES) | {"ref-changed", "ref-sibling-conflict", "kind-removed",
                                                                       "kind-added"})  # the last two: TestMultiDocument

    def test_each_rule_fires_alone_with_its_breaking_flag(self):
        for rule, (old, new) in self.CASES.items():
            with self.subTest(rule=rule):
                found = changes(old, new)
                self.assertEqual([rule], [change.rule for change in found], found)
                self.assertIs(RULES[rule], found[0].breaking)  # a harmless pattern-property-added is False

    def test_identical_schemas_and_annotations_are_not_changes(self):
        base = obj({"a": dict(STR, minLength=1)}, ["a"])
        edited = json.loads(json.dumps(base))
        edited["title"] = "x"
        edited["description"] = "changed"
        edited["properties"]["a"]["description"] = "text"
        edited["properties"]["a"]["default"] = "d"
        edited["x-skm-layers"] = ["machine"]
        self.assertEqual([], rules(base, base))
        self.assertEqual([], rules(base, edited))

    def test_change_carries_path_and_message(self):
        found = changes(obj({"a": {"type": "array", "items": STR}}), obj({"a": {"type": "array", "items": INT}}))
        self.assertEqual([Change("/properties/a/items", "type-changed", True, "type string is now integer")],
                         found)

    def test_paths_escape_pointer_characters(self):
        found = changes(obj({"a/b": STR}), obj({"a/b": INT}))
        self.assertEqual("/properties/a~1b", found[0].path)

    def test_property_removal_is_breaking_only_when_the_new_object_is_closed_and_does_not_cover_it(self):
        self.assertEqual([], rules(obj({"a": STR}), dict(OPEN, properties={})))
        covered = obj({}, patternProperties={"^a": STR})
        self.assertEqual(["pattern-property-added"], rules(obj({"a": STR}), covered))

    def test_type_rules(self):
        self.assertEqual(["type-changed"], rules({"type": "number"}, INT))
        self.assertEqual([], rules(INT, {"type": ["integer"]}))
        self.assertEqual(["type-widened"], rules(INT, {"type": ["integer", "null"]}))
        self.assertEqual(["type-widened"], rules(STR, {}))
        self.assertEqual(["type-changed"], rules({}, STR))
        self.assertEqual(["type-changed"], rules({"type": ["string", "null"]}, STR))

    def test_enum_values_compare_by_json_equality(self):
        self.assertEqual([], rules({"enum": [1, "a"]}, {"enum": ["a", 1.0]}))
        self.assertEqual(["enum-narrowed", "enum-widened"], rules({"enum": [1]}, {"enum": [True]}))
        self.assertEqual(["enum-widened"], rules({"enum": ["a"]}, {}))
        self.assertEqual(["enum-narrowed", "enum-widened"], rules({"enum": ["a", "b"]}, {"enum": ["b", "c"]}))

    def test_bound_rules_for_every_keyword(self):
        for keyword, tight, loose in (("minLength", 3, 1), ("minItems", 3, 1), ("minimum", 3, 1), ("maximum", 1, 3),
                                      ("maxLength", 1, 3), ("maxItems", 1, 3), ("minProperties", 3, 1),
                                      ("maxProperties", 1, 3)):
            with self.subTest(keyword=keyword):
                self.assertEqual(["bound-tightened"], rules({keyword: loose}, {keyword: tight}))
                self.assertEqual(["bound-relaxed"], rules({keyword: tight}, {keyword: loose}))
                self.assertEqual(["bound-tightened"], rules({}, {keyword: tight}))
                self.assertEqual(["bound-relaxed"], rules({keyword: tight}, {}))

    def test_a_zero_minimum_length_or_item_count_is_no_bound(self):
        self.assertEqual([], rules({}, {"minLength": 0, "minItems": 0}))

    def test_closing_an_object_and_opening_it(self):
        self.assertEqual([], rules(CLOSED, OPEN))
        self.assertEqual([], rules(CLOSED, CLOSED))
        self.assertEqual(["additional-closed"], rules(OPEN, CLOSED))

    def test_pattern_property_values_are_compared(self):
        old = {"patternProperties": {"^a": STR}}
        new = {"patternProperties": {"^a": INT}}
        self.assertEqual(["type-changed"], rules(old, new))
        self.assertEqual(["pattern-property-added", "pattern-property-removed"],
                         rules(old, {"patternProperties": {"^b": STR}}))
        graded = {c.rule: c.breaking for c in changes(old, {"patternProperties": {"^b": STR}})}
        self.assertTrue(graded["pattern-property-added"])  # the old object was open: ^b could meet any name

    def test_property_names_removed_or_equal_is_not_reported(self):
        names = {"propertyNames": {"pattern": "^a"}}
        self.assertEqual([], rules(names, names))
        self.assertEqual([], rules(names, {}))
        self.assertEqual(["property-names-changed"], rules(names, {"propertyNames": {"pattern": "^b"}}))

    def test_unique_items_dropped_is_not_reported(self):
        self.assertEqual([], rules({"uniqueItems": True}, {"uniqueItems": False}))

    def test_added_const_and_changed_const(self):
        self.assertEqual(["const-changed"], rules({}, {"const": "x"}))
        self.assertEqual([], rules({"const": "x"}, {"const": "x"}))
        self.assertEqual([], rules({"const": "x"}, {}))

    def test_items_added_or_removed(self):
        self.assertEqual(["type-changed"], rules({"type": "array"}, {"type": "array", "items": STR}))
        self.assertEqual(["type-widened"], rules({"type": "array", "items": STR}, {"type": "array"}))

    def test_oneof_marks_a_changed_branch_once_and_hides_its_detail(self):
        old = {"oneOf": [obj({"a": STR}), obj({"b": STR})]}
        new = {"oneOf": [obj({"a": STR}), obj({"b": INT})]}
        found = changes(old, new)
        self.assertEqual([("/oneOf/1", "oneof-changed")], [(c.path, c.rule) for c in found])
        self.assertIn("type-changed", found[0].message)
        self.assertEqual([], rules(old, old))
        self.assertEqual(["oneof-changed"], rules({}, {"oneOf": [STR]}))

    def test_oneof_branch_that_widened_and_shares_no_document_reports_its_own_changes(self):
        # branch 0 is closed and lacks "loaded", which branch 1 requires: no document matches both
        old = {"oneOf": [obj({"id": STR}, ["id"]), obj({"ref": STR, "loaded": BOOL}, ["ref", "loaded"])]}
        new = {"oneOf": [obj({"id": STR, "origin": STR}, ["id"]), old["oneOf"][1]]}
        found = changes(old, new)
        self.assertEqual([("/oneOf/0/properties/origin", "property-added", False)],
                         [(c.path, c.rule, c.breaking) for c in found])

    def test_oneof_branch_that_widened_but_may_overlap_stays_oneof_changed(self):
        # branch 1 is open: {"id": "x", "origin": "y"} matched branch 1 only and now matches both
        old = {"oneOf": [obj({"id": STR}, ["id"]), {"type": "object", "properties": {"id": STR}, "required": ["id"]}]}
        new = {"oneOf": [obj({"id": STR, "origin": STR}, ["id"]), old["oneOf"][1]]}
        self.assertEqual([("/oneOf/0", "oneof-changed")], [(c.path, c.rule) for c in changes(old, new)])

    def test_required_fields_prove_disjointness_from_bounded_empty_object(self):
        phase = obj({"id": STR}, ["id"])
        old = {"oneOf": [phase, {"type": "object", "maxProperties": 0}]}
        new = {"oneOf": [obj({"id": STR, "readiness": STR}, ["id"]), old["oneOf"][1]]}
        self.assertEqual(["property-added"], rules(old, new))
        # At the boundary the formerly unique {id, readiness} may now match both branches.
        for limit in (1, 2):
            before = {"oneOf": [phase, {"type": "object", "maxProperties": limit}]}
            after = {"oneOf": [new["oneOf"][0], before["oneOf"][1]]}
            self.assertEqual(["oneof-changed"], rules(before, after))

    def test_oneof_discriminator_and_types_prove_branches_apart(self):
        kind = {"kind": {"const": "a"}, "x": STR}
        old = {"oneOf": [{"type": "object", "properties": kind, "required": ["kind"]},
                         {"type": "object", "properties": {"kind": {"enum": ["b", "c"]}}, "required": ["kind"]}]}
        new = {"oneOf": [{"type": "object", "properties": dict(kind, x={"type": ["string", "null"]}),
                          "required": ["kind"]}, old["oneOf"][1]]}
        self.assertEqual(["type-widened"], rules(old, new))
        self.assertEqual(["bound-relaxed"], rules({"oneOf": [{"type": "string", "maxLength": 3}, INT]},
                                                  {"oneOf": [{"type": "string"}, INT]}))
        self.assertEqual(["oneof-changed"], rules({"oneOf": [{"type": "number", "maximum": 3}, INT]},
                                                  {"oneOf": [{"type": "number"}, INT]}))

    def test_oneof_branch_with_a_ref_sibling_conflict_proves_nothing(self):
        # branch 1 is a closed target {id, x} with sibling properties {note}: the merged body would seem to forbid "id",
        # yet {"id": "v"} matched branch 0 only and, once the target stops requiring x, matches both
        body = {"oneOf": [obj({"id": STR}, ["id"]), {"$ref": f"{URN}target:v1", "properties": {"note": STR}}]}
        old, old_id = registry(doc(body), doc(obj({"id": STR, "x": STR}, ["id", "x"]), "target"))
        new, new_id = registry(doc(body), doc(obj({"id": STR, "x": STR}, ["id"]), "target"))
        found = compare(old, old_id, new, new_id)
        self.assertIn(("/oneOf/1", "oneof-changed"), [(c.path, c.rule) for c in found])

    def test_nested_changes_are_found_at_depth(self):
        old = obj({"a": obj({"b": {"type": "array", "items": obj({"c": STR}, ["c"])}})})
        new = obj({"a": obj({"b": {"type": "array", "items": obj({"c": STR}, [])}})})
        found = changes(old, new)
        self.assertEqual([("/properties/a/properties/b/items", "required-removed")],
                         [(c.path, c.rule) for c in found])


class TestPatternPropertySoundness(unittest.TestCase):
    """A document valid by the old schema must stay valid when no breaking change is reported."""

    def breaking(self, old, new):
        return [c.rule for c in changes(old, new) if c.breaking]

    def test_a_pattern_that_also_matches_a_kept_property_is_breaking(self):
        old = obj({"id": STR})
        new = obj({"id": STR}, patternProperties={"^[a-z]+$": INT})
        self.assertEqual(["pattern-property-added"], self.breaking(old, new))

    def test_a_removed_property_covered_by_a_narrower_pattern_is_breaking(self):
        old = obj({"a": STR})
        new = obj({}, patternProperties={"^a$": INT})
        self.assertIn("type-changed", self.breaking(old, new))

    def test_a_removed_property_covered_by_an_equal_pattern_is_compatible(self):
        old = obj({"a": STR})
        new = obj({}, patternProperties={"^a": STR})
        self.assertEqual([], self.breaking(old, new))

    def test_a_pattern_added_to_an_open_object_is_breaking(self):
        self.assertEqual(["pattern-property-added"],
                         self.breaking(OPEN, {"type": "object", "patternProperties": {"^ab": {"minLength": 5}}}))

    def test_a_pattern_added_to_a_closed_object_with_other_names_is_compatible(self):
        self.assertEqual([], self.breaking(obj({"a": STR}), obj({"a": STR}, patternProperties={"^z": STR})))

    def test_a_pattern_added_next_to_an_old_pattern_is_breaking(self):
        old = obj({}, patternProperties={"^a": STR})
        self.assertEqual(["pattern-property-added"],
                         self.breaking(old, obj({}, patternProperties={"^a": STR, "^ab": INT})))

    def test_a_property_added_under_an_old_pattern_is_compared_with_it(self):
        old = obj({}, patternProperties={"^a": STR})
        self.assertEqual(["type-changed"], self.breaking(old, obj({"ab": INT}, patternProperties={"^a": STR})))
        self.assertEqual([], self.breaking(old, obj({"ab": STR}, patternProperties={"^a": STR})))


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
        self.assertEqual([("/properties/y", "bound-tightened", True)], [(c.path, c.rule, c.breaking) for c in found])

    def test_a_looser_sibling_does_not_relax_a_stricter_target(self):
        old = {"s": dict(STR, minLength=5)}
        new = {"s": dict(STR, minLength=100)}
        root = {"$ref": "#/$defs/s"}
        sibling = {"$ref": "#/$defs/s", "minLength": 0}
        found = self.compare(old, root, new, sibling)
        self.assertEqual(["bound-tightened"], [c.rule for c in found])
        self.assertTrue(found[0].breaking)

    def test_siblings_that_cannot_be_merged_are_reported(self):
        old = {"s": {"type": "string", "pattern": "^a"}}
        new = {"s": {"type": "string", "pattern": "^a"}}
        found = self.compare(old, {"$ref": "#/$defs/s"}, new, {"$ref": "#/$defs/s", "pattern": "^b"})
        rules_found = sorted(c.rule for c in found)
        self.assertIn("ref-sibling-conflict", rules_found)
        self.assertTrue(all(c.breaking for c in found if c.rule == "ref-sibling-conflict"))

    def test_a_conflict_present_in_both_versions_still_reports_a_changed_target(self):
        """The sibling keyword replaces nothing: target and sibling both apply, so a tighter target breaks."""
        sibling = {"$ref": "#/$defs/s", "properties": {"a": STR}}
        old = {"s": {"type": "object", "properties": {"a": dict(STR, minLength=1)}}}
        new = {"s": {"type": "object", "properties": {"a": dict(STR, minLength=5)}}}
        found = self.compare(old, sibling, new, sibling)
        self.assertEqual(["ref-sibling-conflict"], [c.rule for c in found])
        self.assertTrue(found[0].breaking)
        self.assertEqual([], self.compare(old, sibling, old, sibling))

    def test_an_empty_type_intersection_is_a_conflict_not_a_fallback(self):
        sibling = {"$ref": "#/$defs/s", "type": "integer"}
        old = {"s": {"type": ["string", "integer"]}}
        new = {"s": {"type": "string"}}
        found = self.compare(old, sibling, new, sibling)
        self.assertIn("ref-sibling-conflict", [c.rule for c in found if c.breaking])

    def test_required_and_type_next_to_a_ref_are_merged(self):
        defs = {"s": obj({"a": STR, "b": STR}, ["a"])}
        found = self.compare(defs, {"$ref": "#/$defs/s"}, defs, {"$ref": "#/$defs/s", "required": ["b"]})
        self.assertEqual(["required-added"], [c.rule for c in found])


class TestRefs(unittest.TestCase):
    def test_refs_resolve_in_both_registries(self):
        old, old_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": obj({"a": STR}, ["a"])}}))
        new, new_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": obj({"a": STR}, [])}}))
        self.assertEqual(["required-removed"], [c.rule for c in compare(old, old_id, new, new_id)])

    def test_a_recursive_schema_terminates_and_reports_the_change_once(self):
        def tree(child_type):
            return doc({"$ref": "#/$defs/node", "$defs": {"node": obj({
                "value": {"type": child_type},
                "left": {"$ref": "#/$defs/node"},
                "right": {"$ref": "#/$defs/node"}})}})

        old, old_id = registry(tree("string"))
        new, new_id = registry(tree("integer"))
        found = compare(old, old_id, new, new_id)
        self.assertEqual(["type-changed"], [c.rule for c in found])
        self.assertEqual([], compare(old, old_id, old, old_id))

    def test_a_ref_that_points_at_itself_is_an_error(self):
        loop = doc({"$ref": "#/$defs/a", "$defs": {"a": {"$ref": "#/$defs/a"}}})
        old, old_id = registry(loop)
        with self.assertRaisesRegex(RefError, "refers to itself"):
            compare(old, old_id, old, old_id)

    def test_an_unresolvable_ref_is_an_error(self):
        old, old_id = registry(doc({"$ref": "urn:other:x:v1"}))
        with self.assertRaises(RefError):
            compare(old, old_id, old, old_id)

    def test_a_ref_to_another_document_is_followed_and_a_moved_target_is_informational(self):
        shared_a = doc({"$defs": {"x": STR}}, "a")
        shared_b = doc({"$defs": {"x": STR}}, "b")
        old, old_id = registry(doc({"$ref": f"{URN}a:v1#/$defs/x"}), shared_a)
        new, new_id = registry(doc({"$ref": f"{URN}b:v1#/$defs/x"}), shared_b)
        found = compare(old, old_id, new, new_id)
        self.assertEqual([("", "ref-changed", False)], [(c.path, c.rule, c.breaking) for c in found])
        changed, changed_id = registry(doc({"$ref": f"{URN}b:v1#/$defs/x"}), doc({"$defs": {"x": INT}}, "b"))
        self.assertEqual(["ref-changed", "type-changed"],
                         sorted(c.rule for c in compare(old, old_id, changed, changed_id)))

    def test_a_ref_on_one_side_only_compares_the_resolved_body(self):
        old, old_id = registry(doc(obj({"a": STR})))
        new, new_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": obj({"a": INT})}}))
        self.assertEqual(["type-changed"], [c.rule for c in compare(old, old_id, new, new_id)])

    def test_keywords_next_to_a_ref_win(self):
        old, old_id = registry(doc({"$ref": "#/$defs/x", "$defs": {"x": {"minLength": 1}}}))
        new, new_id = registry(doc({"$ref": "#/$defs/x", "minLength": 4, "$defs": {"x": {"minLength": 1}}}))
        self.assertEqual(["bound-tightened"], [c.rule for c in compare(old, old_id, new, new_id)])


def git(repo, *arguments):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                    "-C", str(repo)] + list(arguments), check=True, capture_output=True)


def schema_body(kind, version, extra=None):
    body = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"{URN}{kind}:{version}",
            "type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
    body.update(extra or {})
    return body


class TestCommand(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve() / "repo"
        self.schemas = self.repo / "packages" / "mod" / "schemas"
        self.unit = self.repo / "packages" / "mod" / "unit.json"
        self.env = {"PATH": os.environ["PATH"], "HOME": self._tmp.name, "GIT_CONFIG_NOSYSTEM": "1"}
        self.repo.mkdir()
        git(self.repo, "init", "-q")

    def write_schema(self, kind, version, extra=None):
        directory = self.schemas / kind / version
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{kind}.schema.json").write_text(json.dumps(schema_body(kind, version, extra)), encoding="utf-8")

    def write_unit(self, **stability):
        contracts = [{"id": f"{URN}{kind}", "path": f"schemas/{kind}/v1", "version": "v1", "stability": value}
                     for kind, value in stability.items()]
        self.unit.write_text(json.dumps({"stability": "development", "provides": {"contracts": contracts}}),
                             encoding="utf-8")

    def commit(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "state")

    def run_cli(self, *argv, cwd=None):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["schema", *argv], env=self.env, cwd=cwd or self.repo, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def compat(self, *argv):
        return self.run_cli("compat", "--root", str(self.schemas), "--unit", str(self.unit), *argv)

    def breaking_edit(self):
        self.write_schema("thing", "v1", {"required": ["a"]})

    def test_development_contract_warns_and_exits_zero(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="development")
        self.commit()
        self.breaking_edit()
        code, out, err = self.compat("--base", "HEAD")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("thing/v1 /: required-added (warning) property 'a' is now required", out)
        self.assertIn("0 errors, 1 warnings", out)

    def test_graded_stabilities_fail_with_an_error(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        self.breaking_edit()
        for stability in ("beta", "rc", "stable", "deprecated"):
            with self.subTest(stability=stability):
                self.write_unit(thing=stability)  # the grade is read from the working tree
                code, out, _ = self.compat()
                self.assertEqual(1, code)
                self.assertIn("required-added (error)", out)

    def test_alpha_only_warns(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="alpha")
        self.commit()
        self.breaking_edit()
        self.assertEqual(0, self.compat()[0])

    def test_non_breaking_changes_are_notes_for_any_stability(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        self.write_schema("thing", "v1", {"properties": {"a": {"type": "string"}, "b": {"type": "string"}}})
        code, out, _ = self.compat()
        self.assertEqual(0, code)
        self.assertIn("property-added (info)", out)

    def test_json_output(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        self.breaking_edit()
        code, out, _ = self.compat("--json", "--base", "HEAD")
        report = json.loads(out)
        self.assertEqual(1, code)
        self.assertEqual("HEAD", report["base"])
        entry = report["contracts"][0]
        self.assertEqual(("thing", "v1", "stable", "compared"),
                         (entry["contract"], entry["version"], entry["stability"], entry["status"]))
        self.assertEqual([{"path": "", "rule": "required-added", "breaking": True, "severity": "error",
                           "message": "property 'a' is now required"}], entry["changes"])

    def test_unchanged_tree_is_clean(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        code, out, err = self.compat()
        self.assertEqual((0, ""), (code, err))
        self.assertEqual("compat: 1 contracts against HEAD: 0 errors, 0 warnings, 0 notes\n", out)

    def test_new_contract_and_new_major_are_not_compared(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        self.write_schema("fresh", "v1")
        self.write_schema("thing", "v2", {"required": ["a"]})
        code, out, _ = self.compat("--json")
        self.assertEqual(0, code)
        status = {(e["contract"], e["version"]): (e["status"], e["changes"]) for e in json.loads(out)["contracts"]}
        self.assertEqual({("fresh", "v1"): ("new", []), ("thing", "v1"): ("compared", []),
                          ("thing", "v2"): ("major", [])}, status)
        self.assertIn("thing/v2: major (not compared)", self.compat()[1])

    def test_base_may_be_any_commit(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        self.breaking_edit()
        self.commit()
        self.assertEqual(0, self.compat("--base", "HEAD")[0])
        code, out, _ = self.compat("--base", "HEAD~1")
        self.assertEqual(1, code)
        self.assertIn("required-added (error)", out)

    def test_referenced_contracts_come_from_the_base_too(self):
        self.write_schema("shared", "v1", {"$defs": {"x": {"type": "string"}}, "properties": {}})
        self.write_schema("thing", "v1", {"properties": {"a": {"$ref": f"{URN}shared:v1#/$defs/x"}}})
        self.write_unit(thing="stable", shared="stable")
        self.commit()
        self.write_schema("shared", "v1", {"$defs": {"x": {"type": "integer"}}, "properties": {}})
        code, out, _ = self.compat("--json")
        report = {e["contract"]: e["changes"] for e in json.loads(out)["contracts"]}
        self.assertEqual(1, code)
        self.assertEqual([], report["shared"])  # $defs are compared where they are used
        self.assertEqual(["type-changed"], [c["rule"] for c in report["thing"]])
        self.assertEqual("/properties/a", report["thing"][0]["path"])

    def test_contract_filter(self):
        self.write_schema("thing", "v1")
        self.write_schema("other", "v1")
        self.write_unit(thing="stable", other="stable")
        self.commit()
        code, out, _ = self.compat("--contract", "other", "--json")
        self.assertEqual([("other", "v1")], [(e["contract"], e["version"]) for e in json.loads(out)["contracts"]])
        code, _, err = self.compat("--contract", "nosuch")
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_COMPAT_UNKNOWN_CONTRACT: "), err)

    def test_unlisted_contract_follows_the_module_stability(self):
        self.write_schema("thing", "v1")
        self.write_unit()
        self.commit()
        self.breaking_edit()
        code, out, _ = self.compat()
        self.assertEqual(0, code)
        self.assertIn("(warning)", out)

    def test_default_root_is_found_from_the_repository(self):
        self.write_schema("thing", "v1")
        (self.repo / "packages" / "aicore").mkdir(parents=True)
        (self.repo / "packages" / "aicore" / "schemas").symlink_to(self.schemas)
        self.write_unit(thing="stable")
        (self.repo / "packages" / "aicore" / "unit.json").write_text(self.unit.read_text(), encoding="utf-8")
        self.commit()
        self.breaking_edit()
        code, out, err = self.run_cli("compat", cwd=self.repo / "packages" / "mod")
        self.assertIn(code, (0, 1), err)
        self.assertIn("thing/v1", out)

    def test_refusals(self):
        self.write_schema("thing", "v1")
        self.write_unit(thing="stable")
        self.commit()
        code, _, err = self.compat("--base", "nosuch-ref")
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_COMPAT_BAD_REF: "), err)
        code, _, err = self.compat("--base", "--oops")
        self.assertEqual(2, code)
        code, _, err = self.run_cli("compat", "--root", str(self.schemas), "--unit", str(self.repo / "none.json"))
        self.assertEqual((2, True), (code, err.startswith("SCHEMA_COMPAT_UNIT: ")))
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        code, _, err = self.run_cli("compat", "--root", str(outside), "--unit", str(self.unit))
        self.assertEqual((2, True), (code, err.startswith("SCHEMA_COMPAT_ROOT: ")))

    def test_not_a_repository_is_exit_two(self):
        plain = Path(self._tmp.name) / "plain"
        plain.mkdir()
        code, out, err = self.run_cli("compat", cwd=plain)
        self.assertEqual((2, ""), (code, out))
        self.assertTrue(err.startswith("SCHEMA_COMPAT_NO_GIT: "), err)

    def test_a_missing_git_is_exit_two(self):
        self.env["PATH"] = str(Path(self._tmp.name) / "empty")
        code, _, err = self.run_cli("compat")
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_COMPAT_NO_GIT: "), err)

    def test_usage(self):
        code, out, err = self.run_cli("--help")
        self.assertEqual((0, ""), (code, err))
        self.assertTrue(out.startswith("usage: aicore schema <command>"))
        self.assertEqual(2, self.run_cli()[0])
        code, _, err = self.run_cli("nosuch")
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_COMPAT_USAGE: "), err)
        code, out, err = self.run_cli("compat", "--help")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("--base REF", out)
        code, _, err = self.run_cli("compat", "--bogus")
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_COMPAT_USAGE: "), err)

    def test_the_group_is_listed_by_the_dispatcher(self):
        self.assertIn("\n  schema   contract tools: compat, codegen\n", cli.usage())
        self.assertEqual(("aicore.util.schemacli", "main"), cli.GROUPS["schema"][:2])


class TestMultiDocument(unittest.TestCase):
    """Contracts of several documents: one directory ``<contract>/v1/`` with a kind per file."""
    PLAN = "urn:swissknifeman:mod:plan:"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve() / "repo"
        self.env = {"PATH": os.environ["PATH"], "HOME": self._tmp.name, "GIT_CONFIG_NOSYSTEM": "1"}
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.module = "old"

    def schemas(self, module=None):
        return self.repo / "packages" / (module or self.module) / "schemas"

    def write(self, kind, extra=None, stem=None, module=None):
        directory = self.schemas(module) / "plan" / "v1"
        directory.mkdir(parents=True, exist_ok=True)
        body = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"{self.PLAN}{kind}:v1",
                "type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        body.update(extra or {})
        (directory / f"{stem or kind}.schema.json").write_text(json.dumps(body), encoding="utf-8")

    def unit(self, stability="stable", module=None):
        path = self.schemas(module).parent / "unit.json"
        contracts = [{"id": "urn:swissknifeman:mod:plan", "path": "schemas/plan/v1", "version": "v1",
                      "stability": stability}]
        path.write_text(json.dumps({"stability": "development", "provides": {"contracts": contracts}}),
                        encoding="utf-8")

    def commit(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "state")

    def compat(self, *argv, module=None):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["schema", "compat", "--root", str(self.schemas(module)), *argv], env=self.env,
                        cwd=self.repo, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def state(self):
        self.write("alpha")
        self.write("beta")
        self.unit()
        self.commit()

    def test_a_new_optional_field_is_a_note_of_its_kind(self):
        self.state()
        self.write("alpha", {"properties": {"a": {"type": "string"}, "b": {"type": "string"}}})
        code, out, err = self.compat("--base", "HEAD")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("plan/v1:alpha /properties/b: property-added (info)", out)
        self.assertNotIn("plan/v1:beta", out)

    def test_a_breaking_change_names_its_kind_and_fails(self):
        self.state()
        self.write("beta", {"required": ["a"]})
        code, out, _ = self.compat("--json")
        entry = json.loads(out)["contracts"][0]
        self.assertEqual(1, code)
        self.assertEqual([("beta", "required-added", "error")],
                         [(c["kind"], c["rule"], c["severity"]) for c in entry["changes"]])

    def test_a_removed_kind_is_breaking_and_a_new_kind_is_a_note(self):
        self.state()
        (self.schemas() / "plan" / "v1" / "beta.schema.json").unlink()
        self.write("gamma")
        code, out, _ = self.compat()
        self.assertEqual(1, code)
        self.assertIn("plan/v1:beta /: kind-removed (error) document 'beta' removed", out)
        self.assertIn("plan/v1:gamma /: kind-added (info) document 'gamma' added", out)

    def test_documents_named_with_dots_are_read_by_their_kind(self):
        self.write("thing-created", stem="thing.created")
        self.unit()
        self.commit()
        self.write("thing-created", {"required": ["a"]}, stem="thing.created")
        code, out, _ = self.compat()
        self.assertEqual(1, code)
        self.assertIn("plan/v1:thing-created /: required-added (error)", out)

    def test_the_base_may_live_under_another_root(self):
        self.state()
        git(self.repo, "mv", "packages/old", "packages/new")
        self.module = "new"
        self.write("alpha", {"properties": {"a": {"type": "string"}, "b": {"type": "string"}}})
        missing, _, err = self.compat("--base", "HEAD")
        self.assertEqual(0, missing)  # the renamed root has no base: every contract is new
        code, out, err = self.compat("--base", "HEAD", "--base-root", str(self.schemas("old")))
        self.assertEqual((0, ""), (code, err))
        self.assertIn("plan/v1:alpha /properties/b: property-added (info)", out)
        self.assertIn("1 contracts against HEAD", out)

    def test_a_base_root_outside_the_repository_is_refused(self):
        self.state()
        code, _, err = self.compat("--base-root", self._tmp.name)
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_COMPAT_ROOT: "), err)

    def test_a_base_root_that_holds_no_schemas_is_refused_not_all_new(self):
        self.state()
        self.write("alpha", {"required": ["a"]})
        for typo in (".", "packages/old/schema"):
            with self.subTest(base_root=typo):
                code, out, err = self.compat("--base", "HEAD", "--base-root", str(self.repo / typo))
                self.assertEqual((2, ""), (code, out))
                self.assertTrue(err.startswith("SCHEMA_COMPAT_BASE_ROOT: "), err)
        self.assertEqual(1, self.compat("--base", "HEAD", "--base-root", str(self.schemas()))[0])

    def test_a_file_name_outside_the_usual_spelling_is_compared_with_its_base(self):
        self.write("my-extra", stem="my_extra")
        self.write("alpha")
        self.unit()
        self.commit()
        self.write("my-extra", {"required": ["a"]}, stem="my_extra")
        code, out, _ = self.compat()
        self.assertEqual(1, code)
        self.assertIn("plan/v1:my-extra /: required-added (error)", out)
        self.assertNotIn("kind-added", out)

    def test_a_foundation_contract_is_taken_from_the_base_on_the_old_side(self):
        foundation = self.repo / "packages" / "aicore" / "schemas" / "artifact-ref" / "v1"
        foundation.mkdir(parents=True)
        (foundation / "artifact-ref.schema.json").write_text(json.dumps(
            {"$id": "urn:swissknifeman:aicore:artifact-ref:v1", "type": "string"}), encoding="utf-8")
        reference = {"properties": {"a": {"$ref": "urn:swissknifeman:aicore:artifact-ref:v1"}}}
        self.write("alpha", reference)
        self.unit()
        self.commit()
        self.assertEqual(0, self.compat()[0])
        (foundation / "artifact-ref.schema.json").write_text(json.dumps(
            {"$id": "urn:swissknifeman:aicore:artifact-ref:v1", "type": "integer"}), encoding="utf-8")
        code, out, _ = self.compat()
        self.assertEqual(1, code)
        self.assertIn("plan/v1:alpha /properties/a: type-changed (error)", out)

    def test_a_single_document_contract_keeps_its_report_shape(self):
        directory = self.schemas() / "thing" / "v1"
        directory.mkdir(parents=True)
        (directory / "thing.schema.json").write_text(json.dumps(
            {"$id": "urn:swissknifeman:aicore:thing:v1", "type": "string"}), encoding="utf-8")
        self.unit()
        self.commit()
        code, out, err = self.compat("--json")
        self.assertEqual((0, ""), (code, err))
        self.assertEqual([("thing", "v1", "compared", [])],
                         [(e["contract"], e["version"], e["status"], e["changes"]) for e in json.loads(out)["contracts"]])

    def test_a_single_document_contract_of_a_module_is_read_with_its_own_prefix(self):
        directory = self.schemas() / "thing" / "v1"
        directory.mkdir(parents=True)
        body = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:swissknifeman:mod:thing:v1",
                "type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        (directory / "thing.schema.json").write_text(json.dumps(body), encoding="utf-8")
        self.unit()
        self.commit()
        code, out, err = self.compat()
        self.assertEqual((0, ""), (code, err), out)  # was SCHEMA_COMPAT_BASE_INVALID: unknown schema kind
        body["properties"]["a"] = {"type": "integer"}
        (directory / "thing.schema.json").write_text(json.dumps(body), encoding="utf-8")
        code, out, _ = self.compat()  # an unlisted contract follows its module: development only warns
        self.assertEqual(0, code)
        self.assertIn("thing/v1 /properties/a: type-changed (warning)", out)

    def test_a_set_with_an_open_extension_slot_is_compared_on_both_sides(self):
        slot = {"properties": {"opts": {"$ref": f"{self.PLAN}extension:options:v1"}}}
        self.write("alpha", slot)
        self.unit()
        self.commit()
        code, out, err = self.compat()
        self.assertEqual((0, ""), (code, err), out)  # was an unresolved reference at the base
        self.write("alpha", {**slot, "required": ["opts"]})
        code, out, _ = self.compat()
        self.assertEqual(1, code)
        self.assertIn("plan/v1:alpha /: required-added (error)", out)
        self.write("alpha", {"properties": {"opts": {"$ref": f"{self.PLAN}other:options:v1"}}})  # not a slot
        self.assertEqual(1, self.compat()[0])


if __name__ == "__main__":
    unittest.main()
