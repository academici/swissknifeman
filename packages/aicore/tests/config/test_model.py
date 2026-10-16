"""The configuration model: module schemas, layers, merging, validation, versions and error positions."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore import config
from aicore.config import ConfigError, ExtraLayer

from tests.config.support import SCHEMA_FILE, Workspace


def schema_doc(**changes):
    """The demo schema with ``changes`` merged on top of the root (for invalid-schema cases)."""
    doc = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    doc.update(changes)
    return doc


class TestModuleSchema(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def load(self, doc, module_id="demo"):
        path = self.dir / "config.schema.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return config.load_module_schema(path, module_id)

    def assertInvalid(self, doc, fragment=None, module_id="demo"):
        with self.assertRaises(ConfigError) as caught:
            self.load(doc, module_id)
        self.assertEqual(caught.exception.code, "CONFIG_SCHEMA_INVALID")
        if fragment:
            self.assertIn(fragment, str(caught.exception))

    def prop(self, name, node):
        doc = schema_doc()
        doc["properties"][name] = node
        return doc

    def test_demo_schema_loads_with_its_leaves(self):
        schema = self.load(schema_doc())
        self.assertIn(("recompute", "candidate_min_n"), schema.leaves)
        self.assertEqual(schema.leaf("recompute.candidate_min_n").default, 15)
        self.assertTrue(schema.leaf("token").secret)
        self.assertEqual(schema.leaf("cache_dir").layers, ("defaults", "machine"))
        self.assertFalse(schema.leaf("limits.retries").has_default)

    def test_root_must_be_an_object(self):
        self.assertInvalid({"$schema": schema_doc()["$schema"], "$id": "urn:swissknifeman:demo:config:v1",
                            "type": "string"}, "root")

    def test_id_must_name_the_module(self):
        self.assertInvalid(schema_doc(**{"$id": "urn:swissknifeman:other:config:v1"}), "$id")
        self.assertInvalid(schema_doc(), "invalid module id", module_id="Bad_ID")
        self.assertInvalid(schema_doc(), "$id", module_id="other")

    def test_tables_must_be_closed(self):
        doc = schema_doc()
        del doc["properties"]["recompute"]["additionalProperties"]
        self.assertInvalid(doc, "additionalProperties")

    def test_required_is_forbidden(self):
        self.assertInvalid(schema_doc(required=["verbose"]), "required")

    def test_every_leaf_needs_a_description(self):
        self.assertInvalid(self.prop("quiet", {"type": "boolean"}), "description")

    def test_default_must_satisfy_the_leaf(self):
        self.assertInvalid(self.prop("quiet", {"type": "integer", "minimum": 5, "default": 1,
                                               "description": "d"}), "default")

    def test_leaf_types(self):
        for node in ({"type": "object", "description": "d"},
                     {"type": "null", "description": "d"},
                     {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "d"},
                     {"type": "array", "description": "d"},
                     {"description": "d"},
                     {"enum": ["a", 1], "description": "d"}):
            with self.subTest(node=node):
                self.assertInvalid(self.prop("x", node))

    def test_keyword_must_fit_the_leaf_type(self):
        self.assertInvalid(self.prop("x", {"type": "boolean", "minimum": 0, "description": "d"}), "minimum")
        self.assertInvalid(self.prop("x", {"type": "string", "minItems": 1, "description": "d"}), "minItems")

    def test_references_and_alternatives_are_not_allowed(self):
        self.assertInvalid(self.prop("x", {"$ref": "#/$defs/y", "description": "d"}))
        self.assertInvalid(self.prop("x", {"oneOf": [{"type": "string"}], "description": "d"}))

    def test_key_names_are_lowercase_words(self):
        for name in ("Camel", "double__underscore", "_private", "dash-ed", "9lives"):
            with self.subTest(name=name):
                self.assertInvalid(self.prop(name, {"type": "boolean", "description": "d"}), "key name")

    def test_secret_leaf_is_a_plain_string_with_a_reference_default(self):
        self.assertInvalid(self.prop("s", {"type": "integer", "x-skm-secret": True, "description": "d"}), "secret")
        self.assertInvalid(self.prop("s", {"type": "string", "x-skm-secret": True, "pattern": "^a",
                                           "description": "d"}), "secret")
        self.assertInvalid(self.prop("s", {"type": "string", "x-skm-secret": True, "default": "plain",
                                           "description": "d"}), "secret reference")
        schema = self.load(self.prop("s", {"type": "string", "x-skm-secret": True, "default": "env://S",
                                           "description": "d"}))
        self.assertEqual(schema.leaf("s").default, "env://S")

    def test_unknown_annotation_fails_in_the_profile(self):
        self.assertInvalid(self.prop("x", {"type": "string", "x-skm-weird": True, "description": "d"}), "x-skm-weird")

    def test_enum_without_type_takes_the_type_of_its_members(self):
        schema = self.load(self.prop("level", {"enum": [1, 2, 3], "default": 2, "description": "d"}))
        self.assertEqual(schema.leaf("level").type, "integer")

    def test_unreadable_schema_file(self):
        with self.assertRaises(ConfigError) as caught:
            config.load_module_schema(self.dir / "missing.json", "demo")
        self.assertEqual(caught.exception.code, "CONFIG_SCHEMA_INVALID")

    def test_schema_is_found_through_unit_json(self):
        (self.dir / "configs").mkdir()
        (self.dir / "configs" / "config.schema.json").write_text(json.dumps(schema_doc()), encoding="utf-8")
        unit = {"id": "demo", "provides": {"config": "configs/config.schema.json"}}
        (self.dir / "unit.json").write_text(json.dumps(unit), encoding="utf-8")
        env = {"SKM_HOME": str(self.dir / "skm")}
        resolved = config.resolve("demo", unit_root=self.dir, env=env)
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 15)
        (self.dir / "unit.json").write_text(json.dumps({"id": "other", **{"provides": unit["provides"]}}),
                                            encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            config.resolve("demo", unit_root=self.dir, env=env)
        self.assertEqual(caught.exception.code, "CONFIG_SCHEMA_INVALID")
        with self.assertRaises(ConfigError):
            config.resolve("demo", env=env)  # neither a schema nor a unit_root


class TestDefaults(Workspace):
    def test_defaults_come_from_the_schema(self):
        resolved = self.resolve()
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 15)
        self.assertEqual(resolved.get("recompute.window.days"), 7)
        self.assertEqual(resolved.get("sources"), ["local"])
        self.assertIsNone(resolved.get("limits.retries"))
        self.assertEqual(resolved.get("limits.retries", default=3), 3)

    def test_as_dict_is_nested_and_a_copy(self):
        resolved = self.resolve()
        tree = resolved.as_dict()
        self.assertEqual(tree["recompute"]["window"], {"days": 7})
        self.assertNotIn("retries", tree.get("limits", {}))
        self.assertNotIn("token", tree)
        tree["sources"].append("hacked")
        resolved.get("sources").append("hacked")
        self.assertEqual(resolved.get("sources"), ["local"])

    def test_get_of_a_table_and_of_an_unknown_key(self):
        resolved = self.resolve()
        self.assertEqual(resolved.get("recompute.window"), {"days": 7})
        with self.assertRaises(ConfigError) as caught:
            resolved.get("recompute.nope")
        self.assertEqual(caught.exception.code, "CONFIG_UNKNOWN_KEY")

    def test_result_is_immutable(self):
        resolved = self.resolve()
        with self.assertRaises(AttributeError):
            resolved.module = "other"
        with self.assertRaises(AttributeError):
            resolved.anything = 1

    def test_layers_are_listed_in_order_with_presence(self):
        self.machine("[demo]\nverbose = true\n")
        resolved = self.resolve()
        self.assertEqual([(layer.name, layer.present) for layer in resolved.layers],
                         [("defaults", True), ("machine", True), ("project", False), ("env", False),
                          ("invocation", False), ("flags", False)])
        self.assertEqual(resolved.layers[1].file, str(self.machine_file))
        self.assertEqual(resolved.layers[2].file, str(self.project_file))

    def test_without_a_project_there_is_no_project_file(self):
        resolved = self.resolve(project=None)
        project = [layer for layer in resolved.layers if layer.name == "project"][0]
        self.assertEqual((project.file, project.present), (None, False))
        self.assertIsNone(resolved.project)


class TestMerge(Workspace):
    def test_missing_key_falls_through(self):
        self.machine("[demo]\nverbose = true\nmode = \"fast\"\n")
        self.proj("[demo]\nmode = \"safe\"\n")
        resolved = self.resolve()
        self.assertTrue(resolved.get("verbose"))  # the project does not mention it: the machine value stays
        self.assertEqual(resolved.get("mode"), "safe")

    def test_maps_merge_arrays_replace(self):
        self.machine("[demo]\nsources = [\"a\", \"b\"]\n[demo.recompute]\ncandidate_min_n = 20\n")
        self.proj("[demo]\nsources = [\"c\"]\n[demo.recompute]\nratio = 0.9\n")
        resolved = self.resolve()
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 20)  # the project table added a key
        self.assertEqual(resolved.get("recompute.ratio"), 0.9)
        self.assertEqual(resolved.get("sources"), ["c"])  # an array is replaced, not merged

    def test_unset_restores_default(self):
        self.machine("[demo]\nmode = \"fast\"\n[demo.recompute]\ncandidate_min_n = 20\n")
        self.proj("[demo]\n_unset = [\"recompute.candidate_min_n\"]\n")
        resolved = self.resolve()
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 15)
        self.assertEqual(resolved.get("mode"), "fast")

    def test_unset_without_default_removes_the_key(self):
        self.machine("[demo.limits]\nretries = 4\n")
        self.proj("[demo]\n_unset = [\"limits.retries\"]\n")
        resolved = self.resolve()
        self.assertIsNone(resolved.get("limits.retries"))
        self.assertNotIn("limits", resolved.as_dict())

    def test_unset_of_a_table_resets_every_key_below(self):
        self.machine("[demo.recompute]\ncandidate_min_n = 20\nratio = 0.9\n[demo.recompute.window]\ndays = 30\n")
        self.proj("[demo]\n_unset = [\"recompute\"]\n")
        resolved = self.resolve()
        self.assertEqual(resolved.get("recompute"), {"candidate_min_n": 15, "ratio": 0.5, "window": {"days": 7}})

    def test_unset_is_followed_by_the_values_of_the_same_layer(self):
        self.machine("[demo]\nmode = \"fast\"\n")
        self.proj("[demo]\n_unset = [\"mode\"]\nmode = \"fast\"\nverbose = true\n")
        self.assertEqual(self.resolve().get("mode"), "fast")

    def test_unset_of_an_unknown_key(self):
        self.proj("[demo]\n_unset = [\"nope\"]\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_UNKNOWN_KEY")

    def test_append_extends_array(self):
        self.machine("[demo._append]\nsources = [\"m\"]\n")
        self.proj("[demo]\n[demo._append]\nsources = [\"p1\", \"p2\"]\n")
        self.assertEqual(self.resolve().get("sources"), ["local", "m", "p1", "p2"])

    def test_append_accepts_dotted_keys_and_nested_tables(self):
        self.proj("[demo]\n_append = {\"sources\" = [\"x\"]}\n")
        self.assertEqual(self.resolve().get("sources"), ["local", "x"])

    def test_append_to_a_non_array_is_a_type_error(self):
        self.proj("[demo._append]\nmode = [\"x\"]\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")
        self.assertIn("array", str(caught.exception))

    def test_append_of_a_wrong_element_or_a_non_list(self):
        for body in ("sources = [1]", "sources = \"x\""):
            with self.subTest(body=body):
                self.proj(f"[demo._append]\n{body}\n")
                with self.assertRaises(ConfigError) as caught:
                    self.resolve()
                self.assertEqual(caught.exception.code, "CONFIG_TYPE")

    def test_append_unknown_key(self):
        self.proj("[demo._append]\nnope = [\"x\"]\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_UNKNOWN_KEY")

    def test_value_and_append_in_one_layer_conflict(self):
        self.proj("[demo]\nsources = [\"a\"]\n[demo._append]\nsources = [\"b\"]\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_CONFLICT")
        self.assertIn("sources", str(caught.exception))

    def test_operators_are_not_accepted_with_a_wrong_shape(self):
        for body, code in (("_unset = \"mode\"", "CONFIG_TYPE"), ("_unset = [1]", "CONFIG_TYPE"),
                           ("_append = [\"x\"]", "CONFIG_TYPE")):
            with self.subTest(body=body):
                self.proj(f"[demo]\n{body}\n")
                with self.assertRaises(ConfigError) as caught:
                    self.resolve()
                self.assertEqual(caught.exception.code, code)

    def test_merged_value_is_validated_again(self):
        self.proj("[demo._append]\nsources = [\"local\"]\n")  # the default already has "local"
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")
        self.assertEqual(caught.exception.layer, "project")
        self.assertIn("sources", str(caught.exception))

    def test_layer_forbidden(self):
        self.machine("[demo]\ncache_dir = \"/var/cache/demo\"\n")
        self.assertEqual(self.resolve().get("cache_dir"), "/var/cache/demo")
        self.proj("[demo]\ncache_dir = \"/elsewhere\"\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        error = caught.exception
        self.assertEqual((error.code, error.layer, error.key), ("CONFIG_LAYER_FORBIDDEN", "project", "cache_dir"))
        self.assertIn("allowed: defaults, machine", str(error))

    def test_layer_forbidden_covers_unset_append_env_and_flags(self):
        for kwargs in ({"flags": {"cache_dir": "/x"}}, {"env": {"SKM_HOME": "/nowhere", "SKM_DEMO_CACHE_DIR": "/x"}}):
            with self.subTest(kwargs=sorted(kwargs)):
                if "env" in kwargs:
                    kwargs["env"]["SKM_HOME"] = self.env["SKM_HOME"]
                with self.assertRaises(ConfigError) as caught:
                    self.resolve(**kwargs)
                self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")
        self.proj("[demo]\n_unset = [\"cache_dir\"]\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_unknown_key_rejected(self):
        for body, key in (("bogus = 1", "bogus"), ("[demo.recompute]\nbogus = 1", "recompute.bogus"),
                          ("[demo.nowhere]\nx = 1", "nowhere")):
            with self.subTest(body=body):
                self.proj(body if body.startswith("[") else f"[demo]\n{body}\n")
                with self.assertRaises(ConfigError) as caught:
                    self.resolve()
                self.assertEqual((caught.exception.code, caught.exception.key, caught.exception.layer),
                                 ("CONFIG_UNKNOWN_KEY", key, "project"))

    def test_table_and_leaf_confusion(self):
        self.proj("[demo]\nrecompute = 5\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")
        self.proj("[demo]\nmode = {x = 1}\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")

    def test_type_and_range_errors(self):
        cases = ("[demo.recompute]\ncandidate_min_n = \"many\"", "[demo.recompute]\ncandidate_min_n = 0",
                 "[demo.recompute]\ncandidate_min_n = 5000", "[demo.recompute]\ncandidate_min_n = 2.5",
                 "[demo.recompute]\nratio = 1.5", "[demo]\nverbose = 1", "[demo]\nmode = \"slow\"",
                 "[demo]\nsources = [\"\"]")
        for body in cases:
            with self.subTest(body=body):
                self.proj(body + "\n")
                with self.assertRaises(ConfigError) as caught:
                    self.resolve()
                self.assertEqual(caught.exception.code, "CONFIG_TYPE")

    def test_number_leaf_accepts_integers(self):
        self.proj("[demo.recompute]\nratio = 1\n")
        self.assertEqual(self.resolve().get("recompute.ratio"), 1)


class TestFiles(Workspace):
    def test_version_missing(self):
        self.proj("[demo]\nverbose = true\n", version=False)
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_VERSION_MISSING")
        self.assertIn("schema_version = 1", str(caught.exception))

    def test_version_newer(self):
        self.write(self.project_file, "schema_version = 2\n[demo]\nverbose = true\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_VERSION_NEWER")
        self.assertIn("upgrade", str(caught.exception))
        self.assertEqual(caught.exception.line, 1)

    def test_version_invalid(self):
        for value in ("0", "-1", "\"1\"", "1.0", "true"):
            with self.subTest(value=value):
                self.write(self.project_file, f"schema_version = {value}\n")
                with self.assertRaises(ConfigError) as caught:
                    self.resolve()
                self.assertEqual(caught.exception.code, "CONFIG_VERSION_INVALID")

    def test_other_top_level_scalar_is_an_unknown_key(self):
        self.proj("stray = 1\n[demo]\nverbose = true\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual((caught.exception.code, caught.exception.key), ("CONFIG_UNKNOWN_KEY", "stray"))

    def test_sections_of_other_modules_are_ignored(self):
        self.proj("[analyst.recompute]\nwhatever = true\n[demo]\nverbose = true\n")
        self.assertTrue(self.resolve().get("verbose"))

    def test_a_file_without_the_module_section_adds_nothing(self):
        self.write(self.project_file, "schema_version = 1\n[other]\nx = 1\n")
        self.assertFalse(self.resolve().get("verbose"))  # a file without the module's section adds nothing
        self.write(self.project_file, "schema_version = 1\n[demo]\n")
        self.assertTrue(self.resolve().layers[2].present)

    def test_empty_or_comment_only_file_is_an_absent_layer(self):
        for text in ("", "# nothing yet\n", "\n\n"):
            with self.subTest(text=text):
                self.write(self.project_file, text)
                resolved = self.resolve()
                self.assertFalse(resolved.layers[2].present)

    def test_missing_file_is_an_absent_layer(self):
        self.assertFalse(self.resolve().layers[1].present)

    def test_toml_syntax_error_names_file_and_line(self):
        self.proj("[demo]\nverbose = \n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        error = caught.exception
        self.assertEqual((error.code, error.layer, error.file), ("CONFIG_FILE_INVALID", "project", str(self.project_file)))
        self.assertEqual(error.line, 3)

    def test_unreadable_file(self):
        self.project_file.parent.mkdir(parents=True)
        self.project_file.mkdir()  # a directory where the file should be
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_FILE_INVALID")

    def test_error_text_carries_file_line_layer_and_key(self):
        self.proj("[demo]\nverbose = true\n\n[demo.recompute]\ncandidate_min_n = 0\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        text = str(caught.exception)
        self.assertTrue(text.startswith(f"{self.project_file}:6: project: recompute.candidate_min_n: "), text)
        self.assertTrue(text.endswith("[CONFIG_TYPE]"), text)

    def test_line_of_a_machine_layer_error(self):
        self.machine("# comment\n[demo]\nnope = 1\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual((caught.exception.layer, caught.exception.line), ("machine", 4))
        self.assertRegex(str(caught.exception), re.escape(f"{self.machine_file}:4:"))


class TestBackends(Workspace):
    def test_resolution_is_the_same_on_the_vendored_backend(self):
        self.machine("[demo.recompute]\ncandidate_min_n = 18\n")
        self.proj("[demo]\nmode = \"fast\"\n[demo._append]\nsources = [\"x\"]\n")
        expected = self.resolve().explain_json()
        with mock.patch.object(config.toml, "default_backend", return_value="vendored"):
            self.assertEqual(self.resolve().explain_json(), expected)


class TestLayerOrder(Workspace):
    def test_layer_order_full(self):
        key = "recompute.candidate_min_n"
        extra = ExtraLayer("legacy", {"recompute": {"candidate_min_n": 4}})
        self.machine("[demo.recompute]\ncandidate_min_n = 2\n")
        self.proj("[demo.recompute]\ncandidate_min_n = 3\n")
        invocation = self.write(self.root / "extra.toml", "schema_version = 1\n[demo.recompute]\ncandidate_min_n = 6\n")
        steps = [
            ({}, 3), ({"extra_layers": [extra]}, 4),
            ({"extra_layers": [extra], "env": {**self.env, "SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N": "5"}}, 5),
            ({"extra_layers": [extra], "env": {**self.env, "SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N": "5"},
              "config_file": invocation}, 6),
            ({"extra_layers": [extra], "env": {**self.env, "SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N": "5"},
              "config_file": invocation, "flags": {key: "7"}}, 7),
        ]
        for kwargs, expected in steps:
            with self.subTest(expected=expected):
                resolved = self.resolve(**kwargs)
                self.assertEqual(resolved.get(key), expected)
        self.assertEqual([layer.name for layer in resolved.layers],
                         ["defaults", "machine", "project", "legacy", "env", "invocation", "flags"])
        self.assertEqual([entry.layer for entry in resolved.explain(key)], ["flags"])
        self.assertEqual([item.layer for item in resolved.explain(key)[0].overridden],
                         ["invocation", "env", "legacy", "project", "machine", "defaults"])

    def test_machine_then_project_then_lower_layers_win_in_order(self):
        self.machine("[demo]\nmode = \"fast\"\n")
        self.assertEqual(self.resolve().get("mode"), "fast")
        self.proj("[demo]\nmode = \"safe\"\n")
        self.assertEqual(self.resolve().get("mode"), "safe")
        self.assertEqual(self.resolve(project=None).get("mode"), "fast")

    def test_extra_layer_rules(self):
        for name in ("project", "flags", "Bad Name", ""):
            with self.subTest(name=name):
                with self.assertRaises(ConfigError):
                    self.resolve(extra_layers=[ExtraLayer(name, {"verbose": True})])
        with self.assertRaises(ConfigError) as caught:
            self.resolve(extra_layers=[ExtraLayer("legacy", ["not", "a", "table"])])
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")

    def test_extra_layer_is_validated_and_supports_operators(self):
        resolved = self.resolve(extra_layers=[ExtraLayer("legacy", {"_append": {"sources": ["old"]}})])
        self.assertEqual(resolved.get("sources"), ["local", "old"])
        with self.assertRaises(ConfigError) as caught:
            self.resolve(extra_layers=[ExtraLayer("legacy", {"nope": 1})])
        self.assertEqual((caught.exception.code, caught.exception.layer), ("CONFIG_UNKNOWN_KEY", "legacy"))

    def test_extra_layer_error_uses_its_file_and_index(self):
        index = config.toml.LineIndex.from_text("first = 1\nverbose = 2\n")
        extra = ExtraLayer("legacy", {"verbose": 2}, file="/old/demo.toml", index=index)
        with self.assertRaises(ConfigError) as caught:
            self.resolve(extra_layers=[extra])
        self.assertTrue(str(caught.exception).startswith("/old/demo.toml:2: legacy: verbose: "))

    def test_extra_layer_can_be_forbidden_by_x_skm_layers(self):
        with self.assertRaises(ConfigError) as caught:
            self.resolve(extra_layers=[ExtraLayer("legacy", {"cache_dir": "/x"})])
        self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")


class TestInvocationAndFlags(Workspace):
    def test_config_file_layer(self):
        file = self.write(self.root / "run.toml", "schema_version = 1\n[demo]\nmode = \"fast\"\n")
        resolved = self.resolve(config_file=file)
        self.assertEqual(resolved.get("mode"), "fast")
        self.assertEqual(resolved.layers[-2].file, str(file))
        self.assertTrue(resolved.layers[-2].present)

    def test_config_file_must_exist(self):
        with self.assertRaises(ConfigError) as caught:
            self.resolve(config_file=self.root / "absent.toml")
        self.assertEqual((caught.exception.code, caught.exception.layer), ("CONFIG_FILE_INVALID", "invocation"))

    def test_config_file_needs_a_version_too(self):
        file = self.write(self.root / "run.toml", "[demo]\nmode = \"fast\"\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve(config_file=file)
        self.assertEqual(caught.exception.code, "CONFIG_VERSION_MISSING")

    def test_flags_parse_text_by_type_and_skip_none(self):
        resolved = self.resolve(flags={"recompute.candidate_min_n": "42", "verbose": "yes", "recompute.ratio": "0.25",
                                       "sources": "[\"a\", \"b\"]", "mode": None})
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 42)
        self.assertIs(resolved.get("verbose"), True)
        self.assertEqual(resolved.get("recompute.ratio"), 0.25)
        self.assertEqual(resolved.get("sources"), ["a", "b"])
        self.assertEqual(resolved.get("mode"), "safe")

    def test_flags_accept_typed_values(self):
        resolved = self.resolve(flags={"recompute.candidate_min_n": 9, "sources": ["z"]})
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 9)
        self.assertEqual(resolved.get("sources"), ["z"])

    def test_flag_errors(self):
        with self.assertRaises(ConfigError) as caught:
            self.resolve(flags={"nope": "1"})
        self.assertEqual((caught.exception.code, caught.exception.layer), ("CONFIG_UNKNOWN_KEY", "flags"))
        with self.assertRaises(ConfigError) as caught:
            self.resolve(flags={"recompute.candidate_min_n": "many"})
        self.assertEqual((caught.exception.code, caught.exception.layer), ("CONFIG_TYPE", "flags"))
        with self.assertRaises(ConfigError) as caught:
            self.resolve(flags={"recompute.candidate_min_n": "0"})
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")

    def test_parse_value_is_the_one_text_parser(self):
        self.assertEqual(config.parse_value(self.schema, "recompute.candidate_min_n", " 12 "), 12)
        self.assertEqual(config.parse_value(self.schema, "sources", "[\"q\"]"), ["q"])
        with self.assertRaises(ConfigError) as caught:
            config.parse_value(self.schema, "verbose", "maybe")
        self.assertEqual((caught.exception.code, caught.exception.key), ("CONFIG_TYPE", "verbose"))
        with self.assertRaises(ConfigError) as caught:
            config.parse_value(self.schema, "nope", "1")
        self.assertEqual(caught.exception.code, "CONFIG_UNKNOWN_KEY")


class TestLeakOfInput(Workspace):
    def test_resolved_values_do_not_alias_the_inputs(self):
        data = {"sources": ["one"]}
        resolved = self.resolve(extra_layers=[ExtraLayer("legacy", data)])
        data["sources"].append("two")
        self.assertEqual(resolved.get("sources"), ["one"])
        self.assertEqual(copy.deepcopy(resolved.get("sources")), ["one"])


if __name__ == "__main__":
    unittest.main()
