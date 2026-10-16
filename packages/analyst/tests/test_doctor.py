"""analyst doctor: check-result/v1 documents, no writes, no secrets in the output."""
import contextlib
import io
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import aicore
from aicore.util import schema

from analyst.common import Env
from analyst.doctor import cmd_doctor

SENTINEL = "s3cr3t-" + uuid.uuid4().hex
CONTRACT = Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"


def snapshot(*roots):
    seen = {}
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            seen[str(path)] = path.read_bytes() if path.is_file() else None
    return seen


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.skm = self.tmp / "skm"
        self.project = self.tmp / "project"
        for path in (self.home, self.skm, self.project):
            path.mkdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home), "SKM_HOME": str(self.skm),
                                             "AGENTMEMORY_SECRET": SENTINEL, "PATH": ""})
        patch.start()
        self.addCleanup(patch.stop)
        self.env = Env(str(self.tmp / "analyst-root"), "doctor", home=self.home)

    def run_doctor(self, *argv):
        out = io.StringIO()
        previous = os.getcwd()
        os.chdir(self.project)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                try:
                    cmd_doctor(self.env, list(argv))
                except SystemExit:
                    pass
        finally:
            os.chdir(previous)
        return out.getvalue()

    def test_json_is_a_list_of_valid_check_results(self):
        documents = json.loads(self.run_doctor("--json"))
        self.assertEqual([d["check_id"] for d in documents],
                         ["analyst.environment", "analyst.partners", "analyst.events"])
        registry, kind = schema.load_contract(CONTRACT)
        for document in documents:
            self.assertEqual(schema.validate(document, kind, registry), [], document)

    def test_text_lines_are_status_and_check_id(self):
        lines = [l for l in self.run_doctor().splitlines() if not l.startswith("  ")]
        self.assertTrue(all(l.split(" ", 1)[0] in ("ok", "warn", "fail", "skip") for l in lines), lines)

    def test_doctor_writes_nothing(self):
        events = self.project / ".swissknife" / "analytics" / "events.ndjson"
        events.parent.mkdir(parents=True)
        events.write_text("not json\n", encoding="utf-8")
        before = snapshot(self.home, self.skm, self.project)
        self.run_doctor("--json")
        self.run_doctor()
        self.assertEqual(snapshot(self.home, self.skm, self.project), before)

    def test_bad_journal_line_warns(self):
        events = self.project / ".swissknife" / "analytics" / "events.ndjson"
        events.parent.mkdir(parents=True)
        events.write_text(json.dumps({"x": SENTINEL}) + "\n", encoding="utf-8")
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json"))}
        self.assertEqual(by_id["analyst.events"]["status"], "warn")

    def test_secret_is_not_printed(self):
        events = self.project / ".swissknife" / "analytics" / "events.ndjson"
        events.parent.mkdir(parents=True)
        events.write_text(json.dumps({"token": SENTINEL}) + "\n", encoding="utf-8")
        self.assertNotIn(SENTINEL, self.run_doctor("--json"))
        self.assertNotIn(SENTINEL, self.run_doctor())


if __name__ == "__main__":
    unittest.main()
