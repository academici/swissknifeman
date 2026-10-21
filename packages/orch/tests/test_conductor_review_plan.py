"""The review plan of a batch (review.strategy): chosen before the first piece, carried out after the last piece of a group."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import unittest

from tests.test_conductor import GREEN, ConductorCase, executor_ok, report

CLEAN = {"text": "## Findings\nnone\n## Checked and fine\n- a\n"}
REVIEW = "## Findings\n[Major] out/W3.txt:1 - a defect\nScenario: x -> y\nFix: z\n## Checked and fine\n- a\n"


def answer(mode, groups, effort="medium"):
    return {"text": "```json\n" + json.dumps({"mode": mode, "groups": groups, "reviewer": {"effort": effort},
                                              "reason": "test"}) + "\n```\n"}


class ReviewPlanTests(ConductorCase):
    def test_strategist_budget_stop_is_not_swallowed_as_failed_advice(self):
        from unittest import mock
        from orch.conductor import engine
        from orch.conductor.application import review_plan
        from orch.conductor.domain.item import Item
        from orch.conductor.domain.stop import Stop
        from orch import settings
        owner = engine.Conductor(project=self.project, settings=settings.load(project=self.project))
        owner.run_id = "R"
        owner.state = {"tokens": {"input": 10}}
        item = Item("W1", "source-run", {}, self.project, {})
        item.options = {"limits": {"run_tokens_hard_max": 10}}
        with mock.patch.object(owner, "_route", return_value={}), mock.patch.object(owner, "_agent_start") as start, \
                mock.patch.object(engine.process, "run_role") as process:
            with self.assertRaises(Stop) as caught:
                review_plan.ask_strategist(owner, item, [], {"mode": "none", "groups": [], "reviewer": {}})
            self.assertEqual(caught.exception.code, "TOKEN_BUDGET")
            start.assert_not_called()
            process.assert_not_called()

    def test_group_review_waits_for_a_raise_and_resume_does_not_repeat_closed_items(self):
        from unittest import mock
        from orch.conductor import engine
        # Spend the remaining run budget exactly when the completed group is about to be reviewed. This isolates
        # the call outside _step from the post-done checks, which have their own integration coverage.
        original = engine.Conductor._group_review_due

        def due(owner, ref):
            if ref == "W2":
                owner.state["tokens"] = {"input": 500, "output": 0}
                owner._save()
            return original(owner, ref)

        self.set_items({ref: {} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [{"text": REVIEW}]})
        path = self.project.parent / "group-options.json"
        path.write_text(json.dumps({"limits": {"run_tokens_hard_max": 500}, "review": {"strategy": "single"}}))
        with mock.patch.object(engine.Conductor, "_group_review_due", due):
            code, _, err = self.run_items("W1", "W2", extra=("--options", path))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 0))
        self.assertNotIn("group_reviews", self.state(err))
        code, _, resumed = self.conduct("resume", "--run", self.run_dir(err).name,
                                       "--raise-limit", "run_tokens_hard_max=1000", "--json-lines")
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 1))
        self.assertIn("1", self.state(resumed)["group_reviews"])

    def run_model(self, *items):
        """A run whose strategist is the model (``review.strategist: model``): the default is the rules."""
        path = self.project.parent / "strategist-model.json"
        path.write_text(json.dumps({"review": {"strategist": "model"}}), encoding="utf-8")
        return self.run_items(*items, extra=("--options", path))

    def batch(self, *, triager=None, options=None, items=("W1", "W2", "W3")):
        if triager and not (options or {}).get("review", {}).get("strategist"):  # the strategist is asked only when named
            options = {**(options or {}), "review": {**(options or {}).get("review", {}), "strategist": "model"}}
        self.set_items({ref: {} for ref in items})
        self.script({"executor": [executor_ok(ref) for ref in items], "reviewer": [GREEN] * 3 if not triager else [{"text": REVIEW}],
                     **({"triager": [triager]} if triager else {})})
        extra = ()
        if options:
            path = self.project.parent / "opts.json"
            path.write_text(json.dumps(options), encoding="utf-8")
            extra = ("--options", path)
        code, _, err = self.run_items(*items, extra=extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def plan_of(self, err):
        return self.state(err).get("review_strategy")

    def events(self, err, code):
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def test_the_strategist_picks_one_review_for_the_whole_batch(self):
        err = self.batch(triager=answer("single", [["W1", "W2", "W3"]]))
        plan = self.plan_of(err)
        self.assertEqual((plan["mode"], plan["groups"], plan["source"]), ("single", [["W1", "W2", "W3"]], "model"))
        self.assertEqual(self.calls("reviewer"), 1)  # one review of the group, none per piece
        self.assertEqual(self.calls("triager"), 1)
        kept = self.state(err)["group_reviews"]["1"]
        self.assertEqual((kept["refs"], kept["counts"]["Major"]), (["W1", "W2", "W3"], 1))
        self.assertTrue((self.run_dir(err) / "group-review-1.md").is_file())
        self.assertTrue(self.events(err, "GROUP_REVIEW"))
        self.assertTrue(self.events(err, "REVIEW_STRATEGY"))

    def test_a_reply_in_another_format_is_a_failed_review_not_a_clean_one(self):
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        self.script({"executor": [executor_ok(r) for r in ("W1", "W2", "W3")], "reviewer": [{"text": "Looks fine to me."}],
                     "triager": [answer("single", [["W1", "W2", "W3"]])]})
        code, _, err = self.run_model("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.state(err)["group_reviews"]["1"]["format"], "malformed")
        self.assertFalse(self.events(err, "GROUP_REVIEW"))
        self.assertTrue(self.events(err, "GROUP_REVIEW_FAILED"))

    def test_major_findings_come_with_a_ready_followup_input(self):
        err = self.batch(triager=answer("single", [["W1", "W2", "W3"]]))
        kept = self.state(err)["group_reviews"]["1"]
        self.assertEqual(kept["format"], "findings")
        path = self.project / kept["followup"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["provenance"]["kind"], "review_followup")
        self.assertEqual(doc["scope"]["include"], ["out/W3.txt"])
        self.assertIn("[Major] out/W3.txt:1 - a defect", doc["goal"])
        message = self.events(err, "GROUP_REVIEW")[0]["message"]
        self.assertIn("orch conduct run --input", message)

    def grouped(self, routes: dict, options=None) -> str:
        self.set_items({ref: ({"review_route": routes[ref]} if routes.get(ref) else {}) for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN]})
        path = self.project.parent / "group-options.json"
        path.write_text(json.dumps({"review": {"strategy": "single"}, **(options or {})}), encoding="utf-8")
        code, _, err = self.run_items("W1", "W2", extra=("--options", path))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 1)
        return err

    def test_a_group_takes_the_strongest_review_route_of_its_pieces_and_says_so(self):
        err = self.grouped({"W1": {"provider": "codex", "class": "implementation"},
                            "W2": {"provider": "claude-code", "class": "frontier"}})
        start = self.events(err, "GROUP_REVIEW_START")[0]["message"]
        self.assertIn("claude-code/opus/", start)
        conflict = self.events(err, "GROUP_REVIEW_ROUTE_CONFLICT")
        self.assertEqual(len(conflict), 1, err)
        self.assertIn("W1: codex/implementation", conflict[0]["message"])
        self.assertIn("W2: claude-code/frontier", conflict[0]["message"])

    def test_a_group_with_one_shared_review_route_takes_it_without_a_beacon(self):
        route = {"provider": "codex", "model": "gpt-6-sol"}
        err = self.grouped({"W1": route, "W2": route})
        self.assertIn("codex/gpt-6-sol/", self.events(err, "GROUP_REVIEW_START")[0]["message"])
        self.assertFalse(self.events(err, "GROUP_REVIEW_ROUTE_CONFLICT"))

    def test_the_reviewer_of_the_run_reviews_the_group_whatever_the_plan_says(self):
        err = self.grouped({"W1": {"provider": "codex", "class": "frontier"}}, {"reviewer": "claude-code/sonnet/high"})
        self.assertIn("claude-code/sonnet/", self.events(err, "GROUP_REVIEW_START")[0]["message"])
        self.assertFalse(self.events(err, "GROUP_REVIEW_ROUTE_CONFLICT"))

    def test_a_requested_review_under_a_none_strategy_is_said(self):
        self.set_items({ref: {"review_mode": "requested"} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")]})
        path = self.project.parent / "none-options.json"
        path.write_text(json.dumps({"review": {"strategy": "none"}}), encoding="utf-8")
        code, _, err = self.run_items("W1", "W2", extra=("--options", path))
        self.assertEqual((code, self.calls("reviewer")), (0, 0), err)
        said = self.events(err, "REVIEW_REQUESTED_POLICY_OFF")
        self.assertEqual(sorted(line["item"] for line in said), ["W1", "W2"])
        self.assertIn("review strategy of the batch is none", said[0]["message"])

    def disabled_group_reviewer(self, override, expected):
        self.set_items({ref: {"review_mode": mode,
                             "review_route": {"provider": provider, "model": model, "effort": "high"},
                             "options": [{"source": f"item:{ref}", "options": {
                                 "reviewer": f"{provider}/{model}/high"}}]}
                        for ref, mode, provider, model in (("W1", "requested", "grok", "grok-4.7"),
                                                          ("W2", "none", "claude-code", "opus"))})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [CLEAN]})  # W1 is requested: a reply it can read
        path = self.project.parent / "group-options.json"
        path.write_text(json.dumps({"review": {"strategy": "single"}, **override}))
        code, _, err = self.run_items("W1", "W2", extra=("--options", path))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 1)
        self.assertIn(expected, self.events(err, "GROUP_REVIEW_START")[0]["message"])

    def test_disabled_last_piece_does_not_replace_requested_group_reviewer(self):
        self.disabled_group_reviewer({}, "grok/grok-4.7/")

    def test_explicit_run_reviewer_beats_disabled_last_piece_and_requested_route(self):
        self.disabled_group_reviewer({"reviewer": "codex/gpt-6-sol/high"}, "codex/gpt-6-sol/")

    def test_an_effort_named_by_the_reviewer_option_beats_the_strategy(self):
        from orch.conductor import options as opts
        from orch.conductor.application import review_plan
        named = opts.parse_selector("codex/gpt-6.1-sol/high")
        self.assertEqual(review_plan.reviewer_effort(named, "medium"), "high")
        self.assertEqual(review_plan.reviewer_effort(opts.parse_selector("codex/gpt-6.1-sol"), "medium"), "medium")

    def test_the_strategy_beacon_announces_the_effort_the_group_review_runs_at(self):
        from types import SimpleNamespace
        from orch.conductor.application import review_plan
        catalog = SimpleNamespace(conductor={})
        self.assertEqual(review_plan.group_effort(catalog, "codex/gpt-6.1-sol/xhigh", "medium"), "xhigh")
        self.assertEqual(review_plan.group_effort(catalog, "codex/gpt-6.1-sol", "medium"), "medium")
        fixed = SimpleNamespace(conductor={"argv": {"reviewer": ["fake"]}})
        self.assertEqual(review_plan.group_effort(fixed, "codex/gpt-6.1-sol/xhigh", "medium"), "medium")

    def test_the_followup_runs_the_command_checks_of_the_reviewed_pieces(self):
        import tempfile
        from types import SimpleNamespace
        from orch.conductor.application import review_plan
        read = {"findings": [{"severity": "Major", "location": "a.py:1", "text": "a.py:1 - a defect"}]}
        checks = {"W1": [{"id": "V1", "cmd": "bash t.sh", "kind": "acceptance"},
                         {"id": "V2", "cmd": "python3 -m unittest x", "cwd": "pkg dir", "kind": "acceptance"},
                         {"id": "V50", "cmd": "broad --tier all", "cadence": "phase", "kind": "acceptance"},
                         {"id": "V3", "procedure": "looks right", "kind": "acceptance"}],
                  "W2": [{"id": "V1", "cmd": "bash t.sh", "kind": "acceptance"}]}
        with tempfile.TemporaryDirectory() as folder:
            for ref, rows in checks.items():
                (Path(folder) / ref).mkdir()
                (Path(folder) / ref / "input.json").write_text(json.dumps({"acceptance": {"checks": rows}}), encoding="utf-8")
            owner = SimpleNamespace(directory=Path(folder), progress=SimpleNamespace(emit=lambda *a, **k: None),
                                    _relative=lambda path: str(path))
            doc = json.loads(Path(review_plan.followup_input(owner, 1, ["W1", "W2"], read, "high")).read_text(encoding="utf-8"))
        commands = [row.get("cmd") for row in doc["acceptance"]["checks"] if row.get("cmd")]
        self.assertEqual(commands, ["bash t.sh", "cd 'pkg dir' && python3 -m unittest x"])  # once each, no phase check
        self.assertEqual([row for row in doc["acceptance"]["checks"] if row.get("procedure")], [])  # no observed check

    def test_the_followup_asks_no_more_effort_than_the_executor_of_the_run_has(self):
        import tempfile
        from types import SimpleNamespace
        from orch.conductor.application import review_plan
        read = {"findings": [{"severity": "Major", "location": "a.py:1", "text": "a.py:1 - a defect"}]}
        for effort, expected in (("medium", "medium"), (None, "high")):
            with tempfile.TemporaryDirectory() as folder:
                owner = SimpleNamespace(directory=Path(folder), progress=SimpleNamespace(emit=lambda *a, **k: None),
                                        _relative=lambda path: str(path))
                target = review_plan.followup_input(owner, 1, ["W1"], read, effort)
                doc = json.loads(Path(target).read_text(encoding="utf-8"))
                self.assertEqual(doc["route"]["minimum"], {"class": "implementation", "effort": expected})

    def test_a_group_whose_commits_changed_no_production_code_is_not_sent_to_the_reviewer(self):
        from unittest import mock
        from orch.conductor import review_batch
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        self.script({"executor": [executor_ok(r) for r in ("W1", "W2", "W3")], "reviewer": [GREEN],
                     "triager": [answer("single", [["W1", "W2", "W3"]])]})
        with mock.patch.object(review_batch, "INCLUDE", ["nowhere-in-the-project"]):  # the commits touch nothing it names
            code, _, err = self.run_items("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 0)
        self.assertEqual(self.state(err)["group_reviews"]["1"]["error"], "EMPTY_DIFF")
        self.assertTrue(self.events(err, "GROUP_REVIEW_FAILED"))

    def test_a_resume_between_groups_keeps_the_plan_and_reviews_each_group_once(self):
        blocked = report("W3", "blocked", open_issues=[{"text": "needs a decision", "kind": "escalation"}])
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2"), {"result": blocked}, executor_ok("W3")],
                     "reviewer": [{"text": REVIEW}, {"text": REVIEW}],
                     "triager": [answer("groups", [["W1", "W2"], ["W3"]])]})
        code, _, err = self.run_model("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(sorted(self.state(err)["group_reviews"]), ["1"])  # the first group was read before the stop
        doc = self.source()
        doc["items"]["W3"]["status"] = "todo"  # the source reopened the blocked piece
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name, "--retry", "W3", "--json-lines")
        self.assertEqual(code, 0, err2)
        state = json.loads((self.run_dir(err) / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(state["group_reviews"]), ["1", "2"])
        self.assertEqual((self.calls("triager"), self.calls("reviewer")), (1, 2))  # not asked, not read again

    def test_a_batch_review_replaces_the_review_of_each_piece_even_when_dynamic_review_is_on(self):
        err = self.batch(triager=answer("single", [["W1", "W2", "W3"]]),
                         options={"review": {"dynamic": True, "dynamic_threshold": 0}})
        self.assertEqual(self.calls("reviewer"), 1)  # the group review only: no per-piece review was added by the risk score
        self.assertEqual(self.plan_of(err)["mode"], "single")

    def test_groups_are_reviewed_after_the_last_piece_of_each_group(self):
        err = self.batch(triager=answer("groups", [["W1", "W2"], ["W3"]], "high"))
        self.assertEqual(sorted(self.state(err)["group_reviews"]), ["1", "2"])
        self.assertEqual(self.state(err)["group_reviews"]["1"]["refs"], ["W1", "W2"])
        self.assertEqual(self.state(err)["group_reviews"]["2"]["effort"], "high")

    def test_an_unsound_answer_falls_back_to_the_rules(self):
        self.script({"executor": [executor_ok(r) for r in ("W1", "W2", "W3")], "reviewer": [{"text": REVIEW}],
                     "triager": [{"text": "I would just review everything"}]})
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        code, _, err = self.run_model("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        plan = self.plan_of(err)
        self.assertEqual(plan["source"], "rules")
        self.assertTrue(self.events(err, "STRATEGIST_UNSOUND"))

    def test_strategist_rules_asks_no_model(self):
        err = self.batch(options={"review": {"strategist": "rules"}})
        self.assertEqual(self.plan_of(err)["source"], "rules")
        self.assertEqual(self.calls("triager"), 0)

    def test_the_strategist_is_the_rules_by_default_and_a_multi_piece_run_asks_no_model(self):
        from orch.conductor import options as opts
        self.assertEqual(opts.DEFAULT_REVIEW["strategist"], "rules")
        err = self.batch()  # no option names the strategist
        self.assertEqual(self.plan_of(err)["source"], "rules")
        self.assertEqual(self.calls("triager"), 0)
        self.assertFalse((self.run_dir(err) / "streams" / "review-strategist.txt").exists())

    def test_none_reviews_nothing_and_each_keeps_the_review_of_every_piece(self):
        err = self.batch(options={"review": {"strategy": "none"}})
        self.assertEqual((self.plan_of(err)["mode"], self.calls("reviewer")), ("none", 0))

    def test_each_is_the_review_of_every_piece_as_before(self):
        err = self.batch(options={"review": {"strategy": "each"}})
        self.assertEqual((self.plan_of(err)["mode"], self.calls("reviewer")), ("each", 3))

    def test_one_piece_is_reviewed_as_configured_and_no_group_review_runs(self):
        self.set_items({"W1": {}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("group_reviews", self.state(err))
        self.assertEqual(self.calls("reviewer"), 1)


BLOCKER = {"text": "## Findings\n[Blocker] out/W2.txt:1 - a defect\nScenario: x -> y\nFix: z\n## Checked and fine\n- a\n"}
UNREADABLE = {"text": "Looks fine to me."}


class GroupBlockerTests(ConductorCase):
    """A group review that finds a Blocker stops the run until a follow-up run that corrected it is settled."""

    def setUp(self):
        super().setUp()
        self.options = self.project.parent / "group-options.json"
        self.options.write_text(json.dumps({"review": {"strategy": "single"}}), encoding="utf-8")

    def stopped(self, reviewer=None, pieces=None):
        """A two-piece batch whose group review answers ``reviewer`` (a Blocker by default); the err of the stopped run."""
        self.set_items({ref: dict(pieces or {}) for ref in ("W1", "W2")})
        fix = {"write": {"out/W2.txt": "fixed\n"}, "result": report("W2")}
        self.script({"executor": [executor_ok("W1"), executor_ok("W2"), fix], "reviewer": reviewer or [BLOCKER, GREEN, GREEN]})
        code, _, err = self.run_items("W1", "W2", extra=("--options", self.options))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "GROUP_REVIEW_BLOCKER")), err)
        self.run_id = self.run_dir(err).name
        self.err = err
        return err

    def followup_path(self) -> Path:
        return self.run_dir(self.err) / "group-review-1.followup.json"

    def run_followup(self, path=None, *extra) -> str:
        code, _, err = self.conduct("run", "--input", path or self.followup_path(), "--json-lines", "--scenario", "full", *extra)
        self.assertEqual(code, 0, err)
        return self.run_dir(err).name

    def settle(self, followup_run: str, group: int = 1, run: str = None) -> tuple:
        return self.conduct("settle", "--run", run or self.run_id, "--group", group, "--followup-run", followup_run,
                            "--reason", "corrected by the follow-up")

    def state_bytes(self) -> bytes:
        return (self.run_dir(self.err) / "state.json").read_bytes()

    def resume(self) -> tuple:
        code, _, err = self.conduct("resume", "--run", self.run_id, "--json-lines")
        return code, err

    def test_a_blocker_stops_the_run_and_a_resume_stops_again_with_the_same_code(self):  # (g)
        err = self.stopped()
        stop = self.state(err)["stop"]["message"]
        self.assertIn(f"orch conduct run --input {self.followup_path().relative_to(self.project)} --commit", stop)
        self.assertIn(f"orch conduct settle --run {self.run_id} --group 1 --followup-run", stop)
        kept = self.state(err)["group_reviews"]["1"]
        self.assertEqual((kept["blocking"], kept["counts"]["Blocker"]), (True, 1))
        self.assertTrue(self.followup_path().is_file())
        code, again = self.resume()
        self.assertEqual((code, self.outcome(again)), (1, ("stopped", "GROUP_REVIEW_BLOCKER")), again)
        self.assertEqual(self.calls("reviewer"), 1)  # the review is not asked again
        self.assertNotIn("resolved", self.state(again)["group_reviews"]["1"])

    def test_a_settled_followup_lifts_the_stop_and_the_resume_goes_on(self):  # (g2)
        self.stopped()
        followup = self.run_followup(None, "--commit")
        commit = self.git("rev-parse", "HEAD").strip()
        code, _, err = self.settle(followup)
        self.assertEqual(code, 0, err)
        self.assertEqual(err.count("GROUP_REVIEW_RESOLVED"), 1, err)
        resolved = json.loads((self.run_dir(self.err) / "state.json").read_text(encoding="utf-8"))["group_reviews"]["1"]["resolved"]
        self.assertEqual((resolved["followup_run"], resolved["commit"], resolved["reason"]),
                         (followup, commit, "corrected by the follow-up"))
        self.assertTrue(resolved["at"])
        code, resumed = self.resume()
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertEqual(json.loads((self.run_dir(self.err) / "state.json").read_text(encoding="utf-8"))["group_reviews"]["1"]["attempts"], 1)

    def test_a_run_of_another_input_does_not_settle_the_group(self):  # (g3)
        self.stopped()
        other = self.project.parent / "other-followup.json"
        other.write_text(self.followup_path().read_text(encoding="utf-8"), encoding="utf-8")
        followup = self.run_followup(other, "--commit")
        before = self.state_bytes()
        code, _, err = self.settle(followup)
        self.assertEqual(code, 1)
        self.assertIn("GROUP_FOLLOWUP_MISMATCH", err)
        self.assertEqual(self.state_bytes(), before)
        self.assertNotIn("resolved", json.loads(before)["group_reviews"]["1"])
        code, again = self.resume()
        self.assertEqual((code, self.outcome(again)), (1, ("stopped", "GROUP_REVIEW_BLOCKER")), again)

    def test_a_run_that_is_not_there_does_not_settle_the_group(self):
        self.stopped()
        before = self.state_bytes()
        code, _, err = self.settle("cnd-nowhere")
        self.assertEqual(code, 1)
        self.assertIn("GROUP_FOLLOWUP_MISMATCH", err)
        self.assertEqual(self.state_bytes(), before)

    def test_a_followup_that_is_not_finished_and_committed_does_not_settle_the_group(self):  # (g4)
        self.stopped()
        followup = self.run_followup()  # no --commit: finished and done, but nothing committed
        before = self.state_bytes()
        code, _, err = self.settle(followup)
        self.assertEqual(code, 1)
        self.assertIn("GROUP_FOLLOWUP_NOT_DONE", err)
        self.assertIn("no commit", err)
        self.assertEqual(self.state_bytes(), before)
        run_dir = self.run_dir(self.err).parent / followup
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        state["status"] = "stopped"  # a follow-up that stopped half-way, with a commit receipt of its piece
        for item in state["items"].values():
            item["steps"]["commit"] = {"status": "done", "result": {"outcome": "committed", "sha": "0" * 40}}
        (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        code, _, err = self.settle(followup)
        self.assertEqual(code, 1)
        self.assertIn("GROUP_FOLLOWUP_NOT_DONE", err)
        self.assertEqual(self.state_bytes(), before)

    def test_a_group_that_waits_for_nothing_is_unknown(self):
        self.stopped()
        before = self.state_bytes()
        code, _, err = self.settle("cnd-any", group=7)
        self.assertEqual(code, 1)
        self.assertIn("GROUP_UNKNOWN", err)
        self.assertEqual(self.state_bytes(), before)

    def test_a_busy_run_cannot_be_settled_and_its_state_stays(self):  # (g5)
        from orch.conductor.infrastructure.lease import RunLease
        self.stopped()
        followup = self.run_followup(None, "--commit")
        before = self.state_bytes()
        with RunLease(self.run_dir(self.err)).acquire("resume"):
            code, _, err = self.settle(followup)
        self.assertEqual(code, 1)
        self.assertIn("RUN_BUSY", err)
        self.assertEqual(self.state_bytes(), before)

    def test_settle_takes_an_item_and_an_outcome_or_a_group_and_a_followup_run(self):
        self.stopped()
        for argv in (("--group", "1"), ("--item", "W1"), ("--group", "1", "--followup-run", "x", "--item", "W1", "--outcome", "done"),
                     ("--followup-run", "x")):
            with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                self.conduct("settle", "--run", self.run_id, "--reason", "r", *argv)
            self.assertEqual(raised.exception.code, 2, argv)

    def test_a_requested_group_review_in_a_bad_format_stops_and_is_repeated_once(self):  # (h)
        self.stopped_failed([UNREADABLE, UNREADABLE, CLEAN], {"review_mode": "requested"})
        code, err = self.resume()
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "GROUP_REVIEW_FAILED")), err)
        self.assertEqual((self.calls("reviewer"), self.state(err)["group_reviews"]["1"]["attempts"]), (2, 2))
        self.assertIn("no review is asked again", self.state(err)["stop"]["message"])
        for _ in range(2):  # past the cap a resume is no waiver: the same stop, and no third reviewer call
            code, err = self.resume()
            self.assertEqual((code, self.outcome(err), self.calls("reviewer")), (1, ("stopped", "GROUP_REVIEW_FAILED"), 2), err)
            self.assertEqual(self.state(err)["group_reviews"]["1"]["attempts"], 2)

    def test_an_exhausted_requested_review_stays_failed_without_a_reviewer_call(self):  # fake state, no run
        from types import SimpleNamespace
        from unittest import mock
        from orch.conductor.application import review_plan
        from orch.conductor.domain.stop import Stop
        directory = self.project.parent / "fake-run"
        (directory / "W1").mkdir(parents=True)
        (directory / "W1" / "input.json").write_text(json.dumps({"review_mode": "requested"}), encoding="utf-8")
        owner = SimpleNamespace(
            directory=directory, run_id="R",
            state={"review_strategy": {"mode": "single", "groups": [["W1"]], "reviewer": {"effort": "medium"}},
                   "items": {"W1": {"outcome": "done"}},
                   "group_reviews": {"1": {"refs": ["W1"], "format": "malformed", "error": None, "attempts": 2}}})
        with mock.patch.object(review_plan, "group_review") as asked:
            with self.assertRaises(Stop) as raised:
                review_plan.group_review_due(owner, "W1")
            self.assertEqual(raised.exception.code, "GROUP_REVIEW_FAILED")
            asked.assert_not_called()
            owner.state["group_reviews"]["1"]["attempts"] = 1  # below the cap the review is asked once more
            review_plan.group_review_due(owner, "W1")
            asked.assert_called_once()
            asked.reset_mock()
            owner.state["group_reviews"]["1"].update(format="none", attempts=2)  # a review that read ends the failure
            review_plan.group_review_due(owner, "W1")
            asked.assert_not_called()

    def test_a_repeated_group_review_that_reads_ends_the_failure(self):
        self.stopped_failed([UNREADABLE, CLEAN], {"review_mode": "requested"})
        code, err = self.resume()
        self.assertEqual((code, self.outcome(err), self.calls("reviewer")), (0, ("finished", None), 2), err)
        kept = self.state(err)["group_reviews"]["1"]
        self.assertEqual((kept["format"], kept["attempts"]), ("none", 2))

    def test_a_bad_format_stops_nothing_when_no_piece_asked_for_a_review(self):  # (h)
        self.set_items({ref: {"review_mode": "self"} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [UNREADABLE]})
        code, _, err = self.run_items("W1", "W2", extra=("--options", self.options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "GROUP_REVIEW_FAILED"])

    def stopped_failed(self, reviewer, pieces):
        self.set_items({ref: dict(pieces) for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": reviewer})
        code, _, err = self.run_items("W1", "W2", extra=("--options", self.options))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "GROUP_REVIEW_FAILED")), err)
        self.run_id = self.run_dir(err).name
        self.err = err

    def test_a_forced_strategy_leaves_out_a_piece_whose_plan_gives_it_no_review(self):  # (i)
        self.set_items({"W1": {"review_mode": "requested"}, "W2": {"review_mode": "none"}, "W3": {"review_mode": "requested"}})
        self.script({"executor": [executor_ok(ref) for ref in ("W1", "W2", "W3")], "reviewer": [CLEAN]})
        code, _, err = self.run_items("W1", "W2", "W3", extra=("--options", self.options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        plan = self.state(err)["review_strategy"]
        self.assertEqual((plan["mode"], plan["groups"]), ("single", [["W1", "W3"]]))
        said = [line for line in self.lines(err) if line.get("reason_code") == "REVIEW_MODE_NONE_SKIPPED"]
        self.assertEqual(len(said), 1, err)
        self.assertIn("W2", said[0]["message"])
        self.assertEqual(self.state(err)["group_reviews"]["1"]["refs"], ["W1", "W3"])

    def test_forced_drops_the_none_pieces_of_every_mode_and_empty_groups(self):
        from orch.conductor.application.review_plan import forced
        pieces = [{"ref": "A", "review_mode": "requested"}, {"ref": "B", "review_mode": "none"}, {"ref": "C"}]
        proposal = {"mode": "groups", "groups": [["B"], ["A", "B"], ["C"]], "reviewer": {"effort": "medium"}}
        self.assertEqual(forced("single", pieces, proposal)["groups"], [["A", "C"]])
        self.assertEqual(forced("each", pieces, proposal)["groups"], [["A"], ["C"]])
        self.assertEqual(forced("groups", pieces, proposal)["groups"], [["A"], ["C"]])
        self.assertEqual(forced("none", pieces, proposal)["groups"], [])
        flat = dict(proposal, mode="each")
        self.assertEqual(forced("groups", pieces, flat)["groups"], [["A", "C"]])


if __name__ == "__main__":
    unittest.main()
