"""The environment layer: SKM_<MODULE>_<PATH>, parsing by type, unknown variables and layer position."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore import config
from aicore.config import ConfigError

from tests.config.support import Workspace


class TestEnvironmentLayer(Workspace):
    def env_with(self, **variables):
        return {**self.env, **variables}

    def test_env_double_underscore_path(self):
        resolved = self.resolve(env=self.env_with(SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N="30",
                                                  SKM_DEMO_RECOMPUTE__WINDOW__DAYS="3", SKM_DEMO_VERBOSE="1"))
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 30)
        self.assertEqual(resolved.get("recompute.window.days"), 3)
        self.assertIs(resolved.get("verbose"), True)
        self.assertEqual(resolved.explain("verbose")[0].source, "SKM_DEMO_VERBOSE")

    def test_single_underscore_is_part_of_a_name_not_a_separator(self):
        resolved = self.resolve(env=self.env_with(SKM_DEMO_RECOMPUTE_CANDIDATE_MIN_N="30"))
        self.assertEqual(resolved.get("recompute.candidate_min_n"), 15)  # no such path: warned and skipped
        self.assertEqual(len(self.warnings), 1)

    def test_env_unknown_path_warns_once(self):
        env = self.env_with(SKM_DEMO_NOPE="1", SKM_DEMO_RECOMPUTE="2", SKM_DEMO_VERBOSE="true")
        first = self.resolve(env=env)
        second = self.resolve(env=env)
        self.assertTrue(first.get("verbose") and second.get("verbose"))  # known variables still apply
        self.assertEqual(len(self.warnings), 2)  # SKM_DEMO_NOPE and SKM_DEMO_RECOMPUTE, once each
        self.assertTrue(all("CONFIG_ENV_UNKNOWN" in message for message in self.warnings))
        self.assertEqual(len(first.warnings), 2)
        self.assertEqual(len(second.warnings), 2)  # recorded on every result, printed once per process

    def test_unknown_variable_is_reported_on_stderr_by_default(self):
        with mock.patch("sys.stderr") as stderr:
            config.resolve("demo", schema=self.schema, env=self.env_with(SKM_DEMO_NOPE="1"), project=self.project)
            config.resolve("demo", schema=self.schema, env=self.env_with(SKM_DEMO_NOPE="1"), project=self.project)
        written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertEqual(written.count("SKM_DEMO_NOPE"), 1)
        self.assertIn("warning:", written)

    def test_variables_of_other_modules_and_other_prefixes_are_ignored(self):
        resolved = self.resolve(env=self.env_with(SKM_OTHER_VERBOSE="1", SKM_VERBOSE="1", DEMO_VERBOSE="1",
                                                  SKM_DEMOX="1"))
        self.assertFalse(resolved.get("verbose"))
        self.assertEqual(self.warnings, [])

    def test_module_id_with_a_dash_maps_to_an_underscore(self):
        schema = json.loads(Path(self.schema.source).read_text(encoding="utf-8"))
        schema["$id"] = "urn:swissknifeman:my-mod:config:v1"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.schema.json"
            path.write_text(json.dumps(schema), encoding="utf-8")
            loaded = config.load_module_schema(path, "my-mod")
        resolved = config.resolve("my-mod", schema=loaded, env=self.env_with(SKM_MY_MOD_VERBOSE="true"),
                                  project=self.project)
        self.assertIs(resolved.get("verbose"), True)

    def test_names_match_without_regard_to_case_of_the_schema(self):
        # the schema names are lowercase; the variable path is the upper-cased dotted key
        resolved = self.resolve(env=self.env_with(SKM_DEMO_MODE="fast"))
        self.assertEqual(resolved.get("mode"), "fast")

    def test_parsing_by_type(self):
        cases = {
            "SKM_DEMO_MODE": ("fast", "mode", "fast"),
            "SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N": (" 40 ", "recompute.candidate_min_n", 40),
            "SKM_DEMO_RECOMPUTE__RATIO": ("0.75", "recompute.ratio", 0.75),
            "SKM_DEMO_SOURCES": ('["a", "b"]', "sources", ["a", "b"]),
        }
        for name, (text, key, expected) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.resolve(env=self.env_with(**{name: text})).get(key), expected)

    def test_boolean_forms(self):
        for text, expected in (("true", True), ("TRUE", True), ("1", True), ("yes", True), ("Yes", True),
                               ("false", False), ("0", False), ("no", False), ("NO", False)):
            with self.subTest(text=text):
                self.assertIs(self.resolve(env=self.env_with(SKM_DEMO_VERBOSE=text)).get("verbose"), expected)

    def test_unparseable_values(self):
        for name, text in (("SKM_DEMO_VERBOSE", "maybe"), ("SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N", "ten"),
                           ("SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N", "1.5"), ("SKM_DEMO_RECOMPUTE__RATIO", "nan"),
                           ("SKM_DEMO_RECOMPUTE__RATIO", "x"), ("SKM_DEMO_SOURCES", "a,b"),
                           ("SKM_DEMO_SOURCES", '{"a": 1}'), ("SKM_DEMO_SOURCES", "")):
            with self.subTest(name=name, text=text):
                with self.assertRaises(ConfigError) as caught:
                    self.resolve(env=self.env_with(**{name: text}))
                error = caught.exception
                self.assertEqual((error.code, error.layer), ("CONFIG_ENV_VALUE", "env"))
                self.assertIn(name, str(error))

    def test_parsed_value_is_still_validated_by_the_schema(self):
        for name, text in (("SKM_DEMO_RECOMPUTE__CANDIDATE_MIN_N", "0"), ("SKM_DEMO_MODE", "slow"),
                           ("SKM_DEMO_SOURCES", "[1]")):
            with self.subTest(name=name):
                with self.assertRaises(ConfigError) as caught:
                    self.resolve(env=self.env_with(**{name: text}))
                self.assertEqual((caught.exception.code, caught.exception.layer), ("CONFIG_TYPE", "env"))

    def test_env_is_above_files_and_below_the_invocation_file(self):
        self.machine("[demo]\nmode = \"fast\"\n")
        self.proj("[demo]\nmode = \"fast\"\nverbose = false\n")
        self.assertTrue(self.resolve(env=self.env_with(SKM_DEMO_VERBOSE="1")).get("verbose"))

    def test_invocation_between_env_and_flags(self):
        invocation = self.write(self.root / "run.toml", "schema_version = 1\n[demo]\nmode = \"fast\"\nverbose = true\n")
        env = self.env_with(SKM_DEMO_MODE="safe", SKM_DEMO_VERBOSE="false")
        resolved = self.resolve(env=env, config_file=invocation)
        self.assertEqual(resolved.get("mode"), "fast")  # --config beats the environment
        self.assertIs(resolved.get("verbose"), True)
        resolved = self.resolve(env=env, config_file=invocation, flags={"mode": "safe", "verbose": "false"})
        self.assertEqual(resolved.get("mode"), "safe")  # a flag beats --config
        self.assertIs(resolved.get("verbose"), False)

    def test_env_defaults_to_the_process_environment(self):
        with mock.patch.dict(os.environ, {"SKM_HOME": self.env["SKM_HOME"], "SKM_DEMO_MODE": "fast"}):
            resolved = config.resolve("demo", schema=self.schema, project=self.project, warn=self.warnings.append)
        self.assertEqual(resolved.get("mode"), "fast")

    def test_machine_file_follows_skm_home_and_xdg(self):
        other = self.root / "other-home"
        self.write(other / "config" / "config.toml", "schema_version = 1\n[demo]\nmode = \"fast\"\n")
        resolved = self.resolve(env={"SKM_HOME": str(other)})
        self.assertEqual(resolved.get("mode"), "fast")
        xdg = self.root / "xdg"
        self.write(xdg / "swissknifeman" / "config.toml", "schema_version = 1\n[demo]\nverbose = true\n")
        resolved = self.resolve(env={"XDG_CONFIG_HOME": str(xdg)}, home=self.root / "no-home")
        self.assertTrue(resolved.get("verbose"))


if __name__ == "__main__":
    unittest.main()
