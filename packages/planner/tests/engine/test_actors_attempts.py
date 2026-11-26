"""Separate actors and idempotent registration (T5, T7): registrar vs executor, --executed-by, --attempt-id."""
import copy
import io
import itertools
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import check, cli, lifecycle, ops, store, units  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
ARCHIVED_PLAN = REPO / "plans" / "archive" / "2026.10.05-№1-TASK-PLAN-JSON"
OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
SONNET = {"provider": "claude-code", "model": "claude-sonnet-5-5", "effort": "high"}
HAIKU = {"provider": "claude-code", "model": "claude-haiku-4-5-20251001", "effort": "high"}
ROUTER = {"provider": "codex", "model": "gpt-sol-6-1-mini", "effort": "low"}  # a cheap registrar, outside the pool
DETAIL = {
    "summary": "s", "why": "w", "scope": {"include": ["x"]}, "deliverables": ["d"],
    "task_files": [{"path": "lib/**", "change": "any"}],
    "route": {"class": "frontier", "effort": "high"},
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"},
                   {"id": "V2", "cmd": "true", "expect": "exit 0", "kind": "impact"}],
}
UNIT = {"goal": "Piece", "files": ["lib/piece.py"], "route": {"class": "implementation", "effort": "high"},
        "mode": "delegate"}
OLD_EVENT_KEYS = {"v", "ts", "type", "summary", "actor", "item", "phase", "data"}
NEW_KEYS = {"executed_by", "registered_by", "attempt_id", "evidence"}


def _cli(text):
    return "/".join(text[k] for k in ("provider", "model", "effort") if k in text)


