"""skiller list --json: output validates against projects-list/v1; registry place and legacy file."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import aicore
from aicore.util.schema import load_contract, validate

import tests.fixtures as fx
from skiller.listing import cmd_list
from skiller.state import upsert_project

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = Path(aicore.__file__).resolve().parents[2] / "schemas"


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


class TestListJson(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _validate(self, doc):
        registry, kind = load_contract(ROOT / "schemas" / "projects-list" / "v1",
                                       urn_prefix="urn:swissknifeman:skiller:", foundation=FOUNDATION)
        return list(validate(doc, kind, registry))

    def test_empty_registry_validates(self):
        doc = json.loads(capture(cmd_list, self.env, ["--json"]))
        self.assertEqual(doc["projects"], [])
        self.assertEqual(self._validate(doc), [])

    def test_records_validate_with_name_and_connected_at(self):
        project = self.tmp / "alpha"
        project.mkdir()
        upsert_project(self.env, {"path": str(project), "channel": "vendor", "profile": "p"})
        doc = json.loads(capture(cmd_list, self.env, ["--json"]))
        self.assertEqual(self._validate(doc), [])
        record = doc["projects"][0]
        self.assertEqual(record["name"], "alpha")
        self.assertEqual(record["channel"], "vendor")
        self.assertEqual(record["profile"], "p")
        self.assertTrue(record["connected_at"])

    def test_registry_lives_in_the_skiller_state_place(self):
        project = self.tmp / "beta"
        project.mkdir()
        upsert_project(self.env, {"path": str(project), "channel": "connect"})
        self.assertEqual(self.env.db_file, self.env.state_dir / "projects.json")
        self.assertEqual(self.env.state_dir.name, "skiller")
        self.assertTrue(self.env.db_file.is_file())

    def test_legacy_file_is_read_and_stays_the_write_target(self):
        legacy = self.env.home / ".swissknifeman" / "projects.json"
        legacy.parent.mkdir(parents=True)
        project = self.tmp / "gamma"
        project.mkdir()
        legacy.write_text(json.dumps({"version": 1, "projects": [
            {"path": str(project), "channel": "vendor", "updated_at": "2026-01-01T00:00:00Z"}]}))
        (self.env.home / ".swissknifeman" / "topology.json").write_text("{}")
        doc = json.loads(capture(cmd_list, self.env, ["--json"]))
        self.assertEqual([p["name"] for p in doc["projects"]], ["gamma"])
        self.assertEqual(doc["projects"][0]["connected_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(self.env.db_file, legacy)
        self.assertFalse((self.env.state_dir / "projects.json").exists())


if __name__ == "__main__":
    unittest.main()
