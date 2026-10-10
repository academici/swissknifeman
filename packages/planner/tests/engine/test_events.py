"""planner.* events: types and data by schema, emission after the plan lock, best-effort journal, producer fixtures."""
import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_AICORE_LIB = Path(__file__).resolve().parents[3] / "aicore" / "lib"
if (_AICORE_LIB / "aicore" / "__init__.py").is_file() and str(_AICORE_LIB) not in sys.path:
    sys.path.insert(1, str(_AICORE_LIB))

from planner import integration  # noqa: E402
from planner.integration import events as emission  # noqa: E402
from planner.plan import lifecycle, ops, store  # noqa: E402

try:
    from . import demo, test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo
    import test_lifecycle

PLANNER = Path(__file__).resolve().parents[2]
SCHEMAS = PLANNER / "schemas" / "event-data" / "v1"
FIXTURES = PLANNER / "tests" / "fixtures" / "events"
PLAN_PY = PLANNER / "scripts" / "plan.py"
OPUS = test_lifecycle.OPUS
TYPES = ("planner.plan.created", "planner.plan.closed", "planner.phase.closed", "planner.item.started",
         "planner.item.finished", "planner.decision.accepted")
needs_aicore = unittest.skipUnless(integration.available(), "needs the aicore foundation")


def registry():
    from aicore.util import schema
    import aicore
    foundation = Path(aicore.__file__).resolve().parents[2] / "schemas"
    extras = tuple(foundation / name / "v1" for name in ("artifact-ref", "digest", "common"))
    kinds = tuple(t.replace(".", "-") for t in TYPES)
    return schema.load_registry(SCHEMAS, urn_prefix="urn:swissknifeman:planner:event-data:", kinds=kinds,
                                extra_dirs=extras), schema


def data_issues(event_type, data):
    reg, schema = registry()
    return schema.validate(data, event_type.replace(".", "-"), reg)


class EventCase(test_lifecycle.LifeCase):
    """Plan LIFE with a temporary machine home, the journal of its project and no delivery."""

    def setUp(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))
        env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_")}
        env.update(HOME=str(home), SKM_HOME=str(home), SKM_AICORE_EVENTS__DELIVERY="off")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        warned = mock.patch.object(emission, "_WARNED", set())
        warned.start()
        self.addCleanup(warned.stop)
        self.home = home
        super().setUp()
        self.project = self.plans.parent

    def journal(self, *types):
        from aicore.ext import events
        found, problems = events.read_events(self.project)
        self.assertEqual(problems, [])
        return [e for e in found if not types or e.type in types]

    def types(self):
        return [e.type for e in self.journal()]


