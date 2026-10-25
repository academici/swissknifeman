"""The route of a correction of review findings (``review.correction_route``), the class of a named model from the model
catalog, and ``CORRECTION_SCOPE_GREW`` (P7.3)."""
import copy
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor import engine
from orch.conductor.application import route_service
from orch.conductor.domain.stop import Stop
from orch.conductor.policies import routing
from tests.test_conductor import ConductorCase, FIXTURES, FINDING, GREEN, ROLES, executor_ok, quota_failure, report

REPRO = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
TRIAGE = {"result": {"confirmed": [{"finding": "F1", "reproduction": REPRO, "fix": "write done"}], "rejected": []}}
CLAIM_ROUTE = {"class": "implementation", "effort": "high"}
ECONOMY = {"class": "economy", "effort": "medium"}


def fixed(*extra: str, tag: bool = True) -> dict:
    """The answer of a correction round: ``out/W1.txt`` says done, and ``extra`` paths are written too."""
    answer = {"write": {"out/W1.txt": "done\n", **{path: "x\n" for path in extra}}, "result": report("W1")}
    return dict(answer, tag="stage-report") if tag else answer


def blocker() -> dict:
    found = copy.deepcopy(FINDING)
    found["result"]["findings"][0]["severity"] = "Blocker"
    return found


class RuleTests(unittest.TestCase):
    def test_a_known_class_below_the_label_wins_and_a_higher_one_never_raises_it(self):
        self.assertEqual(routing.lowered_class("implementation", "economy"), "economy")
        self.assertEqual(routing.lowered_class("economy", "frontier"), "economy")
        self.assertEqual(routing.lowered_class("frontier", None), "frontier")

    def test_the_correction_minimum_is_route_correction_else_the_route_without_relaxation(self):
        self.assertEqual(routing.correction_minimum({**CLAIM_ROUTE, "correction": ECONOMY}), ECONOMY)
        self.assertEqual(routing.correction_minimum(CLAIM_ROUTE), CLAIM_ROUTE)
        self.assertEqual(routing.correction_minimum(None), {})

    def test_a_bounded_route_below_or_off_the_minimum_is_refused(self):
        route = {"provider": "claude-code", "model": "haiku", "model_class": "economy", "effort": "medium"}
        self.assertIsNone(routing.correction_refusal(ECONOMY, route, "W1"))
        self.assertIn("ROUTE_UNDERSHOOT", routing.correction_refusal(CLAIM_ROUTE, route, "W1"))
        self.assertIn("ROUTE_MISMATCH", routing.correction_refusal({**ECONOMY, "model": "sonnet"}, route, "W1"))
        self.assertIn("ROUTE_MISMATCH", routing.correction_refusal({**ECONOMY, "provider": "codex"}, route, "W1"))

    def test_growth_is_what_the_findings_the_tests_the_changelog_and_the_docs_do_not_cover(self):
        grown = routing.grown_paths(
            ["a/lib.py", "a/other.py", "a/tests/test_x.py", "a/test_y.py", "tests/t.py", "CHANGELOG.md", "docs/x.md",
             "packages/m/docs/y.md", "z.txt"], {"a/lib.py"}, ["a/**"])
        self.assertEqual(grown, ["a/other.py", "tests/t.py", "z.txt"])  # tests count only inside the write set
        self.assertEqual(routing.grown_paths(["a/tests/test_x.py"], set(), None), [])  # no write set named: no fence


