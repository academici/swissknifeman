"""reconcile: integrator closure of phases finished in other trees; idempotence, next reason, check drift."""
import copy
import io
import itertools
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

from planner.plan import catalog, check, cli, lifecycle, ops, store  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo

OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
DETAIL = {
    "summary": "s", "why": "w", "scope": {"include": ["x"]}, "deliverables": ["d"],
    "task_files": [{"path": "lib/x.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}],
}


class ReconcileCase(unittest.TestCase):
    """Plan REC: P1 detailed (P1.1, P1.2 independent, one batch), P2 detailed (P2.1)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        clock = itertools.count()

        def tick():
            n = next(clock)
            return f"2026-10-07T10:{n // 60 % 60:02d}:{n % 60:02d}Z"

        patcher = mock.patch.object(store, "now", tick)
        patcher.start()
        self.addCleanup(patcher.stop)
        plans = Path(tmp.name) / "plans"
        plans.mkdir()
        plan = ops.new_plan("REC", "Reconcile", plans_root=plans, repository="r", owner="o", authoring=OPUS,
                            message="m", date="2026.10.07")
        self.root = plan.root
        for phase_id, title, items in (("P1", "One", ("First", "Second")), ("P2", "Two", ("Third",))):
            ops.add_phase(plan, title)
            ops.patch(plan, phase_id, {"goal": "g"})
            for n, item_title in enumerate(items, 1):
                ops.add_item(plan, phase_id, item_title)
                ops.patch(plan, f"{phase_id}.{n}", copy.deepcopy(DETAIL))
            members = [f"{phase_id}.{n}" for n in range(1, len(items) + 1)]
            ops.set_batches(plan, phase_id, [{"id": "B1", "items": members, "mode": "recommended"}])
            lifecycle.design_done(self.root, phase_id, actor=OPUS)
        self.plan_id = plan.plan["id"]

    def plan(self):
        return store.load_plan(self.root)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def events(self, *types):
        return [e for e in store.read_log(self.root) if not types or e["type"] in types]

    def merged(self, item_id, status="done"):
        """``item_id`` as a merged branch leaves it: terminal, finished in another tree, phase not closed."""
        phase_id = item_id.split(".")[0]
        demo.rewrite(self.root, f"phases/{phase_id}/{item_id}.json", lambda d: d.update(
            status=status, result={"started_at": "2026-10-07T09:00:00Z", "finished_at": "2026-10-07T09:30:00Z",
                                   **({"escalation": "owner"} if status == "blocked" else {})}))

    def warnings(self, code):
        return [i for i in check.check(self.plan()) if i.code == code]

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*argv])
        return code, out.getvalue(), err.getvalue()


class ReconcileTests(ReconcileCase):
    def test_nothing_to_reconcile_writes_nothing(self):
        before, count = self.snapshot(), len(self.events())
        result = lifecycle.reconcile(self.root, actor=OPUS)
        self.assertEqual((result.closed, result.plan_done), ((), False))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.events()), count)
        self.assertEqual(result.text(), f"nothing to reconcile\nnext: {lifecycle.next(self.plan()).exact}")

    def test_terminal_phase_is_closed_once_with_via_reconcile(self):
        self.merged("P1.1")
        self.merged("P1.2", "done_with_deviations")
        result = lifecycle.reconcile(self.root, actor=OPUS)
        self.assertEqual((result.closed, result.plan_done), ((("P1", "done_with_deviations"),), False))
        closed = self.plan().phases["P1"]["closed"]
        self.assertEqual((closed["result"], closed["summary"]), ("done_with_deviations",
                                                                 "2 item(s): 1 done, 1 done_with_deviations"))
        [event] = self.events("phase_closed")
        self.assertEqual((event["phase"], event["summary"], event["data"], event["actor"]),
                         ("P1", "P1 closed: done_with_deviations", {"result": "done_with_deviations",
                                                                    "via": "reconcile"}, OPUS))
        self.assertEqual(self.plan().plan["status"], "active")
        self.assertEqual(result.text(), f"phase P1 closed: done_with_deviations\nnext: {result.next.exact}")
        self.assertEqual(result.next.exact, f"run-items: planner:plan-run {self.plan_id} P2.1")
        before = self.snapshot()
        again = lifecycle.reconcile(self.root)
        self.assertEqual((again.closed, again.plan_done), ((), False))
        self.assertEqual(self.snapshot(), before)

    def test_last_phases_close_together_and_end_the_plan(self):
        for item_id in ("P1.1", "P1.2", "P2.1"):
            self.merged(item_id)
        result = lifecycle.reconcile(self.root)
        self.assertEqual(result.closed, (("P1", "done"), ("P2", "done")))
        self.assertTrue(result.plan_done)
        self.assertEqual(self.plan().plan["status"], "done")
        self.assertEqual([e["phase"] for e in self.events("phase_closed")], ["P1", "P2"])
        self.assertEqual(self.events("phase_closed")[0]["actor"], OPUS)  # default: plan authoring
        self.assertEqual(result.text(), f"phase P1 closed: done\nphase P2 closed: done\nplan done\n"
                                        f"next: archive: planner:plan-close {self.plan_id} archive")
        self.assertEqual([i for i in check.check(self.plan()) if i.level == "error"], [])

    def test_blocked_closure_keeps_the_plan_open(self):
        self.merged("P1.1")
        self.merged("P1.2", "blocked")
        self.merged("P2.1")
        result = lifecycle.reconcile(self.root)
        self.assertEqual(result.closed, (("P1", "blocked"), ("P2", "done")))
        self.assertFalse(result.plan_done)
        self.assertEqual(self.plan().plan["status"], "active")

    def test_closed_phases_with_unfinished_plan_status_finish_the_plan(self):
        lifecycle.start(self.root, ["P1.1", "P1.2"], OPUS)
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0})
        lifecycle.finish(self.root, "P1.2", "done", checks={"V1": 0})
        self.merged("P2.1")
        demo.rewrite(self.root, "phases/P2/phase.json", lambda d: d.update(
            closed={"at": "2026-10-07T09:40:00Z", "result": "done", "summary": "1 item(s): 1 done"}))
        result = lifecycle.reconcile(self.root)
        self.assertEqual((result.closed, result.plan_done), ((), True))
        self.assertEqual(self.plan().plan["status"], "done")
        before = self.snapshot()
        self.assertFalse(lifecycle.reconcile(self.root).plan_done)
        self.assertEqual(self.snapshot(), before)

    def test_finish_still_closes_its_phase_without_via(self):
        lifecycle.start(self.root, ["P1.1", "P1.2"], OPUS)
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0})
        result = lifecycle.finish(self.root, "P1.2", "done", checks={"V1": 0})
        self.assertEqual((result.phase_closed, result.plan_done), ("done", False))
        [event] = self.events("phase_closed")
        self.assertEqual(event["data"], {"result": "done"})
        before = self.snapshot()
        self.assertEqual(lifecycle.reconcile(self.root).closed, ())
        self.assertEqual(self.snapshot(), before)


class NextReasonTests(ReconcileCase):
    def test_terminal_unclosed_phase_names_reconcile(self):
        self.merged("P1.1")
        self.merged("P1.2")
        action = lifecycle.next(self.plan())
        self.assertEqual((action.kind, action.phase), ("waiting", "P1"))
        self.assertEqual(action.exact, f"waiting: P1 closure: plan.py reconcile {self.plan_id}")

    def test_open_item_outside_the_batches_keeps_the_old_reason(self):
        # A detailed phase accepts only a complete item. The placeholder scope has no exclude, which the schema requires.
        complete = copy.deepcopy(DETAIL)
        complete["scope"] = {"include": ["x"], "exclude": []}
        ops.add_item(self.root, "P1", "Third", data=complete)
        ops.patch(self.root, "P1.3", complete)
        ops.set_batches(self.root, "P1", [{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended"}])
        self.merged("P1.1")
        self.merged("P1.2")
        self.assertEqual(lifecycle.next(self.plan()).exact, "waiting: P1 closure (finish the last item)")


class CheckDriftTests(ReconcileCase):
    def test_terminal_unclosed_phase_warns_until_reconciled(self):
        self.assertEqual(self.warnings("phase_unclosed"), [])
        self.merged("P1.1")
        self.merged("P1.2")
        [issue] = self.warnings("phase_unclosed")
        self.assertEqual((issue.level, issue.where), ("warning", "phases/P1/phase.json/closed"))
        self.assertIn(f"plan.py reconcile {self.plan_id}", issue.message)
        lifecycle.reconcile(self.root)
        self.assertEqual(self.warnings("phase_unclosed"), [])

    def test_closed_phase_with_open_item_is_stale(self):
        self.merged("P1.1")
        demo.rewrite(self.root, "phases/P1/phase.json", lambda d: d.update(
            closed={"at": "2026-10-07T09:40:00Z", "result": "done", "summary": "2 item(s): 2 done"}))
        [issue] = self.warnings("phase_closure_stale")
        self.assertEqual((issue.level, issue.where), ("warning", "phases/P1/phase.json/closed"))
        self.assertIn("reopen or finish P1.2", issue.message)
        self.assertEqual([i for i in check.check(self.plan()) if i.level == "error"], [])


class CliTests(ReconcileCase):
    def test_json_output_and_text_noop(self):
        self.merged("P1.1")
        self.merged("P1.2")
        code, out, err = self.run_cli("reconcile", str(self.root), "--actor", "claude-code/claude-opus-5-5/high",
                                      "--json")
        self.assertEqual((code, err), (0, ""))
        data = json.loads(out)
        self.assertEqual((data["closed"], data["plan_done"]), ([{"phase": "P1", "result": "done"}], False))
        self.assertEqual(data["next"]["exact"], f"run-items: planner:plan-run {self.plan_id} P2.1")
        code, out, _ = self.run_cli("reconcile", str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual(out, f"nothing to reconcile\nnext: run-items: planner:plan-run {self.plan_id} P2.1\n")

    def test_catalog_marks_reconcile_as_a_write_verb(self):
        rows = {v["name"]: v for v in catalog.verbs(cli.build_parser())["verbs"]}
        row = rows["reconcile"]
        self.assertEqual(row["mode"], "write")
        self.assertTrue({"PLAN_NOT_FOUND", "PLAN_AMBIGUOUS", "PLAN_LOCKED", "SCHEMA_INVALID"} <= set(row["errors"]))
        self.assertIn("--actor", [a["name"] for a in row["args"]])


if __name__ == "__main__":
    unittest.main()
