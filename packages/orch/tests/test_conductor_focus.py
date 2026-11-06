"""The focus of a review (PLAN4 P9.4, knowledge/p9-prompt#focus): the reviewer prompt gets a ``focus`` block from the
``review_recommendation`` of the executor and the features of ``risk.json``, and ``suggested_model_class`` raises (never
lowers) the class of the reviewer route when the higher route is admitted (beacon ROUTE_UPGRADED)."""
from __future__ import annotations

import json
import time
import unittest
from unittest import mock
from types import SimpleNamespace
from pathlib import Path

from orch.conductor import engine, gates, prompts
from orch.conductor.application import route_service
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from tests.test_conductor import FINDING, GREEN, ConductorCase, DynamicReviewTests, executor_ok, report
from tests.test_conductor_prompts import fixture

ADVICE = {"recommended": True, "reason_codes": ["schema_changed"],
          "focus": ["the migration of the run-options schema", "the default of limits.retries"],
          "suggested_model_class": "frontier"}


def advised(**advice) -> dict:
    return {"write": {"out/W1.txt": "ok\n"}, "result": report("W1", review_recommendation={**ADVICE, **advice})}


class FocusBlockTests(unittest.TestCase):
    def build(self, **extra) -> list:
        return prompts.reviewer(fixture("adhoc"), item="W1", step="review.1", base="abc123", diff="d", round_no=1,
                                checks=[{"id": "V1", "exit": 0}], **extra)

    def test_no_focus_is_no_block(self):
        self.assertNotIn("focus", [block.kind for block in self.build()])
        self.assertNotIn("focus", [block.kind for block in self.build(focus=[])])

    def test_the_focus_block_follows_the_candidate_and_adds_up_to_the_prompt(self):
        blocks = self.build(focus=["a.py: the guard", "risk: schema (+25)"], focus_origin="stage-report+risk.json")
        kinds = [block.kind for block in blocks]
        self.assertEqual(kinds[:3], ["role_text", "input", "candidate"])
        self.assertEqual(kinds[3], "focus")
        block = blocks[3]
        self.assertEqual(block.origin, "stage-report+risk.json")
        self.assertIn("- a.py: the guard\n- risk: schema (+25)", block.text)
        self.assertIn("not reduce", block.text)  # the review keeps its whole scope
        self.assertEqual("".join(each.text for each in blocks), prompts.render(blocks))
        self.assertEqual(prompts.budget_class("focus"), "supporting")

    def test_the_rest_of_the_prompt_is_the_one_without_focus(self):
        plain = prompts.render(self.build())
        blocks = self.build(focus=["x"], focus_origin="stage-report")
        rest = prompts.render([block for block in blocks if block.kind != "focus"])
        self.assertEqual(rest, plain)


class ExactReviewerResumeTests(unittest.TestCase):
    def test_saved_different_reviewer_stops_without_changing_history(self):
        item = Item(ref="W1", orch_run="run", directory=Path("."), claim={},
                    options={"reviewer": "grok/grok-4/high", "fallback_routes": []},
                    sources={"reviewer": "item:W1"},
                    state={"route_overrides": {"reviewer": {"provider": "grok", "model_class": "frontier"}},
                           "steps": {"checks.1": {"status": "done"}}})
        original = json.loads(json.dumps(item.state))
        def route(_item, _role, override=None):
            return {"provider": "grok", "model": "grok-frontier" if override else "grok-4", "effort": "high"}
        with self.assertRaises(Stop) as raised:
            route_service.selected(SimpleNamespace(_route=route), item, "reviewer", True)
        self.assertEqual(raised.exception.code, "EXACT_ROUTE_MISMATCH")
        self.assertEqual(item.state, original)


