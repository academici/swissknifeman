"""Divergence gate JSON-config schemes with runtime validators.

Schemes (schemas/<kind>/v1) — DX/documentation (IntelliSense editor, $schema). Runtime-
validation remains manual and stdlib-only (CONFIG_KEYS in common.py, SKILLSET_KEYS in
skillset.py — without pip-dependencies jsonschema). This test holds published schema in
in sync with the code: if the key is added to Python, but not in the schema (or vice versa) — we fall.
Test runs in scripts/test.sh, who calls scripts/validate.sh (== CI)."""
import json
import unittest
from pathlib import Path

import aicore
from aicore.delivery.materialize import AGENT_DEFAULTS
from aicore.util.schema import load_contract, validate

from skiller.common import CONFIG_KEYS
from skiller.skillset import SKILLSET_KEYS

SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
FOUNDATION = Path(aicore.__file__).resolve().parents[2] / "schemas"
JSON_TYPE = {str: "string", list: "array", int: "integer", dict: "object", bool: "boolean"}


def _load(name):
    kind = name.removesuffix(".schema.json")
    return json.loads((SCHEMA_ROOT / kind / "v1" / name).read_text(encoding="utf-8"))


class TestConfigSchemas(unittest.TestCase):
    def test_swissknife_props_match_config_keys(self):
        props = set(_load("swissknife.schema.json")["properties"])
        self.assertEqual(props, set(CONFIG_KEYS),
                         "schemas/swissknife/v1/swissknife.schema.json separated from CONFIG_KEYS")

    def test_swissknifeman_props_match_skillset_keys(self):
        props = set(_load("swissknifeman-config.schema.json")["properties"])
        self.assertEqual(props, set(SKILLSET_KEYS),
                         "schemas/swissknifeman-config/v1/swissknifeman-config.schema.json separated from SKILLSET_KEYS")

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


def _file_entry():
    return {"path": "a", "url": "https://example/a", "sha256": "abc", "fetched_at": "2026-01-02"}


def _origin(role):
    return {
        "repo": "acme/skills",
        "role": role,
        "url": "https://example/skill",
        "sha256": "abc",
        "fetched_at": "2026-01-02",
    }


def _upstream(**overrides):
    document = {
        "schema_version": 1,
        "source": "github",
        "strategy": "replace",
        "files": [_file_entry()],
    }
    document.update(overrides)
    return document


def _complete_merge():
    return _upstream(
        strategy="merge",
        origins=[_origin("base"), _origin("supplement")],
        merge={"review_pending": False, "last_review": "2026-01-02"},
    )


class TestUpstreamMergeConditional(unittest.TestCase):
    """strategy=merge requires origins and merge; the other strategies do not.

    The frozen draft-07 file states this with if/then. The closed profile has no
    if/then, so the canonical schema uses oneOf. These cases keep that meaning.
    """

    @classmethod
    def setUpClass(cls):
        cls.registry, cls.kind = load_contract(
            SCHEMA_ROOT / "upstream" / "v1",
            urn_prefix="urn:swissknifeman:skiller:",
            foundation=FOUNDATION,
        )

    def _issues(self, document):
        return list(validate(document, self.kind, self.registry))

    def test_replace_notify_and_fork_pass_without_origins_or_merge(self):
        for strategy in ("replace", "notify", "fork"):
            with self.subTest(strategy=strategy):
                self.assertEqual(self._issues(_upstream(strategy=strategy)), [])

    def test_complete_merge_passes(self):
        self.assertEqual(self._issues(_complete_merge()), [])

    def test_merge_missing_origins_fails(self):
        document = _complete_merge()
        del document["origins"]
        self.assertTrue(self._issues(document))

    def test_merge_missing_merge_fails(self):
        document = _complete_merge()
        del document["merge"]
        self.assertTrue(self._issues(document))


if __name__ == "__main__":
    unittest.main()
