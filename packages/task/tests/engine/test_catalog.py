"""API discovery: parser parity, registered refusals, typed data and read-only schema queries."""
import argparse
import ast
import json
from pathlib import Path
import unittest
from unittest import mock

from task.plan import catalog, cli, schema, store

try:
    from . import test_envelope
except ImportError:
    import test_envelope


PLAN_LIB = Path(__file__).resolve().parents[2] / "lib/task/plan"


def choices(parser):
    return next(a.choices for a in parser._actions if isinstance(a, argparse._SubParsersAction))


class ParserCatalogTests(unittest.TestCase):
    def test_catalog_contains_every_parser_verb_and_matches_descriptions(self):
        parser = cli.build_parser()
        result = catalog.verbs(parser)
        self.assertEqual(schema.validate(result, "read-catalog"), [])
        self.assertEqual([v["name"] for v in result["verbs"]], sorted(choices(parser)))
        self.assertEqual(set(catalog.VERB_DATA), set(choices(parser)))
        for row in result["verbs"]:
            self.assertEqual(row["summary"], choices(parser)[row["name"]].description)
            self.assertTrue(row["summary"])
            self.assertIn(row["mode"], ("read", "write"))
            self.assertEqual(row["errors"], sorted(set(row["errors"])))
            self.assertTrue(set(row["errors"]) <= catalog.ERROR_CODES)

    def test_arguments_preserve_required_flags_choices_cardinality_and_aliases(self):
        rows = {v["name"]: v for v in catalog.verbs(cli.build_parser())["verbs"]}
        get = {a["name"]: a for a in rows["get"]["args"]}
        self.assertTrue(get["plan"]["required"])
        self.assertTrue(get["ref"]["required"])
        self.assertFalse(get["--fields"]["required"])
        self.assertEqual(get["--output"]["choices"], ["text", "json"])
        self.assertEqual(get["--output"]["scope"], "global")
        self.assertEqual(get["--repo"]["nargs"], 1)
        start = {a["name"]: a for a in rows["start"]["args"]}
        self.assertTrue(start["--actor"]["required"])
        self.assertEqual(start["items"]["nargs"], "+")
        self.assertEqual(start["--scout"]["aliases"], ["--no-scout"])
        self.assertEqual(start["--scout"]["nargs"], 0)
        set_args = {a["name"]: a for a in rows["set"]["args"]}
        self.assertFalse(set_args["--json"]["required"])
        self.assertTrue(set_args["--json"]["required_group"])
        self.assertEqual(set_args["--json"]["exclusive_with"], ["--file"])
        schema_args = {a["name"]: a for a in rows["schema"]["args"]}
        self.assertNotIn("plan", schema_args)
        self.assertFalse(schema_args["kind"]["required"])
        self.assertEqual(set(schema_args["kind"]["choices"]), {*schema.KINDS, "defs"})
        self.assertEqual(schema_args["kind"]["exclusive_with"], ["--verbs"])

    def test_catalog_reflects_live_parser_changes_without_copied_argument_tables(self):
        parser = cli.build_parser()
        command = choices(parser)["get"]
        command.description = "Changed description from the parser"
        command.add_argument("--test-option", choices=("one", "two"), required=True, help="New parser argument")
        get = next(v for v in catalog.verbs(parser)["verbs"] if v["name"] == "get")
        self.assertEqual(get["summary"], command.description)
        arg = next(a for a in get["args"] if a["name"] == "--test-option")
        self.assertEqual((arg["required"], arg["choices"], arg["help"]), (True, ["one", "two"], "New parser argument"))

    def test_new_verb_missing_metadata_and_missing_summary_fail_closed(self):
        parser = cli.build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        sub.add_parser("unregistered", description="A new verb")
        with self.assertRaisesRegex(ValueError, "metadata"):
            catalog.verbs(parser)
        parser = cli.build_parser()
        choices(parser)["get"].description = None
        with self.assertRaisesRegex(ValueError, "summary"):
            catalog.verbs(parser)

    def test_each_declared_data_kind_resolves_to_a_real_schema(self):
        registry = schema.load_registry()
        rows = {v["name"]: v for v in catalog.verbs(cli.build_parser())["verbs"]}
        for name, kind in catalog.VERB_DATA.items():
            if kind is not None:
                document, ident = registry.for_kind(kind)
                self.assertEqual(document["$id"], ident)
                self.assertEqual(rows[name]["data_kind"], kind)
            else:
                self.assertNotIn("data_kind", rows[name])
        for name in ("get", "list", "events", "artifact", "links", "neighborhood", "schema"):
            self.assertEqual(rows[name]["data_kind"], "read-catalog" if name == "schema" else "read-" + name)
        self.assertEqual(rows["export"]["data_kind"], "snapshot")

    def test_mode_honestly_marks_default_writes_and_read_queries(self):
        rows = {v["name"]: v for v in catalog.verbs(cli.build_parser())["verbs"]}
        for name in ("get", "list", "events", "artifact", "links", "neighborhood", "schema", "brief", "export"):
            self.assertEqual(rows[name]["mode"], "read")
        for name in ("context", "render", "unit", "start", "finish", "set", "import"):
            self.assertEqual(rows[name]["mode"], "write")

    def test_catalog_has_no_shared_mutable_parser_metadata(self):
        parser = cli.build_parser()
        before = catalog.verbs(parser)
        changed = catalog.verbs(parser)
        changed["verbs"][0]["args"][0]["choices"].append("corruption")
        self.assertEqual(catalog.verbs(parser), before)


