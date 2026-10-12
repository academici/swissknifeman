"""Dictionary tables (maps) in the configuration model: schema, merging, checks, explain, editing and example."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from aicore import cli, config
from aicore.config import example, model

from .support import FIXTURES, Workspace

MAPS = FIXTURES / "maps"
SCHEMA_FILE = MAPS / "configs" / "config.schema.json"
ENTRY_KEY = "^[a-z][a-z0-9-]*$"


def load_schema() -> config.ModuleSchema:
    return config.load_module_schema(SCHEMA_FILE, "maps")


def schema_with(properties: dict, directory: Path, module_id: str = "maps") -> Path:
    doc = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"urn:swissknifeman:{module_id}:config:v1",
           "type": "object", "additionalProperties": False, "properties": properties}
    path = directory / "schema.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def a_map(pattern: str = ENTRY_KEY, value: object = None, **extra) -> dict:
    node = {"type": "object", "description": "A map.", "additionalProperties": False,
            "patternProperties": {pattern: value or {"type": "string", "description": "A value."}}}
    node.update(extra)
    return node


class MapsCase(Workspace):
    def setUp(self):
        super().setUp()
        self.schema = load_schema()

    def resolve(self, **kwargs):
        kwargs.setdefault("schema", self.schema)
        kwargs.setdefault("env", dict(self.env))
        kwargs.setdefault("project", self.project)
        kwargs.setdefault("warn", self.warnings.append)
        return config.resolve("maps", **kwargs)

    def errors(self, code, **kwargs):
        with self.assertRaises(config.ConfigError) as caught:
            self.resolve(**kwargs)
        self.assertEqual(code, caught.exception.code, str(caught.exception))
        return caught.exception


class TestSchema(unittest.TestCase):
    def test_maps_are_loaded_with_template_leaves(self):
        schema = load_schema()
        self.assertEqual({("hooks",), ("notes",), ("group", "items")}, set(schema.maps))
        hooks = schema.maps[("hooks",)]
        self.assertEqual(["run", "tags", "level", "enabled"], list(hooks.value_table))
        self.assertEqual(("hooks", "*", "run"), hooks.value_table["run"].key)
        self.assertIsNone(hooks.value_leaf)
        notes = schema.maps[("notes",)]
        self.assertEqual(("notes", "*"), notes.value_leaf.key)
        self.assertIsNone(notes.value_table)
        self.assertNotIn(("hooks", "*", "run"), schema.leaves)  # the fixed part holds no templates

    def test_classify_and_leaf_rewrite_the_template_to_the_entry(self):
        schema = load_schema()
        kinds = {"verbose": "leaf", "hooks": "map", "group": "table", "group.items": "map", "hooks.a": "entry",
                 "hooks.a.run": "leaf", "hooks.a:b.enabled": "leaf", "notes.a:b": "leaf", "group.items.xy": "leaf",
                 "hooks.A": None, "hooks.a.nothing": None, "hooks.a.run.x": None, "notes.ab": None, "nothing": None,
                 "hooks.a.b": None}
        for key, kind in kinds.items():
            with self.subTest(key=key):
                self.assertEqual(kind, schema.classify(key))
        leaf = schema.leaf("hooks.a.run")
        self.assertEqual(("hooks", "a", "run"), leaf.key)
        self.assertEqual(("defaults", "machine", "invocation", "flags"), leaf.layers)
        self.assertEqual(("notes", "x:y"), schema.leaf("notes.x:y").key)
        with self.assertRaises(config.ConfigError) as caught:
            schema.leaf("hooks.A.run")
        self.assertEqual("CONFIG_UNKNOWN_KEY", caught.exception.code)

    def test_refused_schemas(self):
        entry_table = {"type": "object", "description": "e", "additionalProperties": False,
                       "properties": {"x": {"type": "string", "description": "x"}}}
        leaf = {"type": "string", "description": "A value."}
        cases = {
            "unanchored pattern": a_map("[a-z]+"),
            "pattern without the end anchor": a_map("^[a-z]+"),
            "pattern that allows dots": a_map("^[a-z.]+$"),
            "pattern that matches everything": a_map("^.*$"),
            "two patterns": dict(a_map(), patternProperties={ENTRY_KEY: leaf, "^[0-9]+$": leaf}),
            "properties next to a pattern": dict(a_map(), properties={"x": leaf}),
            "open map": {k: v for k, v in a_map().items() if k != "additionalProperties"},
            "nested map": a_map(value={"type": "object", "description": "e", "additionalProperties": False,
                                       "patternProperties": {ENTRY_KEY: leaf}}),
            "table inside an entry": a_map(value=dict(entry_table, properties={"t": entry_table})),
            "entry without properties": a_map(value={"type": "object", "description": "e",
                                                     "additionalProperties": False, "properties": {}}),
            "open entry": a_map(value={k: v for k, v in entry_table.items() if k != "additionalProperties"}),
            "bad property name in an entry": a_map(value=dict(entry_table, properties={"Bad": leaf})),
            "leaf without description": a_map(value={"type": "string"}),
            "map without description": {k: v for k, v in a_map().items() if k != "description"},
            "unknown keyword": a_map(default={}),
            "entry that is neither a leaf nor a table": a_map(value={"type": "object", "description": "e"}),
        }
        for name, node in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                path = schema_with({"things": node}, Path(tmp))
                with self.assertRaises(config.ConfigError) as caught:
                    config.load_module_schema(path, "maps")
                self.assertEqual("CONFIG_SCHEMA_INVALID", caught.exception.code, str(caught.exception))

    def test_dot_message_names_the_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(config.ConfigError, "map keys cannot contain dots"):
                config.load_module_schema(schema_with({"things": a_map("^[a-z.]+$")}, Path(tmp)), "maps")

    def test_patterns_that_can_consume_a_dot_are_refused(self):
        """Not only a pattern that matches 'a.b': an escaped dot or a class with a dot are unreachable by dotted keys."""
        for pattern in (r"^x\.y$", r"^(?!a\.b$)[a-z.]+$", r"^.+$", r"^[^a]+$", r"^\S+$", r"^\W+$", r"^(a|b\.)c$",
                        r"^(a)?(?(1)\.|x)$"):
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(config.ConfigError, "map keys cannot contain dots"):
                    config.load_module_schema(schema_with({"things": a_map(pattern)}, Path(tmp)), "maps")
        for pattern in (r"^(?!a\.b$)[a-z]+$", r"^[a-z][a-z0-9-]*(:[a-z][a-z0-9-]*)?$", r"^[a-z]{1,3}$"):
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as tmp:
                config.load_module_schema(schema_with({"things": a_map(pattern)}, Path(tmp)), "maps")

    def test_template_defaults_are_checked(self):
        leaf = {"type": "integer", "minimum": 1, "default": 0, "description": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(config.ConfigError) as caught:
                config.load_module_schema(schema_with({"things": a_map(value=leaf)}, Path(tmp)), "maps")
        self.assertEqual("CONFIG_SCHEMA_INVALID", caught.exception.code)

    def test_a_schema_without_maps_is_unchanged(self):
        schema = config.load_module_schema(FIXTURES / "demo.config.schema.json", "demo")
        self.assertEqual({}, schema.maps)
        self.assertIsNone(schema.classify("nothing"))


class TestResolve(MapsCase):
    def test_no_entries_by_default(self):
        cfg = self.resolve()
        self.assertEqual({}, cfg.get("hooks"))
        self.assertEqual({}, cfg.get("notes"))
        self.assertEqual({"verbose": False, "hooks": {}, "notes": {}, "group": {"title": "none", "items": {}}},
                         cfg.as_dict())
        self.assertIsNone(cfg.get("hooks.a"))
        self.assertEqual("fallback", cfg.get("hooks.a", "fallback"))
        self.assertIsNone(cfg.get("hooks.a.enabled"))  # the entry does not exist
        self.assertEqual([], [e.key for e in cfg.explain("hooks")])

    def test_an_entry_gets_the_defaults_of_its_leaves(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\n')
        cfg = self.resolve()
        self.assertEqual(["make"], cfg.get("hooks.build.run"))
        self.assertIs(True, cfg.get("hooks.build.enabled"))
        self.assertEqual([], cfg.get("hooks.build.tags"))
        self.assertIsNone(cfg.get("hooks.build.level"))
        self.assertEqual({"run": ["make"], "tags": [], "enabled": True}, cfg.get("hooks.build"))
        self.assertEqual({"build": {"run": ["make"], "tags": [], "enabled": True}}, cfg.as_dict()["hooks"])
        self.assertEqual(7, cfg.get("hooks.build.level", 7))

    def test_entries_merge_by_key_across_layers(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\nlevel = 2\n[maps.hooks.lint]\nrun = ["ruff"]\n')
        self.proj('[maps.hooks.build]\nenabled = false\nlevel = 5\n')
        cfg = self.resolve()
        self.assertEqual(["make"], cfg.get("hooks.build.run"))  # from machine
        self.assertIs(False, cfg.get("hooks.build.enabled"))  # from project
        self.assertEqual(5, cfg.get("hooks.build.level"))  # project replaced the machine value
        self.assertEqual(["ruff"], cfg.get("hooks.lint.run"))
        self.assertEqual(["build", "lint"], list(cfg.get("hooks")))

    def test_unset_removes_an_entry_or_resets_a_leaf(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\nlevel = 2\nenabled = false\n[maps.hooks.lint]\nrun = ["x"]\n')
        self.proj('[maps]\n_unset = ["hooks.build.enabled"]\n')
        cfg = self.resolve()
        self.assertIs(True, cfg.get("hooks.build.enabled"))  # back to the default
        self.proj('[maps]\n_unset = ["hooks.lint"]\n')
        self.errors("CONFIG_LAYER_FORBIDDEN")  # the project may not remove a hook that has a command
        self.proj('[maps]\n_unset = ["hooks.build.level"]\n')
        self.assertIsNone(self.resolve().get("hooks.build.level"))

    def test_unset_of_an_entry_in_a_layer_that_may_define_it(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\n[maps.hooks.lint]\nrun = ["x"]\n')
        flags_less = Path(self.root) / "invocation.toml"
        flags_less.write_text('schema_version = 1\n[maps]\n_unset = ["hooks.build"]\n', encoding="utf-8")
        cfg = self.resolve(config_file=flags_less)
        self.assertEqual(["lint"], list(cfg.get("hooks")))
        self.assertIsNone(cfg.get("hooks.build"))
        self.assertEqual([], [e.key for e in cfg.explain("hooks.build")])
        flags_less.write_text('schema_version = 1\n[maps]\n_unset = ["hooks"]\n', encoding="utf-8")
        self.assertEqual({}, self.resolve(config_file=flags_less).get("hooks"))
        flags_less.write_text('schema_version = 1\n[maps]\n_unset = ["hooks.nothere", "notes.a:b"]\n', encoding="utf-8")
        self.assertEqual(["build", "lint"], list(self.resolve(config_file=flags_less).get("hooks")))

    def test_an_unset_entry_can_be_defined_again_by_a_higher_layer(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\nlevel = 3\n')
        again = Path(self.root) / "again.toml"
        again.write_text('schema_version = 1\n[maps]\n_unset = ["hooks.build"]\n[maps.hooks.build]\nrun = ["ninja"]\n',
                         encoding="utf-8")
        cfg = self.resolve(config_file=again)
        self.assertEqual({"run": ["ninja"], "tags": [], "enabled": True}, cfg.get("hooks.build"))

    def test_unset_of_a_table_removes_the_entries_of_the_maps_below_it(self):
        self.machine('[maps.group]\ntitle = "t"\n[maps.group.items]\nab = 4\n')
        gone = Path(self.root) / "gone.toml"
        gone.write_text('schema_version = 1\n[maps]\n_unset = ["group"]\n', encoding="utf-8")
        cfg = self.resolve(config_file=gone)
        self.assertEqual({"title": "none", "items": {}}, cfg.get("group"))

    def test_append_works_inside_an_entry(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\ntags = ["a"]\n[maps.notes]\n"core:plan" = ["a.md"]\n')
        self.proj('[maps]\n_append = {"hooks.build.tags" = ["b"], "notes.core:plan" = ["b.md"]}\n')
        cfg = self.resolve()
        self.assertEqual(["a", "b"], cfg.get("hooks.build.tags"))
        self.assertEqual(["a.md", "b.md"], cfg.get("notes.core:plan"))
        self.proj('[maps]\n_append = {"notes.core:other" = ["c.md"]}\n')
        self.assertEqual(["c.md"], self.resolve().get("notes.core:other"))  # appending creates the entry
        self.proj('[maps]\n_append = {"hooks.build.tags" = ["b"]}\n[maps.hooks.build]\ntags = ["z"]\n')
        self.errors("CONFIG_CONFLICT")

    def test_a_leaf_valued_map(self):
        self.machine('[maps.notes]\n"core:plan" = ["a.md", "b.md"]\n')
        cfg = self.resolve()
        self.assertEqual(["a.md", "b.md"], cfg.get("notes.core:plan"))
        self.assertEqual({"core:plan": ["a.md", "b.md"]}, cfg.get("notes"))
        reset = Path(self.root) / "reset.toml"
        reset.write_text('schema_version = 1\n[maps]\n_unset = ["notes.core:plan"]\n', encoding="utf-8")
        self.assertEqual({}, self.resolve(config_file=reset).get("notes"))

    def test_a_map_inside_a_table(self):
        self.machine('[maps.group.items]\nab = 4\ncd = 0\n')
        cfg = self.resolve()
        self.assertEqual({"ab": 4, "cd": 0}, cfg.get("group.items"))
        self.assertEqual({"title": "none", "items": {"ab": 4, "cd": 0}}, cfg.get("group"))

    def test_unknown_keys_and_names_outside_the_pattern(self):
        for body, key in (('[maps.hooks.build]\nrun = ["x"]\nnothing = 1\n', "hooks.build.nothing"),
                          ('[maps.hooks.Bad]\nrun = ["x"]\n', "hooks.Bad"),
                          ('[maps.hooks."a.b"]\nrun = ["x"]\n', "hooks.a.b"),
                          ('[maps.notes]\nplain = ["x"]\n', "notes.plain"),
                          ('[maps]\nhooks = 1\n', None)):
            with self.subTest(body=body):
                self.machine(body)
                self.errors("CONFIG_UNKNOWN_KEY" if key else "CONFIG_TYPE")

    def test_values_of_an_entry_are_checked(self):
        for body in ('[maps.hooks.build]\nlevel = 10\n', '[maps.hooks.build]\nrun = "make"\n',
                     '[maps.hooks.build]\nrun = [""]\n', '[maps.notes]\n"a:b" = "x"\n'):
            with self.subTest(body=body):
                self.machine(body)
                self.errors("CONFIG_TYPE")

    def test_layer_restriction_applies_to_the_leaves_of_every_entry(self):
        self.proj('[maps.hooks.build]\nrun = ["make"]\n')
        error = self.errors("CONFIG_LAYER_FORBIDDEN")
        self.assertEqual("hooks.build.run", error.key)
        self.assertEqual("project", error.layer)
        self.assertEqual(3, error.line)
        self.proj('[maps.hooks.build]\nenabled = false\ntags = ["x"]\n')  # allowed in every layer
        self.assertIs(False, self.resolve().get("hooks.build.enabled"))
        self.proj('[maps]\n_append = {"hooks.build.run" = ["x"]}\n')
        self.errors("CONFIG_LAYER_FORBIDDEN")

    def test_flags_set_entry_leaves(self):
        cfg = self.resolve(flags={"hooks.build.run": '["make"]', "hooks.build.level": "3", "notes.a:b": '["x"]'})
        self.assertEqual(["make"], cfg.get("hooks.build.run"))
        self.assertEqual(3, cfg.get("hooks.build.level"))
        self.assertEqual(["x"], cfg.get("notes.a:b"))
        with self.assertRaises(config.ConfigError) as caught:
            self.resolve(flags={"hooks.Build.run": '["x"]'})
        self.assertEqual("CONFIG_UNKNOWN_KEY", caught.exception.code)

    def test_environment_cannot_address_entries(self):
        env = dict(self.env, SKM_MAPS_HOOKS__BUILD__RUN='["x"]', SKM_MAPS_VERBOSE="true")
        cfg = self.resolve(env=env)
        self.assertIs(True, cfg.get("verbose"))
        self.assertEqual({}, cfg.get("hooks"))
        self.assertEqual(1, len(self.warnings), self.warnings)
        self.assertIn("CONFIG_ENV_UNKNOWN", self.warnings[0])
        self.assertIn("SKM_MAPS_HOOKS__BUILD__RUN", self.warnings[0])
        self.assertIn("entry", self.warnings[0])
        self.assertEqual(self.warnings, list(cfg.warnings))
        self.resolve(env=env)
        self.assertEqual(1, len(self.warnings))  # once per variable and process


class TestExplain(MapsCase):
    def test_entry_leaves_are_explained_with_their_layers(self):
        self.machine('[maps.hooks.build]\nrun = ["make"]\nlevel = 2\n')
        self.proj('[maps.hooks.build]\nlevel = 5\nenabled = false\n')
        cfg = self.resolve()
        entries = {e.key: e for e in cfg.explain("hooks")}
        self.assertEqual(["hooks.build.run", "hooks.build.tags", "hooks.build.level", "hooks.build.enabled"],
                         list(entries))  # in the order of the template
        level = entries["hooks.build.level"]
        self.assertEqual(("project", self.proj_line("level")), (level.layer, level.line))
        self.assertEqual(["machine"], [item.layer for item in level.overridden])
        self.assertEqual("defaults", entries["hooks.build.tags"].layer)
        self.assertEqual("project", entries["hooks.build.enabled"].layer)
        self.assertEqual(["defaults"], [item.layer for item in entries["hooks.build.enabled"].overridden])
        self.assertEqual(["hooks.build.level"], [e.key for e in cfg.explain("hooks.build.level")])
        self.assertEqual(4, len(cfg.explain("hooks.build")))
        text = cfg.explain_text("hooks.build.level")
        self.assertIn("hooks.build.level = 5", text)
        self.assertIn("overrides machine", text)

    def proj_line(self, name):
        for number, line in enumerate(self.project_file.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith(name):
                return number

    def test_explain_of_unknown_or_foreign_keys(self):
        cfg = self.resolve()
        with self.assertRaises(config.ConfigError) as caught:
            cfg.explain("hooks.Bad")
        self.assertEqual("CONFIG_UNKNOWN_KEY", caught.exception.code)
        self.assertEqual([], cfg.explain("hooks.build"))

    def test_entries_come_in_order_of_first_appearance_after_the_fixed_keys(self):
        self.machine('[maps.hooks.zeta]\nrun = ["z"]\n[maps.hooks.alpha]\nrun = ["a"]\n[maps.notes]\n"a:b" = ["x"]\n')
        keys = [entry.key for entry in self.resolve().explain()]
        self.assertEqual(["verbose", "group.title"], keys[:2])
        self.assertLess(keys.index("hooks.zeta.run"), keys.index("hooks.alpha.run"))
        self.assertLess(keys.index("hooks.alpha.enabled"), keys.index("notes.a:b"))
        doc = self.resolve().explain_json("hooks.zeta")
        self.assertEqual({"hooks.zeta.run", "hooks.zeta.tags", "hooks.zeta.enabled"},
                         {entry["key"] for entry in doc["entries"]})


class MapsCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.project = self.tmp / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"), "SKM_UNITS_PATH": str(MAPS)}
        self.machine_file = self.tmp / "skm" / "config" / "config.toml"
        self.project_file = self.project / ".swissknifeman" / "config.toml"

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), env=self.env, cwd=self.project, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_set_and_unset_a_key_of_an_entry(self):
        code, out, err = self.run_cli("config", "set", "maps.hooks.build.run", '["make", "-j"]', "--machine")
        self.assertEqual((0, ""), (code, err), out)
        self.assertEqual('schema_version = 1\n\n[maps.hooks.build]\nrun = ["make", "-j"]\n',
                         self.machine_file.read_text(encoding="utf-8").replace("\n\n\n", "\n\n"))
        self.assertEqual(0, self.run_cli("config", "set", "maps.hooks.build.level", "4", "--machine")[0])
        code, out, _ = self.run_cli("config", "show", "maps")
        self.assertEqual(0, code)
        self.assertIn(f'hooks.build.run = ["make", "-j"]  # machine {self.machine_file}', out)
        self.assertIn("hooks.build.level = 4", out)
        self.assertIn("hooks.build.enabled = true  # defaults", out)
        self.assertEqual(0, self.run_cli("config", "unset", "maps.hooks.build.level", "--machine")[0])
        self.assertNotIn("hooks.build.level", self.run_cli("config", "show", "maps")[1])

    def test_set_quotes_a_key_with_a_colon(self):
        code, _, err = self.run_cli("config", "set", "maps.notes.core:plan", '["/x.md"]', "--machine")
        self.assertEqual((0, ""), (code, err))
        text = self.machine_file.read_text(encoding="utf-8")
        self.assertIn('[maps.notes]', text)
        self.assertIn('"core:plan" = ["/x.md"]', text)
        code, out, _ = self.run_cli("config", "explain", "maps", "notes.core:plan", "--json")
        self.assertEqual(0, code)
        entry = json.loads(out)["entries"][0]
        self.assertEqual(("notes.core:plan", ["/x.md"], "machine"), (entry["key"], entry["value"], entry["layer"]))

    def test_set_refuses_a_forbidden_layer_a_bad_name_and_a_bad_value(self):
        code, _, err = self.run_cli("config", "set", "maps.hooks.build.run", '["x"]', "--project")
        self.assertEqual(1, code)
        self.assertIn("CONFIG_LAYER_FORBIDDEN", err)
        self.assertFalse(self.project_file.exists())
        code, _, err = self.run_cli("config", "set", "maps.hooks.Build.enabled", "false", "--project")
        self.assertEqual(1, code)
        self.assertIn("CONFIG_UNKNOWN_KEY", err)
        code, _, err = self.run_cli("config", "set", "maps.hooks.build.level", "99", "--machine")
        self.assertEqual(1, code)
        self.assertIn("CONFIG_TYPE", err)
        code, _, err = self.run_cli("config", "set", "maps.hooks.build.enabled", "false", "--project")
        self.assertEqual((0, ""), (code, err))

    def test_init_writes_the_maps_as_empty_tables(self):
        code, _, err = self.run_cli("config", "init", "--machine", "--module", "maps")
        self.assertEqual((0, ""), (code, err))
        text = self.machine_file.read_text(encoding="utf-8")
        self.assertIn("[maps.hooks]\n", text)
        self.assertIn("# [maps.hooks.example]\n", text)
        self.assertEqual(0, self.run_cli("config", "show", "maps")[0])  # the copy is a valid, empty layer


class TestExample(unittest.TestCase):
    EXPECTED = '''\
# maps configuration, generated from configs/config.schema.json; do not edit by hand.
# Copy into ~/.config/swissknifeman/config.toml or <project>/.swissknifeman/config.toml
# (swissknifeman config init does it) and uncomment the keys you change.
schema_version = 1

[maps]
# Print details. Boolean.
# verbose = false

[maps.hooks]
# Hooks by id.
# [maps.hooks.example]

# Command to run. Array of strings.
# Allowed in layers: defaults, machine, invocation, flags.
# run = <array>

# Labels. Array of strings.
# tags = []

# Severity. Integer >= 1 and <= 9.
# level = <integer>

# Switch the hook off. Boolean.
# enabled = true

[maps.notes]
# Note files by slot <module>:<slot>.
# Files of the slot. Array of strings.
# "module:example" = []

[maps.group]
# Title. String.
# title = "none"

[maps.group.items]
# Items by name.
# Count. Integer >= 0.
# example = 1
'''

    def test_the_example_of_the_fixture(self):
        self.maxDiff = None
        self.assertEqual(self.EXPECTED, example.render(load_schema()))

    def test_the_example_is_a_valid_empty_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skm" / "config").mkdir(parents=True)
            (root / "skm" / "config" / "config.toml").write_text(example.render(load_schema()), encoding="utf-8")
            cfg = config.resolve("maps", schema=load_schema(), env={"SKM_HOME": str(root / "skm")})
            self.assertEqual({}, cfg.get("hooks"))

    def test_a_pattern_that_accepts_no_example_name_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = schema_with({"things": a_map("^[0-9]+$")}, Path(tmp))
            schema = config.load_module_schema(path, "maps")
            with self.assertRaisesRegex(config.ConfigError, "cannot render an example key"):
                example.render(schema)

    def test_a_pattern_with_a_colon_uses_the_module_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            pattern = "^[a-z]+:[a-z]+$"
            schema = config.load_module_schema(schema_with({"things": a_map(pattern)}, Path(tmp)), "maps")
            self.assertIn('# "module:example" = <string>', example.render(schema))

    def test_a_sample_entry_of_an_enum_leaf_shows_the_first_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = {"type": "string", "description": "An engine.", "enum": ["alpha", "beta"]}
            node = {"type": "object", "description": "A map.", "additionalProperties": False,
                    "patternProperties": {"^[a-z]+$": entry}}
            schema = config.load_module_schema(schema_with({"things": node}, Path(tmp)), "maps")
            self.assertIn('# example = "alpha"', example.render(schema))


class TestAicoreSchema(Workspace):
    """The schema of the foundation itself (events, subscriptions, plugins, overlays)."""

    FOUNDATION = Path(__file__).resolve().parents[2]

    def setUp(self):
        super().setUp()
        self.schema = config.load_module_schema(self.FOUNDATION / "configs" / "config.schema.json", "aicore")

    def resolve(self, **kwargs):
        kwargs.setdefault("schema", self.schema)
        kwargs.setdefault("env", dict(self.env))
        kwargs.setdefault("project", self.project)
        kwargs.setdefault("warn", self.warnings.append)
        return config.resolve("aicore", **kwargs)

    def test_unit_declares_the_schema(self):
        unit = json.loads((self.FOUNDATION / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual("configs/config.schema.json", unit["provides"]["config"])
        cfg = config.resolve("aicore", unit_root=self.FOUNDATION, env=dict(self.env), project=self.project)
        self.assertEqual("background", cfg.get("events.delivery"))

    def test_defaults_and_maps(self):
        cfg = self.resolve()
        self.assertEqual(("background", 30, 3), (cfg.get("events.delivery"), cfg.get("events.timeout_seconds"),
                                                   cfg.get("events.max_attempts")))
        self.assertEqual({"subscriptions": {}, "plugins": {}, "overlays": {}},
                         {name: cfg.get(name) for name in ("subscriptions", "plugins", "overlays")})
        self.assertEqual({"events", "subscriptions", "plugins", "overlays", "providers"}, set(cfg.as_dict()))
        self.assertEqual({"contract_version": "1.0.0", "selection": {}}, cfg.get("providers"))

    def test_a_subscription_and_an_overlay_from_the_machine_file(self):
        self.machine('[aicore.subscriptions.notes]\non = ["planner.plan.closed"]\nrun = ["true"]\n'
                     '[aicore.overlays]\n"planner:plan-design" = ["/x.md"]\n')
        cfg = self.resolve()
        self.assertIs(True, cfg.get("subscriptions.notes.enabled"))
        self.assertEqual([], cfg.get("subscriptions.notes.projects"))
        self.assertEqual(["true"], cfg.get("subscriptions.notes.run"))
        self.assertEqual(["/x.md"], cfg.get("overlays.planner:plan-design"))
        self.assertIsNone(cfg.get("subscriptions.notes.timeout_seconds"))

    def test_module_subscription_ids_and_plugin_ids(self):
        self.machine('[aicore.subscriptions."planner:notify"]\nenabled = false\n[aicore.plugins.fmt]\n'
                     'manifest = "~/plugins/fmt/extension.json"\ntrusted = true\n')
        cfg = self.resolve()
        self.assertIs(False, cfg.get("subscriptions.planner:notify.enabled"))
        self.assertIs(True, cfg.get("plugins.fmt.trusted"))
        self.assertEqual(60, cfg.get("plugins.fmt.timeout_seconds"))

    def test_the_project_cannot_define_what_runs(self):
        for body, key in (('[aicore.subscriptions.x]\nrun = ["true"]\n', "subscriptions.x.run"),
                          ('[aicore.subscriptions.x]\non = ["a.b"]\n', "subscriptions.x.on"),
                          ('[aicore.subscriptions.x]\nplugin = "p"\n', "subscriptions.x.plugin"),
                          ('[aicore.subscriptions.x]\nprojects = ["/r"]\n', "subscriptions.x.projects"),
                          ('[aicore.subscriptions.x]\ntimeout_seconds = 5\n', "subscriptions.x.timeout_seconds"),
                          ('[aicore.plugins.p]\nmanifest = "/m.json"\n', "plugins.p.manifest"),
                          ('[aicore.plugins.p]\ntrusted = true\n', "plugins.p.trusted"),
                          ('[aicore.plugins.p]\ntimeout_seconds = 5\n', "plugins.p.timeout_seconds")):
            with self.subTest(key=key):
                self.proj(body)
                with self.assertRaises(config.ConfigError) as caught:
                    self.resolve()
                self.assertEqual(("CONFIG_LAYER_FORBIDDEN", key, "project"),
                                 (caught.exception.code, caught.exception.key, caught.exception.layer))

    def test_the_project_may_switch_off_and_add_overlays(self):
        self.machine('[aicore.subscriptions.notes]\non = ["a.b"]\nrun = ["true"]\n[aicore.plugins.fmt]\n'
                     'manifest = "/m.json"\n')
        self.proj('[aicore.subscriptions.notes]\nenabled = false\n[aicore.plugins.fmt]\nenabled = false\n'
                  '[aicore.overlays]\n"planner:plan-design" = ["rules.md"]\n')
        cfg = self.resolve()
        self.assertIs(False, cfg.get("subscriptions.notes.enabled"))
        self.assertIs(False, cfg.get("plugins.fmt.enabled"))
        self.assertEqual(["true"], cfg.get("subscriptions.notes.run"))
        self.assertEqual(["rules.md"], cfg.get("overlays.planner:plan-design"))
        self.assertEqual("project", [e for e in cfg.explain("subscriptions.notes.enabled")][0].layer)

    def test_names_and_values_are_checked(self):
        for body in ('[aicore.subscriptions.Bad]\nenabled = false\n', '[aicore.plugins."a:b"]\nenabled = false\n',
                     '[aicore.overlays]\nplain = ["x"]\n', '[aicore.events]\ndelivery = "later"\n',
                     '[aicore.events]\nmax_attempts = 0\n', '[aicore.plugins.p]\ntimeout_seconds = 4000\n'):
            with self.subTest(body=body):
                self.machine(body)
                with self.assertRaises(config.ConfigError):
                    self.resolve()

    def test_the_example_matches_the_schema(self):
        text = (self.FOUNDATION / "config.example.toml").read_text(encoding="utf-8")
        self.assertEqual(example.render(self.schema), text)


if __name__ == "__main__":
    unittest.main()
