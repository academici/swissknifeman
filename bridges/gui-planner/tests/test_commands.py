"""gui-planner commands through the aicore plugin protocol (gui:command) against a fake planner command line: the exact
argv of every command, the allowlist of fields, the status and revision guards, and the codes of refusals."""
import json
import os
import sys
import unittest
from pathlib import Path

from aicore.ext.plugins import invoke_one

from .test_queries import BRIDGE, FIXTURES, GUI_DOC, PLAN, AdapterCase

sys.path.insert(0, str(BRIDGE))
import adapter  # noqa: E402

COMMANDS = {command["id"]: command for command in GUI_DOC["commands"]}
BASE = ["planner", "--output", "json"]


class CommandCase(AdapterCase):
    def command(self, command_id, values, *, context=None, umbrella="umbrella-ok", project=True):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / umbrella)}
        given = {"plan_id": PLAN, **(context or {})}
        return invoke_one(self.plugin, "gui:command", {"id": command_id, "context": given, "input": values}, env=env,
                          project=str(self.project) if project else None)

    def ok(self, command_id, values, **kwargs):
        result = self.command(command_id, values, **kwargs)
        self.assertEqual("ok", result.status, (result.code, result.error))
        return result.output

    def refused(self, command_id, values, code, **kwargs):
        result = self.command(command_id, values, **kwargs)
        self.assertEqual(("error", code), (result.status, result.code), result.error)
        return result

    def argvs(self):
        log = self.home / "umbrella.log"
        return [c["argv"] for c in self.calls()] if log.exists() else []

    def writes(self):
        return [a for a in self.argvs() if a[len(BASE):len(BASE) + 1] == ["set"]]

    def revision(self, ref):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home)}
        import subprocess
        out = subprocess.run([str(FIXTURES / "umbrella-ok"), *BASE, "get", PLAN, ref], capture_output=True, text=True,
                             env=env).stdout
        return json.loads(out)["data"]["revision"]


class TestItemSet(CommandCase):
    def set(self, patch, revision=None, item="P2.1", **kwargs):
        values = {"patch": patch if isinstance(patch, str) else json.dumps(patch),
                  "expected_revision": revision or self.revision(item)}
        return self.command("gui-planner.item-set", values, context={"item_id": item}, **kwargs)

    def test_set_passes_the_exact_argv_and_returns_the_new_revision(self):
        before = self.revision("P2.1")
        result = self.set({"summary": "-new text", "route": {"class": "frontier"}})
        self.assertEqual("ok", result.status, result.error)
        self.assertEqual([BASE + ["set", PLAN, "P2.1", "--json", '{"summary":"-new text","route":{"class":"frontier"}}',
                                  f"--expected-revision={before}"]], self.writes())
        self.assertEqual(self.revision("P2.1"), result.output["revision"])
        self.assertNotEqual(before, result.output["revision"])
        self.assertEqual({"errors": 0, "warnings": 1}, result.output["check"])

    def test_the_order_is_status_read_then_set_then_read_back_then_check(self):
        self.set({"title": "T"})
        self.assertEqual(["get", "set", "get", "check"], [a[len(BASE)] for a in self.argvs()][-4:])

    def test_a_stale_revision_is_a_conflict_and_a_second_use_of_the_old_one_too(self):
        old = self.revision("P2.1")
        self.assertEqual("ok", self.set({"title": "one"}, old).status)
        current = self.revision("P2.1")
        again = self.set({"title": "two"}, old)
        self.assertEqual(("error", "PLAN_REVISION_CONFLICT"), (again.status, again.code))
        self.assertEqual(current, self.revision("P2.1"))  # the refused write changed nothing

    def test_lifecycle_and_identity_fields_are_not_editable_and_nothing_is_written(self):
        for field in ("status", "result", "updated_at", "id", "units", "artifacts", "sections", "$schema"):
            with self.subTest(field=field):
                result = self.set({"title": "x", field: "y"})
                self.assertEqual(("error", "FIELD_NOT_EDITABLE"), (result.status, result.code))
        self.assertEqual([], self.writes())

    def test_an_item_in_progress_is_refused_before_the_write(self):
        result = self.set({"title": "x"}, item="P2.2")
        self.assertEqual(("error", "ITEM_IN_PROGRESS"), (result.status, result.code))
        self.assertEqual([], self.writes())

    def test_invalid_input_is_refused_before_any_planner_call(self):
        rev = self.revision("P2.1")
        before = len(self.argvs())
        cases = [("[1]", rev), ("  5", rev), ("not json", rev), ("{}", rev), ('{"title": "x"', rev),
                 (json.dumps({"title": "x" * 70000}), rev), ('{"title": "x"}', None)]
        for patch, revision in cases:
            with self.subTest(patch=patch[:20], revision=revision):
                values = {"patch": patch}
                if revision:
                    values["expected_revision"] = revision
                self.assertEqual("INPUT_INVALID", self.command("gui-planner.item-set", values,
                                                               context={"item_id": "P2.1"}).code)
        for bad in ("abc", "sha256:XYZ", "sha256:" + "0" * 63, 5):
            with self.subTest(revision=bad):
                self.assertEqual("INPUT_INVALID", self.command("gui-planner.item-set", {
                    "patch": '{"title": "x"}', "expected_revision": bad}, context={"item_id": "P2.1"}).code)
        self.assertEqual(before, len(self.argvs()))

    def test_planner_codes_pass_as_they_are(self):
        result = self.command("gui-planner.item-set", {"patch": '{"title": "x"}', "expected_revision": "sha256:" + "a" * 64},
                              context={"item_id": "P2.1"})
        self.assertEqual("PLAN_REVISION_CONFLICT", result.code)
        self.assertEqual("PLAN_NOT_FOUND", self.set({"title": "x"}, "sha256:" + "a" * 64, umbrella="umbrella-missing").code)

    def test_check_errors_after_the_write_are_reported_not_rolled_back(self):
        result = self.set({"title": "x"}, item="P2.4")
        self.assertEqual("ok", result.status, result.error)
        self.assertEqual({"errors": 2, "warnings": 1}, result.output["check"])
        self.assertEqual(1, len(self.writes()))

    def test_a_command_needs_a_project_and_an_item(self):
        self.assertEqual("PLANNER_CONTEXT_MISSING", self.set({"title": "x"}, "sha256:" + "a" * 64, project=False).code)
        result = self.command("gui-planner.item-set", {"patch": '{"title": "x"}', "expected_revision": "sha256:" + "a" * 64})
        self.assertEqual("PLANNER_CONTEXT_MISSING", result.code)


