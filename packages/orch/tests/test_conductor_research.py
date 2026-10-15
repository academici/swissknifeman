"""The research stage (P10.2): the researcher role asks the configured sources through ``orch.py research query``, answers
a closed research-result, and the result is saved where the work source keeps research. The source is a fake command
(tests/fixtures/research/fake_command.py), the researcher a fake role that runs the command of its prompt."""
from __future__ import annotations

import json
import sys
import unittest

from orch import contracts, launch, render, worksource
from orch.worksource_file import FileWorkSource
from orch.conductor import contract
from tests.test_conductor import ConductorCase, GREEN, ROLES, FIXTURES, executor_ok
from tests.test_conductor_input import EXECUTOR, InputCase

RESEARCH = FIXTURES.parent / "research"
SOURCE = ('[orch.research]\npolicy = "required"\n\n[orch.research.sources.fake]\nkind = "command"\n'
          f'argv = {json.dumps([sys.executable, str(RESEARCH / "fake_command.py")])}\norder = 1\n')
RESEARCHER = {"research": "fake"}
URL = "https://example.org/c"


class ResearchCase(ConductorCase):
    def setUp(self):
        super().setUp()
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")},
                          extra=SOURCE)

    def stages(self, err: str) -> list:
        return [(line["event"], line.get("stage")) for line in self.lines(err) if line["event"].startswith("stage.")]


