"""The prompt builders as blocks (PLAN4 P9.1): the blocks add up to the prompt byte for byte, the prompt of every builder
equals the one captured before the builders were split into blocks (``tests/golden/conductor-prompts``), and the
manifest says where each part of a prompt came from."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from aicore.content.budget import estimate_tokens
from aicore.util.digest import sha256_hex

from orch.conductor import contract, observer, options as opts, prompts
from tests.test_conductor import GREEN, ConductorCase, executor_ok

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden" / "conductor-prompts"
INPUTS = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input"
RESEARCH = {"query": "q", "claims": [{"text": "The flag exists.", "sources": ["https://example.org/a", "docs/cli.md"]}],
            "contradictions": ["A says on, B says off"], "unknowns": ["the default value"], "sources_used": ["fake"]}
RULES = "## Rules\n\n- keep it small <!-- generator marker -->\n- stdlib only\n"


def fixture(name: str) -> dict:
    return json.loads((INPUTS / f"{name}.json").read_text(encoding="utf-8"))


def cases() -> dict:
    """``name -> blocks`` of every builder in the shapes the conductor uses; the arguments are fixed."""
    plan, adhoc = fixture("plan-bound"), fixture("adhoc")
    findings = {"verdict": "ATTENTION", "findings": [{"id": "F1", "severity": "Major", "location": "a.py:3"}]}
    return {
        "scout": prompts.scout(plan, item="P1.1", step="scout", skills=["alpha", "beta"],
                               skill_texts={"beta": "Beta body.\n\n\n"}),
        "scout-plain": prompts.scout(adhoc, item="W1", step="scout"),
        "executor-full": prompts.executor(
            plan, item="P1.1", step="executor.2-q1", scout_text="map line 1\n```\ninner\n```\n", rules=["a rule", "b rule"],
            correction="red V1", skills=["alpha", "beta"], repo_rules=RULES, skill_texts={"beta": "Beta body.\n"},
            expected={"paths": ["a/b.py"] + [f"p{n}" for n in range(60)], "tests": ["tests/test_b.py"]},
            answers=[{"id": "Q1", "text": "Which?", "answer": "a", "by": "owner"},
                     {"id": "Q2", "text": "How?", "answer": {"k": 1}, "by": "policy"}],
            fix=prompts.DEVIATION_FIX),
        "executor-research": prompts.executor(
            plan, item="P1.1", step="executor.1", research=RESEARCH, research_origin="plans/T/research/P1.1-1.json"),
        "executor-targeted": prompts.executor(plan, item="P1.1", step="executor.1", scout_text="map"),
        "executor-checks": prompts.executor(adhoc, item="W1", step="executor.1", targeted_tests=False, correction="x"),
        "executor-bounded": prompts.executor(adhoc, item="W1", step="executor.1", role="bounded-implementer"),
        "reviewer-full": prompts.reviewer(
            plan, item="P1.1", step="review.2", base="abc123", diff="diff --git a/x b/x\n+```\n", round_no=2,
            checks=[{"id": "V1", "exit": 0}, {"id": "V2", "verdict": "pass"}], pre_final=True, min_severity="Major",
            corrected=[{"id": "F1", "severity": "Major", "location": "a.py:3", "failure_scenario": "boom", "fix": "guard"}],
            outside=["docs/x.md"], skills=["alpha"], repo_rules=RULES, skill_texts={"alpha": "Alpha body."}),
        "reviewer-pending": prompts.reviewer(plan, item="P1.1", step="review.1", base="abc123", diff="", round_no=1,
                                             checks=[], checks_pending=True),
        "reviewer-checks": prompts.reviewer(adhoc, item="W1", step="review.1", base="abc123", diff="d", round_no=1,
                                            checks=[{"id": "V1", "exit": 1}]),
        "triager": prompts.triager(plan, item="P1.1", step="triage.1", base="abc123", findings=findings,
                                   skills=["alpha"], repo_rules=RULES),
        "closer": prompts.closer(item="P1.1", step="close", command="python3 orch.py source register 'a b'"),
        "report-fixer": prompts.report_fixer(kind="stage-report", problem="/status: missing", answer="x" * 50,
                                             item="P1.1", step="executor.1"),
        "report-fixer-cut": prompts.report_fixer(kind="review-findings", problem="p", answer="y" * 90,
                                                 item="P1.1", step="review.1", limit=40),
    }


class WithheldChecksTests(unittest.TestCase):
    """``checks.executor_runs_checks: false``: the executor prompt names the acceptance checks, never their commands."""

    def test_the_prompt_of_an_executor_that_does_not_run_checks_carries_no_acceptance_command(self):
        doc = fixture("plan-bound")
        doc["acceptance"]["checks"].append({"id": "V2", "cmd": "docker compose run --rm tools gate main",
                                            "cwd": "tools", "expect": "exit 0", "kind": "acceptance"})
        text = prompts.render(prompts.executor(doc, item="P1.1", step="executor.1"))
        for command in ("python3 -m unittest tests.test_cli", "docker compose run --rm tools gate main"):
            self.assertNotIn(command, text)
        self.assertIn("`V1`: exit 0", text)
        self.assertIn("`V2`: exit 0", text)
        self.assertIn("kind `pending`", text)
        self.assertIn("withheld; the conductor runs this check itself", text)

    def test_a_procedure_check_is_withheld_too_and_the_input_is_not_changed(self):
        doc = fixture("adhoc")
        text = prompts.render(prompts.executor(doc, item="W1", step="executor.1"))
        self.assertNotIn("README install section reads", text)
        self.assertIn("procedure", doc["acceptance"]["checks"][0])  # the caller's document keeps its commands

    def test_an_executor_that_runs_checks_still_gets_the_commands(self):
        doc = fixture("plan-bound")
        text = prompts.render(prompts.executor(doc, item="P1.1", step="executor.1", targeted_tests=False))
        self.assertIn("python3 -m unittest tests.test_cli", text)
        self.assertNotIn("do not start containers", text)


class BlockTests(unittest.TestCase):
    def test_every_builder_matches_the_prompt_captured_before_the_split(self):
        for name, blocks in cases().items():
            with self.subTest(case=name):
                self.assertEqual(prompts.render(blocks), (GOLDEN / f"{name}.md").read_text(encoding="utf-8"))

    def test_the_blocks_add_up_to_the_prompt_and_their_tokens_to_its_estimate(self):
        for name, blocks in cases().items():
            with self.subTest(case=name):
                text = prompts.render(blocks)
                self.assertEqual("".join(block.text for block in blocks), text)
                self.assertLessEqual(abs(sum(estimate_tokens(block.text) for block in blocks) - estimate_tokens(text)),
                                     len(blocks))

    def test_blocks_have_a_known_kind_and_an_origin(self):
        for name, blocks in cases().items():
            for block in blocks:
                with self.subTest(case=name, kind=block.kind):
                    self.assertIn(block.kind, prompts.KINDS)
                    self.assertTrue(block.origin)
                    self.assertTrue(block.text)

    def test_executor_blocks_name_their_sources(self):
        blocks = cases()["executor-full"]
        by_kind = {}
        for block in blocks:
            by_kind.setdefault(block.kind, []).append(block)
        self.assertEqual([block.kind for block in blocks][:3], ["role_text", "input", "repository_rules"])
        self.assertEqual(by_kind["role_text"][0].origin, "roles/executor.md")
        self.assertEqual(by_kind["input"][0].origin, "input.json")
        self.assertEqual([(block.kind, block.id) for block in blocks if block.kind.startswith("skill")],
                         [("skill_names", None), ("skill", "beta")])
        self.assertEqual(by_kind["skill"][0].origin, "skill:beta")
        for kind in ("context_map", "expected_paths", "run_rules", "answers", "correction", "progress", "result_contract"):
            self.assertIn(kind, by_kind)
        self.assertEqual(by_kind["context_map"][0].origin, "scout-cache")
        self.assertEqual(by_kind["result_contract"][0].origin, "conductor")

    def test_the_research_block_carries_claims_with_sources_and_names_its_file(self):
        blocks = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", research=RESEARCH,
                                  research_origin="plans/T/research/W1-1.json")
        (block,) = [block for block in blocks if block.kind == "research"]
        self.assertEqual(block.origin, "research-result:plans/T/research/W1-1.json")
        for text in ("The flag exists.", "https://example.org/a", "docs/cli.md", "A says on, B says off", "the default value"):
            self.assertIn(text, block.text)
        self.assertEqual(prompts.budget_class("research"), "retrieval")
        kinds = [item.kind for item in blocks]
        self.assertLess(kinds.index("research"), kinds.index("progress"))

    def test_no_research_no_block(self):
        for research in (None, {}):
            blocks = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", research=research)
            self.assertNotIn("research", [block.kind for block in blocks])
        empty = {"query": "q", "claims": [], "contradictions": [], "unknowns": [], "sources_used": []}
        blocks = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", research=empty)
        self.assertIn("research", [block.kind for block in blocks])  # a stage that found nothing still says so

    def test_the_scout_cache_file_is_the_origin_of_the_context_map(self):
        blocks = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", scout_text="map",
                                  scout_origin="runs/cache/scout/W1/ab.txt")
        self.assertEqual([block.origin for block in blocks if block.kind == "context_map"],
                         ["scout-cache:runs/cache/scout/W1/ab.txt"])

    def test_render_of_nothing_is_empty(self):
        self.assertEqual(prompts.render([]), "")


class ManifestTests(unittest.TestCase):
    def test_the_manifest_lists_blocks_with_digest_and_tokens(self):
        blocks = cases()["executor-full"]
        route = {"provider": "claude-code", "model": "m", "effort": "high", "extra": 1}
        doc = prompts.manifest(blocks, step="executor.1", role="executor", route=route)
        text = prompts.render(blocks)
        self.assertEqual(doc["schema"], "prompt-manifest/v1")
        self.assertEqual((doc["step"], doc["role"]), ("executor.1", "executor"))
        self.assertEqual(doc["route"], {"provider": "claude-code", "model": "m", "effort": "high"})
        self.assertEqual(doc["prompt_sha256"], sha256_hex(text.encode("utf-8")))
        self.assertEqual(doc["estimated_tokens"], estimate_tokens(text))
        self.assertEqual(doc["excluded"], [])
        self.assertEqual([row["kind"] for row in doc["blocks"]], [block.kind for block in blocks])
        for row, block in zip(doc["blocks"], blocks):
            self.assertEqual(row["sha256"], sha256_hex(block.text.encode("utf-8")))
            self.assertEqual(row["tokens"], estimate_tokens(block.text))
            self.assertEqual(row["origin"], block.origin)
            self.assertEqual(row.get("id"), block.id)
        self.assertEqual(sorted(doc), ["blocks", "estimated_tokens", "excluded", "prompt_sha256", "role", "route",
                                       "schema", "step"])
        self.assertEqual({key for row in doc["blocks"] for key in row} - {"id"}, {"kind", "origin", "sha256", "tokens"})

    def test_top_blocks_are_the_heaviest_first(self):
        doc = prompts.manifest(cases()["executor-full"], step="s", role="executor", route={})
        top = prompts.top_blocks(doc, 3)
        self.assertEqual(len(top), 3)
        self.assertEqual([row["tokens"] for row in top], sorted((row["tokens"] for row in doc["blocks"]), reverse=True)[:3])

    def test_explain_table_names_every_block(self):
        doc = prompts.manifest(cases()["executor-full"], step="s", role="executor", route={})
        table = prompts.explain_table(doc)
        for row in doc["blocks"]:
            self.assertIn(row["sha256"][:12], table)
        self.assertIn("estimated tokens", table)


class BudgetTests(unittest.TestCase):
    """PLAN4 P9.3 (knowledge/p9-prompt#budgets): blocks have a class, the manifest measures it against a limit, nothing is cut."""

    LIMITS = {"core": 12000, "supporting": 30000, "retrieval": 50000}

    def test_every_kind_has_one_class_and_the_listed_ones_are_where_the_design_puts_them(self):
        for kind in prompts.KINDS:
            with self.subTest(kind=kind):
                self.assertIn(prompts.budget_class(kind), ("core", "supporting", "retrieval"))
        for kind in ("role_text", "input", "verification", "result_contract", "answers", "correction"):
            self.assertEqual(prompts.budget_class(kind), "core", kind)
        for kind in ("repository_rules", "skill", "skill_names", "context_map", "expected_paths", "focus", "run_rules"):
            self.assertEqual(prompts.budget_class(kind), "supporting", kind)

    def test_the_manifest_adds_up_the_tokens_of_each_class(self):
        blocks = cases()["executor-full"]
        doc = prompts.manifest(blocks, step="executor.1", role="executor", route={}, limits=self.LIMITS)
        self.assertEqual(sorted(doc["budgets"]), ["core", "retrieval", "supporting"])
        for name, row in doc["budgets"].items():
            self.assertEqual(row["limit"], self.LIMITS[name])
            self.assertEqual(row["tokens"], sum(item["tokens"] for item in doc["blocks"]
                                                if prompts.budget_class(item["kind"]) == name), name)
        self.assertEqual(doc["budgets"]["retrieval"]["tokens"], 0)
        self.assertEqual(sum(row["tokens"] for row in doc["budgets"].values()), sum(item["tokens"] for item in doc["blocks"]))
        self.assertEqual(contract.problems(doc, "prompt-manifest"), [])

    def test_a_manifest_without_limits_has_no_budgets(self):
        self.assertNotIn("budgets", prompts.manifest(cases()["scout"], step="s", role="context-scout", route={}))

    def test_the_prompt_is_the_same_whatever_the_limits(self):
        blocks = cases()["executor-full"]
        before = prompts.render(blocks)
        prompts.manifest(blocks, step="s", role="executor", route={}, limits={"core": 1, "supporting": 1, "retrieval": 1})
        self.assertEqual(prompts.render(blocks), before)

    def test_a_class_past_its_limit_names_its_heaviest_block(self):
        blocks = [prompts.Block("role_text", "roles/x.md", "word " * 100 + "\n\n"), prompts.Block("input", "input.json", "word " * 400 + "\n\n"),
                  prompts.Block("skill", "skill:big", "word " * 300, id="big")]
        over = prompts.over_budget(blocks, {"core": 100, "supporting": 100, "retrieval": 0})
        self.assertEqual([(name, block.kind, block.origin) for name, block, _tokens, _limit in over],
                         [("core", "input", "input.json"), ("supporting", "skill", "skill:big")])
        name, block, tokens, limit = over[0]
        self.assertEqual((tokens, limit), (estimate_tokens(blocks[0].text) + estimate_tokens(blocks[1].text), 100))

    def test_a_limit_of_zero_is_off_and_a_class_at_its_limit_is_not_over(self):
        blocks = [prompts.Block("input", "input.json", "word " * 400)]
        self.assertEqual(prompts.over_budget(blocks, {"core": 0}), [])
        self.assertEqual(prompts.over_budget(blocks, {"core": estimate_tokens(blocks[0].text)}), [])

    def test_the_limits_are_run_options_with_defaults_bounds_and_a_closed_schema(self):
        self.assertEqual({key: opts.DEFAULT_LIMITS[key] for key in ("prompt_core_tokens", "prompt_supporting_tokens",
                                                                       "prompt_retrieval_tokens")},
                         {"prompt_core_tokens": 12000, "prompt_supporting_tokens": 30000, "prompt_retrieval_tokens": 50000})
        for key in ("prompt_core_tokens", "prompt_supporting_tokens", "prompt_retrieval_tokens"):
            with self.subTest(key=key):
                self.assertEqual(opts.layer_problems({"limits": {key: 0}}), [])
                self.assertEqual(len(opts.layer_problems({"limits": {key: -1}})), 1)
                self.assertEqual(contract.problems({"limits": {key: 9000}}, "run-options"), [])
                self.assertTrue(contract.problems({"limits": {key: "9000"}}, "run-options"))
        self.assertTrue(contract.problems({"limits": {"prompt_other_tokens": 1}}, "run-options"))


class RunManifestTests(ConductorCase):
    def prompts_dir(self, err: str) -> Path:
        return self.run_dir(err) / "W1" / "prompts"

    def finished(self) -> str:
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def test_every_role_step_leaves_a_manifest_next_to_its_prompt(self):
        folder = self.prompts_dir(self.finished())
        for key in ("scout", "executor.1", "review.1"):
            with self.subTest(step=key):
                doc = json.loads((folder / f"{key}.manifest.json").read_text(encoding="utf-8"))
                text = (folder / f"{key}.md").read_text(encoding="utf-8")
                self.assertEqual(doc["schema"], "prompt-manifest/v1")
                self.assertEqual(doc["step"], key)
                self.assertEqual(doc["prompt_sha256"], sha256_hex(text.encode("utf-8")))
                self.assertEqual(doc["estimated_tokens"], estimate_tokens(text))
                self.assertLessEqual(abs(sum(row["tokens"] for row in doc["blocks"]) - doc["estimated_tokens"]),
                                     len(doc["blocks"]))
                self.assertTrue({"provider", "model"} <= set(doc["route"]), doc["route"])
        executor = json.loads((folder / "executor.1.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(executor["role"], "executor")
        kinds = [row["kind"] for row in executor["blocks"]]
        self.assertEqual(kinds[:2], ["role_text", "input"])
        self.assertEqual(kinds[-1], "result_contract")
        self.assertIn("context_map", kinds)
        origin = [row["origin"] for row in executor["blocks"] if row["kind"] == "context_map"][0]
        self.assertTrue(origin.startswith("scout-cache:") and origin.endswith(".txt"), origin)

    def test_the_prompt_of_the_run_is_the_blocks_rendered(self):
        folder = self.prompts_dir(self.finished())
        self.assertEqual((folder / "executor.1.md").read_text(encoding="utf-8"), self.prompt("executor", 1))

    def test_prompt_explain_prints_the_blocks_and_the_json(self):
        err = self.finished()
        run = self.run_dir(err).name
        code, out, error = self.conduct("prompt", "explain", "--run", run, "--item", "W1", "--step", "executor.1")
        self.assertEqual((code, error), (0, ""))
        for token in ("kind | origin | tokens | sha256", "role_text | roles/executor.md", "input | input.json",
                      "result_contract | conductor"):
            self.assertIn(token, out)
        code, out, _ = self.conduct("prompt", "explain", "--item", "W1", "--step", "review.1", "--json")  # latest run
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["role"], "reviewer")

    def test_prompt_explain_refuses_an_unknown_step_and_run(self):
        err = self.finished()
        code, _, error = self.conduct("prompt", "explain", "--run", self.run_dir(err).name, "--item", "W1", "--step", "nope")
        self.assertEqual(code, 1)
        self.assertTrue(error.startswith("MANIFEST_UNKNOWN:"), error)
        code, _, error = self.conduct("prompt", "explain", "--run", "cnd-none", "--item", "W1", "--step", "scout")
        self.assertEqual(code, 1)
        self.assertTrue(error.startswith("RUN_UNKNOWN:"), error)

    def test_prompt_diff_compares_a_correction_with_the_attempt_before_it(self):
        from tests.test_conductor import report
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")], "reviewer": [GREEN]})  # V1 red, then green
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        run = self.run_dir(err).name
        code, out, error = self.conduct("prompt", "diff", "--run", run, "--item", "W1", "--step", "executor.2", "--json")
        self.assertEqual(code, 0, error)
        doc = json.loads(out)
        self.assertEqual((doc["base"]["step"], doc["target"]["step"], doc["against"]["step"]),
                         ("executor.1", "executor.2", "executor.1"))
        self.assertTrue(doc["counts"]["added"] + doc["counts"]["changed"] >= 1, doc)  # the correction package
        self.assertEqual(doc["tokens"]["delta"], doc["tokens"]["to"] - doc["tokens"]["from"])
        # executor.2 continued the session: its delta prompt has no role text or input, but the continuation and the contract
        self.assertIn("role_text", [row["kind"] for row in doc["blocks"] if row["change"] == "removed"])
        self.assertIn("resumed", [row["kind"] for row in doc["blocks"] if row["change"] == "added"])
        self.assertIn("result_contract", [row["kind"] for row in doc["blocks"] if row["change"] == "same"])
        code, out, _ = self.conduct("prompt", "diff", "--run", run, "--item", "W1", "--step", "executor.2")
        self.assertIn("executor.1 -> executor.2:", out)
        code, out, error = self.conduct("prompt", "diff", "--run", run, "--item", "W1", "--step", "executor.2",
                                        "--against", f"{run}:W1:review.1", "--json")
        self.assertEqual((code, json.loads(out)["base"]["step"]), (0, "review.1"), error)
        code, _, error = self.conduct("prompt", "diff", "--run", run, "--item", "W1", "--step", "executor.1")
        self.assertEqual(code, 1)
        self.assertTrue(error.startswith("PROMPT_BASELINE_MISSING:"), error)
        code, _, error = self.conduct("prompt", "diff", "--run", run, "--item", "W1", "--step", "executor.3")
        self.assertTrue(error.startswith("PROMPT_MANIFEST_MISSING:"), error)
        code, _, error = self.conduct("prompt", "diff", "--run", run, "--item", "W1", "--step", "executor.2",
                                      "--against", f"{run}:W1:triage.7")
        self.assertTrue(error.startswith("PROMPT_MANIFEST_MISSING:"), error)

    def test_blocks_without_an_origin_are_matched_by_kind_and_order(self):
        base = {"step": "a.1", "estimated_tokens": 5, "blocks": [
            {"kind": "note", "origin": "", "sha256": "1", "tokens": 2}, {"kind": "note", "origin": "", "sha256": "2", "tokens": 3}]}
        target = {"step": "a.2", "estimated_tokens": 9, "blocks": [
            {"kind": "note", "origin": "", "sha256": "1", "tokens": 2}, {"kind": "note", "origin": "", "sha256": "9", "tokens": 4},
            {"kind": "stub", "origin": "x.md", "sha256": "3", "tokens": 3}]}
        doc = prompts.diff_manifests(base, target)
        self.assertEqual([row["change"] for row in doc["blocks"]], ["same", "changed", "added"])
        self.assertEqual(doc["tokens"], {"from": 5, "to": 9, "delta": 4})

    def test_the_timeline_gives_every_step_as_an_interval(self):
        err = self.finished()
        code, out, error = self.conduct("timeline", "--run", self.run_dir(err).name, "--item", "W1", "--json")
        self.assertEqual(code, 0, error)
        rows = json.loads(out)["intervals"]
        stages = [row["stage"] for row in rows]
        self.assertIn("executor.1", stages)
        self.assertTrue(all(row["status"] == "done" and row["end"] and row["duration_s"] is not None for row in rows), rows)
        code, out, _ = self.conduct("timeline", "--run", self.run_dir(err).name)
        self.assertIn("W1 executor.1: done", out)

    def test_an_interrupted_and_resumed_step_is_two_intervals(self):
        lines = [{"ts": "2026-10-20T10:00:00Z", "event": "run.start"},
                 {"ts": "2026-10-20T10:00:01Z", "event": "stage.start", "item": "W1", "stage": "executor.1"},
                 {"ts": "2026-10-20T10:05:00Z", "event": "run.end", "outcome": "stopped"},
                 {"ts": "2026-10-20T11:00:00Z", "event": "run.resume"},
                 {"ts": "2026-10-20T11:00:02Z", "event": "stage.start", "item": "W1", "stage": "executor.1"},
                 {"ts": "2026-10-20T11:00:12Z", "event": "stage.end", "item": "W1", "stage": "executor.1", "verdict": "done"},
                 {"ts": "2026-10-20T11:00:13Z", "event": "stage.start", "item": "W1", "stage": "checks.1"}]
        from orch.conductor import progress
        rows = progress.timeline(lines)
        self.assertEqual([(row["stage"], row["status"], row["end"], row["duration_s"]) for row in rows],
                         [("executor.1", "interrupted", "2026-10-20T10:05:00Z", 299),
                          ("executor.1", "done", "2026-10-20T11:00:12Z", 10),
                          ("checks.1", "open", None, None)])
        killed = progress.timeline(lines[:2] + lines[3:5])  # the run died without run.end: no end is known
        self.assertEqual((killed[0]["status"], killed[0]["end"]), ("interrupted", None))

    def test_the_observer_lists_the_heaviest_blocks_by_role(self):
        err = self.finished()
        directory = self.run_dir(err)
        report = observer.build(directory, self.project)
        top = report["prompt_blocks_by_role"]
        self.assertEqual(sorted(top), ["context-scout", "executor", "reviewer"])
        for rows in top.values():
            self.assertLessEqual(len(rows), observer.TOP_BLOCKS)
            self.assertEqual([row["tokens"] for row in rows], sorted((row["tokens"] for row in rows), reverse=True))
        self.assertIn("## Prompt blocks", observer.markdown(report))
        self.assertIn("| executor | ", observer.markdown(report))

    def limit(self, **limits) -> None:
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": limits}}]}})

    def test_the_manifest_of_a_step_measures_the_classes_against_the_default_limits(self):
        folder = self.prompts_dir(self.finished())
        doc = json.loads((folder / "executor.1.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({name: row["limit"] for name, row in doc["budgets"].items()},
                         {"core": 12000, "supporting": 30000, "retrieval": 50000})
        self.assertEqual(sum(row["tokens"] for row in doc["budgets"].values()), sum(row["tokens"] for row in doc["blocks"]))
        self.assertEqual(contract.problems(doc, "prompt-manifest"), [])

    def test_a_class_past_its_limit_is_a_beacon_with_the_block_and_the_prompt_is_not_changed(self):
        self.limit(prompt_core_tokens=50, prompt_supporting_tokens=0)
        err = self.finished()
        beacons = [line for line in self.lines(err) if line.get("reason_code") == "BUDGET_OVER"]
        executor = [line for line in beacons if line.get("role") == "executor"]
        self.assertEqual(len(executor), 1, beacons)
        folder = self.prompts_dir(err)
        doc = json.loads((folder / "executor.1.manifest.json").read_text(encoding="utf-8"))
        heaviest = max((row for row in doc["blocks"] if prompts.budget_class(row["kind"]) == "core"),
                       key=lambda row: row["tokens"])
        self.assertEqual(executor[0]["message"], f"block {heaviest['kind']} {heaviest['origin']} {heaviest['tokens']}")
        self.assertEqual(doc["budgets"]["core"]["limit"], 50)
        text = (folder / "executor.1.md").read_text(encoding="utf-8")  # nothing is cut: the whole prompt is there
        self.assertEqual(sha256_hex(text.encode("utf-8")), doc["prompt_sha256"])
        self.assertEqual(text, self.prompt("executor", 1))
        self.assertIn("## Result", text)  # the last block, the result contract, is whole
        self.assertEqual(sum(row["tokens"] for row in doc["blocks"]) - doc["estimated_tokens"] <= len(doc["blocks"]), True)

    def test_a_limit_of_zero_gives_no_beacon(self):
        self.limit(prompt_core_tokens=0, prompt_supporting_tokens=0, prompt_retrieval_tokens=0)
        err = self.finished()
        self.assertEqual([line for line in self.lines(err) if line.get("reason_code") == "BUDGET_OVER"], [])

    def test_the_observer_sums_the_budgets_by_role(self):
        self.limit(prompt_core_tokens=50)
        directory = self.run_dir(self.finished())
        report = observer.build(directory, self.project)
        budgets = report["prompt_budgets_by_role"]
        self.assertEqual(sorted(budgets), ["context-scout", "executor", "reviewer"])
        core = budgets["executor"]["core"]
        self.assertEqual(core["limit"], 50)
        self.assertGreater(core["max_tokens"], 50)
        self.assertEqual((core["steps"], core["over"]), (1, 1))
        self.assertEqual(budgets["executor"]["retrieval"]["max_tokens"], 0)
        self.assertIn("## Prompt budgets", observer.markdown(report))
        self.assertTrue(any("prompt_core_tokens" in text for text in report["proposals"]), report["proposals"])

    def test_the_observer_has_no_budgets_for_a_manifest_without_them(self):
        directory = self.run_dir(self.finished())
        for file in (directory / "W1" / "prompts").glob("*.manifest.json"):
            doc = json.loads(file.read_text(encoding="utf-8"))
            doc.pop("budgets", None)
            file.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(observer.build(directory, self.project)["prompt_budgets_by_role"], {})

    def test_the_observer_skips_a_manifest_it_cannot_read(self):
        err = self.finished()
        directory = self.run_dir(err)
        (directory / "W1" / "prompts" / "executor.1.manifest.json").write_text("{", encoding="utf-8")
        self.assertNotIn("executor", observer.build(directory, self.project)["prompt_blocks_by_role"])


if __name__ == "__main__":
    unittest.main()