class TestOtherCommands(CommandCase):
    def test_phase_set(self):
        rev = self.revision("P2")
        out = self.ok("gui-planner.phase-set", {"phase": "P2", "patch": '{"goal": "-g"}', "expected_revision": rev})
        self.assertEqual([BASE + ["set", PLAN, "P2", "--json", '{"goal":"-g"}', f"--expected-revision={rev}"]],
                         self.writes())
        self.assertNotEqual(rev, out["revision"])
        for field in ("batches", "items", "design", "closed", "id"):
            with self.subTest(field=field):
                self.refused("gui-planner.phase-set", {"phase": "P2", "patch": json.dumps({field: 1}),
                                                       "expected_revision": rev}, "FIELD_NOT_EDITABLE")
        for phase in ("P2.1", "x", "../P2"):
            with self.subTest(phase=phase):
                self.refused("gui-planner.phase-set", {"phase": phase, "patch": '{"goal": "g"}',
                                                       "expected_revision": rev}, "INPUT_INVALID")
        self.assertEqual(1, len(self.writes()))

    def test_decide_sends_texts_as_one_flag_element_each(self):
        out = self.ok("gui-planner.decision-decide", {"decision": "D2", "accept": "-A", "rationale": "--because", "by": "agent"})
        self.assertTrue(out["done"])
        self.assertEqual([BASE + ["decide", PLAN, "D2", "--accept=-A", "--rationale=--because", "--by=agent",
                                  "--actor=gui/browser"]], self.argvs())

    def test_decide_defaults_to_the_owner_and_validates(self):
        self.ok("gui-planner.decision-decide", {"decision": "D2", "accept": "A", "rationale": "r"})
        self.assertIn("--by=owner", self.argvs()[-1])
        for values in ({"decision": "D2", "accept": "A"}, {"decision": "D2", "rationale": "r"},
                       {"decision": "2", "accept": "A", "rationale": "r"},
                       {"decision": "D2", "accept": "A", "rationale": "r", "by": "root"},
                       {"decision": "D2", "accept": "A", "rationale": "x" * 4001}):
            with self.subTest(values=values):
                self.refused("gui-planner.decision-decide", values, "INPUT_INVALID")

    def test_reopen_grant_and_log_note(self):
        self.ok("gui-planner.item-reopen", {"reason": "-redo"}, context={"item_id": "P1.1"})
        self.ok("gui-planner.grant", {"gate": "OWNER-1", "note": "--ok"})
        self.ok("gui-planner.log-note", {"target": "P1.1", "type": "note", "summary": "-hello"})
        self.ok("gui-planner.log-note", {"target": "P2", "type": "blocker", "summary": "s"})
        self.assertEqual([
            BASE + ["reopen", PLAN, "P1.1", "--reason=-redo", "--actor=gui/browser"],
            BASE + ["grant", PLAN, "OWNER-1", "--note=--ok", "--actor=gui/browser"],
            BASE + ["log", PLAN, "P1.1", "--type=note", "--summary=-hello", "--actor=gui/browser"],
            BASE + ["log", PLAN, "P2", "--type=blocker", "--summary=s", "--actor=gui/browser"]], self.argvs())

    def test_invalid_values_never_reach_the_planner(self):
        cases = [("gui-planner.item-reopen", {"reason": ""}, {"item_id": "P1.1"}),
                 ("gui-planner.item-reopen", {"reason": "r"}, {}),
                 ("gui-planner.grant", {"gate": "lower", "note": "n"}, {}),
                 ("gui-planner.grant", {"gate": "G1"}, {}),
                 ("gui-planner.log-note", {"target": "P1.1", "type": "oops", "summary": "s"}, {}),
                 ("gui-planner.log-note", {"target": "plan", "type": "note", "summary": "s"}, {}),
                 ("gui-planner.log-note", {"target": "P1", "type": "note", "summary": "x" * 1001}, {})]
        for command_id, values, context in cases:
            with self.subTest(command=command_id, values=values):
                result = self.command(command_id, values, context=context)
                self.assertIn(result.code, ("INPUT_INVALID", "PLANNER_CONTEXT_MISSING"))
        self.assertEqual([], self.argvs())

    def test_planner_refusals_keep_their_code(self):
        self.refused("gui-planner.grant", {"gate": "NOGATE", "note": "n"}, "GATE_UNKNOWN")
        self.refused("gui-planner.grant", {"gate": "G", "note": "n"}, "PLAN_NOT_FOUND", umbrella="umbrella-missing")

    def test_unknown_command_and_start_finish_are_not_published(self):
        self.refused("gui-planner.finish", {}, "PLANNER_UNKNOWN_COMMAND")
        self.refused("gui-planner.start", {}, "PLANNER_UNKNOWN_COMMAND")
        self.assertFalse({"gui-planner.start", "gui-planner.finish"} & set(COMMANDS))


