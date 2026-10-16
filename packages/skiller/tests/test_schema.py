"""Divergence gate JSON-config schemes with runtime validators.

Schemes (schema/*.json) — DX/documentation (IntelliSense editor, $schema). Runtime-
validation remains manual and stdlib-only (CONFIG_KEYS in common.py, SKILLSET_KEYS in
skillset.py — without pip-dependencies jsonschema). This test holds published schema in
in sync with the code: if the key is added to Python, but not in the schema (or vice versa) — we fall.
Test runs in scripts/test.sh, who calls scripts/validate.sh (== CI)."""
import json
import unittest
from pathlib import Path

from skiller.common import CONFIG_KEYS
from aicore.delivery.materialize import AGENT_DEFAULTS
from skiller.skillset import SKILLSET_KEYS

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"
JSON_TYPE = {str: "string", list: "array", int: "integer", dict: "object", bool: "boolean"}


def _load(name):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


class TestConfigSchemas(unittest.TestCase):
    def test_swissknife_props_match_config_keys(self):
        props = set(_load("swissknife.schema.json")["properties"])
        self.assertEqual(props, set(CONFIG_KEYS),
                         "schema/swissknife.schema.json separated from CONFIG_KEYS")

    def test_swissknifeman_props_match_skillset_keys(self):
        props = set(_load("swissknifeman-config.schema.json")["properties"])
        self.assertEqual(props, set(SKILLSET_KEYS),
                         "schema/swissknifeman-config.schema.json separated from SKILLSET_KEYS")

    def test_agent_enum_matches_agent_defaults(self):
        agent = _load("swissknife.schema.json")["properties"]["agent"]
        self.assertEqual(set(agent["enum"]), set(AGENT_DEFAULTS))

    def test_mode_enum_is_vendor_only(self):
        mode = _load("swissknifeman-config.schema.json")["properties"]["mode"]
        self.assertEqual(mode["enum"], ["vendor"])

    def test_property_types_align_with_python(self):
        for fname, keys in (("swissknife.schema.json", CONFIG_KEYS),
                            ("swissknifeman-config.schema.json", SKILLSET_KEYS)):
            schema = _load(fname)
            for key, pytype in keys.items():
                prop = schema["properties"][key]
                if isinstance(pytype, tuple):
                    # Multi-type (e.g. memory_brain = (str, dict)) → in the schema oneOf,
                    # where the terms cover exactly the set JSON-types Python-tuple.
                    self.assertNotIn("type", prop,
                                     f"{fname}: '{key}' — multi-type, expected oneOf")
                    member_types = {b.get("type") for b in prop.get("oneOf", [])}
                    self.assertEqual(member_types, {JSON_TYPE[t] for t in pytype},
                                     f"{fname}: oneOf-members '{key}'")
                else:
                    self.assertEqual(prop["type"], JSON_TYPE[pytype],
                                     f"{fname}: type '{key}'")

    def test_schemas_reject_unknown_keys(self):
        # Contract DX: additionalProperties:false + escape for _/$ — as runtime
        # (validators pass keys to '_'/'$', rest - die).
        for fname in ("swissknife.schema.json", "swissknifeman-config.schema.json"):
            schema = _load(fname)
            self.assertIs(schema["additionalProperties"], False, fname)
            self.assertIn("^[_$]", schema["patternProperties"], fname)


if __name__ == "__main__":
    unittest.main()