class MinimumTests(unittest.TestCase):
    """Without ``route.correction`` the minimum of a correction is the whole ordinary minimum, pins included."""

    PINNED = {"class": "implementation", "effort": "high", "provider": "claude-code", "model": "sonnet"}

    def host(self, claim_route, minimum, route):
        item = SimpleNamespace(ref="W1", claim={"route": claim_route}, input_doc={"route": {"minimum": minimum}},
                               options={"review": {"correction_route": "bounded-implementer"}},
                               routes={"bounded-implementer": route})
        host = SimpleNamespace(progress=mock.Mock(), route_problem=lambda found: None,
                               _claude_sandbox_problem=lambda *args: None)
        host._admit = lambda *args: route_service.admit(host, *args)
        return host, item

    def role(self, claim_route, minimum, route):
        host, item = self.host(claim_route, minimum, route)
        return route_service.correction_role(host, item, False), host.progress

    def test_f4_the_pins_of_the_route_reach_the_correction_minimum(self):
        pinned = {"class": "implementation", "effort": "high"}  # the claim answer carries class and effort only
        for provider, model, why in (("codex", "gpt-6-sol", "provider"), ("claude-code", "opus", "model")):
            with self.subTest(provider=provider, model=model):
                route = {"provider": provider, "model": model, "model_class": "implementation", "effort": "high"}
                role, progress = self.role(pinned, self.PINNED, route)
                self.assertEqual(role, "executor")
                said = progress.emit.call_args.kwargs
                self.assertEqual(said["reason_code"], "CORRECTION_ROUTE_REFUSED")
                self.assertIn(f"ROUTE_MISMATCH: W1 pins {why}", said["message"])

    def test_f4_a_route_on_the_pins_runs_and_an_explicit_route_correction_overrides_them(self):
        pinned = {"class": "implementation", "effort": "high"}
        on_pins = {"provider": "claude-code", "model": "sonnet", "model_class": "implementation", "effort": "high"}
        self.assertEqual(self.role(pinned, self.PINNED, on_pins)[0], "bounded-implementer")
        cheap = {"provider": "codex", "model": "gpt-6-luna", "model_class": "economy", "effort": "medium"}
        self.assertEqual(self.role({**pinned, "correction": {"class": "economy", "effort": "medium"}}, self.PINNED,
                                   cheap)[0], "bounded-implementer")
        self.assertEqual(self.role(pinned, self.PINNED, cheap)[0], "executor")

    def test_f1_a_fallback_candidate_is_admitted_against_the_same_minimum(self):
        host, item = self.host({"class": "implementation", "effort": "high", "correction": {
            "class": "implementation", "effort": "high", "provider": "claude-code"}}, self.PINNED, {})
        base = {"provider": "claude-code", "model": "sonnet", "model_class": "implementation", "effort": "high"}
        self.assertIsNone(route_service.admit(host, item, "bounded-implementer", base))
        for change, code in (({"model_class": "economy"}, "ROUTE_UNDERSHOOT"), ({"effort": "medium"}, "ROUTE_UNDERSHOOT"),
                             ({"provider": "codex"}, "ROUTE_MISMATCH")):
            with self.subTest(change=change):
                self.assertTrue(route_service.admit(host, item, "bounded-implementer", {**base, **change}).startswith(code))


class RouteCase(ConductorCase):
    def setUp(self):
        super().setUp()
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                           for role in (*ROLES, "bounded-implementer")})

    def work(self, bounded: bool = True, route: dict | None = None, stages: list | None = None):
        options = {"review": {"correction_route": "bounded-implementer"} if bounded else {}}
        if stages:
            options["stages"] = stages
        self.set_items({"W1": {"route": route or {**CLAIM_ROUTE, "correction": ECONOMY},
                               "options": [{"source": "item:W1", "options": options}]}})

    def beacons(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]