class TestDescriptors(unittest.TestCase):
    def test_commands_are_invoke_with_plan_write_and_the_risk_of_the_decision(self):
        self.assertEqual({"gui-planner.item-set", "gui-planner.phase-set", "gui-planner.decision-decide",
                          "gui-planner.item-reopen", "gui-planner.grant", "gui-planner.log-note"}, set(COMMANDS))
        for command in COMMANDS.values():
            self.assertEqual({"kind": "invoke"}, command["exec"])
            self.assertEqual(["plan.write"], command["effects"])
            self.assertIn("{plan_id}", command["concurrency_key"])
        risk = {cid.split(".")[1]: (c["risk"], c["confirmation"]) for cid, c in COMMANDS.items()}
        self.assertEqual({"item-set": ("medium", "risk-based"), "phase-set": ("medium", "risk-based"),
                          "decision-decide": ("medium", "risk-based"), "item-reopen": ("high", "always"),
                          "grant": ("high", "always"), "log-note": ("low", "none")}, risk)

    def test_the_writes_require_the_revision(self):
        for name in ("item-set", "phase-set"):
            field = [f for f in COMMANDS[f"gui-planner.{name}"]["input"] if f["name"] == "expected_revision"][0]
            self.assertTrue(field["required"])
            self.assertEqual("^sha256:[0-9a-f]{64}$", field["pattern"])

    def test_allowlists_hold_no_lifecycle_or_identity_field(self):
        owned = {"$schema", "id", "status", "result", "updated_at", "units", "artifacts", "sections", "closed", "design",
                 "items", "batches"}
        self.assertFalse(owned & adapter.ALLOW_ITEM)
        self.assertFalse(owned & adapter.ALLOW_PHASE)


if __name__ == "__main__":
    unittest.main()