class FocusRunTests(ConductorCase):
    def manifest(self, err: str, key: str = "review.1") -> dict:
        path = self.run_dir(err) / "W1" / "prompts" / f"{key}.manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def routes(self, err: str) -> dict:
        return json.loads((self.run_dir(err) / "W1" / "routes.json").read_text(encoding="utf-8"))

    def beacons(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def distinct_frontier(self):
        """The fixture grok has one model for every class; an upgrade needs a frontier model of its own."""
        real = engine.Conductor._route

        def route(conductor, item, role, override=None):
            resolved = real(conductor, item, role, override)
            if role == "reviewer" and resolved.get("model_class") == "frontier" and resolved.get("provider") == "grok":
                resolved = {**resolved, "model": "grok-frontier"}
            return resolved
        return mock.patch.object(engine.Conductor, "_route", route)

    def finished(self, *rounds) -> str:
        self.script({"executor": list(rounds) or [advised()], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def test_a_recommendation_with_focus_is_a_block_in_the_prompt_and_the_manifest(self):
        err = self.finished()
        text = self.prompt("reviewer", 1)
        for line in ADVICE["focus"]:
            self.assertIn(f"- {line}", text)
        blocks = [row for row in self.manifest(err)["blocks"] if row["kind"] == "focus"]
        self.assertEqual([row["origin"] for row in blocks], ["stage-report"])
        self.assertEqual(self.manifest(err)["budgets"]["supporting"]["tokens"] > 0, True)
        self.assertLess(text.index("## Candidate"), text.index("## Focus"))
        self.assertLess(text.index("## Focus"), text.index("Acceptance checks run by the conductor"))
        self.assertIn("Diff against the base", text)  # the scope of the review is whole

    def test_a_review_without_a_recommendation_has_no_focus_block(self):
        err = self.finished(executor_ok("W1"))
        self.assertNotIn("focus", [row["kind"] for row in self.manifest(err)["blocks"]])
        self.assertNotIn("## Focus", self.prompt("reviewer", 1))
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])

    def test_suggested_frontier_takes_the_reviewer_to_frontier_with_a_beacon(self):
        with self.distinct_frontier():
            err = self.finished()
        self.assertEqual(self.routes(err)["reviewer"]["model_class"], "frontier")
        self.assertEqual(self.manifest(err)["route"]["provider"], self.routes(err)["reviewer"]["provider"])
        found = self.beacons(err, "ROUTE_UPGRADED")
        self.assertEqual(len(found), 1, err)
        self.assertEqual((found[0]["role"], found[0]["item"]), ("reviewer", "W1"))
        self.assertIn("implementation -> frontier", found[0]["message"])
        kept = self.state(err)["items"]["W1"]["route_overrides"]["reviewer"]  # a resume starts from the upgrade
        self.assertEqual(kept["model_class"], "frontier")

    def test_explicit_item_reviewer_with_no_fallback_cannot_be_upgraded(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "reviewer": "grok/grok-4/high", "fallback_routes": []}}]}})
        with self.distinct_frontier():
            err = self.finished()
        self.assertEqual(self.routes(err)["reviewer"]["model"], "grok-4")
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])
        self.assertNotIn("reviewer", self.state(err)["items"]["W1"].get("route_overrides", {}))

    def test_explicit_invocation_options_reviewer_with_no_fallback_cannot_be_upgraded(self):
        path = self.project.parent / "pinned-reviewer.json"
        path.write_text(json.dumps({"reviewer": "grok/grok-4/high", "fallback_routes": []}))
        self.script({"executor": [advised()], "reviewer": [GREEN]})
        with self.distinct_frontier():
            code, _, err = self.run_items("W1", extra=("--options", str(path)))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.routes(err)["reviewer"]["model"], "grok-4")
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])
        self.assertNotIn("reviewer", self.state(err)["items"]["W1"].get("route_overrides", {}))

    def test_the_default_reviewer_class_is_kept_without_a_suggestion(self):
        advice = {key: value for key, value in ADVICE.items() if key != "suggested_model_class"}
        err = self.finished({"write": {"out/W1.txt": "ok\n"}, "result": report("W1", review_recommendation=advice)})
        self.assertEqual(self.routes(err)["reviewer"]["model_class"], "implementation")
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])
        self.assertIn("- the migration of the run-options schema", self.prompt("reviewer", 1))

    def test_a_suggestion_at_or_below_the_route_never_lowers_it(self):
        for suggested in ("economy", "implementation"):
            with self.subTest(suggested=suggested):
                self.setUp()
                err = self.finished(advised(suggested_model_class=suggested))
                self.assertEqual(self.routes(err)["reviewer"]["model_class"], "implementation")
                self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])

    def test_a_frontier_reviewer_is_not_lowered_by_an_economy_suggestion(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "stages": [{"role": "reviewer", "model_class": "frontier"}]}}]}})
        err = self.finished(advised(suggested_model_class="economy"))
        self.assertEqual(self.routes(err)["reviewer"]["model_class"], "frontier")
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])

    def test_a_higher_class_on_the_same_model_is_no_upgrade(self):
        err = self.finished()  # the fixture grok resolves both classes to one model: nothing changes, no beacon
        self.assertEqual(self.routes(err)["reviewer"]["model_class"], "implementation")
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])
        self.assertNotIn("route_overrides", self.state(err)["items"]["W1"])

    def test_a_higher_route_that_is_not_admitted_is_not_taken(self):
        real = engine.Conductor.route_problem

        def problem(conductor, route):
            return "PROVIDER_UNAVAILABLE: no frontier here" if route.get("model_class") == "frontier" else real(conductor, route)

        with mock.patch.object(engine.Conductor, "route_problem", problem):
            err = self.finished()
        self.assertEqual(self.routes(err)["reviewer"]["model_class"], "implementation")
        self.assertEqual(self.beacons(err, "ROUTE_UPGRADED"), [])
        self.assertIn("- the migration of the run-options schema", self.prompt("reviewer", 1))  # the focus stays

    def test_a_gated_provider_does_not_take_the_upgrade(self):
        gates.set_gate("grok", until=time.time() + 3600, code="PROVIDER_QUOTA", run_id="other", now=time.time())
        err = self.finished()  # the reviewer is already on its fallback route; the upgrade is judged on that route
        routes = self.routes(err)["reviewer"]
        self.assertEqual(routes["provider"], "claude-code")
        self.assertEqual(routes["model_class"], "frontier")  # the fallback of the reviewer is frontier already

    def test_the_upgrade_is_made_once_over_the_review_rounds(self):
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [advised(), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [triage]})
        with self.distinct_frontier():
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("reviewer")), (0, 2), err)
        self.assertEqual(len(self.beacons(err, "ROUTE_UPGRADED")), 1, err)
        self.assertEqual(self.routes(err)["reviewer"]["model_class"], "frontier")
        self.assertIn("## Focus", self.prompt("reviewer", 2))  # the later rounds keep the first recommendation


