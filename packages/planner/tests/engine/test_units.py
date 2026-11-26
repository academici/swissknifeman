"""Units (D3): every transition and refusal, UNITS_OPEN, the golden brief, the pack's Units section, the CLI verbs."""
import copy
import io
import itertools
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import check, cli, context, lifecycle, ops, settings, store, units  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
HAIKU = "claude-code/haiku"
SONNET = "claude-code/sonnet"
DETAIL = {
    "summary": "s", "why": "w", "scope": {"include": ["x"]}, "deliverables": ["d"], "rules": ["Keep it small"],
    "task_files": [{"path": "lib/**", "change": "any"}, {"path": "docs/*.md", "change": "any"}],
    "reads": [{"path": "docs/spec.md", "why": "the spec", "required": True}],
    "validation": [{"id": "V1", "cmd": "python3 -m unittest", "expect": "OK", "kind": "acceptance"}],
    "decisions": [],
}
U1 = {"goal": "Error types", "files": ["lib/errors.py"], "route": {"class": "economy", "effort": "medium"},
      "mode": "delegate", "instructions": "Pure dataclasses.", "checks": ["V1"],
      "reads": [{"path": "docs/errors.md", "why": "message format"}]}
U2 = {"goal": "Docs", "files": ["docs/errors.md"], "route": {"class": "economy", "effort": "low"}, "mode": "either"}
U3 = {"goal": "Glue", "files": ["lib/config.py"], "mode": "self", "depends_on": ["U1"]}