class ErrorRegistryTests(unittest.TestCase):
    def test_registered_codes_match_plan_error_literals_and_cli_refusals(self):
        observed = set()
        for path in PLAN_LIB.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ("PlanError", "_failure") and node.args
                        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    observed.add(node.args[0].value)
        self.assertEqual(catalog.ERROR_CODES, observed)
        declared = set().union(*catalog.VERB_ERRORS.values()) | {"IO_ERROR", "USAGE", "SCHEMA_INVALID"}
        self.assertEqual(declared, observed)
        item_schema = schema.load_registry().for_kind("read-catalog")[0]
        registered = item_schema["properties"]["verbs"]["items"]["properties"]["errors"]["items"]["enum"]
        self.assertEqual(set(registered), observed)


class SchemaCliTests(unittest.TestCase):
    def answer(self, *args, status=0):
        code, out, err = test_envelope.run(*args)
        self.assertEqual(code, status, err or out)
        document = json.loads(out)
        self.assertEqual(schema.validate(document, "envelope"), [])
        self.assertEqual(document["ok"], status == 0)
        self.assertEqual(err, "")
        return document

    def test_schema_no_args_and_verbs_return_the_same_valid_catalog(self):
        default = self.answer("schema")["data"]
        self.assertEqual(default, self.answer("schema", "--verbs")["data"])
        self.assertEqual(default, self.answer("--output", "json", "schema", "--verbs")["data"])
        self.assertEqual(schema.validate(default, "read-catalog"), [])

    def test_every_schema_is_returned_completely_without_plan_discovery(self):
        with mock.patch.object(store, "load_plan", side_effect=AssertionError("loaded plan")), \
                mock.patch.object(store, "resolve_plan_dir", side_effect=AssertionError("resolved plan")), \
                mock.patch.object(store.PlanLock, "__enter__", side_effect=AssertionError("acquired lock")), \
                mock.patch.object(store, "atomic_write", side_effect=AssertionError("wrote file")):
            self.answer("schema", "--verbs")
            for kind in (*schema.KINDS, "defs"):
                with self.subTest(kind=kind):
                    result = self.answer("schema", kind)["data"]
                    source = json.loads((schema.default_schema_dir() / f"{kind}.schema.json").read_text())
                    self.assertEqual(result, source)

    def test_unknown_schema_conflicting_selection_and_extra_plan_are_usage_errors(self):
        for args in (("schema", "unknown"), ("schema", "item", "--verbs"), ("schema", "PLAN7", "item")):
            with self.subTest(args=args):
                self.assertEqual(self.answer(*args, status=2)["error"]["code"], "USAGE")

    def test_invalid_catalog_data_is_refused_before_printing(self):
        with mock.patch.object(catalog, "verbs", return_value={"verbs": [{"name": "bad"}]}):
            document = self.answer("schema", "--verbs", status=1)
        self.assertEqual(document["error"]["code"], "SCHEMA_INVALID")
        self.assertTrue(document["error"]["issues"])

    def test_read_catalog_schema_rejects_unregistered_codes_and_unknown_fields(self):
        result = catalog.verbs(cli.build_parser())
        result["verbs"][0]["errors"].append("UNREGISTERED")
        self.assertTrue(schema.validate(result, "read-catalog"))
        result = catalog.verbs(cli.build_parser())
        result["verbs"][0]["args"][0]["unexpected"] = True
        self.assertTrue(schema.validate(result, "read-catalog"))


if __name__ == "__main__":
    unittest.main()
