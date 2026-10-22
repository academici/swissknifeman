"""Lifecycle verbs (dossier §6): every refusal code, resume, closure worst-of, plan done, reopen, archive."""
import copy
import itertools
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import check, cli, lifecycle, ops, settings, store  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402
try:
    from . import demo
except ImportError:  # direct discovery from tests/engine
    import demo

OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
SONNET = {"provider": "claude-code", "model": "claude-sonnet-5-5", "effort": "high"}
HAIKU = {"provider": "claude-code", "model": "claude-haiku-4-5-20251001", "effort": "high"}
DETAIL = {
    "summary": "s", "why": "w", "scope": {"include": ["x"]}, "deliverables": ["d"],
    "task_files": [{"path": "lib/x.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"},
                   {"id": "V2", "cmd": "true", "expect": "exit 0", "kind": "impact"}],
}


class LifeCase(unittest.TestCase):
    """Plan LIFE: P1 detailed (P1.1, P1.2 depends on P1.1, one batch), P2 skeleton (P2.1 frontier/high)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        commands = [
            ["new", "--codename", "LIFE", "--title", "Life", "--repository", "r", "--owner", "o",
             "--actor", "claude-code/claude-opus-5-5/high", "--message", "m", "--date", "2026.10.07"],
            ["add-phase", "PLAN1", "--title", "One"],
            ["set", "PLAN1", "P1", "--json", '{"goal":"g"}'],
            ["add-item", "PLAN1", "P1", "--title", "First"],
            ["add-item", "PLAN1", "P1", "--title", "Second"],
            ["set", "PLAN1", "P1.1", "--json", json.dumps(DETAIL)],
            ["set", "PLAN1", "P1.2", "--json", json.dumps({**DETAIL, "depends_on": ["P1.1"]})],
            ["batches", "PLAN1", "P1", "--json", '[{"id":"B1","items":["P1.1","P1.2"],"mode":"recommended"}]'],
            ["add-phase", "PLAN1", "--title", "Two"],
            ["set", "PLAN1", "P2", "--json", '{"goal":"g"}'],
            ["add-item", "PLAN1", "P2", "--title", "Third"],
            ["set", "PLAN1", "P2.1", "--json", json.dumps({**DETAIL, "route": {"class": "frontier", "effort": "high"}})],
            ["design-done", "PLAN1", "P1", "--actor", "claude-code/claude-opus-5-5/high"],
        ]
        clock = itertools.count()
        self.root = demo.copy_cli_seed(self.plans, commands, clock=clock)
        base = datetime(2026, 10, 7, tzinfo=timezone.utc)
        def tick():
            return (base + timedelta(seconds=next(clock))).strftime("%Y-%m-%dT%H:%M:%SZ")
        patcher = mock.patch.object(store, "now", tick)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ---- helpers
    def load(self):
        return store.load_plan(self.root)

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def refused(self, code, call, *args, **kwargs):
        """The call raises ``code`` and leaves every byte of the plan directory unchanged."""
        before = self.tree()
        with self.assertRaises(PlanError) as caught:
            call(self.root, *args, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception)
        self.assertEqual(self.tree(), before, f"{code} refusal changed the plan directory")
        return caught.exception

    def start(self, *items, actor=OPUS, **kwargs):
        return lifecycle.start(self.root, items, actor, **kwargs)

    def finish(self, item, status="done", **kwargs):
        kwargs.setdefault("checks", {"V1": 0})
        return lifecycle.finish(self.root, item, status, **kwargs)

    def events(self, *types):
        events = store.read_log(self.root)
        return [e for e in events if not types or e["type"] in types]

    def design_p2(self):
        lifecycle.design_done(self.root, "P2", actor=OPUS)

    def run_phase_one(self):
        self.start("P1.1", "P1.2")
        self.finish("P1.1")
        return self.finish("P1.2")


class RoutePoolTests(unittest.TestCase):
    def test_pool_classes_by_id_and_pattern(self):
        self.assertEqual(lifecycle.admitted_class("claude-code", "claude-opus-5-5"), "frontier")
        self.assertEqual(lifecycle.admitted_class("claude-code", "claude-fable-5-1"), "frontier")
        self.assertEqual(lifecycle.admitted_class("claude-code", "claude-sonnet-5-5"), "implementation")
        self.assertEqual(lifecycle.admitted_class("claude-code", "claude-haiku-4-5-20251001"), "economy")
        self.assertEqual(lifecycle.admitted_class("codex", "gpt-6-sol"), "implementation")
        self.assertEqual(lifecycle.admitted_class("codex", "gpt-6.2-sol"), "frontier")

    def test_unknown_model_or_provider_is_none(self):
        self.assertIsNone(lifecycle.admitted_class("claude-code", "mystery-model"))
        self.assertIsNone(lifecycle.admitted_class("nobody", "claude-opus-5-5"))
        self.assertIsNone(lifecycle.admitted_class("cursor", "auto"))  # roles name no class

    def test_retired_entries_are_skipped_and_an_exact_id_beats_a_pattern(self):
        source = json.loads(lifecycle.ROUTING_PATH.read_text(encoding="utf-8"))
        entries = source["mappings"]["claude-code"]["model_inventory"]["entries"]
        entries[0]["status"] = "retired"  # fable
        entries.append({"id": "claude-opus-special", "roles": ["economy"]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routing.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            self.assertIsNone(lifecycle.admitted_class("claude-code", "claude-fable-5-1", path))
            self.assertEqual(lifecycle.admitted_class("claude-code", "claude-opus-special", path), "economy")
            self.assertEqual(lifecycle.admitted_class("claude-code", "claude-opus-5-5", path), "frontier")

    def test_unreadable_routing_carrier_is_a_typed_refusal(self):
        with self.assertRaises(PlanError) as caught:
            lifecycle.admitted_class("claude-code", "claude-opus-5-5", "/nonexistent/routing.json")
        self.assertEqual(caught.exception.code, "ROUTING_UNAVAILABLE")


class FixtureSeedTests(unittest.TestCase):
    def test_cli_seed_resumes_each_cases_deterministic_clock_on_cache_hits(self):
        first, second = LifeCase(), LifeCase()
        first.setUp()
        self.addCleanup(first.doCleanups)
        first_tick = store.now()
        self.assertTrue(first_tick.startswith("2026-10-07T"))
        stamps = [event["ts"] for event in first.events()]
        stamps.append(first.load().plan["updated_at"])
        self.assertTrue(all(stamp < first_tick for stamp in stamps))
        with mock.patch.object(demo.subprocess, "run", side_effect=AssertionError("seed must be cached")):
            second.setUp()
        self.addCleanup(second.doCleanups)
        self.assertEqual(store.now(), first_tick)
        self.assertEqual(first.tree(), second.tree())

    def test_cli_seed_is_independent_for_each_case_and_retains_negative_inputs(self):
        first, second = LifeCase(), LifeCase()
        first.setUp()
        self.addCleanup(first.doCleanups)
        second.setUp()
        self.addCleanup(second.doCleanups)
        self.assertNotEqual(first.root, second.root)
        self.assertEqual(first.tree(), second.tree())
        before = second.tree()
        ops.patch(store.load_plan(first.root), "P1.1", {"title": "only the first case"})
        self.assertEqual(second.tree(), before)
        self.assertEqual(store.load_plan(second.root).items["P1.1"]["title"], "First")
        self.assertEqual(store.load_plan(second.root).items["P1.2"]["depends_on"], ["P1.1"])
        self.assertEqual(store.load_plan(second.root).phases["P2"]["design"], "skeleton")


class StartTests(LifeCase):
    def test_start_moves_items_to_in_progress_and_logs_one_event_per_item(self):
        result = self.start("P1.1", "P1.2")
        self.assertEqual((result.items, result.phase, result.batch, result.route), (("P1.1", "P1.2"), "P1", "B1", "ok"))
        plan = self.load()
        for item_id in ("P1.1", "P1.2"):
            item = plan.items[item_id]
            self.assertEqual(item["status"], "in_progress")
            self.assertEqual(item["result"]["executor"], OPUS)
            self.assertIn("started_at", item["result"])
        events = self.events("start")
        self.assertEqual([e["item"] for e in events], ["P1.1", "P1.2"])
        self.assertEqual(events[0]["data"], {"requested": ["P1.1", "P1.2"], "route": "ok", "batch": "B1"})
        self.assertIn("P1.1", (self.root / "views/status.md").read_text(encoding="utf-8"))
        self.assertEqual([i for i in check.check(plan) if i.level == "error"], [])

    def test_start_refreshes_the_callers_plan_snapshot(self):
        plan = self.load()
        lifecycle.start(plan, ["P1.1"], OPUS)
        self.assertEqual(plan.items["P1.1"]["status"], "in_progress")

    def test_resume_keeps_started_at_and_takes_the_new_executor(self):
        self.start("P1.1")
        first = self.load().items["P1.1"]["result"]["started_at"]
        result = self.start("P1.1", actor=SONNET)
        self.assertEqual(result.resumed, ("P1.1",))
        item = self.load().items["P1.1"]
        self.assertEqual(item["status"], "in_progress")
        self.assertEqual(item["result"]["started_at"], first)
        self.assertEqual(item["result"]["executor"], SONNET)
        self.assertEqual(len(self.events("start")), 2)

    def test_a_dependency_inside_the_request_counts(self):
        self.refused("DEPENDENCY_NOT_READY", lambda root, *a, **k: lifecycle.start(root, ["P1.2"], OPUS))
        self.start("P1.1", "P1.2")

    def test_refusal_codes_leave_the_plan_untouched(self):
        start = lifecycle.start
        cases = [
            ("ITEMS_REQUIRED", [], OPUS),
            ("ITEMS_DUPLICATE", ["P1.1", "P1.1"], OPUS),
            ("REF_UNKNOWN", ["P1.9"], OPUS),
            ("ITEMS_SPAN_PHASES", ["P1.1", "P2.1"], OPUS),
            ("PHASE_NOT_DETAILED", ["P2.1"], OPUS),
            ("DEPENDENCY_NOT_READY", ["P1.2"], OPUS),
            ("ROUTE_UNDERSHOOT", ["P1.1"], HAIKU),
            ("ROUTE_UNDERSHOOT", ["P1.1"], {**OPUS, "effort": "medium"}),
            ("ACTOR_REQUIRED", ["P1.1"], {}),
        ]
        for code, items, actor in cases:
            with self.subTest(code=code, items=items, actor=actor.get("model")):
                self.refused(code, lambda root, *a, items=items, actor=actor: start(root, items, actor))
        self.assertEqual(self.events("start"), [])

    def test_a_finished_item_is_not_startable(self):
        self.start("P1.1")
        self.finish("P1.1")
        self.refused("ITEM_NOT_STARTABLE", lambda root, *a: lifecycle.start(root, ["P1.1"], OPUS))

    def test_phase_dependency_must_be_closed(self):
        self.design_p2()
        self.refused("DEPENDENCY_NOT_READY", lambda root, *a: lifecycle.start(root, ["P2.1"], OPUS))

    def test_a_blocked_phase_does_not_satisfy_its_dependents(self):
        self.design_p2()
        self.start("P1.1", "P1.2")
        self.finish("P1.1")
        self.finish("P1.2", "blocked", escalation="owner must pick")
        self.assertEqual(self.load().phases["P1"]["closed"]["result"], "blocked")
        error = self.refused("DEPENDENCY_NOT_READY", lambda root, *a: lifecycle.start(root, ["P2.1"], OPUS))
        self.assertIn("blocked", error.message)

    def test_class_below_the_item_route_refuses_but_a_stronger_model_is_admitted(self):
        ops.patch(self.root, "P1.1", {"route": {"class": "frontier", "effort": "low"}})
        self.refused("ROUTE_UNDERSHOOT", lambda root, *a: lifecycle.start(root, ["P1.1"], SONNET))
        self.start("P1.1", actor=OPUS)

    def test_unknown_model_warns_in_the_event_and_is_not_refused(self):
        result = self.start("P1.1", actor={"provider": "claude-code", "model": "mystery-model"})
        self.assertEqual(result.route, "ROUTE_MODEL_UNKNOWN")
        self.assertEqual(self.events("start")[0]["data"]["route"], "ROUTE_MODEL_UNKNOWN")
        self.assertEqual(self.load().items["P1.1"]["status"], "in_progress")

    def test_strict_route_refuses_unknown_model_without_writing(self):
        self.refused("ROUTE_MODEL_UNKNOWN", lifecycle.start, ["P1.1"],
                     {"provider": "claude-code", "model": "mystery-model"}, strict_route=True)
        self.start("P1.1", strict_route=True)

    def test_configured_refusal_applies_without_strict_route(self):
        config = settings.for_plan(self.load())
        strict = replace(config, values={**config.values, "routing.unknown_model": "refuse"})
        with mock.patch.object(settings, "for_plan", return_value=strict):
            self.refused("ROUTE_MODEL_UNKNOWN", lifecycle.start, ["P1.1"],
                         {"provider": "claude-code", "model": "mystery-model"})
            self.start("P1.1")

    def test_cli_passes_strict_route_to_start(self):
        with mock.patch.object(lifecycle, "start", side_effect=PlanError("ROUTE_MODEL_UNKNOWN", "unknown")) as start:
            with mock.patch("sys.stderr"):
                code = cli.main(["start", str(self.root), "P1.1", "--actor", "claude-code/mystery-model",
                                 "--strict-route", "--no-scout"])
        self.assertEqual(code, 1)
        self.assertTrue(start.call_args.kwargs["strict_route"])

    def test_owner_gate_needs_a_grant_event_or_a_grant_now(self):
        ops.patch(self.root, "P1.1", {"authority": {"kind": "owner_gate", "gate": "RELEASE-1", "scope": "tag"}})
        self.refused("GATE_NOT_GRANTED", lambda root, *a: lifecycle.start(root, ["P1.1"], OPUS))
        self.refused("GATE_UNKNOWN", lambda root, *a: lifecycle.start(root, ["P1.1"], OPUS, grants=["NOPE"]))
        self.start("P1.1", grants=["RELEASE-1"])
        granted = self.events("gate_granted")
        self.assertEqual((len(granted), granted[0]["data"]["gate"]), (1, "RELEASE-1"))
        self.assertIn("RELEASE-1", lifecycle.granted_gates(self.load()))

    def test_legacy_owner_gate_label_can_be_granted_without_inventing_an_id(self):
        label = "Запускай P1.1"
        ops.patch(self.root, "P1.1", {"authority": {"kind": "owner_gate", "label": label,
                                                        "scope": "Exact source instruction"}})
        self.refused("GATE_NOT_GRANTED", lambda root, *a: lifecycle.start(root, ["P1.1"], OPUS))
        self.start("P1.1", grants=[label])
        self.assertIn(label, lifecycle.granted_gates(self.load()))

    def test_external_gate_waits_and_cannot_be_started_or_owner_granted(self):
        label = "DEPENDENCY-RECEIPT"
        ops.patch(self.root, "P1.1", {"authority": {"kind": "external_gate", "gate": label,
                                                        "scope": "Wait for the owning repository receipt."}})
        self.assertEqual(lifecycle.next(self.load()).exact, f"waiting: external gate {label}")
        self.refused("EXTERNAL_GATE", lambda root, *a: lifecycle.start(root, ["P1.1"], OPUS))
        self.refused("GATE_UNKNOWN", lambda root, *a: lifecycle.grant(root, label, "Owner says go."))


class StartGateTests(LifeCase):
    def test_owner_phase_understands_file_item_unit_and_phase_locations(self):
        plan = self.load()
        cases = {"phases/P1/P1.1.json/validation": "P1", "phases/P2/phase.json": "P2",
                 "phases/P2/P2.1/U1.json/files": "P2", "P2.1": "P2", "P2.1/U1": "P2", "P2": "P2",
                 "plan.json/phases": None, "decisions/D1.json": None, "log.jsonl:1": None,
                 "P9.1/U1": None}
        for where, phase in cases.items():
            with self.subTest(where=where):
                self.assertEqual(check.owner_phase(plan, check.Issue("error", "probe", where, "bad")), phase)

    def test_start_refuses_corrupted_detail_with_item_location(self):
        # Authoring now refuses these edits itself. Bypass it to model old or externally damaged plans.
        original = self.load().items["P1.2"]
        for patch in ({"validation": []}, {"deliverables": []}, {"scope": {"include": []}}):
            with self.subTest(patch=patch):
                demo.rewrite(self.root, "phases/P1/P1.2.json", lambda d: d.update({**original, **patch}))
                error = self.refused("PLAN_INVALID", lifecycle.start, ["P1.1"], OPUS)
                field = "scope/include" if "scope" in patch else next(iter(patch))
                self.assertTrue(any(i.code == "incomplete" and i.where.endswith(f"P1.2.json/{field}")
                                    for i in error.issues))
                self.assertIn("block P1:", error.message)

    def test_start_refuses_plan_level_errors(self):
        decision = ops.add_decision(self.root, "Missing accepted decision fields")
        demo.rewrite(self.root, f"decisions/{decision}.json", lambda d: d.update(status="accepted"))
        error = self.refused("PLAN_INVALID", lifecycle.start, ["P1.1"], OPUS)
        self.assertTrue(any(i.code == "decision_fields" and check.owner_phase(self.load(), i) is None
                            for i in error.issues))

    def test_start_ignores_other_phase_errors_and_warnings_and_checks_once_for_batch(self):
        self.design_p2()
        demo.rewrite(self.root, "phases/P2/P2.1.json", lambda d: d.update(validation=[]))
        self.assertTrue(any(i.level == "error" and check.owner_phase(self.load(), i) == "P2"
                            for i in check.check(self.load())))
        self.assertTrue(any(i.level == "warning" for i in check.check(self.load())))
        with mock.patch.object(check, "check", wraps=check.check) as checked:
            result = self.start("P1.1", "P1.2")
        self.assertEqual(result.items, ("P1.1", "P1.2"))
        self.assertEqual(checked.call_count, 1)

    def test_resume_also_checks_the_phase(self):
        self.start("P1.1")
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(validation=[]))
        self.refused("PLAN_INVALID", lifecycle.start, ["P1.1"], OPUS)

    def test_start_catches_cycle_with_item_id_location(self):
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(depends_on=["P1.2"]))
        error = self.refused("PLAN_INVALID", lifecycle.start, ["P1.1", "P1.2"], OPUS)
        self.assertTrue(any(i.code == "cycle" and i.where in {"P1.1", "P1.2"} for i in error.issues))


class BatchHintTests(LifeCase):
    def test_next_names_the_batch_its_mode_and_the_ready_command(self):
        action = lifecycle.next(self.load())
        self.assertEqual((action.kind, action.mode), ("run-items", "recommended"))
        self.assertEqual(action.batch_line, f"batch B1 (recommended: run together, a split needs log --type deviation) "
                                            f"-> {action.command}")
        self.assertEqual(action.as_dict()["mode"], "recommended")

    def three_templates(self, mode="recommended", depends=()):
        """P1.1 and P1.3 on one route template (economy/high), P1.2 on another (implementation/xhigh), all ready."""
        plan = self.load()
        ops.add_item(plan, "P1", "Third", data={**copy.deepcopy(DETAIL), "scope": {"include": ["x"], "exclude": []},
                                              **({"depends_on": list(depends)} if depends else {})})
        ops.patch(plan, "P1.2", {"depends_on": []})
        for item, route in (("P1.1", ("economy", "high")), ("P1.2", ("implementation", "xhigh")),
                            ("P1.3", ("economy", "high"))):
            ops.patch(plan, item, {"route": {"class": route[0], "effort": route[1]}})
        ops.set_batches(plan, "P1", [{"id": "B1", "items": ["P1.1", "P1.2", "P1.3"], "mode": mode}])

    def test_a_recommended_batch_of_two_route_templates_is_offered_template_by_template(self):
        self.three_templates()
        action = lifecycle.next(self.load())
        self.assertEqual((action.kind, action.items, action.route), ("run-items", ("P1.1", "P1.3"),
                                                                       {"class": "economy", "effort": "high"}))
        self.assertEqual(action.later, (("P1.2",),))
        self.assertEqual(action.command, f"planner:plan-run {self.load().plan['id']} P1.1 P1.3")
        self.assertIn("split by route template", action.batch_line)
        self.assertIn("then P1.2 (implementation/xhigh)", action.batch_line)
        self.assertEqual(action.as_dict()["later"], [{"items": ["P1.2"],
                                                      "route": {"class": "implementation", "effort": "xhigh"}}])

    def test_the_split_by_template_starts_without_the_warning_of_a_split_batch(self):
        self.three_templates()
        self.assertEqual(self.start("P1.1", "P1.3").warnings, ())

    def test_items_that_depend_on_each_other_stay_in_one_run_under_the_maximum_route(self):
        self.three_templates(depends=["P1.2"])  # P1.3 (economy/high) waits for P1.2 (implementation/xhigh)
        action = lifecycle.next(self.load())
        self.assertEqual((action.items, action.later), (("P1.1",), (("P1.2", "P1.3"),)))
        self.assertEqual(action.later_routes, ({"class": "implementation", "effort": "xhigh"},))

    def test_a_required_batch_of_two_templates_stays_one_run(self):
        self.three_templates(mode="required")
        action = lifecycle.next(self.load())
        self.assertEqual((action.items, action.later), (("P1.1", "P1.2", "P1.3"), ()))
        self.assertIn("required: run as one", action.batch_line)
        self.assertNotIn("later", action.as_dict())

    def test_one_template_stays_one_run_and_names_no_split(self):
        action = lifecycle.next(self.load())
        self.assertEqual(action.later, ())
        self.assertNotIn("later", action.as_dict())

    def test_a_required_batch_says_run_as_one(self):
        ops.set_batches(self.load(), "P1", [{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "required"}])
        self.assertIn("required: run as one", lifecycle.next(self.load()).batch_line)

    def test_start_of_part_of_a_batch_warns_and_records_the_batch(self):
        result = self.start("P1.1")
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("P1.1 is in batch B1 [P1.1, P1.2]", result.warnings[0])
        self.assertIn("log --type deviation", result.warnings[0])
        self.assertIn(result.warnings[0], result.text("LIFE"))
        self.assertEqual(self.events("start")[0]["data"]["batch"], "B1")

    def test_start_of_the_whole_batch_does_not_warn(self):
        self.assertEqual(self.start("P1.1", "P1.2").warnings, ())

    def test_the_item_pack_carries_its_batch(self):
        from planner.plan import context
        found = context.collect(self.load(), "P1.2", with_scout=False)["batch"]
        self.assertEqual((found["id"], found["items"], found["mode"]), ("B1", ["P1.1", "P1.2"], "recommended"))
        self.assertEqual(found["run_with"], f"planner:plan-run {self.load().plan['id']} P1.1 P1.2")


class PhaseChecksTests(LifeCase):
    """phase.validation is the full pass of a phase: the item that closes the phase records it, once."""

    FULL = {"id": "V9", "cmd": "python3 scripts/affected-tests.py --tier all --run", "expect": "exit 0", "kind": "acceptance"}

    def test_the_item_that_closes_a_phase_records_the_phase_checks(self):
        ops.patch(self.load(), "P1", {"validation": [dict(self.FULL)]})
        self.start("P1.1")
        self.finish("P1.1")  # another item is still open: the phase checks are not this item's
        self.start("P1.2")
        finish = lifecycle.finish
        error = self.refused("CHECKS_MISSING", lambda root, *a: finish(root, "P1.2", "done", checks={"V1": 0}))
        self.assertIn("closes phase P1", error.message)
        self.refused("CHECKS_RED", lambda root, *a: finish(root, "P1.2", "done", checks={"V1": 0, "V9": 1}))
        result = self.finish("P1.2", checks={"V1": 0, "V9": 0})
        self.assertEqual(result.phase_closed, "done")

    def test_check_refuses_a_shared_id_and_warns_about_a_heavy_item_check(self):
        ops.patch(self.load(), "P1", {"validation": [dict(self.FULL, id="V1")]})
        codes = [(issue.level, issue.code) for issue in check.check(self.load())]
        self.assertIn(("warning", "validation_id_clash"), codes)
        ops.patch(self.load(), "P1", {"validation": []})
        ops.patch(self.load(), "P1.1", {"validation": [dict(self.FULL, id="V1")]})
        codes = [(issue.level, issue.code) for issue in check.check(self.load())]
        self.assertIn(("warning", "check_cadence"), codes)
        self.assertNotIn(("warning", "validation_id_clash"), codes)

class FinishTests(LifeCase):
    def test_done_needs_every_acceptance_check_with_exit_zero(self):
        self.start("P1.1")
        finish = lifecycle.finish
        self.refused("CHECKS_MISSING", lambda root, *a: finish(root, "P1.1", "done", notes="n"))
        self.refused("CHECKS_RED", lambda root, *a: finish(root, "P1.1", "done", checks={"V1": 1}))
        self.refused("CHECK_UNKNOWN", lambda root, *a: finish(root, "P1.1", "done", checks={"V1": 0, "V7": 0}))
        self.refused("STATUS_INVALID", lambda root, *a: finish(root, "P1.1", "todo"))
        item = self.load().items["P1.1"]
        self.assertEqual((item["status"], len(self.events("finish"))), ("in_progress", 0))

    def test_done_records_result_and_log(self):
        self.start("P1.1", "P1.2")
        result = self.finish("P1.1", notes="3 tests", commits=["a1b2c3d"], pending=["docs"], checks={"V1": 0, "V2": 3})
        self.assertEqual((result.item, result.status, result.phase_closed, result.plan_done), ("P1.1", "done", None, False))
        item = self.load().items["P1.1"]
        self.assertEqual(item["status"], "done")
        recorded = item["result"]
        self.assertEqual((recorded["notes"], recorded["commits"], recorded["pending"]), ("3 tests", ["a1b2c3d"], ["docs"]))
        self.assertEqual([(c["id"], c["exit"]) for c in recorded["checks"]], [("V1", 0), ("V2", 3)])
        self.assertTrue(recorded["finished_at"] > recorded["started_at"])
        self.assertEqual(recorded["executor"], OPUS)
        self.assertEqual(self.events("finish")[0]["data"], {"status": "done", "checks": {"V1": 0, "V2": 3}})
        self.assertEqual([i for i in check.check(self.load()) if i.level == "error"], [])

    def test_finish_returns_the_next_step(self):
        self.start("P1.1", "P1.2")
        result = self.finish("P1.1")
        self.assertEqual(result.next.kind, "run-items")
        self.assertEqual(result.next.items, ("P1.2",))
        self.assertIn("P1.1 done", result.text())

    def test_not_started_items_cannot_finish_except_skipped(self):
        self.refused("NOT_STARTED", lambda root, *a: lifecycle.finish(root, "P1.1", "done", checks={"V1": 0}))
        self.start("P1.1")
        self.finish("P1.1")
        error = self.refused("NOT_STARTED", lambda root, *a: lifecycle.finish(root, "P1.1", "done", checks={"V1": 0}))
        self.assertIn("reopen", error.message)

    def test_done_with_deviations_needs_recorded_checks_and_a_deviation(self):
        self.start("P1.1")
        finish = lifecycle.finish
        self.refused("CHECKS_MISSING", lambda root, *a: finish(root, "P1.1", "done_with_deviations", deviations=["d"]))
        self.refused("DEVIATION_REQUIRED", lambda root, *a: finish(root, "P1.1", "done_with_deviations", checks={"V1": 0}))
        self.finish("P1.1", "done_with_deviations", checks={"V1": 2}, deviations=["V1 flaky"])
        result = self.load().items["P1.1"]["result"]
        self.assertEqual((result["deviations"], result["checks"][0]["exit"]), (["V1 flaky"], 2))

    def test_blocked_needs_an_escalation_and_no_checks(self):
        self.start("P1.1")
        self.refused("ESCALATION_REQUIRED", lambda root, *a: lifecycle.finish(root, "P1.1", "blocked"))
        self.finish("P1.1", "blocked", checks={}, escalation="owner must pick a format")
        item = self.load().items["P1.1"]
        self.assertEqual((item["status"], item["result"]["escalation"]), ("blocked", "owner must pick a format"))

    def test_skipped_needs_an_accepted_decision_and_may_come_from_todo(self):
        ops.add_decision(self.root, "Drop the item")  # D1, open
        finish = lifecycle.finish
        self.refused("DECISION_REQUIRED", lambda root, *a: finish(root, "P1.1", "skipped"))
        self.refused("DECISION_REQUIRED", lambda root, *a: finish(root, "P1.1", "skipped", decision="D1"))  # still open
        self.refused("DECISION_REQUIRED", lambda root, *a: finish(root, "P1.1", "skipped", decision="D9"))
        self.refused("DECISION_REQUIRED", lambda root, *a: finish(root, "P1.1", "skipped", decision="P1"))
        lifecycle.decide(self.root, "D1", accept="not needed anymore", rationale="scope cut", by="owner")
        self.finish("P1.1", "skipped", checks={}, decision="D1")
        item = self.load().items["P1.1"]
        self.assertEqual((item["status"], item["result"]["decision"]), ("skipped", "D1"))
        self.assertNotIn("started_at", item["result"])
        self.assertEqual([i for i in check.check(self.load()) if i.level == "error"], [])

    def test_a_qualified_decision_is_accepted_without_a_lookup(self):
        self.finish("P1.1", "skipped", checks={}, decision="PLAN3.D2")
        self.assertEqual(self.load().items["P1.1"]["status"], "skipped")


class ClosureTests(LifeCase):
    def test_last_item_closes_the_phase_with_the_worst_result(self):
        self.start("P1.1", "P1.2")
        self.finish("P1.1")
        result = self.finish("P1.2", "done_with_deviations", checks={"V1": 0}, deviations=["slow"])
        self.assertEqual(result.phase_closed, "done_with_deviations")
        closed = self.load().phases["P1"]["closed"]
        self.assertEqual(closed["result"], "done_with_deviations")
        self.assertEqual(closed["summary"], "2 item(s): 1 done, 1 done_with_deviations")
        self.assertEqual(self.events("phase_closed")[0]["data"], {"result": "done_with_deviations"})
        self.assertEqual(self.load().plan["status"], "active")  # P2 is still open
        self.assertIn("P2", result.next.exact)

    def test_blocked_is_worse_than_deviations_and_all_skipped_is_skipped(self):
        self.start("P1.1", "P1.2")
        self.finish("P1.1", "done_with_deviations", deviations=["d"])
        self.finish("P1.2", "blocked", checks={}, escalation="e")
        self.assertEqual(self.load().phases["P1"]["closed"]["result"], "blocked")

    def test_all_skipped_phase_closes_as_skipped(self):
        ops.add_decision(self.root, "Skip all")
        lifecycle.decide(self.root, "D1", accept="skip", rationale="r", by="owner")
        self.finish("P1.1", "skipped", checks={}, decision="D1")
        self.finish("P1.2", "skipped", checks={}, decision="D1")
        self.assertEqual(self.load().phases["P1"]["closed"]["result"], "skipped")

    def test_every_phase_closed_marks_the_plan_done_and_next_archives(self):
        self.run_phase_one()
        self.design_p2()
        self.start("P2.1")
        result = self.finish("P2.1")
        self.assertTrue(result.plan_done)
        self.assertEqual(self.load().plan["status"], "done")
        self.assertEqual(result.next.exact, f"archive: planner:plan-close {self.load().plan['id']} archive")
        self.assertIn("plan done", result.text())
        self.assertEqual([i for i in check.check(self.load()) if i.level == "error"], [])

    def test_a_blocked_phase_keeps_the_plan_active_and_next_names_the_blocker(self):
        self.start("P1.1", "P1.2")
        self.finish("P1.1")
        self.finish("P1.2", "blocked", checks={}, escalation="owner must pick")
        self.design_p2()
        ops.patch(self.root, "P2", {"depends_on": []})
        self.start("P2.1")
        result = self.finish("P2.1")
        self.assertFalse(result.plan_done)
        self.assertEqual(self.load().plan["status"], "active")
        self.assertEqual(result.next.exact, "waiting: blocked P1.2 — owner must pick")


class LogDecideGrantTests(LifeCase):
    def test_log_appends_friction_for_items_and_phases(self):
        event = lifecycle.log(self.root, "P1.1", "difficulty", "tests import config", impact="P1.2 too", next="reuse fixture",
                              refs=["lib/x.py"], actor=SONNET)
        self.assertEqual((event["item"], event["phase"], event["actor"]), ("P1.1", "P1", SONNET))
        lifecycle.log(self.root, "P1", "note", "phase-wide note")
        events = self.events("difficulty", "note")
        self.assertEqual([e["summary"] for e in events], ["tests import config", "phase-wide note"])
        self.assertEqual(events[1]["actor"], OPUS)  # plan authoring when nobody else is known
        self.assertIn("tests import config", (self.root / "views/handoff.md").read_text(encoding="utf-8"))

    def test_log_keeps_a_data_object_in_the_event(self):
        event = lifecycle.log(self.root, "P1.1", "deviation", "outside", data={"class": "write_set", "outcome": "accepted"})
        self.assertEqual(event["data"], {"class": "write_set", "outcome": "accepted"})
        self.assertEqual(self.events("deviation")[0]["data"]["class"], "write_set")
        self.assertNotIn("data", lifecycle.log(self.root, "P1.1", "note", "plain"))
        self.refused("LOG_DATA_INVALID", lambda root, *a: lifecycle.log(root, "P1.1", "note", "x", data=["not", "an", "object"]))

    def test_log_takes_the_item_executor_as_default_actor(self):
        self.start("P1.1", actor=SONNET)
        self.assertEqual(lifecycle.log(self.root, "P1.1", "assumption", "a")["actor"], SONNET)

    def test_log_refusals(self):
        self.refused("LOG_TYPE_INVALID", lambda root, *a: lifecycle.log(root, "P1.1", "start", "x"))
        self.refused("REF_UNKNOWN", lambda root, *a: lifecycle.log(root, "P1.9", "note", "x"))
        self.refused("REF_UNKNOWN", lambda root, *a: lifecycle.log(root, "P9", "note", "x"))
        self.refused("REF_INVALID", lambda root, *a: lifecycle.log(root, "D1", "note", "x"))

    def test_decide_by_option_and_by_text(self):
        ops.add_decision(self.root, "Format", data={"options": [{"id": "A", "text": "English"}, {"id": "B", "text": "Russian"}]})
        ops.add_decision(self.root, "Free")
        doc = lifecycle.decide(self.root, "D1", accept="A", rationale="repo convention", by="owner")
        self.assertEqual((doc["status"], doc["decision"], doc["answered_by"]), ("accepted", "A — English", "owner"))
        lifecycle.decide(self.root, "D2", accept="Use snake_case", rationale="style")
        stored = self.load().decisions["D2"]
        self.assertEqual((stored["decision"], stored["answered_by"]), ("Use snake_case", "agent"))
        self.assertEqual([e["data"]["id"] for e in self.events("decision")], ["D1", "D2"])
        self.assertEqual(self.events("decision")[0]["data"]["option"], "A")
        self.assertEqual([i for i in check.check(self.load()) if i.level == "error"], [])

    def test_decide_refusals(self):
        ops.add_decision(self.root, "Format", data={"options": [{"id": "A", "text": "English"}]})
        decide = lifecycle.decide
        self.refused("REF_UNKNOWN", lambda root, *a: decide(root, "D9", "x", "r"))
        self.refused("OPTION_UNKNOWN", lambda root, *a: decide(root, "D1", "C", "r"))
        self.refused("RATIONALE_REQUIRED", lambda root, *a: decide(root, "D1", "A", " "))
        self.refused("ACCEPT_REQUIRED", lambda root, *a: decide(root, "D1", "", "r"))
        self.refused("BY_INVALID", lambda root, *a: decide(root, "D1", "A", "r", by="robot"))
        decide(self.root, "D1", "A", "r")
        self.refused("DECISION_NOT_OPEN", lambda root, *a: decide(root, "D1", "A", "r"))

    def test_supersede_links_both_decisions(self):
        for title in ("Old", "New"):
            ops.add_decision(self.root, title)
        self.refused("DECISION_NOT_ACCEPTED", lambda root, *a: lifecycle.supersede(root, "D1", "D2"))
        lifecycle.decide(self.root, "D1", "old rule", "r")
        lifecycle.decide(self.root, "D2", "new rule", "r")
        self.refused("DECISION_SELF_SUPERSEDE", lambda root, *a: lifecycle.supersede(root, "D1", "D1"))
        lifecycle.supersede(self.root, "D1", "D2")
        plan = self.load()
        self.assertEqual((plan.decisions["D1"]["status"], plan.decisions["D1"]["superseded_by"]), ("superseded", "D2"))
        self.assertEqual(plan.decisions["D2"]["supersedes"], ["D1"])
        self.refused("DECISION_SUPERSEDED", lambda root, *a: lifecycle.supersede(root, "D1", "D2"))

    def test_grant_records_the_owner_message_once_and_unblocks_next(self):
        ops.patch(self.root, "P1.1", {"authority": {"kind": "owner_gate", "gate": "RELEASE-1", "scope": "tag"}})
        self.assertEqual(lifecycle.next(self.load()).exact, "waiting: gate RELEASE-1")
        grant = lifecycle.grant
        self.refused("NOTE_REQUIRED", lambda root, *a: grant(root, "RELEASE-1", " "))
        self.refused("GATE_UNKNOWN", lambda root, *a: grant(root, "OTHER-1", "go"))
        self.refused("GATE_INVALID", lambda root, *a: grant(root, "lower", "go"))
        following = grant(self.root, "RELEASE-1", "Owner: tag it.")
        self.assertEqual(following.kind, "run-items")
        events = self.events("gate_granted")
        self.assertEqual(events[0]["data"], {"gate": "RELEASE-1", "note": "Owner: tag it."})
        grant(self.root, "RELEASE-1", "again")
        self.assertEqual(len(self.events("gate_granted")), 1)


class DesignDoneTests(LifeCase):
    def test_cycle_with_item_id_location_blocks_design_done(self):
        ops.add_item(self.root, "P2", "Fourth", data={**DETAIL, "scope": {"include": ["x"], "exclude": []},
                                                   "depends_on": ["P2.1"]})
        ops.patch(self.root, "P2.1", {"depends_on": ["P2.2"]})
        error = self.refused("DESIGN_INCOMPLETE", lifecycle.design_done, "P2")
        self.assertIn("cycle", error.message)
        self.assertIn("P2.1", error.message)

    def test_unit_overlap_with_unit_id_location_blocks_design_done(self):
        for uid in ("U1", "U2"):
            doc = demo.fixture("unit-e3a-u1")
            doc.update(id=uid, item="P2.1", files=["lib/shared.py"])
            demo.write_doc(self.root / "phases/P2/P2.1" / f"{uid}.json", doc, "unit")
        ops.patch(self.root, "P2.1", {"units": ["U1", "U2"]})
        error = self.refused("DESIGN_INCOMPLETE", lifecycle.design_done, "P2")
        self.assertIn("P2.1/U1", error.message)
        self.assertIn("both own", error.message)

    def test_incomplete_phase_is_refused_with_the_check_errors(self):
        ops.patch(self.root, "P2.1", {"deliverables": None})
        error = self.refused("DESIGN_INCOMPLETE", lambda root, *a: lifecycle.design_done(root, "P2"))
        self.assertIn("deliverables", error.message)
        self.assertEqual(self.load().phases["P2"]["design"], "skeleton")

    def test_phase_without_items_is_refused(self):
        ops.add_phase(self.root, "Empty")
        self.refused("DESIGN_INCOMPLETE", lambda root, *a: lifecycle.design_done(root, "P3"))

    def test_complete_phase_becomes_detailed_and_is_logged_once(self):
        self.design_p2()
        self.assertEqual(self.load().phases["P2"]["design"], "detailed")
        self.assertEqual([e["phase"] for e in self.events("design_done")], ["P1", "P2"])
        lifecycle.design_done(self.root, "P2")  # idempotent
        self.assertEqual(len(self.events("design_done")), 2)

    def test_unknown_phase(self):
        self.refused("REF_UNKNOWN", lambda root, *a: lifecycle.design_done(root, "P9"))


class DesignReportTests(LifeCase):
    SECTIONS = [{"id": "s", "title": "S", "text": "x" * 2000}]

    def test_legacy_unbound_document_is_reported_with_a_warning(self):
        ops.set_plan(self.root, {"settings": {"context_pack": "legacy"}})
        ops.add_document(self.root, {"id": "loose", "title": "Loose", "sections": self.SECTIONS})
        report = lifecycle.design_done(self.root, "P2", actor=OPUS)
        self.assertEqual((report["phase"], report["mode"]), ("P2", "legacy"))
        self.assertGreater(report["items"][0]["unbound_bytes"], 0)
        self.assertIn("context_unbound", [w["code"] for w in report["warnings"]])

    def test_repeat_on_detailed_phase_builds_the_report_without_writing(self):
        self.design_p2()
        before = (self.tree(), len(self.events("design_done")))
        report = lifecycle.design_done(self.root, "P2")
        self.assertEqual([i["item"] for i in report["items"]], ["P2.1"])
        self.assertEqual((self.tree(), len(self.events("design_done"))), before)

    def test_phase_document_no_item_reads_is_listed_as_unread(self):
        ops.add_document(self.root, {"id": "bound", "title": "B", "applies_to": ["P2"], "sections": self.SECTIONS})
        ops.add_document(self.root, {"id": "read", "title": "R", "applies_to": ["P2"], "sections": self.SECTIONS})
        ops.patch(self.root, "P2.1", {"reads": [{"ref": "knowledge/read#s", "why": "w", "required": True}]})
        report = lifecycle.design_done(self.root, "P2", actor=OPUS)
        self.assertEqual(report["phase_documents_unread"], ["knowledge/bound"])

    def test_small_budget_marks_items_over(self):
        ops.set_plan(self.root, {"settings": {"context_budget_kb": 1}})
        report = lifecycle.design_done(self.root, "P2", actor=OPUS)
        self.assertTrue(report["items"][0]["over_budget"])


class ReopenTests(LifeCase):
    def test_reopen_clears_result_phase_closure_and_plan_done(self):
        self.run_phase_one()
        self.design_p2()
        self.start("P2.1")
        self.finish("P2.1")
        self.assertEqual(self.load().plan["status"], "done")
        lifecycle.reopen(self.root, "P1.2", "acceptance missed a case", actor=SONNET)
        plan = self.load()
        self.assertEqual((plan.items["P1.2"]["status"], plan.items["P1.2"]["result"]), ("todo", None))
        self.assertIsNone(plan.phases["P1"]["closed"])
        self.assertEqual(plan.plan["status"], "active")
        note = self.events("note")[-1]
        self.assertEqual((note["item"], note["actor"], note["data"]), ("P1.2", SONNET, {"reopened_from": "done"}))
        self.assertIn("acceptance missed a case", note["summary"])
        self.assertEqual(lifecycle.next(plan).items, ("P1.2",))
        self.assertEqual([i for i in check.check(plan) if i.level == "error"], [])

    def test_reopen_refusals(self):
        self.refused("NOT_TERMINAL", lambda root, *a: lifecycle.reopen(root, "P1.1", "why"))
        self.start("P1.1", actor={**OPUS, "session": "run-x"})
        held = self.refused("NOT_TERMINAL", lambda root, *a: lifecycle.reopen(root, "P1.1", "why"))
        self.assertIn("held by", held.message)  # who holds it and who frees it, not a bare refusal
        self.assertIn("in session run-x", held.message)
        self.assertIn("the owner of that session frees it", held.message)
        self.finish("P1.1")
        self.refused("REASON_REQUIRED", lambda root, *a: lifecycle.reopen(root, "P1.1", " "))
        self.refused("REF_UNKNOWN", lambda root, *a: lifecycle.reopen(root, "P1.9", "why"))

    def test_a_reopened_item_can_be_started_again_with_a_fresh_started_at(self):
        self.start("P1.1")
        self.finish("P1.1")
        lifecycle.reopen(self.root, "P1.1", "redo")
        self.start("P1.1")
        item = self.load().items["P1.1"]
        self.assertEqual(set(item["result"]), {"started_at", "executor"})


class ArchiveTests(LifeCase):
    def finish_plan(self):
        self.run_phase_one()
        self.design_p2()
        self.start("P2.1")
        self.finish("P2.1")

    def test_archive_requires_done_or_a_forced_reason(self):
        self.refused("PLAN_NOT_DONE", lambda root, *a: lifecycle.archive(root))
        self.refused("REASON_REQUIRED", lambda root, *a: lifecycle.archive(root, force=True))
        self.assertTrue(self.root.is_dir())

    def test_archive_moves_the_directory_after_writing_status_and_event(self):
        self.finish_plan()
        plan = self.load()
        target = lifecycle.archive(plan)
        archived = self.plans / "archive" / self.root.name
        self.assertEqual(target, archived)
        self.assertFalse(self.root.exists())
        self.assertTrue(archived.is_dir())
        self.assertEqual(plan.root, archived)
        reopened = store.open_plan(self.root.name, self.plans)
        self.assertEqual(reopened.plan["status"], "archived")
        self.assertEqual(store.read_log(archived)[-1]["type"], "archived")
        self.assertEqual(lifecycle.next(reopened).exact, "terminal: plan done")
        self.assertEqual([i for i in check.check(reopened) if i.level == "error"], [])
        self.assertIn("archived", (archived / "views/plan.md").read_text(encoding="utf-8"))

    def test_forced_archive_records_the_reason(self):
        lifecycle.archive(self.root, force=True, reason="abandoned by the owner")
        event = store.read_log(self.plans / "archive" / self.root.name)[-1]
        self.assertEqual(event["data"], {"forced": True, "reason": "abandoned by the owner"})

    def test_archive_refuses_a_taken_target_and_an_already_archived_plan(self):
        self.finish_plan()
        (self.plans / "archive" / self.root.name).mkdir(parents=True)
        self.refused("ARCHIVE_EXISTS", lambda root, *a: lifecycle.archive(root))
        (self.plans / "archive" / self.root.name).rmdir()
        archived = lifecycle.archive(self.root)
        with self.assertRaises(PlanError) as caught:
            lifecycle.archive(archived)
        self.assertEqual(caught.exception.code, "ALREADY_ARCHIVED")


class DeclaredOrderTests(LifeCase):
    """``batches`` fix the execution order of a phase; item numbers never do."""

    def declare_reversed_order(self):
        plan = self.load()
        ops.add_item(plan, "P1", "Third", data={**copy.deepcopy(DETAIL), "scope": {"include": ["x"], "exclude": []}})
        ops.set_batches(plan, "P1", [{"id": "B1", "items": ["P1.3"], "mode": "recommended"},
                                     {"id": "B2", "items": ["P1.1", "P1.2"], "mode": "recommended"}])

    def test_next_follows_declared_batches_not_item_numbers(self):
        self.declare_reversed_order()
        action = lifecycle.next(self.load())
        self.assertEqual((action.kind, action.batch, action.items), ("run-items", "B1", ("P1.3",)))
        plan = self.load()
        self.assertEqual(lifecycle.batch_state(plan, "P1", lifecycle.batches_of(plan, "P1")[1], action, set()),
                         "waiting: B1")

    def test_after_the_first_batch_the_next_one_becomes_ready(self):
        self.declare_reversed_order()
        self.start("P1.3")
        self.finish("P1.3")
        action = lifecycle.next(self.load())
        self.assertEqual((action.kind, action.batch, action.items), ("run-items", "B2", ("P1.1", "P1.2")))


class NextWiringTests(LifeCase):
    def test_paused_plan_reports_the_source_pause_instead_of_ready_work(self):
        ops.set_plan(self.root, {"pause": {"reason": "PLAN3 owns the successor work"}})
        plan = self.load()
        plan.plan["status"] = "paused"
        store.save(plan.path("plan"), plan.plan, "plan")
        action = lifecycle.next(self.load())
        self.assertEqual(action.kind, "waiting")
        self.assertEqual(action.reason, "paused: PLAN3 owns the successor work")

    def test_next_dict_form_matches_the_text_form(self):
        action = lifecycle.next(self.load())
        self.assertEqual(action.exact, f"run-items: planner:plan-run {self.load().plan['id']} P1.1 P1.2")  # P1.2 follows P1.1
        data = action.as_dict()
        self.assertEqual((data["kind"], data["items"], data["batch"], data["command"]),
                         ("run-items", ["P1.1", "P1.2"], "B1", action.command))
        self.assertEqual(data["launch"]["claude"], f"/{action.command}")

    def test_handoff_uses_the_lifecycle_next(self):
        text = (self.root / "views/handoff.md").read_text(encoding="utf-8")
        self.assertIn(f"run-items: planner:plan-run {self.load().plan['id']} P1.1 P1.2", text)
        self.start("P1.1")
        self.finish("P1.1")
        text = (self.root / "views/handoff.md").read_text(encoding="utf-8")
        self.assertIn(f"planner:plan-run {self.load().plan['id']} P1.2", text)

    def test_blocked_closed_phase_does_not_stop_independent_work(self):
        self.start("P1.1", "P1.2")
        self.finish("P1.1")
        self.finish("P1.2", "blocked", checks={}, escalation="owner must pick")
        self.design_p2()
        self.assertEqual(lifecycle.next(self.load()).kind, "run-items")


if __name__ == "__main__":
    unittest.main()
