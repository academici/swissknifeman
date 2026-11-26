"""The run-options schema is the one statement of its bounds: every numeric bound is a ``minimum``/``maximum`` of the
schema (none is kept in a table of the code), a value one past a bound is refused as ``OPTIONS_INVALID`` and every
default of the code lies inside its bounds and matches the default the description states."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from orch.conductor import contract, options

SCHEMA = json.loads((contract.CONTRACT_DIR / "run-options.schema.json").read_text(encoding="utf-8"))
LIMITS = SCHEMA["$defs"]["limits"]["properties"]
MIRROR = Path(__file__).resolve().parents[3] / "bridges" / "planner-orch" / "schemas" / "run-options.schema.json"


def refused(layer: dict) -> bool:
    try:
        options.effective({}, {}, [{"source": "invocation:--options", "options": layer, "trusted": True}])
    except options.OptionsError as error:
        return error.code == "OPTIONS_INVALID"
    return False


def numeric_fields():
    """``(group, key, node)`` of every integer field of run-options."""
    yield from (("limits", key, node) for key, node in LIMITS.items() if node.get("type") == "integer")  # not unmetered, role_timeout_s
    for group in ("checks", "review"):
        yield from ((group, key, node) for key, node in SCHEMA["properties"][group]["properties"].items()
                    if node.get("type") == "integer")


class SchemaBoundsTests(unittest.TestCase):
    def test_every_integer_field_has_a_minimum(self):
        missing = [f"{group}.{key}" for group, key, node in numeric_fields() if "minimum" not in node]
        self.assertEqual(missing, [])

    def test_one_past_a_bound_is_refused_and_the_bound_itself_is_taken(self):
        for group, key, node in numeric_fields():
            with self.subTest(field=f"{group}.{key}"):
                self.assertTrue(refused({group: {key: node["minimum"] - 1}}))
                self.assertFalse(refused({group: {key: node["minimum"]}}))
                if "maximum" in node:
                    self.assertTrue(refused({group: {key: node["maximum"] + 1}}))
                    self.assertFalse(refused({group: {key: node["maximum"]}}))

    def test_on_error_max_and_repeated_check_kinds_are_refused(self):
        self.assertTrue(refused({"on_error": {"quota": {"action": "retry", "max": -1}}}))
        self.assertTrue(refused({"checks": {"kinds": ["acceptance", "acceptance"]}}))
        self.assertTrue(refused({"limits": {"retries": "2"}}))

    def test_code_defaults_lie_inside_the_bounds_and_cover_the_schema(self):
        self.assertEqual(set(options.DEFAULT_LIMITS), set(LIMITS))
        defaults = {"limits": options.DEFAULT_LIMITS, "checks": options.DEFAULT_CHECKS, "review": options.DEFAULT_REVIEW}
        for group, key, node in numeric_fields():
            value = defaults[group][key]
            with self.subTest(field=f"{group}.{key}"):
                self.assertGreaterEqual(value, node["minimum"])
                self.assertLessEqual(value, node.get("maximum", value))

    def test_a_default_stated_in_a_description_is_the_default_of_the_code(self):
        defaults = {"limits": options.DEFAULT_LIMITS, "checks": options.DEFAULT_CHECKS, "review": options.DEFAULT_REVIEW}
        wrong = []
        for group, key, node in numeric_fields():
            stated = re.search(r"[Dd]efault:? (\d+)", node["description"]) or re.search(r"(\d+) \(default\)", node["description"])
            if stated and int(stated.group(1)) != defaults[group][key]:
                wrong.append(f"{group}.{key}: description {stated.group(1)}, code {defaults[group][key]}")
        self.assertEqual(wrong, [])

    def test_hard_token_limits_have_the_same_optional_zero_default_in_all_three_places(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "configs/config.schema.json").read_text())
        configured = config["properties"]["conductor"]["properties"]["limits"]["properties"]
        for key in ("tokens_hard_max", "run_tokens_hard_max"):
            self.assertNotIn(key, SCHEMA["$defs"]["limits"]["required"])
            self.assertEqual(options.DEFAULT_LIMITS[key], 0)
            for node in (LIMITS[key], configured[key]):
                self.assertEqual((node["type"], node["minimum"], node["default"]), ("integer", 0, 0))
            for invalid in (True, 1.5, "1", -1):
                self.assertTrue(refused({"limits": {key: invalid}}))

    @unittest.skipUnless(MIRROR.is_file(), "planner-orch bridge not in this tree")
    def test_the_bridge_mirror_is_the_schema(self):
        self.assertEqual(json.loads(MIRROR.read_text(encoding="utf-8")), SCHEMA)


if __name__ == "__main__":
    unittest.main()