class CorrectionRouteTests(RouteCase):
    def test_i_a_major_correction_goes_to_the_bounded_implementer_within_route_correction(self):
        self.work()
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING, GREEN], "triager": [TRIAGE],
                     "bounded-implementer": [fixed()]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("bounded-implementer")), (1, 1))
        self.assertIn("done", (self.project / "out/W1.txt").read_text())
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        started = [line for line in self.lines(err) if line["event"] == "stage.start" and line["stage"] == "executor.2"]
        self.assertEqual(started[0]["role"], "bounded-implementer")
        self.assertEqual(self.beacons(err, "CORRECTION_ROUTE_REFUSED"), [])
        self.assertEqual(self.beacons(err, "CORRECTION_SCOPE_GREW"), [])
        self.assertIn("Bounded implementer", self.prompt("bounded-implementer", 1))
        self.assertIn("F1", self.prompt("bounded-implementer", 1))

    def test_without_the_option_the_executor_corrects_as_before(self):
        self.work(bounded=False)
        self.script({"executor": [executor_ok("W1"), fixed(tag=False)], "reviewer": [FINDING, GREEN],
                     "triager": [TRIAGE]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("bounded-implementer")), (2, 0))

    def test_j_a_blocker_finding_always_goes_to_the_executor(self):
        self.work()
        self.script({"executor": [executor_ok("W1"), fixed(tag=False)], "reviewer": [blocker(), GREEN],
                     "triager": [TRIAGE], "bounded-implementer": [fixed()]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("bounded-implementer")), (2, 0))
        self.assertEqual(self.beacons(err, "CORRECTION_ROUTE_REFUSED"), [])  # a Blocker is no refusal: it is the rule

    def test_k_a_bounded_route_below_the_minimum_falls_back_to_the_executor_with_a_beacon(self):
        self.work(route={**CLAIM_ROUTE, "correction": {"class": "implementation", "effort": "high"}})
        self.script({"executor": [executor_ok("W1"), fixed(tag=False)], "reviewer": [FINDING, GREEN],
                     "triager": [TRIAGE], "bounded-implementer": [fixed()]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("bounded-implementer")), (2, 0))
        refused = self.beacons(err, "CORRECTION_ROUTE_REFUSED")
        self.assertEqual(len(refused), 1, err)
        self.assertIn("ROUTE_UNDERSHOOT", refused[0]["message"])

    def test_without_route_correction_the_minimum_is_the_route_of_the_work(self):
        self.work(route=dict(CLAIM_ROUTE))  # implementation/high: the economy/medium launch entry does not meet it
        self.script({"executor": [executor_ok("W1"), fixed(tag=False)], "reviewer": [FINDING, GREEN],
                     "triager": [TRIAGE], "bounded-implementer": [fixed()]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("bounded-implementer")), (2, 0))
        self.assertEqual(len(self.beacons(err, "CORRECTION_ROUTE_REFUSED")), 1)

    def test_a_stage_that_lifts_the_bounded_route_to_the_minimum_runs_it(self):
        self.work(route=dict(CLAIM_ROUTE), stages=[{"role": "bounded-implementer", "model_class": "implementation",
                                                   "effort": "high"}])
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING, GREEN], "triager": [TRIAGE],
                     "bounded-implementer": [fixed()]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("bounded-implementer")), (1, 1))

    def test_a_bounded_route_that_cannot_start_leaves_the_correction_with_the_executor(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
                          | {"bounded-implementer": ["/nonexistent/bounded"]})
        self.work()
        self.script({"executor": [executor_ok("W1"), fixed(tag=False)], "reviewer": [FINDING, GREEN],
                     "triager": [TRIAGE]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertIn("PROVIDER_UNAVAILABLE", self.beacons(err, "CORRECTION_ROUTE_REFUSED")[0]["message"])


class FallbackTests(RouteCase):
    """A bounded-implementer that fails at the provider moves only to a route that still meets the minimum."""

    HIGH = {"class": "implementation", "effort": "high", "correction": {"class": "implementation", "effort": "high",
                                                                        "provider": "claude-code"}}

    def work_with(self, fallback: dict, pinned: bool = True):
        route = self.HIGH if pinned else {**self.HIGH, "correction": {"class": "implementation", "effort": "high"}}
        self.set_items({"W1": {"route": route, "options": [{"source": "item:W1", "options": {
            "review": {"correction_route": "bounded-implementer"},
            "stages": [{"role": "bounded-implementer", "model_class": "implementation", "effort": "high"}],
            "fallback_routes": [dict(fallback, role="bounded-implementer")]}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING, GREEN], "triager": [TRIAGE],
                     "bounded-implementer": [dict(quota_failure(3600), tag="stage-report"), fixed()]})

    def refused(self, fallback: dict):
        self.work_with(fallback)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_QUOTA")), err)
        self.assertEqual(self.calls("bounded-implementer"), 1)  # the refused candidate never ran
        self.assertEqual(self.beacons(err, "ROUTE_FALLBACK"), [])

    def test_f1_a_fallback_of_a_lower_class_never_executes(self):
        self.refused({"provider": "claude-code", "model_class": "economy"})

    def test_f1_a_fallback_of_a_lower_effort_never_executes(self):
        self.refused({"provider": "claude-code", "model_class": "implementation", "effort": "low"})

    def test_f1_a_fallback_on_another_provider_than_the_pinned_one_never_executes(self):
        self.refused({"provider": "codex", "model_class": "implementation", "effort": "high"})

    def test_f1_a_fallback_that_meets_the_minimum_runs_the_correction(self):
        self.work_with({"provider": "codex", "model_class": "implementation", "effort": "xhigh"}, pinned=False)
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("bounded-implementer"), 2)
        self.assertEqual(len(self.beacons(err, "ROUTE_FALLBACK")), 1)


class ScopeGrowthTests(RouteCase):
    def stop_after_the_round(self):
        """The conductor ends after ``executor.2`` is saved done and before its scope check."""
        return mock.patch.object(engine.Conductor, "_correction_scope", side_effect=Stop("RUN_TIMEOUT", "test interrupt"))

    def test_f2_a_resume_after_the_saved_round_still_blocks_a_bounded_growth(self):
        self.work()
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING, GREEN], "triager": [TRIAGE],
                     "bounded-implementer": [fixed("lib/extra.py")]})
        with self.stop_after_the_round():
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "RUN_TIMEOUT")), err)
        run_id = self.run_dir(err).name
        code, _, err = self.conduct("resume", "--run", run_id, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.calls("reviewer"), 1)  # blocked before another review round
        escalations = [row["text"] for row in self.source()["items"]["W1"]["report"]["open_issues"]
                       if row["kind"] == "escalation"]
        self.assertEqual(escalations, ["CORRECTION_SCOPE_GREW: lib/extra.py"])

    def test_f2_a_resume_after_the_saved_round_keeps_an_executor_growth_as_a_deviation(self):
        self.work(bounded=False)
        self.script({"executor": [executor_ok("W1"), fixed("lib/extra.py", tag=False)],
                     "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        with self.stop_after_the_round():
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "RUN_TIMEOUT")), err)
        code, _, err = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual(code, 0, err)
        issues = [row for row in self.source()["items"]["W1"]["report"]["open_issues"]
                  if str(row.get("text")).startswith("CORRECTION_SCOPE_GREW")]
        self.assertEqual([(row["kind"], row["outcome"], row["evidence"]) for row in issues],
                         [("deviation", "accepted", ["lib/extra.py"])])

    def test_f3_a_growth_inside_the_write_set_registers_done_with_deviations(self):
        self.set_items({"W1": {"write_set": ["out/W1.txt", "lib/**"]}})
        self.script({"executor": [executor_ok("W1"), fixed("lib/extra.py", tag=False)],
                     "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(list(self.source()["registered"].values()), ["done_with_deviations"])
        self.assertEqual(self.source()["items"]["W1"]["status"], "done_with_deviations")

    def test_l_an_executor_correction_that_grows_is_an_accepted_deviation_and_a_beacon(self):
        self.work(bounded=False)
        self.script({"executor": [executor_ok("W1"), fixed("lib/extra.py", tag=False)],
                     "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        grew = self.beacons(err, "CORRECTION_SCOPE_GREW")
        self.assertEqual(len(grew), 1)
        self.assertIn("lib/extra.py", grew[0]["message"])
        issues = [row for row in self.source()["items"]["W1"]["report"]["open_issues"]
                  if str(row.get("text")).startswith("CORRECTION_SCOPE_GREW")]
        self.assertEqual([(row["kind"], row["class"], row["outcome"], row["evidence"]) for row in issues],
                         [("deviation", "other", "accepted", ["lib/extra.py"])])

    def test_l_a_bounded_correction_that_grows_blocks_the_piece(self):
        self.work()
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING, GREEN], "triager": [TRIAGE],
                     "bounded-implementer": [fixed("lib/extra.py")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.source()["items"]["W1"]["status"], "blocked")
        escalations = [row["text"] for row in self.source()["items"]["W1"]["report"]["open_issues"]
                       if row["kind"] == "escalation"]
        self.assertEqual(escalations, ["CORRECTION_SCOPE_GREW: lib/extra.py"])
        self.assertEqual([line["event"] for line in self.beacons(err, "CORRECTION_SCOPE_GREW")], ["info", "item.end"])

    def test_a_correction_inside_its_findings_the_tests_the_changelog_and_the_docs_does_not_grow(self):
        self.work(bounded=False)
        self.script({"executor": [executor_ok("W1"), fixed("tests/test_w1.py", "CHANGELOG.md", "docs/w1.md",
                                                           tag=False)],
                     "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        self.set_items({"W1": {"write_set": ["out/W1.txt", "tests/**"], "options": [
            {"source": "item:W1", "options": {}}]}})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.beacons(err, "CORRECTION_SCOPE_GREW"), [])


class NamedModelClassTests(RouteCase):
    def test_h_a_cheap_model_named_by_a_stage_is_economy_and_undershoots_an_implementation_item(self):
        self.work(bounded=False, stages=[{"role": "executor", "provider": "claude-code", "model": "haiku",
                                          "model_class": "implementation"}])
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROUTE_UNDERSHOOT")), err)
        self.assertEqual(self.calls("executor"), 0)

    def test_a_stage_label_is_kept_for_a_model_that_is_not_as_low_as_the_label(self):
        self.work(bounded=False, stages=[{"role": "executor", "provider": "claude-code", "model": "sonnet",
                                          "model_class": "implementation"}])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)

    def test_an_unknown_model_keeps_its_label_and_is_said_once_per_role(self):
        self.work(bounded=False, stages=[{"role": "executor", "provider": "claude-code", "model": "mystery-model",
                                          "model_class": "implementation"}])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        said = [line for line in self.beacons(err, "ROUTE_MODEL_UNKNOWN") if line.get("role") == "executor"]
        self.assertEqual(len(said), 1)
        self.assertIn("mystery-model", said[0]["message"])


if __name__ == "__main__":
    unittest.main()
