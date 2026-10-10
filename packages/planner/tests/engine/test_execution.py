"""Execution: the scenario of an item (item → phase → plan → class → default) and one owner per item attempt."""
import json
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import catalog, check, cli, context, execution, lifecycle, ops, settings  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

try:
    from . import test_lifecycle, test_settings
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle
    import test_settings

OPUS = test_lifecycle.OPUS
needs_aicore = test_settings.needs_aicore


def session(actor, name):
    return {**actor, "session": name}


class ScenarioCase(test_settings.ConfigCase):
    """Plan LIFE: P1.1 and P1.2 (implementation/high by default), P2.1 (frontier/high)."""

    def scenario(self, item="P1.1"):
        return execution.scenario(self.load(), item)

    def declare(self, ref, scenario):
        ops.patch(self.load(), ref, {"orchestration": {"scenario": scenario}})


class ScenarioResolutionTests(ScenarioCase):
    def test_default_is_solo(self):
        self.assertEqual(self.scenario(), ("solo", "config:default"))

    @needs_aicore
    def test_every_source_in_order(self):
        self.project_file("[planner.orchestration]\ndefault_scenario = \"cfg-default\"\n"
                          "[planner.orchestration.by_class]\nimplementation = \"cfg-class\"\n")
        self.assertEqual(self.scenario("P1.1"), ("cfg-class", "config:by_class"))
        self.assertEqual(self.scenario("P2.1"), ("cfg-default", "config:default"))  # frontier has no class entry
        self.declare("plan", "from-plan")
        self.assertEqual(self.scenario("P1.1"), ("from-plan", "plan"))
        self.declare("P1", "from-phase")
        self.assertEqual(self.scenario("P1.1"), ("from-phase", "phase"))
        self.assertEqual(self.scenario("P2.1"), ("from-plan", "plan"))
        self.declare("P1.1", "from-item")
        self.assertEqual(self.scenario("P1.1"), ("from-item", "item"))
        self.assertEqual(self.scenario("P1.2"), ("from-phase", "phase"))

    @needs_aicore
    def test_empty_class_entry_falls_to_the_default(self):
        self.project_file("[planner.orchestration]\ndefault_scenario = \"cfg-default\"\n"
                          "[planner.orchestration.by_class]\nimplementation = \"\"\n")
        self.assertEqual(self.scenario("P1.1"), ("cfg-default", "config:default"))

    @needs_aicore
    def test_item_without_a_route_goes_to_the_default(self):
        self.project_file("[planner.orchestration]\ndefault_scenario = \"cfg-default\"\n"
                          "[planner.orchestration.by_class]\nimplementation = \"cfg-class\"\n")
        plan = self.load()
        for route in (None, {}):
            plan.items["P1.1"]["route"] = route
            self.assertEqual(execution.scenario(plan, "P1.1"), ("cfg-default", "config:default"))
        del plan.items["P1.1"]["route"]
        self.assertEqual(execution.scenario(plan, "P1.1"), ("cfg-default", "config:default"))

    def test_declared_scenario_beats_the_configuration_without_aicore(self):
        with test_settings.without_aicore():
            settings._CACHE.clear()
            self.assertEqual(self.scenario(), ("solo", "config:default"))
            self.declare("P1.1", "from-item")
            self.assertEqual(self.scenario(), ("from-item", "item"))


class ScenarioPackTests(ScenarioCase):
    def test_pack_carries_scenario_and_source_next_to_the_policy(self):
        pack = context.collect(self.load(), "P1.1")
        self.assertEqual(pack["orchestration"], {"strategy": "dag", "scenario": "solo", "scenario_source": "config:default"})
        self.declare("P1", "from-phase")
        ops.patch(self.load(), "P1.1", {"orchestration": {"scenario": "from-item", "max_parallel": 2}})
        pack = context.collect(self.load(), "P1.1")
        self.assertEqual(pack["orchestration"], {"strategy": "dag", "max_parallel": 2, "scenario": "from-item",
                                                 "scenario_source": "item"})
        self.assertEqual(context.collect(self.load(), "P1.2")["orchestration"]["scenario_source"], "phase")

    def test_started_pack_file_has_the_scenario(self):
        self.start("P1.1")
        pack = json.loads((self.root / "context" / "P1.1.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["orchestration"]["scenario"], "solo")

    def test_the_schema_accepts_only_a_profile_name(self):
        scenario = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "plan" / "v1" / "defs.schema.json")
                              .read_text(encoding="utf-8"))["$defs"]["orchestration"]
        self.assertEqual(scenario["properties"]["scenario"]["pattern"], "^[a-z][a-z0-9-]*$")
        self.assertNotIn("scenario", scenario.get("required", []))
        self.declare("P1.1", "engine-profile-2")
        for name in ("Bad Name", "2fast", "", "solo!"):
            with self.assertRaises(PlanError, msg=name) as caught:
                self.declare("P1.1", name)
            self.assertEqual(caught.exception.code, "SCHEMA_INVALID", name)
        self.assertEqual(self.scenario("P1.1"), ("engine-profile-2", "item"))

    def test_a_plan_without_a_scenario_stays_valid(self):
        self.assertEqual([i for i in check.check(self.load()) if i.level == "error"], [])


