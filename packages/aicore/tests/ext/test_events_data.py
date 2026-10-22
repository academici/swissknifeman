"""aicore.ext.events.validate_data and check_data: the data of an event against the schema its dataschema names."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.ext import events
from aicore.ext.errors import CODES, ExtError

ID = "urn:swissknifeman:demo:event-data:demo-thing-made:v1"
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": ID, "title": "demo.thing.made",
    "description": "A thing was made.", "type": "object",
    "properties": {"name": {"type": "string", "minLength": 1, "description": "Name."},
                   "count": {"type": "integer", "minimum": 0, "description": "How many."}},
    "required": ["name"], "additionalProperties": False,
}


class DataCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "event-data" / "v1"
        self.dir.mkdir(parents=True)
        (self.dir / "demo.thing.made.schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")


class TestValidateData(DataCase):
    def test_valid_data_has_no_problems(self):
        self.assertEqual([], events.validate_data({"name": "a", "count": 2}, ID, self.dir))

    def test_each_violation_is_a_message_with_its_path(self):
        problems = events.validate_data({"name": "", "count": -1, "extra": True}, ID, self.dir)
        self.assertEqual(3, len(problems), problems)
        self.assertTrue(all(problem.startswith("/") for problem in problems), problems)

    def test_a_missing_required_field_is_reported(self):
        problems = events.validate_data({"count": 1}, ID, self.dir)
        self.assertEqual(1, len(problems))
        self.assertIn("name", problems[0])

    def test_data_that_is_not_an_object_is_reported(self):
        self.assertEqual(1, len(events.validate_data(["name"], ID, self.dir)))

    def test_an_unknown_dataschema_is_one_problem_naming_id_and_directory(self):
        other = "urn:swissknifeman:demo:event-data:demo-thing-lost:v1"
        self.assertEqual([f"dataschema {other} is not in {self.dir}"], events.validate_data({}, other, self.dir))

    def test_the_directory_is_loaded_once(self):
        events.validate_data({"name": "a"}, ID, self.dir)
        with mock.patch("aicore.util.schema.load_contract_set", side_effect=AssertionError("loaded again")):
            self.assertEqual([], events.validate_data({"name": "b"}, ID, self.dir))


class TestCheckData(DataCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_data_gives_none(self):
        self.assertIsNone(events.check_data({"name": "a"}, ID, self.dir))

    def test_invalid_data_gives_the_first_problem_in_the_working_mode(self):
        problem = events.check_data({"extra": 1}, ID, self.dir)
        self.assertIsInstance(problem, str)
        self.assertEqual(events.validate_data({"extra": 1}, ID, self.dir)[0], problem)

    def test_strict_mode_raises_event_data_invalid(self):
        for env, process in (({}, "1"), ({"SKM_CONTRACTS_STRICT": "1"}, "")):
            with self.subTest(env=env, process=process), mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": process}):
                with self.assertRaises(ExtError) as caught:
                    events.check_data({"extra": 1}, ID, self.dir, env=env)
                self.assertEqual("EVENT_DATA_INVALID", caught.exception.code)

    def test_strict_mode_lets_valid_data_through(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            self.assertIsNone(events.check_data({"name": "a"}, ID, self.dir))

    def test_only_the_value_one_is_strict(self):
        for value in ("0", "true", "yes"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": value}):
                self.assertFalse(events.contracts_strict())

    def test_data_with_a_secret_is_left_to_build_event(self):
        from aicore.config import Secret
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            self.assertIsNone(events.check_data({"name": Secret("env://X", lambda: "x")}, ID, self.dir))
        with self.assertRaises(ExtError) as caught:
            events.build_event("demo.thing.made", {"name": Secret("env://X", lambda: "x")}, source="demo")
        self.assertEqual("EVENT_SECRET", caught.exception.code)

    def test_the_code_is_a_known_code(self):
        self.assertIn("EVENT_DATA_INVALID", CODES)


if __name__ == "__main__":
    unittest.main()