@needs_aicore
class EmissionTests(EventCase):
    def test_new_plan_emits_created_with_the_plan_identity(self):
        [event] = self.journal()
        plan = self.load().plan
        self.assertEqual((event.type, event.source, event.subject), ("planner.plan.created", "urn:swissknifeman:module:planner",
                                                                    plan["id"]))
        self.assertEqual(event.dataschema, "urn:swissknifeman:planner:event-data:planner-plan-created:v1")
        self.assertEqual(event.data, {"plan_id": plan["id"], "short_id": plan["short_id"], "title": plan["title"],
                                      "repository": "r", "created": "2026-10-07"})
        self.assertEqual(data_issues(event.type, event.data), [])

    def test_start_emits_item_started_per_item_in_one_chain(self):
        self.start("P1.1", "P1.2")
        first, second = self.journal("planner.item.started")
        self.assertEqual([e.data["item_id"] for e in (first, second)], ["P1.1", "P1.2"])
        self.assertEqual(first.data["executor"], OPUS)
        self.assertEqual((first.data["phase_id"], first.data["title"], first.data["resumed"]), ("P1", "First", False))
        self.assertNotIn("take_over", first.data)
        created = self.journal("planner.plan.created")[0]
        self.assertIsNone(created.causationid)
        self.assertIsNone(first.causationid)  # a batch is its own chain
        self.assertEqual(second.causationid, first.id)
        for event in (first, second):
            self.assertEqual(data_issues(event.type, event.data), [])

    def test_resume_and_take_over_are_marked(self):
        self.start("P1.1", actor={**OPUS, "session": "s1"})
        self.start("P1.1", actor={**OPUS, "session": "s1"})
        self.start("P1.1", actor={**OPUS, "session": "s2"}, take_over=True)
        started = self.journal("planner.item.started")
        self.assertEqual([e.data["resumed"] for e in started], [False, True, True])
        self.assertEqual([e.data.get("take_over") for e in started], [None, None, True])
        self.assertEqual(started[2].data["executor"]["session"], "s2")
        for event in started:
            self.assertEqual(data_issues(event.type, event.data), [])

    def test_a_refused_command_emits_nothing(self):
        before = self.types()
        self.refused("NOT_STARTED", lifecycle.finish, "P1.1", "done", checks={"V1": 0})
        with self.assertRaises(Exception):
            self.start("P2.1")
        self.assertEqual(self.types(), before)

    def test_finish_emits_item_finished_and_the_closures_in_order(self):
        self.start("P1.1", "P1.2")
        self.finish("P1.1", commits=["abcdef1"], deviations=[], attempt_id="a-1")
        self.finish("P1.2", status="done_with_deviations", deviations=["changed"])
        finished = self.journal("planner.item.finished")
        self.assertEqual(finished[0].data, {
            "plan_id": finished[0].data["plan_id"], "short_id": finished[0].data["short_id"], "title": "First",
            "repository": "r", "item_id": "P1.1", "phase_id": "P1", "status": "done", "attempt_id": "a-1",
            "checks": {"V1": 0}, "commits": ["abcdef1"], "deviation_count": 0})
        self.assertEqual((finished[1].data["status"], finished[1].data["deviation_count"]),
                         ("done_with_deviations", 1))
        self.assertEqual(self.types(), ["planner.plan.created", "planner.item.started", "planner.item.started",
                                        "planner.item.finished", "planner.item.finished", "planner.phase.closed"])
        closed = self.journal("planner.phase.closed")
        self.assertEqual(len(closed), 1)
        self.assertEqual((closed[0].data["phase_id"], closed[0].data["result"], closed[0].data["title"]),
                         ("P1", "done_with_deviations", "One"))
        self.assertEqual(closed[0].data["summary"], "2 item(s): 1 done, 1 done_with_deviations")
        self.assertEqual(closed[0].causationid, finished[1].id)
        for event in finished + closed:
            self.assertEqual(data_issues(event.type, event.data), [])

    def test_the_last_finish_closes_the_plan_with_counts_and_phases(self):
        self.run_phase_one()
        self.design_p2()
        self.start("P2.1", actor=OPUS)
        self.finish("P2.1")
        tail = self.journal()[-3:]
        self.assertEqual([e.type for e in tail], ["planner.item.finished", "planner.phase.closed", "planner.plan.closed"])
        self.assertEqual(tail[1].causationid, tail[0].id)
        self.assertEqual(tail[2].causationid, tail[1].id)
        data = tail[2].data
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["counts"], {"items": 3, "done": 3, "done_with_deviations": 0, "blocked": 0, "skipped": 0})
        self.assertEqual([(p["id"], p["title"], p["status"]) for p in data["phases"]],
                         [("P1", "One", "done"), ("P2", "Two", "done")])
        self.assertEqual(data["goal"], self.load().plan["goal"])
        self.assertRegex(data["closed_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertNotIn("artifacts", data)
        self.assertEqual(data_issues(tail[2].type, data), [])

    def test_repeating_an_attempt_emits_nothing(self):
        self.start("P1.1")
        self.finish("P1.1", attempt_id="a-1")
        before = self.types()
        again = self.finish("P1.1", attempt_id="a-1")
        self.assertTrue(again.already_registered)
        self.assertEqual(self.types(), before)

    def test_reconcile_emits_the_closures(self):
        for item_id in ("P1.1", "P1.2"):
            demo.rewrite(self.root, f"phases/P1/{item_id}.json", lambda d: d.update(
                status="done", result={"started_at": "2026-10-07T09:00:00Z", "finished_at": "2026-10-07T09:30:00Z"}))
        lifecycle.reconcile(self.root, actor=OPUS)
        self.assertEqual(self.types()[1:], ["planner.phase.closed"])
        self.design_p2()
        demo.rewrite(self.root, "phases/P2/P2.1.json", lambda d: d.update(
            status="done", result={"started_at": "2026-10-07T09:00:00Z", "finished_at": "2026-10-07T09:30:00Z"}))
        lifecycle.reconcile(self.root, actor=OPUS)
        self.assertEqual(self.types()[1:], ["planner.phase.closed", "planner.phase.closed", "planner.plan.closed"])
        before = self.types()
        lifecycle.reconcile(self.root, actor=OPUS)  # nothing to close
        self.assertEqual(self.types(), before)

    def test_decide_emits_decision_accepted_and_cuts_a_long_text(self):
        decision = ops.add_decision(self.root, "Naming")
        lifecycle.decide(self.root, decision, accept="Use snake_case", rationale="style", by="owner")
        [event] = self.journal("planner.decision.accepted")
        self.assertEqual((event.data["decision_id"], event.data["decision"], event.data["answered_by"],
                          event.data["title"]), (decision, "Use snake_case", "owner", "Naming"))
        self.assertEqual(data_issues(event.type, event.data), [])
        long_one = ops.add_decision(self.root, "Long")
        lifecycle.decide(self.root, long_one, accept="x" * 5000, rationale="r")
        text = self.journal("planner.decision.accepted")[-1].data["decision"]
        self.assertEqual((len(text), text[-1]), (4096, "…"))

    def test_events_disabled_by_configuration_leave_the_journal_empty(self):
        with mock.patch.dict(os.environ, {"SKM_PLANNER_EVENTS__ENABLED": "false"}):
            self.start("P1.1")
            self.finish("P1.1")
        self.assertEqual(self.types(), ["planner.plan.created"])

    def test_without_aicore_the_command_succeeds_silently(self):
        stderr = io.StringIO()
        with mock.patch.dict(integration._PROBE, {"available": False, "root": None, "reason": "x"}, clear=True), \
                redirect_stderr(stderr):
            self.start("P1.1")
            self.finish("P1.1")
        self.assertEqual(self.load().items["P1.1"]["status"], "done")
        self.assertEqual((stderr.getvalue(), self.types()), ("", ["planner.plan.created"]))

    @unittest.skipIf(os.geteuid() == 0, "a read-only folder is not enforced for root")
    def test_a_broken_journal_does_not_fail_the_command(self):
        journal = self.project / ".swissknifeman" / "state" / "events.jsonl"
        journal.chmod(0o400)
        self.addCleanup(journal.chmod, 0o600)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.start("P1.1", "P1.2")
        self.assertEqual(self.load().items["P1.1"]["status"], "in_progress")
        self.assertEqual(self.types(), ["planner.plan.created"])
        self.assertEqual(len([line for line in stderr.getvalue().splitlines() if line.strip()]), 1)

    def test_an_exception_of_the_journal_is_one_warning_per_process(self):
        from aicore.ext import events
        from aicore.ext.errors import ExtError
        stderr = io.StringIO()
        with mock.patch.object(events, "emit", side_effect=ExtError("EVENT_INVALID", "bad")) as emit, \
                redirect_stderr(stderr):
            self.start("P1.1", "P1.2")
            self.finish("P1.1")
        self.assertEqual(emit.call_count, 2)  # one per command: a failed batch is abandoned
        self.assertEqual(stderr.getvalue().splitlines(), ["PLANNER_EVENT_NOT_EMITTED: EVENT_INVALID: bad"])
        self.assertEqual(self.load().items["P1.1"]["status"], "done")


@needs_aicore
class SubscriberTests(EventCase):
    def test_invocation_config_controls_delivery_and_subscriptions(self):
        from aicore.state import machine_config_file
        from planner.plan import settings
        marker = self.home / "invocation-marker.txt"
        script = self.home / "invocation-subscriber.py"
        script.write_text(f"import sys\nfrom pathlib import Path\nsys.stdin.read()\n"
                          f"Path({str(marker)!r}).write_text('delivered')\n", encoding="utf-8")
        machine = machine_config_file()
        machine.parent.mkdir(parents=True, exist_ok=True)
        machine.write_text('schema_version = 1\n[aicore.events]\ndelivery = "off"\n', encoding="utf-8")
        invocation = self.home / "invocation.toml"
        invocation.write_text('schema_version = 1\n[aicore.events]\ndelivery = "sync"\n'
                              '[aicore.subscriptions.invocation]\non = ["planner.item.started"]\n'
                              f'run = [{json.dumps(sys.executable)}, {json.dumps(str(script))}]\n', encoding="utf-8")
        settings.set_invocation(invocation)
        self.addCleanup(settings.set_invocation, None)
        with mock.patch.dict(os.environ):
            os.environ.pop("SKM_AICORE_EVENTS__DELIVERY", None)
            self.start("P1.1")
        self.assertEqual(marker.read_text(), "delivered")
        self.assertEqual(len(self.journal("planner.item.started")), 1)

    def test_invocation_off_overrides_machine_sync_delivery(self):
        from aicore.state import machine_config_file
        from aicore.ext import delivery
        from planner.plan import settings
        machine = machine_config_file()
        machine.parent.mkdir(parents=True, exist_ok=True)
        machine.write_text('schema_version = 1\n[aicore.events]\ndelivery = "sync"\n', encoding="utf-8")
        invocation = self.home / "invocation.toml"
        invocation.write_text('schema_version = 1\n[aicore.events]\ndelivery = "off"\n', encoding="utf-8")
        settings.set_invocation(invocation)
        self.addCleanup(settings.set_invocation, None)
        with mock.patch.dict(os.environ), mock.patch.object(delivery, "deliver") as deliver, \
                mock.patch.object(delivery, "spawn_background") as background:
            os.environ.pop("SKM_AICORE_EVENTS__DELIVERY", None)
            self.start("P1.1")
        deliver.assert_not_called()
        background.assert_not_called()
        self.assertEqual(len(self.journal("planner.item.started")), 1)

    def test_a_sync_subscriber_that_calls_plan_py_on_the_same_plan_is_not_blocked(self):
        from aicore.state import machine_config_file
        marker = self.home / "marker.txt"
        script = self.home / "subscriber.py"
        script.write_text(
            "import subprocess, sys\n"
            f"plan, py, marker = {str(self.root)!r}, {str(PLAN_PY)!r}, {str(marker)!r}\n"
            "sys.stdin.read()\n"
            "for argv in (['show', plan], ['log', plan, 'P1.1', '--type', 'note', '--summary', 'from subscriber']):\n"
            "    done = subprocess.run([sys.executable, py] + argv, capture_output=True, text=True, timeout=30)\n"
            "    if done.returncode:\n"
            "        sys.exit(done.stderr or 'failed')\n"
            "open(marker, 'a').write('ok\\n')\n", encoding="utf-8")
        config = machine_config_file()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(f'schema_version = 1\n[aicore.subscriptions.log-in]\non = ["planner.item.started"]\nrun = [{json.dumps(sys.executable)}, '
                          f'{json.dumps(str(script))}]\ntimeout_seconds = 60\n', encoding="utf-8")
        with mock.patch.dict(os.environ, {"SKM_AICORE_EVENTS__DELIVERY": "sync", "SKM_PLANNER_LOCK__TIMEOUT_SECONDS": "5"}):
            self.start("P1.1")
        self.assertEqual(marker.read_text(), "ok\n")
        self.assertIn("from subscriber", [e.get("summary") for e in store.read_log(self.root)])


class ArchitectureTests(unittest.TestCase):
    def test_emit_all_is_never_called_inside_a_with_block(self):
        for name in ("lifecycle", "ops"):
            path = _LIB / "planner" / "plan" / f"{name}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            calls = 0
            for node in ast.walk(tree):
                if isinstance(node, (ast.With, ast.AsyncWith)):
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Call) and getattr(inner.func, "attr", "") == "emit_all":
                            self.fail(f"{name}.py:{inner.lineno}: emit_all inside a with block")
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "emit_all":
                    calls += 1
            self.assertGreaterEqual(calls, 1, f"{name}.py never emits")

    def test_every_type_has_a_closed_schema_and_a_unit_declaration(self):
        unit = json.loads((PLANNER / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual(set(unit["provides"]["events"]), set(TYPES))
        self.assertIn({"id": "urn:swissknifeman:planner:event-data", "path": "schemas/event-data/v1", "version": "v1",
                       "stability": "beta"}, unit["provides"]["contracts"])
        for event_type in TYPES:
            schema = json.loads((SCHEMAS / f"{event_type}.schema.json").read_text(encoding="utf-8"))
            self.assertEqual(schema["$id"], emission.data_schema(event_type))
            self.assertIs(schema["additionalProperties"], False)
            self.assertTrue({"plan_id", "title"} <= set(schema["required"]))


@needs_aicore
class FixtureTests(EventCase):
    """``tests/fixtures/events/<type>/valid-full.json`` are envelopes the engine really emitted (``PLANNER_UPDATE_FIXTURES=1``
    rewrites them); the test compares their shape, not the id, time and cause."""

    def scenario(self):
        decision = ops.add_decision(self.root, "Naming")
        self.start("P1.1", "P1.2")
        self.finish("P1.1", commits=["abcdef1"], attempt_id="a-1")
        self.finish("P1.2")
        self.design_p2()
        self.start("P2.1")
        self.finish("P2.1")
        lifecycle.decide(self.root, decision, accept="Use snake_case", rationale="style", by="owner")
        return {t: [e for e in self.journal(t)][0] for t in TYPES}

    def test_fixtures_are_the_shape_of_real_emission(self):
        shape = lambda doc: {k: v for k, v in doc.items() if k not in ("id", "time", "causationid")}  # noqa: E731
        for event_type, event in self.scenario().items():
            envelope = event.to_json()
            path = FIXTURES / event_type / "valid-full.json"
            if os.environ.get("PLANNER_UPDATE_FIXTURES") == "1":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            self.assertTrue(path.is_file(), f"missing fixture {path.relative_to(PLANNER)}")
            self.assertEqual(shape(json.loads(path.read_text(encoding="utf-8"))), shape(envelope), event_type)

    def test_fixtures_are_valid_envelopes_of_their_schema(self):
        from aicore.ext import events
        for event_type in TYPES:
            for path in sorted((FIXTURES / event_type).glob("valid-*.json")):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(events.validate_document(doc), [], path.name)
                self.assertEqual((doc["type"], doc["dataschema"]), (event_type, emission.data_schema(event_type)))
                self.assertEqual(data_issues(event_type, doc["data"]), [], path.name)


if __name__ == "__main__":
    unittest.main()