class OwnerCase(test_lifecycle.LifeCase):
    A = session(OPUS, "session-a")
    B = session(OPUS, "session-b")

    def started_by(self, actor):
        self.start("P1.1", actor=actor)
        return self.load().items["P1.1"]["result"]

    def start_events(self):
        return self.events("start")


class ItemOwnerTests(OwnerCase):
    def test_another_session_is_refused_and_nothing_is_written(self):
        self.started_by(self.A)
        error = self.refused("ITEM_OWNED", lifecycle.start, ["P1.1"], self.B)
        self.assertIn("session session-a", str(error))
        self.assertIn("--take-over", str(error))
        self.assertEqual(len(self.start_events()), 1)
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"], self.A)

    def test_take_over_replaces_the_executor_and_records_the_previous_one(self):
        first = self.started_by(self.A)
        self.start("P1.1", actor=self.B, take_over=True)
        result = self.load().items["P1.1"]["result"]
        self.assertEqual(result["executor"], self.B)
        self.assertEqual(result["started_at"], first["started_at"])
        event = self.start_events()[-1]
        self.assertEqual(event["data"]["take_over"], {"previous": self.A})
        self.assertNotIn("take_over", self.start_events()[0]["data"])

    def test_same_session_resumes_without_a_take_over_record(self):
        self.started_by(self.A)
        resumed = self.start("P1.1", actor=self.A)
        self.assertEqual(resumed.resumed, ("P1.1",))
        self.assertNotIn("take_over", self.start_events()[-1]["data"])

    def test_take_over_flag_without_a_conflict_is_harmless(self):
        self.start("P1.1", actor=self.A, take_over=True)  # todo item
        self.start("P1.1", actor=self.A, take_over=True)  # same session
        self.assertTrue(all("take_over" not in e["data"] for e in self.start_events()))

    def test_without_a_session_on_either_side_the_attempt_continues(self):
        self.started_by(OPUS)
        self.start("P1.1", actor=self.B)  # prior has no session
        self.start("P1.1", actor=OPUS)  # new call has no session
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"], OPUS)
        self.assertTrue(all("take_over" not in e["data"] for e in self.start_events()))

    def test_one_owned_item_refuses_the_whole_start(self):
        self.started_by(self.A)
        self.refused("ITEM_OWNED", lifecycle.start, ["P1.1", "P1.2"], self.B)
        self.assertEqual(self.load().items["P1.2"]["status"], "todo")

    def test_the_registrar_is_not_an_owner(self):
        self.start("P1.1", actor=self.A, registrar=self.B)
        self.start("P1.1", actor=self.A, registrar=session(OPUS, "session-c"))
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"], self.A)

    def test_finish_does_not_check_the_owner(self):
        self.started_by(self.A)
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0}, notes="n", actor=OPUS, executed_by=self.B)
        self.assertEqual(self.load().items["P1.1"]["status"], "done")
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"], self.B)

    def test_finish_by_another_session_without_executed_by_passes_too(self):
        self.started_by(self.A)
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0}, notes="n", actor=self.B)
        self.assertEqual(self.load().items["P1.1"]["status"], "done")


class OwnerCliTests(OwnerCase):
    def run_start(self, session_id, *extra):
        return test_settings.run("start", str(self.root), "P1.1", "--actor", "claude-code/claude-opus-5-5/high",
                                 "--session", session_id, *extra)

    def test_cli_refuses_then_takes_over(self):
        code, _, err = self.run_start("session-a")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_start("session-b")
        self.assertEqual(code, 1)
        self.assertIn("ITEM_OWNED", out + err)
        code, _, err = self.run_start("session-b", "--take-over")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load().items["P1.1"]["result"]["executor"]["session"], "session-b")

    def test_the_catalog_lists_the_flag_and_the_refusal(self):
        row = next(v for v in catalog.verbs(cli.build_parser())["verbs"] if v["name"] == "start")
        self.assertIn("ITEM_OWNED", row["errors"])
        self.assertIn("--take-over", [a["name"] for a in row["args"]])


if __name__ == "__main__":
    unittest.main()
