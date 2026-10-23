"""Write-protected paths: the policy that names them, the executor rule and the escalation the journal keeps."""
from __future__ import annotations

import unittest
from unittest import mock

from orch.conductor import engine, progress, prompts
from orch.conductor.policies import protected_writes
from tests.test_conductor import ConductorCase, report

QUIET = ["claude", "-p", "--permission-prompts", "none"]


class PolicyTests(unittest.TestCase):
    def test_files_and_folders_at_any_depth(self):
        found = protected_writes.protected("claude-code", QUIET, [
            "pyrightconfig.json", ".claude/skills/**", "packages/x/.vscode/settings.json", "packages/x/pyrightconfig.json",
            ".mcp.json", ".git/hooks/post-commit"])
        self.assertEqual(found, sorted([
            "pyrightconfig.json", ".claude/skills/**", "packages/x/.vscode/settings.json", "packages/x/pyrightconfig.json",
            ".mcp.json", ".git/hooks/post-commit"]))

    def test_written_paths_are_not_protected(self):
        self.assertEqual(protected_writes.protected("claude-code", QUIET, [
            "CLAUDE.md", ".claude-plugin/marketplace.json", ".github/workflows/a.yml", "pyproject.toml",
            "configs/claude-code/settings.global.json", ".env.example", "docs/.claude.md"]), [])

    def test_a_session_with_prompts_or_another_provider_is_not_protected(self):
        self.assertEqual(protected_writes.protected("claude-code", ["claude", "-p"], ["pyrightconfig.json"]), [])
        self.assertEqual(protected_writes.protected("codex", QUIET, ["pyrightconfig.json"]), [])
        self.assertEqual(protected_writes.protected("claude-code", QUIET, None), [])


class RuleTests(unittest.TestCase):
    def test_the_rule_names_the_paths_the_staging_folder_and_the_code(self):
        text = prompts.protected_rule(["pyrightconfig.json"], ".swissknifeman/orch-artifacts/r/W1/protected")
        self.assertIn("`pyrightconfig.json`", text)
        self.assertIn("`.swissknifeman/orch-artifacts/r/W1/protected/<the same path>`", text)
        self.assertIn("WRITE_PROTECTED_PATH: <path> -> <staged path>", text)
        self.assertIn("do not write them through Bash", text)


class JournalTests(unittest.TestCase):
    def test_status_keeps_the_escalation_of_a_blocked_piece(self):
        lines = [{"ts": "2026-10-23T00:00:00Z", "run": "cnd-x", "event": "run.start"},
                 {"ts": "2026-10-23T00:00:01Z", "run": "cnd-x", "event": "item.end", "item": "W1", "outcome": "blocked",
                  "reason_code": "WRITE_PROTECTED_PATH", "message": "WRITE_PROTECTED_PATH: pyrightconfig.json -> x"},
                 {"ts": "2026-10-23T00:00:02Z", "run": "cnd-x", "event": "item.end", "item": "W2", "outcome": "done"}]
        rows = {row["item"]: row for row in progress.summarize(lines)["items"]}
        self.assertEqual(rows["W1"]["reason_code"], "WRITE_PROTECTED_PATH")
        self.assertEqual(rows["W1"]["escalation"], "WRITE_PROTECTED_PATH: pyrightconfig.json -> x")
        self.assertNotIn("escalation", rows["W2"])


class ConductTests(ConductorCase):
    def test_a_protected_path_is_said_before_the_scout_and_the_blocked_piece_shows_its_escalation(self):
        self.set_items({"W1": {"write_set": ["out/W1.txt", "pyrightconfig.json"]}})
        escalation = {"text": "WRITE_PROTECTED_PATH: pyrightconfig.json -> protected/pyrightconfig.json",
                      "kind": "escalation", "impact": "the gate is not effective", "next": "the owner places the file"}
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n"},
                                   "result": report("W1", "blocked", open_issues=[escalation])}]})
        with mock.patch.object(engine.Conductor, "_write_protected", lambda self, item: ["pyrightconfig.json"]):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        lines = self.lines(err)
        beacon = next(index for index, line in enumerate(lines) if line.get("reason_code") == "WRITE_PROTECTED_PATH")
        first_stage = next(index for index, line in enumerate(lines) if line["event"] == "stage.start"
                           and line.get("stage") in ("scout", "executor.1"))
        self.assertLess(beacon, first_stage)
        prompt = self.prompt("executor", 1)
        self.assertIn("## Protected paths", prompt)
        self.assertIn("`pyrightconfig.json`", prompt)
        end = next(line for line in lines if line["event"] == "item.end")
        self.assertEqual((end["outcome"], end["reason_code"]), ("blocked", "WRITE_PROTECTED_PATH"))
        self.assertIn("pyrightconfig.json -> protected/pyrightconfig.json", end["message"])
        code, out, _ = self.conduct("status", "--run", lines[0]["run"])
        self.assertEqual(code, 0)
        self.assertIn("W1: blocked (WRITE_PROTECTED_PATH)", out)
        self.assertIn("    escalation: WRITE_PROTECTED_PATH: pyrightconfig.json", out)


if __name__ == "__main__":
    unittest.main()
