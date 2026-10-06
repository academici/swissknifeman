"""`--output json` is one API: every verb answers with the envelope schema, refusals carry a code, `--out` is checked."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import brief, cli, schema, store  # noqa: E402
from task.plan.model import PlanError  # noqa: E402

try:
    from . import test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle

ACTOR = "claude-code/claude-opus-5-5/high"


def run(*argv):
    """``(exit code, stdout, stderr)`` of ``plan.py`` run in-process."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def verbs() -> set[str]:
    parser = cli.build_parser()
    return set(parser._subparsers._group_actions[0].choices)


class EnvelopeCase(test_lifecycle.LifeCase):
    def envelope(self, *argv, code=None):
        """Run ``--output json <argv>``; the envelope must validate and agree with the exit code."""
        status, out, _ = run("--output", "json", *argv)
        document = json.loads(out)
        self.assertEqual(schema.validate(document, "envelope"), [], f"{argv}: {out}")
        self.assertEqual(document["ok"], status == 0, f"{argv}: {out}")
        if code is not None:
            self.assertEqual(status, code, f"{argv}: {out}")
        return document


class VerbCoverageTests(EnvelopeCase):
    """One case per verb; a new verb without a case fails ``test_every_verb_has_a_case``."""

    def cases(self, tmp: Path):
        root, plan = str(self.root), str(self.root)
        snapshot = tmp / "snapshot.json"
        patch = tmp / "patch.json"
        patch.write_text(json.dumps([{"ref": "P1.1", "patch": {"summary": "changed"}}]))
        document = tmp / "document.json"
        document.write_text(json.dumps({"id": "notes", "title": "Notes", "sections": [{"id": "a", "title": "A", "text": "t"}]}))
        batches = tmp / "batches.json"
        batches.write_text(json.dumps([{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended"}]))
        return [  # (verb, argv, expected exit code); order matters: later verbs see earlier writes
            ("show", ["show", plan], 0),
            ("get", ["get", plan, "P1.1"], 0),
            ("list", ["list", plan, "items"], 0),
            ("events", ["events", plan], 0),
            ("artifact", ["artifact", plan, "artifact/absent"], 1),
            ("links", ["links", plan, "P1.1"], 0),
            ("neighborhood", ["neighborhood", plan, "P1.1"], 0),
            ("check", ["check", plan], 0),
            ("next", ["next", plan], 0),
            ("stats", ["stats", plan], 0),
            ("render", ["render", plan], 0),
            ("export", ["export", plan], 0),
            ("context", ["context", plan, "P1.1", "--stdout"], 0),
            ("brief", ["brief", plan, "P1.1"], 0),
            ("set", ["set", plan, "P1.1", "--json", '{"summary": "again"}'], 0),
            ("apply", ["apply", plan, "--file", str(patch)], 0),
            ("push", ["push", plan, "P1.1", "scope.include", "--json", '"extra"'], 0),
            ("add-document", ["add-document", plan, "--file", str(document)], 0),
            ("add-decision", ["add-decision", plan, "--title", "Pick"], 0),
            ("add-phase", ["add-phase", plan, "--title", "Three"], 0),
            ("add-item", ["add-item", plan, "P2", "--title", "Fourth"], 0),
            ("batches", ["batches", plan, "P1", "--file", str(batches)], 0),
            ("design-done", ["design-done", plan, "P2", "--actor", ACTOR], 1),  # P2.2 is still a skeleton
            ("start", ["start", plan, "P1.1", "--actor", ACTOR], 0),
            ("unit", ["unit", plan, "P1.1", "next"], 0),
            ("log", ["log", plan, "P1.1", "--type", "note", "--summary", "n"], 0),
            ("finish", ["finish", plan, "P1.1", "--status", "done", "--check", "V1=0", "--check", "V2=0"], 0),
            ("decide", ["decide", plan, "D1", "--accept", "x", "--rationale", "y"], 0),
            ("supersede", ["supersede", plan, "D1", "D1"], 1),
            ("grant", ["grant", plan, "NOPE", "--note", "n"], 1),
            ("reopen", ["reopen", plan, "P1.1", "--reason", "again"], 0),
            ("archive", ["archive", plan], 1),  # the plan is not done
            ("import", ["import", str(tmp / self.root.name), "--file", str(snapshot)], 0),
            ("new", ["new", "--plans-root", str(self.plans), "--codename", "ENVY", "--title", "T", "--actor", ACTOR,
                         "--message", "first owner message"], 0),
        ]

    def test_every_verb_has_a_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            covered = {verb for verb, _, _ in self.cases(Path(tmp))}
        self.assertEqual(verbs(), covered)

    def test_every_verb_answers_with_the_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "snapshot.json").write_text(run("export", self.root)[1])
            for verb, argv, expected in self.cases(tmp):
                with self.subTest(verb=verb):
                    document = self.envelope(*argv, code=expected)
                    if not expected:
                        self.assertIn("data", document)
                    else:
                        self.assertRegex(document["error"]["code"], r"^[A-Z][A-Z0-9_]*$")


class ErrorEnvelopeTests(EnvelopeCase):
    def test_read_verbs_validate_data_before_printing(self):
        from task.plan import query
        for name, call, invalid in (("get", ["get", self.root, "P1.1"], {"doc": {}}),
                                    ("list_rows", ["list", self.root, "items"], [{"ref": 3}]),
                                    ("events", ["events", self.root], [{"type": "note"}]),
                                    ("artifact", ["artifact", self.root, "artifact/a"], {"exists": True}),
                                    ("links", ["links", self.root, "P1.1"], {"ref": "P1.1"}),
                                    ("neighborhood", ["neighborhood", self.root, "P1.1"], {"item": {}})):
            with self.subTest(name=name), mock.patch.object(query, name, return_value=invalid):
                doc = self.envelope(*call, code=1)
                self.assertEqual(doc["error"]["code"], "SCHEMA_INVALID")
                self.assertTrue(doc["error"]["issues"])

    def test_refusals_keep_their_code_and_issues(self):
        unknown = self.envelope("show", self.root, "P9.9", code=1)
        self.assertEqual(unknown["error"]["code"], "REF_UNKNOWN")
        invalid = self.envelope("set", self.root, "P1.1", "--json", '{"status": "done"}', code=1)
        self.assertEqual(invalid["error"]["code"], "FIELD_OWNED")
        schema_bad = self.envelope("set", self.root, "P1.1", "--json", '{"title": 5}', code=1)
        self.assertEqual(schema_bad["error"]["code"], "SCHEMA_INVALID")
        self.assertTrue(schema_bad["error"]["issues"])

    def test_usage_errors_are_enveloped_with_exit_2(self):
        document = self.envelope("set", self.root, "P1.1", "--json", "{broken", code=2)
        self.assertEqual(document["error"]["code"], "USAGE")

    def test_a_failing_check_keeps_its_issues(self):
        (self.root / "phases" / "P1" / "P1.1.json").write_text("not json")
        document = self.envelope("check", self.root, "--json", code=1)
        self.assertEqual(document["error"]["code"], "VERB_FAILED")

    def test_the_envelope_schema_rejects_malformed_answers(self):
        for bad in ({"ok": True}, {"ok": False, "error": {"code": "lower", "message": "m"}},
                    {"ok": True, "data": 1, "extra": 1}, {"ok": False, "data": 1},
                    {"ok": False, "error": {"code": "A", "message": "m", "extra": 1}}):
            self.assertTrue(schema.validate(bad, "envelope"), bad)
        for good in ({"ok": True, "data": None}, {"ok": True, "data": [1]},
                     {"ok": False, "error": {"code": "A_1", "message": "m", "issues": [{"path": "/x"}]}}):
            self.assertEqual(schema.validate(good, "envelope"), [], good)

    def test_an_envelope_outside_the_schema_is_a_bug_not_output(self):
        with self.assertRaises(RuntimeError):
            cli._emit({"ok": True})


class BriefOutTests(EnvelopeCase):
    def test_out_must_be_a_file_outside_the_plan(self):
        plan = store.load_plan(self.root)
        for bad in ("", str(self.root / "brief-copy.json"), str(self.root / "phases" / "P1" / "P1.1.json"),
                    str(self.root), str(self.plans)):
            with self.subTest(out=bad):
                with self.assertRaises(PlanError) as ctx:
                    brief.write(plan, "P1.1", bad)
                self.assertEqual(ctx.exception.code, "OUT_INVALID")
        self.assertFalse((self.root / "brief-copy.json").exists())

    def test_a_refused_out_leaves_the_plan_untouched_and_enveloped(self):
        before = (self.root / "phases" / "P1" / "P1.1.json").read_bytes()
        document = self.envelope("brief", self.root, "P1.1", "--out", self.root / "phases" / "P1" / "P1.1.json", code=1)
        self.assertEqual(document["error"]["code"], "OUT_INVALID")
        self.assertEqual((self.root / "phases" / "P1" / "P1.1.json").read_bytes(), before)

    def test_malformed_ids_are_refused_by_the_api_not_the_parser(self):
        for argv, code in ((("P1.1", "--unit", "x"), "REF_INVALID"), (("P1", ), "REF_INVALID"),
                           (("P1.1", "--unit", "U9"), "REF_UNKNOWN")):
            with self.subTest(argv=argv):
                self.assertEqual(self.envelope("brief", self.root, *argv, code=1)["error"]["code"], code)

    def test_out_writes_a_new_file_and_reports_its_path(self):
        target = self.plans.parent / "briefs" / "p1.json"
        document = self.envelope("brief", self.root, "P1.1", "--out", target, code=0)
        self.assertEqual(document["data"], {"message": str(target.resolve())})
        self.assertEqual(json.loads(target.read_text())["input_id"].split("@")[0], "PLAN1.P1.1")


if __name__ == "__main__":
    unittest.main()
