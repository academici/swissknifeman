"""v3 plan schemas and the closed-profile validator: fixtures, profile fail-closed, pointers."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import model, schema  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA_DIR = schema.default_schema_dir()


def split_kind(name: str, prefix_len: int = 0) -> str:
    """Longest known kind that prefixes ``name[prefix_len:]`` (kinds may contain a hyphen)."""
    rest = name[prefix_len:]
    kinds = [k for k in schema.KINDS if rest == k or rest.startswith(k + "-")]
    if not kinds:
        raise AssertionError(f"fixture name has no known kind: {name}")
    return max(kinds, key=len)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def codes(issues):
    return {i.code for i in issues}


class FixtureTests(unittest.TestCase):
    def test_valid_fixtures_have_no_issues(self):
        files = sorted((FIXTURES / "valid").glob("*.json"))
        self.assertGreaterEqual(len(files), 10)
        for path in files:
            with self.subTest(path.name):
                kind = split_kind(path.stem)
                self.assertEqual(schema.validate(load(path), kind), [])

    def test_invalid_fixtures_yield_exactly_their_code(self):
        files = sorted((FIXTURES / "invalid").glob("*.json"))
        seen = set()
        for path in files:
            with self.subTest(path.name):
                code = path.stem.split("-", 1)[0]
                self.assertIn(code, schema.ERROR_CODES)
                issues = schema.validate(load(path), split_kind(path.stem, len(code) + 1))
                self.assertEqual(codes(issues), {code}, issues)
                seen.add(code)
        # `ref` cannot be produced by a document; it is covered by test_dangling_ref below.
        self.assertEqual(seen | {"ref"}, set(schema.ERROR_CODES))

    def test_every_valid_fixture_is_canonical_json(self):
        for path in sorted((FIXTURES / "valid").glob("*.json")):
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text, json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n")


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.item = load(FIXTURES / "valid" / "item-e3.json")

    def test_collects_all_issues(self):
        self.item["status"] = "finished"
        self.item["id"] = "P1"
        del self.item["why"]
        self.assertEqual(sorted(codes(schema.validate(self.item, "item"))), ["enum", "pattern", "required"])

    def test_pointer_points_into_nested_arrays(self):
        self.item["reads"][1]["path"] = "/abs/path"
        issues = schema.validate(self.item, "item")
        self.assertEqual([(i.path, i.code) for i in issues], [("/reads/1/path", "pattern")])
        self.assertTrue(issues[0].message.startswith("/reads/1/path: "))

    def test_a_read_names_exactly_one_of_path_or_ref(self):
        self.item["reads"] = [{"ref": "knowledge/design#validation", "why": "w", "required": True},
                              {"ref": "artifact/catalog", "section": "s", "why": "w", "required": False}]
        self.assertEqual(schema.validate(self.item, "item"), [])
        both = {"ref": "D1", "path": "lib/x.py", "why": "w", "required": True}
        neither = {"why": "w", "required": True}
        for read in (both, neither):
            self.item["reads"] = [read]
            self.assertEqual([(i.path, i.code) for i in schema.validate(self.item, "item")], [("/reads/0", "one_of")], read)

    def test_ref_fields_take_the_whole_grammar_and_nothing_else(self):
        good = ["P1", "P1.2", "D3", "P1.2/U4", "knowledge/design", "knowledge/design#validation", "artifact/catalog",
                "PLAN2.P6.1/U1", "repo:PLAN2.knowledge/x#y"]
        for ref in good:
            self.item["related"] = [{"ref": ref, "relation": "informs"}]
            self.assertEqual(schema.validate(self.item, "item"), [], ref)
        for ref in ("knowledge/", "artifact/", "P1/U1", "U1", "x", "knowledge/a#"):
            self.item["related"] = [{"ref": ref, "relation": "informs"}]
            self.assertEqual([i.code for i in schema.validate(self.item, "item")], ["pattern"], ref)

    def test_artifact_ids_are_optional_and_pattern_checked(self):
        self.item["artifacts"] = [{"id": "catalog", "path": "x.json", "role": "output"}, {"path": "y.json", "role": "input"}]
        self.assertEqual(schema.validate(self.item, "item"), [])
        self.item["artifacts"][0]["id"] = "bad id"
        self.assertEqual([(i.path, i.code) for i in schema.validate(self.item, "item")], [("/artifacts/0/id", "pattern")])

    def test_pointer_escapes_special_characters(self):
        self.item["a/b~c"] = 1
        issues = schema.validate(self.item, "item")
        self.assertEqual([(i.path, i.code) for i in issues], [("/a~1b~0c", "additional")])

    def test_root_type_error_uses_empty_pointer(self):
        issues = schema.validate([], "item")
        self.assertEqual([(i.path, i.code) for i in issues], [("", "type")])

    def test_booleans_are_not_integers_or_numbers(self):
        self.item["result"]["checks"][0]["exit"] = True
        self.assertEqual([(i.path, i.code) for i in schema.validate(self.item, "item")],
                         [("/result/checks/0/exit", "type")])

    def test_boolean_does_not_equal_const_one(self):
        event = load(FIXTURES / "valid" / "log-event-e5-start.json")
        event["v"] = True
        self.assertEqual(codes(schema.validate(event, "log-event")), {"type"})
        event["v"] = 2
        self.assertEqual(codes(schema.validate(event, "log-event")), {"const"})

    def test_trailing_newline_does_not_satisfy_anchored_pattern(self):
        self.item["id"] = "P1.1\n"
        self.assertEqual(codes(schema.validate(self.item, "item")), {"pattern"})

    def test_nullable_fields_accept_null_and_objects(self):
        phase = load(FIXTURES / "valid" / "phase-e2.json")
        phase["closed"] = {"at": "2026-10-05T10:40:00Z", "result": "done", "summary": "ok"}
        self.assertEqual(schema.validate(phase, "phase"), [])
        phase["closed"] = {"at": "2026-10-05T10:40:00Z"}
        self.assertEqual(codes(schema.validate(phase, "phase")), {"required"})

    def test_migration_preserves_fractional_timestamps_procedures_and_missing_routes(self):
        event = load(FIXTURES / "valid" / "log-event-e5-start.json")
        event["ts"] = "2026-09-11T13:53:26.807745Z"
        self.assertEqual(schema.validate(event, "log-event"), [])
        self.item["route"] = None
        self.item["validation"][0]["procedure"] = "Owner compares the signed acceptance packet."
        self.item["validation"][0].pop("cmd")
        self.item["skills"] = ["blender:mcp-blender", "skill-creator"]
        self.assertEqual(schema.validate(self.item, "item"), [])

    def test_object_data_payload_is_free_form(self):
        event = load(FIXTURES / "valid" / "log-event-e5-start.json")
        event["data"] = {"any": ["thing", 1, None], "nested": {"x": True}}
        self.assertEqual(schema.validate(event, "log-event"), [])

    def test_unknown_kind_is_a_profile_error(self):
        with self.assertRaises(schema.SchemaProfileError):
            schema.validate({}, "defs")
        with self.assertRaises(schema.SchemaProfileError):
            schema.validate({}, "nonsense")

    def test_dangling_ref_yields_ref_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            body = {
                "$schema": schema.DIALECT, "$id": f"{schema.SCHEMA_URN_PREFIX}plan:v1",
                "type": "object",
                "properties": {"a": {"$ref": "#/$defs/missing"}, "b": {"$ref": "urn:other:v1#/$defs/x"}},
            }
            (tmp / "plan.schema.json").write_text(json.dumps(body), encoding="utf-8")
            registry = schema.load_registry(tmp)
            issues = schema.validate({"a": 1, "b": 2}, "plan", registry)
        self.assertEqual([(i.path, i.code) for i in issues], [("/a", "ref"), ("/b", "ref")])

    def test_registry_is_cached_per_directory(self):
        self.assertIs(schema.load_registry(), schema.load_registry(SCHEMA_DIR))


class ReadDataTests(unittest.TestCase):
    def test_read_data_schemas_accept_results_and_reject_broken_contracts(self):
        event = load(FIXTURES / "valid" / "log-event-e5-difficulty.json")
        good = {
            "read-get": {"ref": "knowledge/notes#a", "kind": "document", "doc": {"sections": []}},
            "read-list": [{"ref": "P1.1", "title": "First", "status": "todo"}],
            "read-events": [event],
            "read-artifact": {"ref": "artifact/data", "path": "@plan/artifacts/data.json", "role": "output",
                              "exists": False, "sha256": None},
        }
        for kind, value in good.items():
            with self.subTest(kind=kind):
                self.assertEqual(schema.validate(value, kind), [])
                broken = copy.deepcopy(value)
                record = broken[0] if isinstance(broken, list) else broken
                record["unexpected"] = True
                self.assertIn("additional", codes(schema.validate(broken, kind)))
        for ref in ("views/plan.md", "knowledge/../notes", "P1.1\n"):
            self.assertTrue(schema.validate({"ref": ref, "kind": "item", "doc": {}}, "read-get"))
        self.assertTrue(schema.validate({**good["read-artifact"], "sha256": "wrong"}, "read-artifact"))
        self.assertTrue(schema.validate([{**event, "type": "unknown"}], "read-events"))


class ProfileTests(unittest.TestCase):
    """The schema files themselves stay inside the closed profile and carry the documented contract."""

    def schema_files(self):
        return sorted(SCHEMA_DIR.glob("*.schema.json"))

    def test_schema_files_exist_and_parse(self):
        names = [p.name for p in self.schema_files()]
        self.assertEqual(names, sorted(f"{k}.schema.json" for k in
                                       ("defs", *schema.KINDS)))
        for path in self.schema_files():
            self.assertIsInstance(load(path), dict)

    def test_ids_follow_the_urn_convention(self):
        for path in self.schema_files():
            kind = path.name.removesuffix(".schema.json")
            self.assertEqual(load(path)["$id"], f"urn:swissknifeman:task:plan:{kind}:v1")

    def test_every_object_is_closed_and_every_field_is_described(self):
        def walk(node, where):
            if "properties" in node:
                self.assertIs(node.get("additionalProperties"), False, where)
                for name, child in node["properties"].items():
                    self.assertTrue(child.get("description"), f"{where}/{name} has no description")
                    walk(child, f"{where}/{name}")
            for name, child in node.get("$defs", {}).items():
                self.assertTrue(child.get("description"), f"{where}/$defs/{name} has no description")
                walk(child, f"{where}/$defs/{name}")
            if "items" in node:  # the array field itself carries the description
                walk(node["items"], f"{where}/items")
            for index, branch in enumerate(node.get("oneOf", ())):
                walk(branch, f"{where}/oneOf/{index}")

        for path in self.schema_files():
            walk(load(path), path.name)

    def test_defs_patterns_match_model_regexes(self):
        defs = load(SCHEMA_DIR / "defs.schema.json")["$defs"]
        for name, regex in (("itemId", model.ITEM_ID), ("phaseId", model.PHASE_ID),
                            ("decisionId", model.DECISION_ID), ("ref", model.REF)):
            self.assertEqual(defs[name]["pattern"], regex.pattern, name)
        plan_props = load(SCHEMA_DIR / "plan.schema.json")["properties"]
        self.assertEqual(plan_props["id"]["pattern"], model.PLAN_ID.pattern)
        self.assertEqual(plan_props["short_id"]["pattern"], model.SHORT_ID.pattern)

    def copy_schemas(self, tmp: str) -> Path:
        target = Path(tmp) / "v1"
        shutil.copytree(SCHEMA_DIR, target)
        return target

    def test_unknown_keyword_fails_closed_negative_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.copy_schemas(tmp)
            path = target / "plan.schema.json"
            body = load(path)
            body["if"] = {"properties": {}}
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword 'if'"):
                schema.load_registry(target)

    def test_unknown_keyword_in_nested_property_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.copy_schemas(tmp)
            path = target / "item.schema.json"
            body = load(path)
            body["properties"]["summary"]["format"] = "uri"
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaisesRegex(schema.SchemaProfileError, "unsupported keyword 'format'"):
                schema.load_registry(target)

    def test_additional_properties_true_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.copy_schemas(tmp)
            path = target / "brief.schema.json"
            body = load(path)
            body["additionalProperties"] = True
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaisesRegex(schema.SchemaProfileError, "additionalProperties may only be false"):
                schema.load_registry(target)

    def test_bad_pattern_and_empty_directory_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.copy_schemas(tmp)
            path = target / "unit.schema.json"
            body = copy.deepcopy(load(path))
            body["properties"]["id"]["pattern"] = "^(unclosed"
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaisesRegex(schema.SchemaProfileError, "invalid pattern"):
                schema.load_registry(target)
            empty = Path(tmp) / "empty"
            empty.mkdir()
            with self.assertRaises(schema.SchemaProfileError):
                schema.load_registry(empty)


if __name__ == "__main__":
    unittest.main()