class PlanBoundResearchTests(ResearchCase):
    def test_the_researcher_asks_the_fake_source_and_the_result_is_saved_in_the_plan(self):
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual((self.calls("researcher"), self.calls("executor")), (1, 1))
        stages = self.stages(err)
        for key in ("research.1", "research-save.1"):
            self.assertIn(("stage.end", key), stages)
        self.assertLess(stages.index(("stage.end", "research.1")), stages.index(("stage.start", "executor.1")))
        saved = json.loads((self.project / "plans/T/research/W1-1.json").read_text())
        self.assertEqual(contract.problems(saved, "research-result"), [])
        self.assertEqual(saved["sources_used"], ["fake"])
        (claim,) = saved["claims"]
        self.assertEqual(claim["sources"], [URL])
        self.assertTrue(claim["text"].startswith("command answer: Research for this work:"))
        self.assertEqual(self.source()["research"], [{"ref": "W1", "number": 1, "path": "plans/T/research/W1-1.json"}])
        self.assertIn("plans/T/research/W1-1.json", self.git("ls-files").split())  # the commit of the piece took the file
        self.assertIn("plans/T/research/W1-1.json", self.source()["commits"][0]["paths"])

    def test_the_prompt_names_the_question_the_allowed_sources_and_the_one_command(self):
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        self.run_items("W1")
        prompt = self.prompt("researcher", 1)
        self.assertIn("## Research question", prompt)
        self.assertIn("Research for this work: Create the output of W1.", prompt)
        self.assertIn("## Allowed sources\n\nAsk only these sources, by id:\n\n- `fake`", prompt)
        self.assertRegex(prompt, r"```sh\npython3 \S+/scripts/orch\.py research query --source fake --query-file \S+\n```")
        self.assertIn("```research-result", prompt)
        self.assertIn("[orch]", prompt)  # the progress lines

    def test_the_step_records_the_role_its_route_and_the_result(self):
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        step = self.state(err)["items"]["W1"]["steps"]["research.1"]
        self.assertEqual(step["role"], "researcher")
        self.assertTrue(step["route"].startswith("claude-code/"), step["route"])
        self.assertEqual(step["result"]["result"]["sources_used"], ["fake"])
        self.assertEqual(step["verdict"], "1 claim(s), 0 unknown(s)")

    def test_a_source_that_refuses_research_leaves_the_result_in_the_artifacts_of_the_piece(self):
        self.set_items({"W1": {}}, refuse=["research"])
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        kept = json.loads((self.project / "plans/T/artifacts/W1/research-1.json").read_text())
        self.assertEqual(kept["claims"][0]["sources"], [URL])
        self.assertFalse((self.project / "plans/T/research").exists())
        self.assertIn("RESEARCH_NOT_SAVED", [line.get("reason_code") for line in self.lines(err)])
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["research-save.1"]["result"]["outcome"], "kept")

    def test_a_blocked_executor_still_leaves_one_research_round_behind(self):
        self.script({"researcher": [RESEARCHER], "executor": [{"result": {**executor_ok("W1")["result"], "status": "blocked",
                     "open_issues": [{"text": "needs the owner", "kind": "escalation", "impact": "x", "next": "y"}]}}],
                     "reviewer": [GREEN]})
        self.run_items("W1")
        self.assertEqual(self.calls("researcher"), 1)
        self.assertEqual(self.source()["research"][0]["number"], 1)

    def test_the_default_policy_adds_no_research_stage(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("researcher")), (0, 0), err)
        self.assertNotIn("research.1", [stage for _, stage in self.stages(err)])
        self.assertNotIn("research", self.source())

    def test_the_policy_off_adds_no_research_stage(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")},
                          extra=SOURCE.replace('policy = "required"', 'policy = "off"'))
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("researcher")), (0, 0), err)

    def test_a_required_policy_without_a_source_stops_before_any_work(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")},
                          extra='[orch.research]\npolicy = "required"\n')
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "RESEARCH_NO_SOURCES")), err)
        self.assertEqual((self.calls("researcher"), self.calls("executor")), (0, 0))

    def test_a_claim_without_a_source_is_refused_by_the_contract(self):
        self.script({"researcher": [{"result": {"query": "q", "claims": [{"text": "from memory", "sources": []}],
                                               "contradictions": [], "unknowns": [], "sources_used": ["fake"]},
                                     "tag": "research-result"}],
                     "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.calls("executor"), 0)
        self.assertIn("ROLE_OUTPUT_INVALID", err)


class ConditionalPolicyTests(ResearchCase):
    """PLAN4 P10.3 (knowledge/p10-research#triggers): the research need is the designer's decision, carried by the input."""

    def configure(self, policy: str) -> None:
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")},
                          extra=SOURCE.replace('policy = "required"', f'policy = "{policy}"'))

    def run_with(self, need: str, policy: str = "conditional") -> tuple:
        self.configure(policy)
        self.set_items({"W1": {"research": {"need": need, "notes": "what the flag does"}}})
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def test_need_none_adds_no_stage_under_conditional(self):
        err = self.run_with("none")
        self.assertEqual(self.calls("researcher"), 0)
        self.assertNotIn("research.1", [stage for _, stage in self.stages(err)])

    def test_need_optional_adds_no_stage_under_conditional(self):
        self.run_with("optional")
        self.assertEqual(self.calls("researcher"), 0)

    def test_need_required_adds_the_stage_before_the_executor_under_conditional(self):
        err = self.run_with("required")
        self.assertEqual((self.calls("researcher"), self.calls("executor")), (1, 1))
        stages = self.stages(err)
        self.assertLess(stages.index(("stage.end", "research.1")), stages.index(("stage.start", "executor.1")))
        self.assertIn("plans/T/research/W1-1.json", self.git("ls-files").split())

    def test_the_default_policy_is_conditional(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")},
                          extra=SOURCE.replace('policy = "required"\n', ""))
        self.set_items({"W1": {"research": {"need": "required"}}})
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("researcher")), (0, 1), err)

    def test_the_policy_off_never_researches(self):
        self.run_with("required", "off")
        self.assertEqual(self.calls("researcher"), 0)

    def test_the_policy_required_researches_a_piece_whose_need_is_none(self):
        self.run_with("none", "required")
        self.assertEqual(self.calls("researcher"), 1)

    def test_a_required_need_without_a_source_stops_before_any_work(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")})
        self.set_items({"W1": {"research": {"need": "required"}}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "RESEARCH_NO_SOURCES")), err)
        self.assertEqual(self.calls("executor"), 0)


