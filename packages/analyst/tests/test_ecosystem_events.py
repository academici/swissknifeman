"""analyst events ingest/list and the status block, driven by the consumer contract fixtures."""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from analyst.cli import main
from analyst.ecosystem_events import JOURNAL, SUBSCRIBED

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "events"


def _fixture(kind):
    return json.loads((FIXTURES / kind / "valid-1.json").read_text(encoding="utf-8"))


class TestEcosystemEvents(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name
        self._old = {k: os.environ.get(k) for k in ("HOME", "SKM_HOME")}
        os.environ["HOME"] = self.home
        os.environ["SKM_HOME"] = os.path.join(self.home, "skm")
        self.addCleanup(self._restore)
        self.cwd = os.getcwd()
        os.chdir(self.home)
        self.addCleanup(os.chdir, self.cwd)

    def _restore(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                main([self.cwd, *args])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue(), err.getvalue()

    def _ingest(self, doc):
        path = os.path.join(self.home, "event.json")
        Path(path).write_text(json.dumps(doc), encoding="utf-8")
        return self._run("events", "ingest", "--event", path)

    def _journal(self):
        code, out, _ = self._run("events", "list", "--json")
        self.assertEqual(code, 0)
        return json.loads(out)

    def test_every_subscribed_type_is_recorded_once(self):
        for kind in SUBSCRIBED:
            self.assertEqual(self._ingest(_fixture(kind))[0], 0, kind)
        listed = self._journal()
        self.assertEqual({e["type"] for e in listed["events"]}, set(SUBSCRIBED))
        self.assertEqual(listed["counts"]["planner.plan.closed"], {"done": 1})
        self.assertEqual(listed["counts"]["orch.run.refused"], {"none": 1})
        for entry in listed["events"]:
            self.assertTrue(entry["data_digest"].startswith("sha256:"))
            self.assertNotIn("data", entry)

    def test_stdout_is_a_subscriber_status_document(self):
        code, out, _ = self._ingest(_fixture("planner.plan.closed"))
        self.assertEqual((code, json.loads(out)["status"]), (0, "ok"))
        doc = _fixture("planner.plan.closed")
        doc["type"] = "planner.plan.created"
        self.assertEqual(json.loads(self._ingest(doc)[1])["status"], "skipped")

    def test_repeat_is_a_noop(self):
        doc = _fixture("planner.plan.closed")
        self.assertEqual(self._ingest(doc)[0], 0)
        self.assertEqual(self._ingest(doc)[0], 0)
        self.assertEqual(len(self._journal()["events"]), 1)

    def test_other_type_is_skipped(self):
        doc = _fixture("planner.plan.closed")
        doc["type"] = "planner.plan.created"
        code, _, err = self._ingest(doc)
        self.assertEqual(code, 0)
        self.assertIn("analyst events: skip planner.plan.created", err)
        self.assertEqual(self._journal()["events"], [])

    def test_invalid_event_exits_2(self):
        doc = _fixture("planner.item.finished")
        del doc["data"]["item_id"]
        code, _, err = self._ingest(doc)
        self.assertEqual(code, 2)
        self.assertIn("ANALYST_EVENT_INVALID", err)
        bad = copy.deepcopy(_fixture("planner.plan.closed"))
        bad["specversion"] = "9"
        self.assertEqual(self._ingest(bad)[0], 2)

    def test_float_in_data_is_invalid_not_a_crash(self):
        doc = _fixture("planner.item.finished")
        doc["data"]["deviation_count"] = 1.5
        code, _, err = self._ingest(doc)
        self.assertEqual(code, 2)
        self.assertIn("ANALYST_EVENT_INVALID", err)
        self.assertEqual(self._journal()["events"], [])

    def test_secret_values_stay_out_of_the_journal(self):
        doc = _fixture("planner.plan.closed")
        doc["data"]["goal"] = "do-not-copy-this-value"
        self._ingest(doc)
        journal = Path(self.home, "skm")
        text = "".join(p.read_text(encoding="utf-8") for p in journal.rglob(JOURNAL))
        self.assertNotIn("do-not-copy-this-value", text)
        self.assertNotIn("Ecosystem split", text)

    def test_list_filters_and_status(self):
        for kind in SUBSCRIBED:
            self._ingest(_fixture(kind))
        code, out, _ = self._run("events", "list", "--type", "orch.run.finished", "--json")
        self.assertEqual([e["type"] for e in json.loads(out)["events"]], ["orch.run.finished"])
        code, out, _ = self._run("events", "list", "--since", "2030-01-01T00:00:00Z", "--json")
        self.assertEqual(json.loads(out)["events"], [])
        code, out, _ = self._run("status", "--json")
        self.assertEqual(code, 0)
        self.assertIn("ecosystem_events", json.loads(out))


if __name__ == "__main__":
    unittest.main()