class FocusRiskTests(ConductorCase):
    """The features of ``risk.json`` go into the focus of the review that the score added."""

    scenario = "scout-solo"
    SCHEMA = DynamicReviewTests.SCHEMA
    piece = DynamicReviewTests.piece

    def test_the_features_of_risk_json_are_in_the_focus_block(self):
        self.piece(extra="[orch.conductor.risk.weights]\nschema = 70")
        self.script({"executor": [self.SCHEMA], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        text = self.prompt("reviewer", 1)
        self.assertIn("## Focus", text)
        self.assertIn("- risk schema (+70): 1 changed path(s): out/schemas/W1.json", text)
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "review.1.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([row["origin"] for row in manifest["blocks"] if row["kind"] == "focus"], ["risk.json"])

    def test_both_sources_name_the_origin_of_the_block(self):
        self.piece(extra="[orch.conductor.risk.weights]\nschema = 70")
        both = {**self.SCHEMA, "result": report("W1", changed_paths=["out/W1.txt", "out/schemas/W1.json"],
                                                review_recommendation={"recommended": True, "reason_codes": ["other"],
                                                                       "focus": ["the schema"]})}
        self.script({"executor": [both], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "review.1.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([row["origin"] for row in manifest["blocks"] if row["kind"] == "focus"], ["stage-report+risk.json"])
        text = self.prompt("reviewer", 1)
        self.assertLess(text.index("- the schema"), text.index("- risk schema"))


if __name__ == "__main__":
    unittest.main()
