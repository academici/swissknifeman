"""``aicore schema codegen``: the mapping of the closed profile, determinism, ``--check`` and the fail-closed cases."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import typing
import unittest
from pathlib import Path

from aicore import cli
from aicore.util import schemacodegen

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "codegen"
LIB = Path(schemacodegen.__file__).resolve().parents[2]


def load_module(path: Path, name: str = "generated_fixture"):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # get_type_hints resolves a quoted name in the module of the class
    spec.loader.exec_module(module)
    return module


def run(*argv, cwd=None):
    out, err = io.StringIO(), io.StringIO()
    code = schemacodegen.main(list(argv), cwd=cwd, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class GeneratedBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.path = Path(cls.tmp.name) / "basic.py"
        cls.text = schemacodegen.generate(FIXTURES / "basic")
        cls.path.write_text(cls.text, encoding="utf-8")
        cls.module = load_module(cls.path)
        cls.addClassCleanup(sys.modules.pop, "generated_fixture", None)


class TestMapping(GeneratedBase):
    def test_required_and_optional_keys_follow_required(self):
        widget = self.module.Widget
        self.assertEqual({"name", "kind"}, set(widget.__required_keys__))
        self.assertIn("weight", widget.__optional_keys__)
        self.assertIn("$schema", widget.__optional_keys__)
        inner = self.module.WidgetInner
        self.assertEqual({"id"}, set(inner.__required_keys__))
        self.assertEqual({"note"}, set(inner.__optional_keys__))

    def test_enum_and_const_become_literal(self):
        hints = typing.get_type_hints(self.module.Widget, include_extras=False)
        self.assertEqual(typing.Literal["small", "large"], hints["kind"])
        self.assertEqual(typing.Literal["urn:swissknifeman:fixture:codegen:widget:v1"], hints["$schema"])
        self.assertEqual(typing.Literal["s", "m", "l"], self.module.PartSize)

    def test_pattern_properties_become_a_dict_of_the_value_type(self):
        hints = typing.get_type_hints(self.module.Widget)
        self.assertEqual(typing.Dict[str, self.module.WidgetPart], hints["by_label"])

    def test_one_of_of_objects_becomes_a_union_of_named_variants(self):
        hints = typing.get_type_hints(self.module.Widget)
        self.assertEqual(typing.Union[self.module.WidgetShapeVariant1, self.module.WidgetShapeVariant2, str],
                         hints["shape"])
        self.assertEqual({"radius"}, set(self.module.WidgetShapeVariant1.__required_keys__))

    def test_a_local_reference_names_the_class_even_in_a_cycle(self):
        hints = typing.get_type_hints(self.module.WidgetPart)
        self.assertEqual(typing.List[self.module.WidgetPart], hints["children"])

    def test_a_reference_into_another_document_of_the_directory_names_its_definition(self):
        self.assertIs(self.module.PartSize, typing.get_type_hints(self.module.Widget)["size"])

    def test_a_reference_outside_the_directory_is_any_and_says_where_it_points(self):
        self.assertEqual(typing.Any, typing.get_type_hints(self.module.Widget)["alien"])
        self.assertIn("# external: urn:swissknifeman:fixture:other:thing:v1", self.text)

    def test_unsupported_key_names_use_the_functional_syntax(self):
        self.assertIn('Widget = TypedDict("Widget", {', self.text)
        self.assertIn('"$schema": NotRequired[', self.text)
        self.assertIn('"from": NotRequired[str]', self.text)  # a keyword is no attribute name either
        self.assertIn("class WidgetInner(TypedDict):", self.text)  # identifiers keep the class syntax

    def test_null_and_open_objects_and_lists(self):
        hints = typing.get_type_hints(self.module.Widget)
        self.assertEqual(typing.Optional[float], hints["weight"])
        self.assertEqual(typing.Dict[str, typing.Any], hints["extra"])
        self.assertEqual(typing.List[str], hints["tags"])

    def test_constraint_branches_leave_the_keys_optional(self):
        choice = self.module.Choice
        self.assertEqual(set(), set(choice.__required_keys__))
        self.assertEqual({"left", "right"}, set(choice.__optional_keys__))

    def test_a_map_with_a_tag_is_a_dict_of_the_tag_and_the_catch_all_pattern(self):
        # `^.+$` applies to every key, so the narrower `^x-.+$` does not widen the value type
        self.assertIn("Loose = Dict[str, Union[Literal[", self.text)
        self.assertIn("LooseWide]", self.text.split("Loose = Dict[str, Union[", 1)[1].splitlines()[0])
        self.assertNotIn("LooseNarrow]", self.text.split("Loose = Dict[str, Union[", 1)[1].splitlines()[0])

    def test_a_definition_without_a_type_of_its_own_is_a_marked_alias(self):
        self.assertIn("LooseGate = Dict[str, Any]  # constraint-only schema: no type of its own", self.text)

    def test_an_object_closed_on_top_of_a_ref_keeps_the_keys_and_types_of_the_target(self):
        tight = self.module.ClosedTight
        self.assertTrue(typing.is_typeddict(tight))
        self.assertEqual({"status", "extra"}, set(tight.__required_keys__))  # base required + sibling required
        self.assertEqual({"note", "added"}, set(tight.__optional_keys__))
        hints = typing.get_type_hints(tight)
        self.assertEqual(typing.Literal["a", "b"], hints["status"])  # the sibling only annotates the key
        self.assertEqual(typing.Optional[str], hints["note"])
        self.assertEqual(int, hints["extra"])
        self.assertEqual(bool, hints["added"])  # a key only the sibling declares
        self.assertEqual(typing.Dict[str, typing.Any], self.module.ClosedBase)  # the open target itself stays open

    def test_a_document_without_a_type_declares_only_its_definitions(self):
        self.assertFalse(hasattr(self.module, "Part"))

    def test_the_header_names_the_root_and_the_digest(self):
        first = self.text.splitlines()[0]
        self.assertRegex(first, r"^# Generated by aicore schema codegen from .+ \(sha256 [0-9a-f]{64}\); do not edit\.$")

    def test_only_the_used_typing_names_are_imported(self):
        imported = self.text.splitlines()[1]
        self.assertEqual("from typing import Any, Dict, List, Literal, NotRequired, Optional, TypedDict, Union",
                         imported)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tiny.schema.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "urn:swissknifeman:fixture:codegen:tiny:v1",
                "type": "object", "additionalProperties": False, "required": ["a"],
                "properties": {"a": {"type": "string"}}}), encoding="utf-8")
            self.assertEqual("from typing import TypedDict", schemacodegen.generate(Path(tmp)).splitlines()[1])


class TestDeterminism(GeneratedBase):
    def test_two_runs_give_the_same_bytes(self):
        self.assertEqual(self.text, schemacodegen.generate(FIXTURES / "basic"))

    def test_the_text_does_not_depend_on_where_the_schemas_are(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "elsewhere"
            shutil.copytree(FIXTURES / "basic", copy)
            moved = schemacodegen.generate(copy, label="x")
        self.assertEqual(self.text.split("\n", 1)[1], moved.split("\n", 1)[1])

    def test_a_changed_schema_changes_the_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "basic"
            shutil.copytree(FIXTURES / "basic", copy)
            path = copy / "part.schema.json"
            path.write_text(path.read_text(encoding="utf-8").replace('"m", ', ""), encoding="utf-8")
            changed = schemacodegen.generate(copy)
        self.assertNotEqual(self.text.splitlines()[0].split("(sha256 ")[1], changed.splitlines()[0].split("(sha256 ")[1])
        self.assertIn('PartSize = Literal["s", "l"]', changed)


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        shutil.copytree(FIXTURES / "basic", self.cwd / "schemas")

    def test_write_then_check_is_in_sync(self):
        code, out, err = run("--root", "schemas", "--out", "types/widget.py", cwd=self.cwd)
        self.assertEqual((0, ""), (code, err))
        self.assertTrue((self.cwd / "types" / "widget.py").is_file())
        code, out, err = run("--root", "schemas", "--out", "types/widget.py", "--check", cwd=self.cwd)
        self.assertEqual((0, ""), (code, err), out)

    def test_check_reports_drift_after_a_schema_change(self):
        run("--root", "schemas", "--out", "widget.py", cwd=self.cwd)
        path = self.cwd / "schemas" / "part.schema.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"m", ', ""), encoding="utf-8")
        code, _, err = run("--root", "schemas", "--out", "widget.py", "--check", cwd=self.cwd)
        self.assertEqual(1, code)
        self.assertEqual("SCHEMA_CODEGEN_DRIFT: widget.py\n", err)

    def test_check_reports_drift_after_a_hand_edit_and_writes_nothing(self):
        run("--root", "schemas", "--out", "widget.py", cwd=self.cwd)
        target = self.cwd / "widget.py"
        target.write_text(target.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
        edited = target.read_bytes()
        code, _, err = run("--root", "schemas", "--out", "widget.py", "--check", cwd=self.cwd)
        self.assertEqual((1, "SCHEMA_CODEGEN_DRIFT: widget.py\n"), (code, err))
        self.assertEqual(edited, target.read_bytes())

    def test_check_of_a_missing_file_is_drift(self):
        code, _, err = run("--root", "schemas", "--out", "absent.py", "--check", cwd=self.cwd)
        self.assertEqual((1, "SCHEMA_CODEGEN_DRIFT: absent.py\n"), (code, err))

    def test_usage_errors_exit_two(self):
        self.assertEqual(2, run("--out", "x.py", cwd=self.cwd)[0])
        code, _, err = run("--root", "nowhere", "--out", "x.py", cwd=self.cwd)
        self.assertEqual(2, code)
        self.assertTrue(err.startswith("SCHEMA_CODEGEN_USAGE: "), err)


class TestFailClosed(unittest.TestCase):
    def refusal(self, name):
        with self.assertRaises(schemacodegen.CodegenError) as caught:
            schemacodegen.generate(FIXTURES / name)
        return str(caught.exception)

    def test_items_as_a_list_is_unsupported(self):
        self.assertRegex(self.refusal("items-list"),
                         r"^SCHEMA_CODEGEN_UNSUPPORTED: tuple\.schema\.json:/properties/pair/items\b")

    def test_a_branch_key_the_object_does_not_declare_is_unsupported(self):
        message = self.refusal("branch-key")
        self.assertTrue(message.startswith("SCHEMA_CODEGEN_UNSUPPORTED: branch.schema.json:/oneOf/1"), message)

    def test_a_one_of_that_mixes_typed_and_constraint_branches_is_unsupported(self):
        message = self.refusal("mixed-one-of")
        self.assertTrue(message.startswith("SCHEMA_CODEGEN_UNSUPPORTED: mixed.schema.json:/properties/value"), message)

    def test_a_sibling_that_retypes_a_key_of_the_ref_target_is_unsupported(self):
        message = self.refusal("ref-retype")
        self.assertTrue(message.startswith("SCHEMA_CODEGEN_UNSUPPORTED: retype.schema.json:/$defs/tight/properties/status"),
                        message)

    def test_siblings_of_a_ref_outside_the_directory_are_unsupported(self):
        message = self.refusal("ref-external")
        self.assertTrue(message.startswith("SCHEMA_CODEGEN_UNSUPPORTED: outside.schema.json:/$defs/tight"), message)

    def test_a_reference_to_a_missing_definition_is_unsupported(self):
        message = self.refusal("unresolved")
        self.assertTrue(message.startswith("SCHEMA_CODEGEN_UNSUPPORTED: dangling.schema.json:/properties/value"), message)

    def test_a_keyword_outside_the_profile_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.schema.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "urn:swissknifeman:fixture:codegen:x:v1", "type": "object", "allOf": []}), encoding="utf-8")
            with self.assertRaises(schemacodegen.CodegenError) as caught:
                schemacodegen.generate(Path(tmp))
        self.assertTrue(str(caught.exception).startswith("SCHEMA_CODEGEN_UNSUPPORTED: x.schema.json:/"))

    def test_the_command_exits_one_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.py"
            code, out, err = run("--root", str(FIXTURES / "items-list"), "--out", str(target))
            self.assertEqual(1, code)
            self.assertTrue(err.startswith("SCHEMA_CODEGEN_UNSUPPORTED: tuple.schema.json:"), err)
            self.assertFalse(target.exists())


class TestStandalone(GeneratedBase):
    def test_the_generated_module_imports_in_a_clean_interpreter_without_aicore(self):
        code = ("import importlib.util, sys; "
                f"spec = importlib.util.spec_from_file_location('g', {str(self.path)!r}); "
                "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
                "assert 'aicore' not in sys.modules and 'aicore' not in sys.path, 'aicore was imported'; "
                "print(sorted(module.Widget.__required_keys__))")
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, check=False)
        self.assertEqual((0, "['kind', 'name']\n"), (done.returncode, done.stdout), done.stderr)

    def test_the_module_imports_nothing_but_typing(self):
        imports = [line for line in self.text.splitlines() if line.startswith(("import ", "from "))]
        self.assertEqual(1, len(imports), imports)
        self.assertTrue(imports[0].startswith("from typing import "))


class TestCommandLine(unittest.TestCase):
    def test_the_schema_group_routes_codegen_and_compat(self):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "w.py"
            code = cli.main(["schema", "codegen", "--root", str(FIXTURES / "basic"), "--out", str(target)],
                            out=out, err=err)
            self.assertEqual((0, ""), (code, err.getvalue()))
            self.assertTrue(target.is_file())
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(0, cli.main(["schema", "--help"], out=out, err=err))
        self.assertIn("codegen", out.getvalue())
        self.assertIn("compat", out.getvalue())
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(0, cli.main(["schema", "compat", "--help"], out=out, err=err))
        self.assertIn("--base REF", out.getvalue())
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(2, cli.main(["schema", "bogus"], out=out, err=err))


if __name__ == "__main__":
    unittest.main()