class AttemptCase(unittest.TestCase):
    """Plan ACT: P1.1 and P1.2 (frontier/high) in one detailed phase."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        clock = itertools.count()
        lock = threading.Lock()

        def tick():
            with lock:
                n = next(clock)
            return f"2026-10-07T{n // 3600:02d}:{n // 60 % 60:02d}:{n % 60:02d}Z"

        patcher = mock.patch.object(store, "now", tick)
        patcher.start()
        self.addCleanup(patcher.stop)
        plans = Path(tmp.name) / "plans"
        plans.mkdir()
        plan = ops.new_plan("ACT", "Actors", plans_root=plans, repository="r", owner="o", authoring=OPUS,
                            message="m", date="2026.10.07")
        self.root = plan.root
        ops.add_phase(plan, "One")
        ops.patch(plan, "P1", {"goal": "g"})
        ops.add_item(plan, "P1", "First")
        ops.add_item(plan, "P1", "Second")
        ops.patch(plan, "P1.1", copy.deepcopy(DETAIL))
        ops.patch(plan, "P1.2", copy.deepcopy(DETAIL))
        lifecycle.design_done(self.root, "P1", actor=OPUS)

    def load(self):
        return store.load_plan(self.root)

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def events(self, *types):
        return [e for e in store.read_log(self.root) if not types or e["type"] in types]

    def refused(self, code, call, *args, **kwargs):
        before = self.tree()
        with self.assertRaises(PlanError) as caught:
            call(self.root, *args, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception)
        self.assertEqual(self.tree(), before, f"{code} refusal changed the plan directory")
        return caught.exception

    def finish(self, item="P1.1", status="done", **kwargs):
        kwargs.setdefault("checks", {"V1": 0})
        return lifecycle.finish(self.root, item, status, **kwargs)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main([argv[0], str(self.root), *argv[1:]])
        return code, out.getvalue()


class StartRegistrarTests(AttemptCase):
    def test_registrar_lands_in_the_start_event_only(self):  # case 8
        lifecycle.start(self.root, ["P1.1"], OPUS, registrar=ROUTER)
        event = self.events("start")[0]
        self.assertEqual(event["actor"], OPUS)
        self.assertEqual(event["registered_by"], ROUTER)
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"], OPUS)
        self.assertNotIn("registered_by", self.load().items["P1.1"]["result"])

    def test_start_without_registrar_keeps_the_old_event_keys(self):
        lifecycle.start(self.root, ["P1.1"], OPUS)
        self.assertEqual(set(self.events("start")[0]), OLD_EVENT_KEYS)

    def test_registrar_is_not_route_checked_but_the_executor_is(self):
        lifecycle.start(self.root, ["P1.1"], OPUS, registrar=HAIKU)
        self.refused("ROUTE_UNDERSHOOT", lambda root, *a: lifecycle.start(root, ["P1.2"], HAIKU, registrar=OPUS))

    def test_cli_flag(self):
        code, _ = self.run_cli("start", "P1.1", "--actor", _cli(OPUS), "--registrar", _cli(ROUTER))
        self.assertEqual(code, 0)
        self.assertEqual(self.events("start")[0]["registered_by"], ROUTER)


class FinishActorTests(AttemptCase):
    def setUp(self):
        super().setUp()
        lifecycle.start(self.root, ["P1.1", "P1.2"], OPUS)

    def test_finish_without_new_flags_keeps_event_and_result_keys(self):  # case 1
        result = self.finish(notes="n")
        self.assertFalse(result.already_registered)
        event = self.events("finish")[0]
        self.assertEqual(set(event), OLD_EVENT_KEYS)
        self.assertEqual(event["actor"], OPUS)
        self.assertEqual(set(self.load().items["P1.1"]["result"]),
                         {"started_at", "executor", "finished_at", "notes", "checks"})
        self.assertEqual(result.text().splitlines()[0], "P1.1 done")

    def test_actor_is_the_registrar_and_never_the_executor(self):  # case 2
        self.finish(actor=ROUTER)
        event = self.events("finish")[0]
        self.assertEqual(event["actor"], ROUTER)
        self.assertEqual(event["executed_by"], OPUS)
        self.assertEqual(event["registered_by"], ROUTER)
        recorded = self.load().items["P1.1"]["result"]
        self.assertEqual(recorded["executor"], OPUS)
        self.assertEqual(recorded["registered_by"], ROUTER)
        self.assertNotIn("attempt_id", recorded)

    def test_registrar_equal_to_the_executor_is_not_repeated(self):
        self.finish(actor={"provider": "claude-code", "model": "claude-opus-5-5"})
        event = self.events("finish")[0]
        self.assertEqual(event["executed_by"], OPUS)
        self.assertNotIn("registered_by", event)
        self.assertNotIn("registered_by", self.load().items["P1.1"]["result"])

    def test_executed_by_replaces_the_executor(self):
        stronger = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "max"}
        self.finish(executed_by=stronger, actor=ROUTER)
        recorded = self.load().items["P1.1"]["result"]
        self.assertEqual(recorded["executor"], stronger)
        event = self.events("finish")[0]
        self.assertEqual((event["actor"], event["executed_by"]), (ROUTER, stronger))

    def test_executed_by_alone_is_the_event_actor(self):
        self.finish(executed_by=OPUS)
        event = self.events("finish")[0]
        self.assertEqual((event["actor"], event["executed_by"]), (OPUS, OPUS))
        self.assertNotIn("registered_by", event)

    def test_executed_by_below_the_route_is_refused(self):  # case 3
        self.refused("ROUTE_UNDERSHOOT", lifecycle.finish, "P1.1", "done", checks={"V1": 0}, executed_by=SONNET)
        self.refused("ROUTE_UNDERSHOOT", lifecycle.finish, "P1.1", "done", checks={"V1": 0},
                     executed_by={**OPUS, "effort": "low"})

    def test_invalid_attempt_id_is_refused(self):
        for bad in ("", "-a", "a b", "x" * 129, "é"):
            self.refused("ATTEMPT_ID_INVALID", lifecycle.finish, "P1.1", "done", checks={"V1": 0}, attempt_id=bad)

    def test_check_evidence_and_settings_evidence_are_valid_optional_fields(self):
        self.finish(attempt_id="a1")
        plan = self.load()
        item = copy.deepcopy(plan.items["P1.1"])
        item["result"]["checks"][0]["evidence"] = "@plan/evidence/V1.json"
        store.check_doc(item, "item", "item")
        plan_doc = copy.deepcopy(plan.plan)
        plan_doc["settings"]["evidence"] = "required"
        store.check_doc(plan_doc, "plan", "plan")
        plan_doc["settings"]["evidence"] = "always"
        with self.assertRaises(PlanError):
            store.check_doc(plan_doc, "plan", "plan")


class FinishAttemptTests(AttemptCase):
    def setUp(self):
        super().setUp()
        lifecycle.start(self.root, ["P1.1", "P1.2"], OPUS)

    def test_repeat_of_the_same_attempt_is_a_no_op(self):  # case 4
        first = self.finish(attempt_id="run-1:P1.1", actor=ROUTER, checks={"V1": 0, "V2": 0})
        self.assertFalse(first.already_registered)
        self.assertEqual(self.load().items["P1.1"]["result"]["attempt_id"], "run-1:P1.1")
        self.assertEqual(self.events("finish")[0]["attempt_id"], "run-1:P1.1")
        lines = (self.root / store.LOG).read_text(encoding="utf-8").count("\n")
        before = self.tree()
        again = self.finish(attempt_id="run-1:P1.1", actor=ROUTER, checks={"V1": 0, "V2": 0})
        self.assertTrue(again.already_registered)
        self.assertEqual((again.item, again.status), ("P1.1", "done"))
        self.assertEqual(again.text().splitlines()[0], "P1.1 already registered (attempt run-1:P1.1)")
        self.assertEqual((self.root / store.LOG).read_text(encoding="utf-8").count("\n"), lines)
        self.assertEqual(self.tree(), before)
        subset = self.finish(attempt_id="run-1:P1.1", checks={"V1": 0})  # checks not passed are not compared
        self.assertTrue(subset.already_registered)

    def test_same_attempt_with_another_outcome_conflicts(self):  # case 5
        self.finish(attempt_id="A")
        self.refused("ATTEMPT_CONFLICT", lifecycle.finish, "P1.1", "blocked", escalation="e", attempt_id="A")
        self.refused("ATTEMPT_CONFLICT", lifecycle.finish, "P1.1", "done", checks={"V1": 1}, attempt_id="A")
        self.refused("ATTEMPT_CONFLICT", lifecycle.finish, "P1.1", "done", checks={"V1": 0, "V2": 4},
                     attempt_id="A")

    def test_attempt_check_runs_before_not_started(self):
        self.finish(attempt_id="A")
        self.refused("NOT_STARTED", lifecycle.finish, "P1.1", "done", checks={"V1": 0}, attempt_id="B")
        self.refused("NOT_STARTED", lifecycle.finish, "P1.1", "done", checks={"V1": 0})

    def test_reopen_makes_the_old_attempt_stale(self):  # case 6
        self.finish(attempt_id="A")
        lifecycle.reopen(self.root, "P1.1", "redo")
        self.refused("NOT_STARTED", lifecycle.finish, "P1.1", "done", checks={"V1": 0}, attempt_id="A")
        lifecycle.start(self.root, ["P1.1"], OPUS)
        self.assertFalse(self.finish(attempt_id="A").already_registered)
        self.assertEqual(len(self.events("finish")), 2)

    def test_concurrent_finishes_of_one_attempt_register_once(self):
        barrier, results, errors = threading.Barrier(4), [], []

        def run():
            barrier.wait()
            try:
                results.append(lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0}, attempt_id="A"))
            except PlanError as exc:  # pragma: no cover - surfaced by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(r.already_registered for r in results), [False, True, True, True])
        self.assertEqual(len(self.events("finish")), 1)

    def test_closing_finish_repeat_reports_the_done_plan(self):
        self.finish("P1.1")
        closing = self.finish("P1.2", attempt_id="last")
        self.assertTrue(closing.plan_done)
        again = self.finish("P1.2", attempt_id="last")
        self.assertTrue(again.already_registered)
        self.assertIsNone(again.phase_closed)
        self.assertTrue(again.plan_done)
        self.assertEqual(len(self.events("phase_closed")), 1)

    def test_cli_flags_and_json(self):
        argv = ("finish", "P1.1", "--status", "done", "--check", "V1=0", "--actor", _cli(ROUTER),
                "--executed-by", _cli(OPUS), "--attempt-id", "A", "--json")
        code, out = self.run_cli(*argv)
        self.assertEqual(code, 0)
        self.assertNotIn("already_registered", json.loads(out))
        code, out = self.run_cli(*argv)
        self.assertEqual((code, json.loads(out)["already_registered"]), (0, True))
        code, out = self.run_cli(*argv[:-1])
        self.assertEqual((code, out.splitlines()[0]), (0, "P1.1 already registered (attempt A)"))
        envelope = io.StringIO()
        with redirect_stdout(envelope):
            cli.main(["--output", "json", "finish", str(self.root), *argv[1:]])
        self.assertTrue(json.loads(envelope.getvalue())["data"]["already_registered"])
        self.assertEqual(len(self.events("finish")), 1)


class UnitAttemptTests(AttemptCase):
    def setUp(self):
        super().setUp()
        lifecycle.start(self.root, ["P1.1"], OPUS)
        self.unit_id = units.add_unit(self.root, "P1.1", "Piece", copy.deepcopy(UNIT))
        units.dispatch(self.root, "P1.1", self.unit_id, _cli(SONNET))

    def outcome(self):
        return self.load().units[f"P1.1/{self.unit_id}"]["outcome"]

    def delegates(self, status):
        return [e for e in self.events("delegate") if e["data"]["status"] == status]

    def test_return_without_new_flags_keeps_event_and_outcome_keys(self):
        units.return_unit(self.root, "P1.1", self.unit_id, notes="done", changed=["lib/piece.py"])
        self.assertFalse(NEW_KEYS & set(self.delegates("returned")[0]))
        self.assertFalse(NEW_KEYS & set(self.outcome()))
        self.assertEqual(self.delegates("returned")[0]["actor"], SONNET)

    def test_repeat_return_with_the_same_attempt_is_a_no_op(self):  # case 7
        self.assertFalse(units.return_unit(self.root, "P1.1", self.unit_id, notes="n", attempt_id="w1",
                                           actor=ROUTER))
        outcome = self.outcome()
        self.assertEqual((outcome["agent"], outcome["registered_by"], outcome["attempt_id"]), (SONNET, ROUTER, "w1"))
        event = self.delegates("returned")[0]
        self.assertEqual((event["actor"], event["registered_by"], event["attempt_id"]), (SONNET, ROUTER, "w1"))
        before = self.tree()
        self.assertTrue(units.return_unit(self.root, "P1.1", self.unit_id, notes="n", attempt_id="w1"))
        self.assertEqual(self.tree(), before)
        self.refused("ATTEMPT_CONFLICT", units.return_unit, "P1.1", self.unit_id, notes="other", attempt_id="w1")
        self.refused("ATTEMPT_CONFLICT", units.return_unit, "P1.1", self.unit_id, notes="n",
                     changed=["lib/piece.py"], attempt_id="w1")
        self.refused("ATTEMPT_CONFLICT", units.accept, "P1.1", self.unit_id, attempt_id="w1")

    def test_return_repeat_after_accept_is_still_a_no_op(self):
        units.return_unit(self.root, "P1.1", self.unit_id, notes="n", attempt_id="w1")
        units.accept(self.root, "P1.1", self.unit_id, notes="reviewed")
        self.assertNotIn("attempt_id", self.outcome())
        before = self.tree()
        self.assertTrue(units.return_unit(self.root, "P1.1", self.unit_id, notes="n", attempt_id="w1"))
        self.assertEqual(self.tree(), before)
        self.refused("UNIT_STATE", units.return_unit, "P1.1", self.unit_id, notes="n", attempt_id="w2")

    def test_repeat_accept_keeps_the_returned_notes(self):
        units.return_unit(self.root, "P1.1", self.unit_id, notes="n", changed=["lib/piece.py"])
        self.assertFalse(units.accept(self.root, "P1.1", self.unit_id, attempt_id="i1"))
        self.assertTrue(units.accept(self.root, "P1.1", self.unit_id, attempt_id="i1"))
        self.refused("ATTEMPT_CONFLICT", units.accept, "P1.1", self.unit_id, notes="late remark", attempt_id="i1")
        self.assertEqual(len(self.delegates("accepted")), 1)

    def test_executed_by_matches_the_worker_or_passes_the_unit_route(self):
        self.refused("ROUTE_UNDERSHOOT", units.return_unit, "P1.1", self.unit_id, executed_by=HAIKU)
        units.return_unit(self.root, "P1.1", self.unit_id, executed_by={**SONNET, "effort": "low"})
        event = self.delegates("returned")[0]
        self.assertEqual((event["actor"], event["executed_by"]), (SONNET, {**SONNET, "effort": "low"}))
        self.assertEqual(self.outcome()["agent"], SONNET)

    def test_a_stronger_other_executor_is_admitted(self):
        units.return_unit(self.root, "P1.1", self.unit_id, executed_by=OPUS)
        self.assertEqual(self.delegates("returned")[0]["executed_by"], OPUS)

    def test_a_later_transition_without_attempt_drops_the_attempt_fields(self):
        units.return_unit(self.root, "P1.1", self.unit_id, notes="n", attempt_id="w1", actor=ROUTER)
        units.rework(self.root, "P1.1", self.unit_id, notes="again")
        self.assertFalse({"attempt_id", "registered_by"} & set(self.outcome()))
        self.refused("ATTEMPT_CONFLICT", units.accept, "P1.1", self.unit_id, attempt_id="w1")
        self.assertTrue(units.return_unit(self.root, "P1.1", self.unit_id, notes="n", attempt_id="w1"))

    def test_cli_flags(self):
        ref = f"P1.1/{self.unit_id}"
        argv = ("unit", "P1.1", self.unit_id, "return", "--notes", "n", "--executed-by", _cli(SONNET),
                "--attempt-id", "w1", "--actor", _cli(ROUTER))
        self.assertEqual(self.run_cli(*argv), (0, f"{ref} return\n"))
        self.assertEqual(self.run_cli(*argv), (0, f"{ref} already registered (attempt w1)\n"))
        accept = ("unit", "P1.1", self.unit_id, "accept", "--attempt-id", "i1")
        self.assertEqual(self.run_cli(*accept), (0, f"{ref} accept\n"))
        self.assertEqual(self.run_cli(*accept), (0, f"{ref} already registered (attempt i1)\n"))
        self.assertEqual(self.run_cli("unit", "P1.1", self.unit_id, "accept", "--executed-by", _cli(OPUS))[0], 2)
        self.assertEqual(self.run_cli("unit", "P1.1", self.unit_id, "reject", "--notes", "x",
                                      "--attempt-id", "r1")[0], 2)


class CompatTests(unittest.TestCase):
    @unittest.skipUnless((ARCHIVED_PLAN / "plan.json").is_file(), "archived plan 1 is not in this checkout")
    def test_archived_plan_still_checks_clean(self):  # case 9
        # human_view (reads naming plan Markdown) is a later authoring rule the archived plan predates: it is a
        # warning there; every error, schema conformance included, must stay absent.
        issues = check.check(store.load_plan(ARCHIVED_PLAN))
        errors = [i for i in issues if i.level == "error"]
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
