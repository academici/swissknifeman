"""Typed media gate `.swissknife.json` (plan).

Two invariants for which it was created `ProjectConfig`:
  1) the list of config keys has ONE medium - object fields; `CONFIG_KEYS`
     is derived from them and must match the literal that lived in `common.py`
     before editing (the photo below was taken on `d9bf22d9` — commit BEFORE item-commit P6.2);
  2) changing media does not change boot BEHAVIOR: same `die`/`warn`, same
     empty config without file, same values (including both forms `memory_brain`
     and `_`/`$`-keys), same `raw` for the provider branch.
"""
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from dataclasses import FrozenInstanceError
from pathlib import Path

from skiller.common import CONFIG_KEYS, Env
from skiller.config import ProjectConfig, load_config, provider_config_layer

# Public snapshot of CONFIG_KEYS. The additive `plugins` key is part of the current
# schema; names, types and order remain guarded because `skiller doctor` and
# test_schema.py consume them, including the memory_brain oneOf tuple.
EXPECTED_CONFIG_KEYS = {
    "project_type": str, "buckets": list, "plugins": list,
    "exclude": list, "presets": list,
    "skills_path": str, "agent": str,
    "providers": dict,
    "memory_brain": (str, dict), "coordinator_ignore": list,
    "shape": str, "stacks": list, "skills_map": dict,
    "policy_profile": str,
}

FULL_CONFIG = {
    "$schema": "../schema/swissknife.schema.json",
    "_comment": "DX-key: not validated, but must survive loading",
    "project_type": "fixture",
    "buckets": ["general"],
    "plugins": ["task"],
    "exclude": ["system/shared-memory"],
    "presets": [],
    "skills_path": ".claude/skills",
    "agent": "claude",
    "providers": {"contract_version": "1.0.0", "selection": {"codex": {"enabled": True}}},
    "memory_brain": {"path": "/synthetic/brain"},
    "coordinator_ignore": ["x"],
    "shape": "backend",
    "stacks": ["python"],
    "skills_map": {"backend": ["python/py-arch"]},
    "policy_profile": "base",
}


class _Fixture:
    """Synthetic registry + project: at the root of THIS repository `.swissknife.json`
    is not present, so the fixture is built in a temporary directory."""

    def __init__(self, tmp, contents=None, profile="fixture"):
        root = tmp / "registry"
        (root / "profiles").mkdir(parents=True)
        (root / "profiles" / f"{profile}.json").write_text("{}\n", encoding="utf-8")
        self.env = Env(root, home=tmp / "home")
        self.project = tmp / "project"
        self.project.mkdir()
        self.path = self.project / ".swissknife.json"
        if contents is not None:
            self.path.write_text(json.dumps(contents, indent=2) + "\n", encoding="utf-8")


@contextmanager
def fixture(contents=None, profile="fixture"):
    with tempfile.TemporaryDirectory() as tmp:
        yield _Fixture(Path(tmp), contents, profile)


class TestConfigKeysSingleCarrier(unittest.TestCase):
    def test_config_keys_match_the_public_snapshot(self):
        self.assertEqual(CONFIG_KEYS, EXPECTED_CONFIG_KEYS)

    def test_key_order_is_preserved(self):
        self.assertEqual(list(CONFIG_KEYS), list(EXPECTED_CONFIG_KEYS))

    def test_multitype_member_is_a_tuple_not_a_flattened_type(self):
        # The schema gate expands the tuple to oneOf; flattening it into str, we would silently
        # changed the verdict `doctor`/`test_schema` by memory_brain.
        self.assertEqual(CONFIG_KEYS["memory_brain"], (str, dict))

    def test_common_reexports_the_derived_object_itself(self):
        from skiller import config as config_module
        self.assertIs(CONFIG_KEYS, config_module.CONFIG_KEYS)

    def test_fields_without_json_type_are_not_config_keys(self):
        # `raw` — object field, but NOT file key.
        self.assertNotIn("raw", CONFIG_KEYS)


