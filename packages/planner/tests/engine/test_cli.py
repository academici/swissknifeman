"""plan.py CLI through a real subprocess: flow, exit codes, refusals, render --check."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
ACTOR = "claude-code/claude-opus-5-5/high"
ITEM_DETAIL = json.dumps({
    "summary": "Keys are checked", "why": "KeyError is unclear", "scope": {"include": ["config.py"]},
    "deliverables": ["checks"], "task_files": [{"path": "lib/config.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]})


class CliCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.plans = self.tmp / "plans"

    def run_plan(self, *args, expect=0, stdin=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60,
                                cwd=self.tmp, input=stdin)
        self.assertEqual(result.returncode, expect, f"{args}\nstdout: {result.stdout}\nstderr: {result.stderr}")
        return result

    def verb(self, name, *args, **kwargs):
        return self.run_plan(name, *args, "--plans-root", str(self.plans), **kwargs)

    def new_plan(self, codename="DEMO"):
        self.run_plan("new", "--codename", codename, "--title", "Demo", "--actor", ACTOR, "--message",
                      "Make errors aggregate.", "--date", "2026.10.05", "--plans-root", str(self.plans))
        return "PLAN1"

    def read(self, plan_id, rel):
        return (self.plans / "2026.10.05-№1-DEMO" / rel).read_text(encoding="utf-8")


class HelpAndUsageTests(CliCase):
    def test_help_lists_the_authoring_verbs(self):
        out = self.run_plan("--help").stdout
        for verb in ("new", "show", "set", "push", "add-phase", "add-item", "add-decision", "batches", "check", "render", "next"):
            self.assertIn(verb, out)

    def test_every_verb_has_help(self):
        for verb in ("new", "show", "set", "push", "add-phase", "add-item", "add-decision", "batches", "check", "render", "next"):
            self.assertEqual(self.run_plan(verb, "--help").returncode, 0)

    def test_usage_errors_exit_2(self):
        self.run_plan(expect=2)
        self.run_plan("bogus", expect=2)
        self.run_plan("new", "--title", "T", "--actor", ACTOR, expect=2)  # no codename / plan-id
        self.run_plan("new", "--codename", "X", "--title", "T", "--actor", "claude-code", expect=2)  # bad actor
        self.run_plan("new", "--codename", "X", "--title", "T", "--actor", "a/b/impossible", expect=2)  # bad effort
        self.run_plan("check", expect=2)  # plan missing

    def test_invalid_json_input_exits_2(self):
        self.new_plan()
        for args in (("set", "PLAN1", "plan", "--json", "{not json"), ("set", "PLAN1", "plan"),
                     ("set", "PLAN1", "plan", "--json", "@/nonexistent/patch.json"),
                     ("set", "PLAN1", "plan", "--json", "{}", "--file", "x.json")):
            with self.subTest(args=args):
                self.run_plan(*args, "--plans-root", str(self.plans), expect=2)


class AuthoringFlowTests(CliCase):
    def test_new_add_set_batches_check_render_next(self):
        self.run_plan("new", "--codename", "DEMO", "--title", "Demo", "--actor", ACTOR, "--message", "Make errors aggregate.",
                      "--date", "2026.10.05", "--plans-root", str(self.plans))
        plan_dir = self.plans / "2026.10.05-№1-DEMO"
        self.assertTrue((plan_dir / "plan.json").is_file())
        self.assertTrue((plan_dir / "views/status.md").is_file())
        self.assertEqual(self.verb("add-phase", "PLAN1", "--title", "Config validation").stdout.strip(), "P1")
        self.assertEqual(self.verb("add-item", "PLAN1", "P1", "--title", "Validate keys").stdout.strip(), "P1.1")
        self.assertEqual(self.verb("add-item", "PLAN1", "P1", "--title", "Validate types", "--batch", "B1",
                                   "--json", '{"summary": "Types are checked"}').stdout.strip(), "P1.2")
        self.verb("set", "PLAN1", "plan", "--json", '{"goal": "Errors are aggregated.", "context": "Loader crashes late."}')
        self.verb("set", "PLAN1", "P1", "--json", '{"goal": "Aggregated errors"}')
        self.verb("set", "PLAN1", "P1.1", "--json", '{"summary": "Keys are checked", "why": "KeyError is unclear",'
                  '"scope": {"include": ["config.py"]}, "deliverables": ["checks"],'
                  '"task_files": [{"path": "lib/config.py", "change": "any"}],'
                  '"validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}')
        self.verb("push", "PLAN1", "P1.1", "rules", "--json", '"collect all errors"')
        self.verb("batches", "PLAN1", "P1", "--json",
                  '[{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended"}]')
        checked = self.verb("check", "PLAN1")
        self.assertIn("0 error(s)", checked.stdout)
        self.verb("render", "PLAN1", "--check")
        shown = json.loads(self.verb("show", "PLAN1", "P1.1").stdout)
        self.assertEqual((shown["summary"], shown["rules"]), ("Keys are checked", ["collect all errors"]))
        self.assertEqual(self.verb("next", "PLAN1").stdout.strip(),
                         "design-phase: planner:plan-design 2026.10.05-№1-DEMO P1")

    def test_new_reads_the_message_from_a_file(self):
        message = self.tmp / "message.txt"
        message.write_text("Verbatim owner message.\n", encoding="utf-8")
        self.run_plan("new", "--codename", "FILED", "--date", "2026.08.01", "--title", "Filed",
                      "--actor", ACTOR, "--message-file", str(message), "--plans-root", str(self.plans))
        brief = json.loads((self.plans / "2026.08.01-№1-FILED" / "brief.json").read_text(encoding="utf-8"))
        self.assertEqual(brief["messages"][0]["text"], "Verbatim owner message.\n")
        self.assertEqual(json.loads(self.verb("show", "PLAN1", "plan").stdout)["short_id"], "PLAN1")

    def test_json_values_may_come_from_files(self):
        self.new_plan()
        patch = self.tmp / "patch.json"
        patch.write_text('{"goal": "From a file."}', encoding="utf-8")
        self.verb("set", "PLAN1", "plan", "--file", str(patch))
        self.verb("set", "PLAN1", "plan", "--json", f"@{patch}")
        self.assertEqual(json.loads(self.verb("show", "PLAN1", "plan").stdout)["goal"], "From a file.")

    def test_add_decision_and_show_by_reference(self):
        self.new_plan()
        self.assertEqual(self.verb("add-decision", "PLAN1", "--title", "Pick a format").stdout.strip(), "D1")
        decision = json.loads(self.verb("show", "PLAN1", "D1").stdout)
        self.assertEqual((decision["status"], decision["question"]), ("open", "Pick a format"))
        self.assertIn("Pick a format", self.read("PLAN1", "views/open-questions.md"))

    def test_show_overview_text_and_json(self):
        self.new_plan()
        self.verb("add-phase", "PLAN1", "--title", "Phase one")
        self.verb("add-item", "PLAN1", "P1", "--title", "First")
        text = self.verb("show", "PLAN1").stdout
        for fragment in ("PLAN1 2026.10.05-№1-DEMO", "P1 Phase one (skeleton, 0/1)", "P1.1 ⬜ Not started  First", "next: design-phase"):
            self.assertIn(fragment, text)
        overview = json.loads(self.verb("show", "PLAN1", "--json").stdout)
        self.assertEqual(overview["phases"][0]["items"][0], {"id": "P1.1", "title": "First", "status": "todo"})

    def test_plans_are_found_by_id_by_short_id_and_by_path(self):
        self.new_plan()
        for ref in ("2026.10.05-№1-DEMO", "PLAN1", str(self.plans / "2026.10.05-№1-DEMO")):
            with self.subTest(ref=ref):
                self.assertIn("0 error(s)", self.run_plan("check", ref, "--plans-root", str(self.plans)).stdout)

    def test_default_plans_root_is_found_upwards_from_cwd(self):
        self.new_plan()
        result = subprocess.run([sys.executable, str(SCRIPT), "check", "PLAN1"], capture_output=True, text=True,
                                cwd=self.plans / "2026.10.05-№1-DEMO")
        self.assertEqual(result.returncode, 0, result.stderr)


class LifecycleFlowTests(CliCase):
    """new -> design-done -> start -> log -> finish -> phase closed -> archive, through real subprocesses."""

    def designed_plan(self):
        self.new_plan()
        self.verb("add-phase", "PLAN1", "--title", "Config validation")
        self.verb("add-item", "PLAN1", "P1", "--title", "Validate keys")
        self.verb("set", "PLAN1", "P1.1", "--json", ITEM_DETAIL)

    def item_path(self):
        return self.plans / "2026.10.05-№1-DEMO" / "phases" / "P1" / "P1.1.json"

    def test_help_lists_the_lifecycle_verbs(self):
        out = self.run_plan("--help").stdout
        for verb in ("start", "finish", "log", "decide", "supersede", "grant", "design-done", "reopen", "archive"):
            self.assertIn(verb, out)
            self.assertEqual(self.run_plan(verb, "--help").returncode, 0)

    def test_design_done_prints_the_report_as_text_and_json(self):
        self.designed_plan()
        out = self.verb("design-done", "PLAN1", "P1", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        report = json.loads(out.stdout)
        self.assertEqual(report["phase"], "P1")
        self.assertEqual([i["item"] for i in report["items"]], ["P1.1"])
        again = self.verb("design-done", "PLAN1", "P1")
        self.assertRegex(again.stdout, r"^P1 detailed\n  P1\.1 \d+ KB")

    def test_full_flow_from_design_to_archive(self):
        self.designed_plan()
        self.assertEqual(self.verb("design-done", "PLAN1", "P1").stdout.splitlines()[0], "P1 detailed")
        plan_id = "2026.10.05-№1-DEMO"
        self.assertEqual(self.verb("next", "PLAN1").stdout.strip(), f"run-items: planner:plan-run {plan_id} P1.1  (implementation/high)")
        started = self.verb("start", "PLAN1", "P1.1", "--actor", ACTOR, "--session", "auto")
        self.assertIn("started P1.1 (phase P1, batch BP1-1; route ok)", started.stdout)
        self.verb("log", "PLAN1", "P1.1", "--type", "difficulty", "--summary", "tests import config", "--next", "reuse fixture")
        self.assertIn("tests import config", self.read("PLAN1", "views/handoff.md"))  # open friction until the phase closes

        before = self.item_path().read_bytes()  # negative control: no acceptance evidence, no state change
        refused = self.verb("finish", "PLAN1", "P1.1", "--status", "done", expect=1)
        self.assertTrue(refused.stderr.startswith("CHECKS_MISSING: "), refused.stderr)
        self.assertEqual(self.item_path().read_bytes(), before)

        finished = self.verb("finish", "PLAN1", "P1.1", "--status", "done", "--check", "V1=0", "--notes", "3 tests",
                             "--commit", "a1b2c3d")
        for fragment in ("P1.1 done", "phase P1 closed: done", "plan done", f"next: archive: planner:plan-close {plan_id} archive"):
            self.assertIn(fragment, finished.stdout)
        item = json.loads(self.item_path().read_text(encoding="utf-8"))
        self.assertEqual((item["status"], item["result"]["notes"], item["result"]["commits"]), ("done", "3 tests", ["a1b2c3d"]))
        self.assertIn("No open friction", self.read("PLAN1", "views/handoff.md"))
        self.assertIn("0 error(s)", self.verb("check", "PLAN1").stdout)

        archived = self.verb("archive", "PLAN1")
        self.assertIn("archived to", archived.stdout)
        self.assertFalse((self.plans / plan_id).exists())
        self.assertEqual(self.verb("next", "PLAN1").stdout.strip(), "terminal: plan done")
        self.assertIn("0 error(s)", self.verb("check", "PLAN1").stdout)

    def test_json_output_of_start_and_finish(self):
        self.designed_plan()
        self.verb("design-done", "PLAN1", "P1")
        started = json.loads(self.verb("start", "PLAN1", "P1.1", "--actor", ACTOR, "--json").stdout)
        self.assertEqual((started["items"], started["route"]), (["P1.1"], "ok"))
        self.assertEqual([Path(p).name for p in started["packs"]], ["P1.1.json"])
        finished = json.loads(self.verb("finish", "PLAN1", "P1.1", "--status", "done", "--check", "V1=0", "--json").stdout)
        self.assertEqual((finished["phase_closed"], finished["plan_done"], finished["next"]["kind"]), ("done", True, "archive"))

    def test_decide_grant_reopen_flow(self):
        self.designed_plan()
        self.verb("set", "PLAN1", "P1.1", "--json", '{"authority": {"kind": "owner_gate", "gate": "TAG-1", "scope": "tag"}}')
        self.verb("design-done", "PLAN1", "P1")
        self.assertIn("waiting: gate TAG-1", self.verb("next", "PLAN1").stdout)
        self.assertIn("next: run-items", self.verb("grant", "PLAN1", "TAG-1", "--note", "Owner: tag it.").stdout)
        self.verb("start", "PLAN1", "P1.1", "--actor", ACTOR)
        self.verb("finish", "PLAN1", "P1.1", "--status", "done", "--check", "V1=0")
        self.assertEqual(self.verb("reopen", "PLAN1", "P1.1", "--reason", "missed a case").stdout.strip(), "P1.1 reopened")
        self.assertEqual(json.loads(self.item_path().read_text(encoding="utf-8"))["status"], "todo")
        self.verb("add-decision", "PLAN1", "--title", "Format", "--json", '{"options": [{"id": "A", "text": "English"}]}')
        self.assertEqual(self.verb("decide", "PLAN1", "D1", "--accept", "A", "--rationale", "convention", "--by", "owner").stdout.strip(),
                         "D1 accepted: A — English")

    def test_lifecycle_refusals_exit_1_and_usage_errors_exit_2(self):
        self.designed_plan()
        for args, code in (
            (("start", "PLAN1", "P1.1", "--actor", ACTOR), "PHASE_NOT_DETAILED"),
            (("design-done", "PLAN1", "P9"), "REF_UNKNOWN"),
            (("finish", "PLAN1", "P1.1", "--status", "done"), "NOT_STARTED"),
            (("log", "PLAN1", "P1.1", "--type", "note", "--summary", "x", "--ref", "r"), None),
            (("reopen", "PLAN1", "P1.1", "--reason", "why"), "NOT_TERMINAL"),
            (("grant", "PLAN1", "TAG-1", "--note", "go"), "GATE_UNKNOWN"),
            (("archive", "PLAN1"), "PLAN_NOT_DONE"),
        ):
            with self.subTest(args=args):
                if code is None:
                    self.verb(*args)
                    continue
                self.assertTrue(self.verb(*args, expect=1).stderr.startswith(f"{code}: "))
        self.verb("design-done", "PLAN1", "P1")
        low = "claude-code/claude-haiku-4-5-20251001/high"
        self.assertTrue(self.verb("start", "PLAN1", "P1.1", "--actor", low, expect=1).stderr.startswith("ROUTE_UNDERSHOOT: "))
        self.verb("start", "PLAN1", "P1.1", expect=2)  # --actor is required
        self.verb("finish", "PLAN1", "P1.1", "--status", "bogus", expect=2)
        self.verb("finish", "PLAN1", "P1.1", "--status", "done", "--check", "V1", expect=2)
        self.verb("design-done", "PLAN1", "phase-1", expect=2)


class RefusalTests(CliCase):
    def test_json_envelopes_include_schema_and_input_errors(self):
        self.new_plan()
        result = self.run_plan("--output", "json", "set", "PLAN1", "plan", "--json", '{"bogus": 1}',
                               "--plans-root", str(self.plans), expect=1)
        value = json.loads(result.stdout)
        self.assertFalse(value["ok"])
        self.assertEqual(value["error"]["code"], "SCHEMA_INVALID")
        self.assertEqual(value["error"]["issues"][0]["path"], "/bogus")
        result = self.run_plan("--output", "json", "set", "PLAN1", "plan", "--json", '{broken',
                               "--plans-root", str(self.plans), expect=2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "USAGE")
        self.assertEqual(result.stderr, "")

    def test_refusals_exit_1_with_code_and_message_on_stderr(self):
        cases = [
            (("new", "--codename", "X", "--title", "T", "--actor", ACTOR, "--plans-root", str(self.plans)), "MESSAGE_REQUIRED"),
            (("show", "PLAN9", "--plans-root", str(self.plans)), "PLAN_NOT_FOUND"),
        ]
        for args, code in cases:
            with self.subTest(code=code):
                result = self.run_plan(*args, expect=1)
                self.assertTrue(result.stderr.startswith(f"{code}: "), result.stderr)
        self.new_plan()
        for args, code in (
            (("set", "PLAN1", "P9", "--json", "{}"), "REF_UNKNOWN"),
            (("set", "PLAN1", "plan", "--json", '{"status": "done"}'), "FIELD_OWNED"),
            (("set", "PLAN1", "plan", "--json", '{"bogus": 1}'), "SCHEMA_INVALID"),
            (("push", "PLAN1", "plan", "title", "--json", '"x"'), "FIELD_NOT_ARRAY"),
            (("add-item", "PLAN1", "P7", "--title", "x"), "REF_UNKNOWN"),
            (("add-phase", "PLAN1", "--title", "x", "--json", '{"design": "detailed"}'), "FIELD_OWNED"),
        ):
            with self.subTest(code=code):
                before = self.read("PLAN1", "plan.json")
                result = self.run_plan(*args, "--plans-root", str(self.plans), expect=1)
                self.assertTrue(result.stderr.startswith(f"{code}: "), result.stderr)
                self.assertEqual(self.read("PLAN1", "plan.json"), before)

    def test_add_item_with_malformed_phase_is_a_usage_error(self):
        self.new_plan()
        self.run_plan("add-item", "PLAN1", "phase-1", "--title", "x", "--plans-root", str(self.plans), expect=2)


class CheckAndRenderTests(CliCase):
    def test_check_errors_exit_1_with_codes_on_stderr_and_json_mode(self):
        self.new_plan()
        self.verb("add-phase", "PLAN1", "--title", "P")
        (self.plans / "2026.10.05-№1-DEMO" / "phases" / "P1" / "phase.json").write_text("{broken", encoding="utf-8")
        result = self.run_plan("check", "PLAN1", "--plans-root", str(self.plans), expect=1)
        self.assertIn("json: phases/P1/phase.json", result.stderr)
        self.assertIn("error(s)", result.stdout)
        report = json.loads(self.run_plan("check", "PLAN1", "--json", "--plans-root", str(self.plans), expect=1).stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(report["issues"][0]["code"], "json")

    def test_check_warnings_do_not_fail_and_are_listed(self):
        self.new_plan()
        result = self.verb("check", "PLAN1")
        self.assertIn("warning context_default: plan.json/context", result.stdout)
        report = json.loads(self.verb("check", "PLAN1", "--json").stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], 0)

    def test_negative_control_hand_edited_view_fails_render_check_with_its_name(self):
        self.new_plan()
        self.verb("render", "PLAN1", "--check")
        (self.plans / "2026.10.05-№1-DEMO" / "views/status.md").write_text("hand edit\n", encoding="utf-8")
        result = self.verb("render", "PLAN1", "--check", expect=1)
        self.assertIn("STALE_VIEW: views/status.md", result.stderr)
        self.assertEqual(self.read("PLAN1", "views/status.md"), "hand edit\n")  # --check never writes
        self.assertIn("0 error(s)", self.verb("check", "PLAN1").stdout)
        self.assertIn("views/status.md", self.verb("render", "PLAN1").stdout)
        self.verb("render", "PLAN1", "--check")

    def test_next_text_and_json(self):
        self.new_plan()
        self.assertEqual(self.verb("next", "PLAN1").stdout.strip(), "waiting: no phases yet (add-phase)")
        self.verb("add-phase", "PLAN1", "--title", "P")
        self.verb("set", "PLAN1", "P1", "--json", '{"goal": "g"}')
        action = json.loads(self.verb("next", "PLAN1", "--json").stdout)
        self.assertEqual((action["kind"], action["phase"]), ("design-phase", "P1"))


if __name__ == "__main__":
    unittest.main()
