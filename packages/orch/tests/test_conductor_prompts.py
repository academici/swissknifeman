"""The prompt builders as blocks (PLAN4 P9.1): the blocks add up to the prompt byte for byte, the prompt of every builder
equals the one captured before the builders were split into blocks (``tests/golden/conductor-prompts``), and the
manifest says where each part of a prompt came from."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from aicore.content.budget import estimate_tokens
from aicore.util.digest import sha256_hex

from orch.conductor import engine, observer, prompts
from tests.test_conductor import GREEN, ConductorCase, executor_ok

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden" / "conductor-prompts"
INPUTS = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input"
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

    def test_the_observer_lists_the_heaviest_blocks_by_role(self):
        err = self.finished()
        directory = self.run_dir(err)
        report = observer.build(directory, self.project)
        top = report["prompt_blocks_by_role"]
        self.assertEqual(sorted(top), ["context-scout", "executor", "reviewer"])
        for role, rows in top.items():
            self.assertLessEqual(len(rows), observer.TOP_BLOCKS)
            self.assertEqual([row["tokens"] for row in rows], sorted((row["tokens"] for row in rows), reverse=True))
        self.assertIn("## Prompt blocks", observer.markdown(report))
        self.assertIn("| executor | ", observer.markdown(report))

    def test_the_observer_skips_a_manifest_it_cannot_read(self):
        err = self.finished()
        directory = self.run_dir(err)
        (directory / "W1" / "prompts" / "executor.1.manifest.json").write_text("{", encoding="utf-8")
        self.assertNotIn("executor", observer.build(directory, self.project)["prompt_blocks_by_role"])


if __name__ == "__main__":
    unittest.main()