class TestProjectConfigLoad(unittest.TestCase):
    def test_missing_file_gives_empty_config_with_defaults(self):
        with fixture() as fx:
            config = load_config(fx.env, fx.project)
        self.assertIsInstance(config, ProjectConfig)
        self.assertFalse(config)                      # old behavior: empty config
        self.assertEqual(config.raw, {})
        self.assertEqual(config.buckets, [])
        self.assertEqual(config.skills_path, "")
        self.assertIsNone(config.providers)
        self.assertIsNone(config.memory_brain)

    def test_every_config_key_is_read_through_an_attribute(self):
        with fixture(FULL_CONFIG) as fx, redirect_stderr(io.StringIO()):
            config = load_config(fx.env, fx.project)  # stderr — _RESERVED-warnings
        for key in CONFIG_KEYS:
            self.assertEqual(getattr(config, key), FULL_CONFIG[key], key)

    def test_dx_keys_survive_load_and_stay_out_of_fields(self):
        with fixture(FULL_CONFIG) as fx, redirect_stderr(io.StringIO()):
            config = load_config(fx.env, fx.project)
        self.assertEqual(config["_comment"], FULL_CONFIG["_comment"])
        self.assertEqual(config["$schema"], FULL_CONFIG["$schema"])
        self.assertEqual(config.raw, FULL_CONFIG)     # raw — source dictionary as is

    def test_memory_brain_accepts_both_forms(self):
        for value in ("/synthetic/brain", {"path": "/synthetic/brain", "sync": {}}):
            with self.subTest(form=type(value).__name__), fixture({"memory_brain": value}) as fx:
                config = load_config(fx.env, fx.project)
                self.assertEqual(config.memory_brain, value)

    def test_memory_brain_object_without_path_dies_with_the_same_text(self):
        err = io.StringIO()
        with fixture({"memory_brain": {"sync": {}}}) as fx:
            with self.assertRaises(SystemExit), redirect_stderr(err):
                load_config(fx.env, fx.project)
            self.assertEqual(
                err.getvalue(),
                f"ERROR: {fx.path}: 'memory_brain' object must have a non-empty 'path'\n")

    def test_unknown_key_dies_with_the_same_text_and_hint(self):
        err = io.StringIO()
        with fixture({"bucket": ["general"]}) as fx:
            with self.assertRaises(SystemExit), redirect_stderr(err):
                load_config(fx.env, fx.project)
            self.assertEqual(
                err.getvalue(),
                f"ERROR: {fx.path}: unknown key 'bucket' — did you mean 'buckets'?\n")

    def test_wrong_type_dies_with_the_same_text(self):
        err = io.StringIO()
        with fixture({"buckets": "general"}) as fx:
            with self.assertRaises(SystemExit), redirect_stderr(err):
                load_config(fx.env, fx.project)
            self.assertEqual(err.getvalue(),
                             f"ERROR: {fx.path}: 'buckets' must be a list of strings\n")

    def test_reserved_keys_still_warn(self):
        err = io.StringIO()
        with fixture({"shape": "backend", "stacks": ["python"],
                      "skills_map": {"backend": []}, "coordinator_ignore": ["x"]}) as fx:
            with redirect_stderr(err):
                config = load_config(fx.env, fx.project)
        warnings = err.getvalue().splitlines()
        self.assertEqual([w.split(": ")[2] for w in warnings],
                         ["'skills_map' reserved but not yet implemented - ignored",
                          "'shape' reserved for agent-packs, not yet implemented - ignored",
                          "'stacks' reserved for agent-packs, not yet implemented - ignored",
                          "'coordinator_ignore' legacy-key without consumer - ignored"])
        self.assertEqual(config.shape, "backend")

    def test_invalid_json_dies_with_the_same_prefix(self):
        err = io.StringIO()
        with fixture() as fx:
            fx.path.write_text("{", encoding="utf-8")
            with self.assertRaises(SystemExit), redirect_stderr(err):
                load_config(fx.env, fx.project)
            self.assertTrue(err.getvalue().startswith(f"ERROR: {fx.path}: invalid JSON: "),
                            err.getvalue())

    def test_load_does_not_rewrite_the_file(self):
        with fixture(FULL_CONFIG) as fx:
            before = fx.path.read_bytes()
            with redirect_stderr(io.StringIO()):
                load_config(fx.env, fx.project)
            self.assertEqual(fx.path.read_bytes(), before)


class TestBackCompatSurface(unittest.TestCase):
    """Consumers not yet converted to attributes (integrate/quality/hub and alien
    code), are required to continue reading the config as a mapping."""

    def setUp(self):
        self.config = ProjectConfig.from_raw(dict(FULL_CONFIG))

    def test_mapping_reads_match_the_raw_dict(self):
        self.assertEqual(self.config.get("agent"), "claude")
        self.assertEqual(self.config["buckets"], ["general"])
        self.assertIsNone(self.config.get("unknown"))
        self.assertIn("policy_profile", self.config)
        self.assertEqual(dict(self.config), FULL_CONFIG)
        self.assertEqual(self.config, FULL_CONFIG)
        self.assertEqual(len(self.config), len(FULL_CONFIG))

    def test_empty_config_is_falsy_like_the_old_empty_dict(self):
        self.assertFalse(ProjectConfig())
        self.assertEqual(dict(ProjectConfig()), {})

    def test_object_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.config.agent = "cursor"

    def test_coerce_accepts_dict_and_passes_objects_through(self):
        coerced = ProjectConfig.coerce({"agent": "cursor"})
        self.assertEqual(coerced.agent, "cursor")
        self.assertIs(ProjectConfig.coerce(self.config), self.config)
        self.assertEqual(ProjectConfig.coerce(None).raw, {})

    def test_provider_branch_reads_the_same_layer_from_dict_and_object(self):
        from_dict = provider_config_layer(dict(FULL_CONFIG), "demo")
        from_object = provider_config_layer(self.config, "demo")
        self.assertEqual(from_object.value, from_dict.value)
        self.assertEqual(from_object.source.id, "project:demo")
        self.assertIsNone(provider_config_layer(ProjectConfig(), "demo"))


if __name__ == "__main__":
    unittest.main()
