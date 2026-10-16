"""``aicore events emit|list`` through the group dispatcher (temporary HOME, units from the fixtures)."""
import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from aicore.ext import journal

from tests.ext.support import TempCase, run_cli

PACKAGE = Path(__file__).resolve().parents[2]
SENTINEL = "s3cr3t-" + uuid.uuid4().hex


class CliCase(TempCase):
    def run_events(self, *argv, cwd=None):
        return run_cli("events", *argv, env=self.env, cwd=cwd or self.tmp)

    def emit(self, *extra, source="demo", type="demo.thing.happened"):
        return self.run_events("emit", "--source", source, "--type", type, "--project", str(self.project), *extra)


class TestEmit(CliCase):
    def test_emit_prints_the_id_and_journals(self):
        code, out, err = self.emit("--subject", "X", "--data", '{"n": 1}', "--delivery", "off")
        self.assertEqual((code, err), (0, ""))
        event_id = out.strip()
        self.assertRegex(event_id, r"^[0-9a-f]{32}$")
        doc = json.loads(journal.journal_path(self.journal).read_text(encoding="utf-8"))
        self.assertEqual((doc["id"], doc["subject"], doc["data"]), (event_id, "X", {"n": 1}))

    def test_emit_json_prints_the_event(self):
        code, out, _ = self.emit("--json")
        doc = json.loads(out)
        self.assertEqual((code, doc["type"], doc["source"]), (0, "demo.thing.happened", "urn:swissknifeman:module:demo"))
        self.assertNotIn("data", doc)

    def test_data_file(self):
        path = self.tmp / "data.json"
        path.write_text('{"k": ["v"]}', encoding="utf-8")
        code, out, _ = self.emit("--data-file", str(path), "--json")
        self.assertEqual((code, json.loads(out)["data"]), (0, {"k": ["v"]}))

    def test_undeclared_type_warns_unless_strict(self):
        code, out, err = self.emit(type="demo.other.done")
        self.assertEqual(code, 0)
        self.assertIn("EVENT_TYPE_UNDECLARED", err)
        self.assertRegex(out.strip(), r"^[0-9a-f]{32}$")
        before = journal.size(self.journal)
        code, out, err = self.emit("--strict-type", type="demo.other.done")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("EVENT_TYPE_UNDECLARED", err)
        self.assertEqual(journal.size(self.journal), before)
        code, _, err = self.emit("--strict-type")
        self.assertEqual((code, err), (0, ""))

    def test_refusals_exit_one_with_the_code(self):
        for extra, code_text in ((("--data", "[1]"), "EVENT_INVALID"), (("--data", "{bad"), "EVENT_INVALID"),
                                 (("--data-file", str(self.tmp / "missing.json")), "EVENT_INVALID"),
                                 (("--data", json.dumps({"k": "x" * 70000})), "EVENT_DATA_TOO_LARGE")):
            code, out, err = self.emit(*extra)
            self.assertEqual((code, out), (1, ""), extra)
            self.assertIn(code_text, err)
        code, _, err = self.emit(type="other.thing.happened")
        self.assertEqual(code, 1)
        self.assertIn("EVENT_INVALID", err)
        self.assertEqual(journal.size(self.journal), 0)

    def test_usage_errors_exit_two(self):
        for argv in (("emit",), ("emit", "--source", "demo"), ("list", "--limit", "x"), ("nosuch",), (),
                     ("emit", "--source", "demo", "--type", "demo.a.b", "--data", "{}", "--data-file", "x"),
                     ("emit", "--source", "demo", "--type", "demo.a.b", "--delivery", "later")):
            code, out, _ = self.run_events(*argv)
            self.assertEqual((code, out), (2, ""), argv)

    def test_strict_emit_reports_an_unwritable_journal(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        self.emit()
        path = journal.journal_path(self.journal)
        os.chmod(path, 0o400)
        self.addCleanup(os.chmod, path, 0o600)
        code, out, err = self.emit()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("JOURNAL_IO", err)

    def test_project_defaults_to_the_nearest_project_else_the_machine_journal(self):
        nested = self.project / "src" / "deep"
        nested.mkdir(parents=True)
        code, out, _ = self.run_events("emit", "--source", "demo", "--type", "demo.thing.happened", cwd=nested)
        self.assertEqual(code, 0)
        self.assertEqual(len(list(journal.iter_lines(self.journal))), 1)
        elsewhere = self.tmp / "nowhere"
        elsewhere.mkdir()
        code, out, _ = self.run_events("emit", "--source", "demo", "--type", "demo.thing.happened", cwd=elsewhere)
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "skm" / "state" / "events" / "events.jsonl").is_file())
        self.assertFalse((elsewhere / ".swissknifeman").exists())


