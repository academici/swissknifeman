"""Гейт от расхождения JSON-схем конфигов с рантайм-валидаторами.

Схемы (schema/*.json) — DX/документация (IntelliSense редактора, $schema). Рантайм-
валидация остаётся ручной и stdlib-only (CONFIG_KEYS в common.py, SKILLSET_KEYS в
skillset.py — без pip-зависимости jsonschema). Этот тест держит published schema в
синхроне с кодом: если ключ добавили в Python, но не в схему (или наоборот) — падаем.
Тест гоняется в scripts/test.sh, который зовёт scripts/validate.sh (== CI)."""
import json
import unittest
from pathlib import Path

from skiller.common import AGENT_DEFAULTS, CONFIG_KEYS
from skiller.skillset import SKILLSET_KEYS

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"
JSON_TYPE = {str: "string", list: "array", int: "integer", dict: "object", bool: "boolean"}


def _load(name):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


class TestConfigSchemas(unittest.TestCase):
    def test_swissknife_props_match_config_keys(self):
        props = set(_load("swissknife.schema.json")["properties"])
        self.assertEqual(props, set(CONFIG_KEYS),
                         "schema/swissknife.schema.json разошлась с CONFIG_KEYS")

    def test_swissknifeman_props_match_skillset_keys(self):
        props = set(_load("swissknifeman-config.schema.json")["properties"])
        self.assertEqual(props, set(SKILLSET_KEYS),
                         "schema/swissknifeman-config.schema.json разошлась с SKILLSET_KEYS")

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
                self.assertEqual(schema["properties"][key]["type"],
                                 JSON_TYPE[pytype], f"{fname}: тип '{key}'")

    def test_schemas_reject_unknown_keys(self):
        # Контракт DX: additionalProperties:false + escape для _/$ — как рантайм
        # (валидаторы пропускают ключи на '_'/'$', остальное — die).
        for fname in ("swissknife.schema.json", "swissknifeman-config.schema.json"):
            schema = _load(fname)
            self.assertIs(schema["additionalProperties"], False, fname)
            self.assertIn("^[_$]", schema["patternProperties"], fname)


if __name__ == "__main__":
    unittest.main()
