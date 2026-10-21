"""Agent runs of a conductor run (P6.2): a folder per start of a role, with its request, result, usage and lineage."""
from __future__ import annotations

import json
import sys
import unittest

from orch.conductor import agents, contract, observer
from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report


class AgentRunTests(ConductorCase):
    def agent_dirs(self, err: str) -> dict:
        folder = self.run_dir(err) / "W1" / agents.AGENTS
        return {path.name: {name: json.loads((path / name).read_text()) for name in ("request.json", "result.json", "usage.json")}
                for path in sorted(folder.iterdir())}

    def test_every_role_start_has_a_folder_with_request_result_and_usage(self):
        self.script({"executor": [dict(executor_ok("W1"), usage={"input_tokens": 700, "output_tokens": 70,
                                                                     "cache_read_input_tokens": 5})],
                     "reviewer": [dict(GREEN, usage={"input_tokens": 300, "output_tokens": 30})]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        found = self.agent_dirs(err)
        suffix = self.run_dir(err).name[4:]
        self.assertEqual(list(found), [f"agent-{suffix}-{n}" for n in range(1, len(found) + 1)])
        by_step = {doc["request.json"]["step"]: doc for doc in found.values()}
        self.assertTrue({"scout", "executor.1", "review.1"} <= set(by_step), sorted(by_step))
        executor = by_step["executor.1"]
        self.assertEqual((executor["request.json"]["role"], executor["request.json"]["causation"],
                          executor["request.json"]["attempt"]), ("executor", "executor.1", 1))
        self.assertTrue(executor["request.json"]["prompt"].endswith("W1/prompts/executor.1.md"))
        self.assertTrue((self.project / executor["request.json"]["prompt"]).is_file())
        self.assertNotIn("parent_agent_run_id", executor["request.json"])
        self.assertEqual((executor["result.json"]["exit"], executor["result.json"]["decisions"]), (0, []))
        self.assertTrue((self.project / executor["result.json"]["stream"]).is_file())
        self.assertEqual(executor["usage.json"], {"input": 700, "cached": 5, "output": 70, "usage_complete": True})
        self.assertEqual(by_step["review.1"]["usage.json"],
                         {"input": 300, "cached": 0, "output": 30, "usage_complete": True})
        # the tokens of the agent runs are the tokens of the piece
        state = self.state(err)["items"]["W1"]["tokens"]
        self.assertEqual((sum(doc["usage.json"]["input"] for doc in found.values()),
                          sum(doc["usage.json"]["output"] for doc in found.values())), (state["input"], state["output"]))

    def test_progress_lines_name_the_agent_and_stay_inside_the_contract(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        ids = set(self.agent_dirs(err))
        ended = [line for line in self.lines(err) if line["event"] == "stage.end" and line.get("agent")]
        self.assertTrue({"executor.1", "review.1"} <= {line["stage"] for line in ended})
        self.assertTrue({line["agent"] for line in ended} <= ids)
        for line in ended:
            self.assertEqual(contract.problems(line, "progress-line"), [], line)

    def test_status_lists_the_agents_of_the_current_item_and_the_observer_the_tokens_by_agent(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        code, out, _ = self.conduct("status", "--json")
        self.assertEqual(code, 0)
        listed = json.loads(out)["agents"]
        self.assertEqual({row["agent_run_id"] for row in listed}, set(self.agent_dirs(err)))
        self.assertTrue(all(row["status"] == "ok" for row in listed), listed)
        self.assertEqual(next(row for row in listed if row["step"] == "executor.1")["tokens"]["input"], 100)
        code, text, _ = self.conduct("status")
        self.assertIn("agent agent-", text)
        built = observer.build(self.run_dir(err), self.project)
        self.assertEqual({row["agent_run_id"] for row in built["tokens_by_agent"]}, set(self.agent_dirs(err)))
        self.assertIn("## Agent runs", observer.markdown(built))

    def test_the_report_fixer_names_the_role_it_mended_as_its_parent(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES + ("report-fixer",)})
        broken = {"write": {"out/W1.txt": "ok\n"}, "result": report("W1", changed_paths=["out/W1.txt", "out/W1.txt"])}
        self.script({"executor": [broken], "reviewer": [GREEN],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        found = self.agent_dirs(err)
        fixer = next(doc for doc in found.values() if doc["request.json"]["role"] == "report-fixer")
        executor = next(doc for doc in found.values() if doc["request.json"]["role"] == "executor")
        self.assertEqual(fixer["request.json"]["parent_agent_run_id"], executor["request.json"]["agent_run_id"])
        self.assertEqual(fixer["request.json"]["step"], "executor.1")
        self.assertTrue(fixer["request.json"]["prompt"].endswith("executor.1-fix1.md"))
        self.assertEqual(fixer["usage.json"]["input"], 100)
        self.assertEqual(executor["usage.json"]["input"], 100)  # the fixer's tokens are not the executor's

    def test_a_role_that_fails_at_the_provider_still_leaves_its_result(self):
        self.script({"executor": [{"is_error": True, "text": "boom", "api_error_status": 401, "exit": 1}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        executor = [doc for doc in self.agent_dirs(err).values() if doc["request.json"]["role"] == "executor"]
        self.assertTrue(executor)
        self.assertTrue(all("result.json" in doc and doc["result.json"].get("error") for doc in executor), executor)

    def test_a_provider_failure_that_a_repeat_overcame_is_not_an_error_of_the_agent_run(self):  # review F1
        self.script({"executor": [{"exit": 1, "stderr": "something odd"}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        executor = next(doc for doc in self.agent_dirs(err).values() if doc["request.json"]["role"] == "executor")
        self.assertEqual(executor["result.json"]["exit"], 0)
        self.assertNotIn("error", executor["result.json"])
        self.assertTrue(executor["result.json"]["decisions"])  # the repeat itself stays recorded
        listed = json.loads(self.conduct("status", "--json")[1])["agents"]
        self.assertTrue(all(row["status"] == "ok" for row in listed), listed)

    def test_the_counter_is_kept_in_the_state_and_the_id_follows_the_run(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        before = self.state(err)["agents"]
        self.assertEqual(before, len(self.agent_dirs(err)))
        self.assertEqual(agents.agent_id("cnd-x", 4), "agent-x-4")


class SilentDenialTests(ConductorCase):
    DENIED = [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "make secret"}},
              {"tool_name": "Bash", "tool_use_id": "t2", "tool_input": {}},
              {"tool_name": "WebFetch", "tool_use_id": "t3", "tool_input": {}}]

    def test_denied_tools_are_a_beacon_and_a_note_in_the_report_of_the_executor(self):
        self.script({"executor": [dict(executor_ok("W1"), permission_denials=self.DENIED)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        beacons = [line for line in self.lines(err) if line.get("reason_code") == "RESULT_SILENT_DENIAL"]
        self.assertEqual([(line["stage"], line["role"]) for line in beacons], [("executor.1", "executor")])
        self.assertIn("Bash×2, WebFetch", beacons[0]["message"])
        self.assertNotIn("secret", json.dumps(beacons))
        notes = [issue for issue in self.source()["items"]["W1"]["report"]["open_issues"]
                 if issue["text"].startswith("tools denied without a prompt")]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "tools denied without a prompt: Bash×2, WebFetch")
        self.assertEqual((notes[0]["kind"], notes[0]["impact"]), ("note", "the role could not use them"))
        self.assertIn("allowedTools", notes[0]["next"])
        self.assertNotIn("secret", json.dumps(self.source()))

    def test_a_reviewer_denial_is_a_beacon_only(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [dict(GREEN, permission_denials=self.DENIED[:1])]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        beacons = [line for line in self.lines(err) if line.get("reason_code") == "RESULT_SILENT_DENIAL"]
        self.assertEqual([line["role"] for line in beacons], ["reviewer"])
        issues = self.source()["items"]["W1"]["report"]["open_issues"]
        self.assertFalse([issue for issue in issues if "denied" in issue["text"]])

    def test_no_denials_no_beacon_no_note(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "RESULT_SILENT_DENIAL"])
        self.assertEqual(self.source()["items"]["W1"]["report"]["open_issues"], [])


if __name__ == "__main__":
    unittest.main()
