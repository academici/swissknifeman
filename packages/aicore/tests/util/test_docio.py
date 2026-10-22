"""aicore.util.docio: parse -> migrate -> validate on read, validate -> durable_replace on write."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from aicore.util.docio import DocumentCorrupt, DocumentInvalid, read_document, write_document
from aicore.util.schema import Registry

PREFIX = "urn:swissknifeman:test:"
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": PREFIX + "thing:v1",
    "type": "object",
    "required": ["name", "count"],
    "additionalProperties": False,
    "properties": {"name": {"type": "string", "minLength": 1}, "count": {"type": "integer", "minimum": 0}},
}


def registry():
    return Registry({SCHEMA["$id"]: SCHEMA}, urn_prefix=PREFIX, kinds=("thing",))


class DocioTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "sub" / "thing.json"
        self.reg = registry()

    def read(self, **kwargs):
        return read_document(self.path, kind="thing", registry=self.reg, **kwargs)

    def test_a_missing_file_is_none(self):
        self.assertIsNone(self.read())

    def test_write_then_read(self):
        write_document(self.path, {"name": "é", "count": 2}, kind="thing", registry=self.reg)
        self.assertEqual({"name": "é", "count": 2}, self.read())
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(json.dumps({"count": 2, "name": "é"}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", text)

    def test_the_file_mode_is_private_by_default_and_settable(self):
        write_document(self.path, {"name": "a", "count": 1}, kind="thing", registry=self.reg)
        self.assertEqual(0o600, stat.S_IMODE(os.stat(self.path).st_mode))
        write_document(self.path, {"name": "a", "count": 1}, kind="thing", registry=self.reg, mode=0o640)
        self.assertEqual(0o640, stat.S_IMODE(os.stat(self.path).st_mode))

    def test_an_invalid_document_is_not_written(self):
        write_document(self.path, {"name": "a", "count": 1}, kind="thing", registry=self.reg)
        before = self.path.read_bytes()
        with self.assertRaises(DocumentInvalid) as caught:
            write_document(self.path, {"name": "", "count": -1, "extra": 1}, kind="thing", registry=self.reg)
        self.assertGreaterEqual(len(caught.exception.issues), 3)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([self.path.name], sorted(p.name for p in self.path.parent.iterdir()), "no temporary left")

    def test_an_invalid_file_is_reported_with_every_issue(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"name": 3}), encoding="utf-8")
        with self.assertRaises(DocumentInvalid) as caught:
            self.read()
        self.assertEqual(self.path, caught.exception.path)
        self.assertGreaterEqual(len(caught.exception.issues), 2)

    def test_a_corrupt_file(self):
        self.path.parent.mkdir()
        for payload in (b"{not json", b"\xff\xfe\x00bad", b""):
            self.path.write_bytes(payload)
            with self.subTest(payload=payload), self.assertRaises(DocumentCorrupt):
                self.read()

    def test_migrate_runs_before_validation(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"title": "old", "n": 4}), encoding="utf-8")
        with self.assertRaises(DocumentInvalid):
            self.read()
        migrated = self.read(migrate=lambda doc: {"name": doc["title"], "count": doc["n"]})
        self.assertEqual({"name": "old", "count": 4}, migrated)
        # a migration that yields a bad document is still refused
        with self.assertRaises(DocumentInvalid):
            self.read(migrate=lambda doc: {"name": 1, "count": 1})

    def test_a_symlink_target_is_refused(self):
        self.path.parent.mkdir()
        real = self.path.parent / "real.json"
        real.write_text("{}", encoding="utf-8")
        self.path.symlink_to(real)
        with self.assertRaises(OSError):
            write_document(self.path, {"name": "a", "count": 1}, kind="thing", registry=self.reg)
        self.assertEqual("{}", real.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