class UnitCase(unittest.TestCase):
    """Plan UNT: P1.1 in progress (OPUS) and P1.2 todo; units are added by the tests."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        clock = itertools.count()
        patcher = mock.patch.object(store, "now", lambda: f"2026-10-07T00:{next(clock) // 60:02d}:{next(clock) % 60:02d}Z")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = Path(tmp.name)
        self.plans = self.repo / "plans"
        self.plans.mkdir()
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
        plan = ops.new_plan("UNT", "Units", plans_root=self.plans, repository="r", owner="o", authoring=OPUS,
                            message="m", date="2026.10.07")
        self.root = plan.root
        ops.add_phase(plan, "One")
        ops.patch(plan, "P1", {"goal": "g"})
        ops.add_item(plan, "P1", "First")
        ops.add_item(plan, "P1", "Second")
        ops.patch(plan, "P1.1", copy.deepcopy(DETAIL))
        ops.patch(plan, "P1.2", copy.deepcopy(DETAIL))
        lifecycle.design_done(self.root, "P1", actor=OPUS)
        lifecycle.start(self.root, ["P1.1"], OPUS)

    def load(self):
        return store.load_plan(self.root)

    def unit(self, key="P1.1/U1"):
        return self.load().units[key]

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def refused(self, code, call, *args, **kwargs):
        before = self.tree()
        with self.assertRaises(PlanError) as caught:
            call(self.root, *args, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception)
        self.assertEqual(self.tree(), before, f"{code} refusal changed the plan directory")

    def add(self, title, data):
        return units.add_unit(self.root, "P1.1", title, data)

    def delegate_events(self):
        return [e for _, e, _ in store.log_lines(self.root) if e and e.get("type") == "delegate"]

    def returned(self, unit="U1"):
        units.dispatch(self.root, "P1.1", unit, HAIKU)
        units.return_unit(self.root, "P1.1", unit, notes="done", changed=["lib/errors.py"])


class AddTests(UnitCase):
    def test_add_creates_the_unit_file_and_lists_it(self):
        self.assertEqual(self.add("Errors", U1), "U1")
        self.assertEqual(self.add("Docs", U2), "U2")
        plan = self.load()
        self.assertEqual(plan.items["P1.1"]["units"], ["U1", "U2"])
        self.assertTrue((self.root / "phases" / "P1" / "P1.1" / "U1.json").is_file())
        unit = plan.units["P1.1/U2"]
        self.assertEqual((unit["status"], unit["outcome"], unit["item"]), ("todo", None, "P1.1"))
        self.assertEqual([i for i in check.check(plan) if i.level == "error"], [])

    def test_defaults_come_from_the_item(self):
        self.add("Bare", {"files": ["lib/a.py"]})
        unit = self.unit()
        self.assertEqual((unit["goal"], unit["mode"], unit["route"]), ("Bare", "either", {"class": "implementation", "effort": "high"}))

    def test_lifecycle_owned_fields_and_missing_files_are_refused(self):
        self.refused("FIELD_OWNED", units.add_unit, "P1.1", "X", {"files": ["lib/a.py"], "status": "accepted"})
        self.refused("UNIT_INVALID", units.add_unit, "P1.1", "X", {})
        self.refused("REF_UNKNOWN", units.add_unit, "P9.9", "X", {"files": ["a"]})

    def test_independent_units_with_overlapping_files_are_refused(self):
        self.add("Errors", U1)
        self.refused("UNIT_INVALID", units.add_unit, "P1.1", "Clash", {"files": ["lib/errors.py"]})
        self.add("Chained", {"files": ["lib/errors.py"], "depends_on": ["U1"]})  # a dependency path makes it legal


class DispatchTests(UnitCase):
    def test_unknown_worker_warns_in_delegate_event(self):
        self.add("Errors", U1)
        path = units.dispatch(self.root, "P1.1", "U1", "claude-code/mystery-model/high")
        self.assertTrue(path.is_file())
        self.assertEqual(self.unit()["status"], "dispatched")
        self.assertEqual(self.delegate_events()[0]["data"]["route"], "ROUTE_MODEL_UNKNOWN")
        self.assertEqual(self.delegate_events()[0]["data"]["class"], "unknown")

    def test_unknown_worker_refused_by_configuration_without_writing(self):
        self.add("Errors", U1)
        config = settings.for_plan(self.load())
        strict = replace(config, values={**config.values, "routing.unknown_model": "refuse"})
        with mock.patch.object(settings, "for_plan", return_value=strict):
            self.refused("ROUTE_MODEL_UNKNOWN", units.dispatch, "P1.1", "U1", "claude-code/mystery-model/high")
            self.assertTrue(units.dispatch(self.root, "P1.1", "U1", HAIKU).is_file())

    def test_dispatch_writes_the_brief_and_logs_the_event(self):
        self.add("Errors", U1)
        path = units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.assertEqual(path, self.root / "phases" / "P1" / "P1.1" / "U1" / "brief.json")
        unit = self.unit()
        self.assertEqual(unit["status"], "dispatched")
        self.assertEqual(unit["outcome"]["agent"], {"provider": "claude-code", "model": "haiku"})
        (event,) = self.delegate_events()
        self.assertEqual(event["data"], {"unit": "U1", "class": "economy", "model": "haiku", "status": "dispatched"})

    def test_json_brief_contains_contract_and_reporting_api(self):
        self.add("Errors", U1)
        value = json.loads(units.dispatch(self.root, "P1.1", "U1", HAIKU).read_text())
        self.assertEqual(value["unit"]["goal"], "Error types")
        self.assertEqual(value["context"]["item"]["rules"], ["Keep it small"])
        self.assertNotIn("report_api", value)

    def test_refusals(self):
        self.add("Errors", U1)
        self.add("Glue", U3)  # U2
        self.refused("AGENT_REQUIRED", units.dispatch, "P1.1", "U1", "nobody")
        self.refused("UNIT_SELF", units.dispatch, "P1.1", "U2", HAIKU)
        self.refused("REF_UNKNOWN", units.dispatch, "P1.1", "U7", HAIKU)
        self.add("Strong", {"files": ["lib/s.py"], "mode": "delegate", "route": {"class": "frontier", "effort": "high"}})
        self.refused("ROUTE_UNDERSHOOT", units.dispatch, "P1.1", "U3", SONNET)
        self.refused("ROUTE_UNDERSHOOT", units.dispatch, "P1.1", "U1", "claude-code/haiku/low")
        self.add("Later", {"files": ["lib/l.py"], "mode": "delegate", "depends_on": ["U1"]})
        self.refused("UNIT_DEPENDENCY", units.dispatch, "P1.1", "U4", HAIKU)
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.refused("UNIT_STATE", units.dispatch, "P1.1", "U1", HAIKU)

    def test_the_item_must_be_in_progress(self):
        units.add_unit(self.root, "P1.2", "Other", {"files": ["lib/o.py"], "mode": "delegate"})
        self.refused("ITEM_NOT_IN_PROGRESS", units.dispatch, "P1.2", "U1", SONNET)


class TransitionTests(UnitCase):
    def setUp(self):
        super().setUp()
        self.add("Errors", U1)

    def test_return_accept(self):
        self.returned()
        self.assertEqual(self.unit()["status"], "returned")
        self.assertEqual(self.unit()["outcome"]["changed"], ["lib/errors.py"])
        units.accept(self.root, "P1.1", "U1", notes="diff reviewed, V1 rerun OK", minutes=6)
        outcome = self.unit()["outcome"]
        self.assertEqual((self.unit()["status"], outcome["minutes"], outcome["agent"]["model"]),
                         ("accepted", 6, "haiku"))
        events = [e["data"] for e in self.delegate_events()]
        self.assertEqual([d["status"] for d in events], ["dispatched", "returned", "accepted"])
        self.assertEqual(events[-1]["minutes"], 6)

    def test_rework_sends_the_unit_back_with_notes_and_counts(self):
        self.returned()
        units.rework(self.root, "P1.1", "U1", notes="use frozen dataclasses")
        unit = self.unit()
        self.assertEqual((unit["status"], unit["outcome"]["notes"]), ("dispatched", "use frozen dataclasses"))
        brief = (self.root / "phases/P1/P1.1/U1/brief.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(brief)["rework"], "use frozen dataclasses")
        units.return_unit(self.root, "P1.1", "U1", notes="fixed")
        units.rework(self.root, "P1.1", "U1", notes="once more")
        counts = [e["data"].get("rework") for e in self.delegate_events() if e["data"]["status"] == "reworked"]
        self.assertEqual(counts, [1, 2])
        units.return_unit(self.root, "P1.1", "U1", notes="ok")
        units.accept(self.root, "P1.1", "U1")

    def test_rework_stops_at_the_review_rounds_limit(self):
        self.returned()
        units.rework(self.root, "P1.1", "U1", notes="round one")
        units.return_unit(self.root, "P1.1", "U1", notes="fixed")
        units.rework(self.root, "P1.1", "U1", notes="round two")
        units.return_unit(self.root, "P1.1", "U1", notes="fixed again")
        self.refused("REWORK_LIMIT", units.rework, "P1.1", "U1", notes="round three")
        self.assertEqual(self.unit()["status"], "returned")
        units.accept(self.root, "P1.1", "U1")

    def test_reject_needs_notes_and_works_from_dispatched_or_returned(self):
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.refused("NOTES_REQUIRED", units.reject, "P1.1", "U1", notes=" ")
        units.reject(self.root, "P1.1", "U1", notes="wrong approach, doing it myself")
        self.assertEqual(self.unit()["status"], "rejected")
        self.assertEqual(self.delegate_events()[-1]["data"]["status"], "rejected")

    def test_wrong_state_refusals(self):
        self.refused("UNIT_STATE", units.return_unit, "P1.1", "U1", notes="x")  # todo
        self.refused("UNIT_STATE", units.accept, "P1.1", "U1")
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.refused("UNIT_STATE", units.accept, "P1.1", "U1")
        self.refused("UNIT_STATE", units.rework, "P1.1", "U1", notes="x")
        units.return_unit(self.root, "P1.1", "U1", notes="x")
        self.refused("MINUTES_INVALID", units.accept, "P1.1", "U1", minutes=-1)
        self.refused("NOTES_REQUIRED", units.rework, "P1.1", "U1", notes="")
        units.accept(self.root, "P1.1", "U1")
        self.refused("UNIT_STATE", units.reject, "P1.1", "U1", notes="x")


class FinishTests(UnitCase):
    def finish(self, status="done"):
        return lifecycle.finish(self.root, "P1.1", status, checks={"V1": 0}, deviations=["d"] if status != "done" else [])

    def test_units_still_out_block_done_and_done_with_deviations(self):
        self.add("Errors", U1)
        self.refused("UNITS_OPEN", lifecycle.finish, "P1.1", "done", checks={"V1": 0})
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        units.return_unit(self.root, "P1.1", "U1")
        units.accept(self.root, "P1.1", "U1")
        self.finish()
        self.assertEqual(self.load().items["P1.1"]["status"], "done")

    def test_dispatched_and_returned_units_refuse_finish(self):
        self.add("Errors", U1)
        self.add("Docs", U2)
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.returned("U2")
        for status in ("done", "done_with_deviations"):
            self.refused("UNITS_OPEN", lifecycle.finish, "P1.1", status, checks={"V1": 0}, deviations=["d"])
        self.refused("UNITS_OPEN", lifecycle.finish, "P1.1", "done", checks={"V1": 0})
        units.reject(self.root, "P1.1", "U1", notes="mine now")
        units.accept(self.root, "P1.1", "U2")
        self.finish()
        lifecycle.reopen(self.root, "P1.1", "again")
        self.assertEqual(self.load().items["P1.1"]["status"], "todo")

    def test_blocked_is_allowed_with_units_out(self):
        self.add("Errors", U1)
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        lifecycle.finish(self.root, "P1.1", "blocked", escalation="owner decides")
        self.assertEqual(self.load().items["P1.1"]["status"], "blocked")


class PackTests(UnitCase):
    def pack(self):
        return context.render(self.load(), "P1.1")

    def test_no_units_no_section(self):
        self.assertNotIn("## Units", self.pack())

    def test_units_and_ready_candidates_are_json(self):
        self.add("Errors", U1)
        self.add("Docs", U2)
        self.add("Glue", U3)
        value = json.loads(self.pack())
        self.assertEqual([u["id"] for u in value["units"]], ["U1", "U2", "U3"])
        self.assertEqual([u["ref"] for u in value["ready_units"]], ["P1.1/U1", "P1.1/U2"])
        self.assertEqual(units.parallel_pairs(self.load(), "P1.1"), [("U1", "U2"), ("U2", "U3")])
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.assertEqual(json.loads(self.pack())["units"][0]["status"], "dispatched")

    def test_finished_units_leave_the_parallel_hint(self):
        self.add("Errors", U1)
        self.add("Docs", U2)
        self.returned()
        units.accept(self.root, "P1.1", "U1")
        self.assertNotIn("Parallel-safe", self.pack())


class CliTests(UnitCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*argv, "--plans-root", str(self.plans)])
        return code, out.getvalue(), err.getvalue()

    def test_verbs_walk_a_unit_through_its_life(self):
        plan = self.root.name
        self.assertEqual(self.run_cli("unit", plan, "P1.1", "add", "--title", "Errors", "--json", json.dumps(U1))[:2],
                         (0, "P1.1/U1 added\n"))
        code, out, _ = self.run_cli("unit", plan, "P1.1", "U1", "dispatch", "--agent", HAIKU)
        self.assertEqual(code, 0)
        self.assertIn("brief:", out)
        for argv in (("return", "--notes", "ok", "--changed", "lib/errors.py"), ("accept", "--notes", "reviewed", "--minutes", "5")):
            self.assertEqual(self.run_cli("unit", plan, "P1.1", "U1", *argv)[0], 0)
        self.assertEqual(self.unit()["status"], "accepted")
        code, out, _ = self.run_cli("stats", plan)
        self.assertEqual(code, 0)
        self.assertIn("economy/haiku: accepted 1", out)

    def test_refusals_and_usage_errors(self):
        plan = self.root.name
        self.assertEqual(self.run_cli("unit", plan, "P1.1", "U1", "dispatch")[0], 2)  # --agent missing
        code, _, err = self.run_cli("unit", plan, "P1.1", "U9", "accept")
        self.assertEqual((code, err.split(":")[0]), (1, "REF_UNKNOWN"))
        self.assertEqual(self.run_cli("unit", plan, "P1.1", "add")[0], 2)
        self.assertEqual(self.run_cli("unit", plan, "P1.1", "U1", "explode")[0], 2)
        self.add("Errors", U1)
        units.dispatch(self.root, "P1.1", "U1", HAIKU)
        self.assertEqual(self.run_cli("unit", plan, "P1.1", "U1", "reject")[0], 2)


if __name__ == "__main__":
    unittest.main()