class TestList(CliCase):
    def test_text_and_json(self):
        self.emit("--subject", "A", "--data", '{"n": 1}')
        self.emit("--subject", "B", type="demo.other.done")
        code, out, _ = self.run_events("list", "--project", str(self.project))
        lines = out.splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 2)
        first = lines[0].split(" ")
        self.assertEqual((first[1], first[2]), ("demo.thing.happened", "A"))
        code, out, _ = self.run_events("list", "--project", str(self.project), "--json")
        doc = json.loads(out)
        self.assertEqual(sorted(doc), ["events", "problems"])
        self.assertEqual([event["type"] for event in doc["events"]], ["demo.thing.happened", "demo.other.done"])
        self.assertEqual(doc["events"][0]["data"], {"n": 1})

    def test_control_characters_in_a_subject_cannot_forge_rows(self):
        for separator in ("\n", "\r", "\x85", "\u2028", "\u2029", "\x0b", "\x1b"):
            with self.subTest(separator=repr(separator)):
                (self.journal / "events.jsonl").unlink(missing_ok=True)
                forged = "hello" + separator + "2026-01-01T00:00:00.000Z forged.type.evt - " + "ab" * 16
                self.emit("--subject", forged)
                code, out, _ = self.run_events("list", "--project", str(self.project))
                self.assertEqual(code, 0)
                self.assertEqual(len(out.splitlines()), 1)
                self.assertTrue(out.isprintable() or out.endswith("\n") and out[:-1].isprintable(), repr(out))
                code, out, _ = self.run_events("list", "--project", str(self.project), "--json")
                self.assertEqual(json.loads(out)["events"][0]["subject"], forged)

    def test_filters(self):
        self.emit()
        self.emit(type="demo.other.done")
        self.emit()
        first = json.loads(self.run_events("list", "--project", str(self.project), "--json")[1])["events"]
        code, out, _ = self.run_events("list", "--project", str(self.project), "--type", "demo.thing.*", "--json")
        self.assertEqual(len(json.loads(out)["events"]), 2)
        code, out, _ = self.run_events("list", "--project", str(self.project), "--since", first[0]["id"], "--limit", "1",
                                       "--json")
        self.assertEqual([e["id"] for e in json.loads(out)["events"]], [first[2]["id"]])
        code, out, err = self.run_events("list", "--project", str(self.project), "--since", "f" * 32)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("EVENT_NOT_FOUND", err)

    def test_broken_lines_go_to_stderr_and_exit_zero(self):
        self.emit()
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(b"garbage\n")
        code, out, err = self.run_events("list", "--project", str(self.project))
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn("EVENT_MALFORMED", err)
        code, out, err = self.run_events("list", "--project", str(self.project), "--json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["problems"][0]["code"], "EVENT_MALFORMED")

    def test_empty_journal(self):
        code, out, err = self.run_events("list", "--project", str(self.project), "--json")
        self.assertEqual((code, err, json.loads(out)), (0, "", {"events": [], "problems": []}))


class TestAsProcess(unittest.TestCase):
    def test_python_dash_m_aicore_events(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            (project / ".swissknifeman").mkdir(parents=True)
            env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "PYTHONPATH": str(PACKAGE / "lib")}
            run = lambda *argv: subprocess.run([sys.executable, "-m", "aicore", "events", *argv], env=env,
                                               capture_output=True, text=True, cwd=tmp, timeout=60)
            made = run("emit", "--source", "planner", "--type", "planner.plan.closed", "--project", str(project),
                       "--data", '{"n": 1}', "--delivery", "off")
            self.assertEqual(made.returncode, 0, made.stderr)
            listed = run("list", "--project", str(project), "--json")
            doc = json.loads(listed.stdout)
            self.assertEqual(doc["events"][0]["source"], "urn:swissknifeman:module:planner")
            self.assertTrue((project / ".swissknifeman" / "state" / "events.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