class ExecutorBlockTests(ResearchCase):
    def test_the_executor_prompt_carries_the_result_as_a_research_block(self):
        self.script({"researcher": [RESEARCHER], "executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        prompt = self.prompt("executor", 1)
        self.assertIn("## Research", prompt)
        self.assertIn(URL, prompt)
        self.assertIn("command answer: Research for this work:", prompt)
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").read_text())
        (row,) = [row for row in manifest["blocks"] if row["kind"] == "research"]
        self.assertTrue(row["origin"].startswith("research-result:"), row["origin"])

    def test_a_piece_without_research_has_no_block(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        self.run_items("W1")
        self.assertNotIn("## Research", self.prompt("executor", 1))


class ContractTests(unittest.TestCase):
    def doc(self, **fields) -> dict:
        return {"query": "q", "claims": [{"text": "t", "sources": ["u"]}], "contradictions": [], "unknowns": [],
                "sources_used": ["fake"], **fields}

    def test_a_source_the_role_was_not_given_is_refused(self):
        self.assertEqual(contract.research_problems(["fake"], self.doc()), [])
        (issue,) = contract.research_problems(["fake"], self.doc(sources_used=["fake", "other"]))
        self.assertIn("other is not an allowed source", issue)

    def test_claims_need_a_source_that_was_asked(self):
        (issue,) = contract.research_problems(["fake"], self.doc(sources_used=[]))
        self.assertIn("no source was asked", issue)
        self.assertEqual(contract.research_problems(["fake"], self.doc(claims=[], sources_used=[])), [])

    def test_the_researcher_is_launched_with_one_command_and_no_editing_tool(self):
        catalog = launch.load_catalog()
        argv = launch.build_argv(catalog, "researcher", "claude-code", model="sonnet")
        self.assertEqual(argv[argv.index("--tools") + 1], "Bash,Read,Grep,Glob")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Bash(python3 *orch.py research query *)")
        self.assertNotIn("Edit", argv[argv.index("--tools") + 1])
        self.assertEqual(sorted(catalog["launch"]["researcher"]), ["claude-code"])  # no codex route: no network in its sandbox
        self.assertEqual(launch.entry(catalog, "researcher", "claude-code")["model_class"], "implementation")


class ResearcherRoleTests(unittest.TestCase):
    def test_the_researcher_reads_asks_and_never_writes(self):
        manifest, text = render.load_role("researcher")
        self.assertEqual(contracts.validate(manifest, "role-manifest"), [])
        self.assertEqual((manifest["write_authority"], manifest["result_shape"], manifest["model_class_min"]),
                         ("none", "research-result", "implementation"))
        self.assertEqual(manifest["tools"], {"filesystem": "read", "shell": "read_only", "network": "allowed", "plan_api": "none"})
        self.assertIn("Put every statement without a source", text)
        self.assertIn("Invent a source", text)
        self.assertIn("research query", text)


class WorkSourceTests(unittest.TestCase):
    def request(self, **fields) -> dict:
        return {"op": "research", "plan": "T", "ref": "W1", "run_id": "run-1", "number": 1, "result": {"query": "q"}, **fields}

    def test_the_research_operation_is_part_of_the_contract(self):
        self.assertIn("research", worksource.OPS)
        self.assertEqual(worksource.problems(self.request(), "input"), [])
        self.assertEqual(worksource.problems({"op": "research", "outcome": "recorded", "path": "plans/T/research/W1-1.json"},
                                             "output"), [])
        self.assertNotEqual(worksource.problems(self.request(number="1"), "input"), [])
        self.assertNotEqual(worksource.problems(self.request(extra=1), "input"), [])
        self.assertNotEqual(worksource.problems({"op": "research", "outcome": "done"}, "output"), [])


class FileInputResearchTests(InputCase):
    def test_an_input_run_keeps_the_research_result_next_to_its_stage_report(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "researcher")},
                          extra=SOURCE)
        path = self.write_input()
        self.script({"researcher": [RESEARCHER], "executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        saved = json.loads((self.artifacts(err) / "research-1.json").read_text())
        self.assertEqual(contract.problems(saved, "research-result"), [])
        self.assertEqual(saved["claims"][0]["sources"], [URL])
        self.assertEqual(self.source().get("research"), None)  # the plan source is not asked for a file input
        self.assertTrue((self.artifacts(err) / "stage-report.json").is_file())

    def test_the_file_source_records_a_result_once(self):
        path = self.write_input()
        source = FileWorkSource(path, project=self.project)
        fields = {"plan": str(path), "ref": self.input_doc["input_id"], "run_id": "run-1", "number": 2, "result": {"query": "q"}}
        first = source.research(**fields)
        self.assertEqual(first["outcome"], "recorded")
        self.assertTrue(first["path"].endswith(f"{self.input_doc['input_id']}/research-2.json"))
        self.assertEqual(json.loads((self.project / first["path"]).read_text()), {"query": "q"})
        self.assertEqual(source.research(**fields)["outcome"], "no-op")


if __name__ == "__main__":
    unittest.main()
