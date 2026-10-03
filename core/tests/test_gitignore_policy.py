"""Gitignore policy: shipped map is valid and the checker reports real drift."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from core import gitignore_policy as gp


def git(root, *args):
    # `-f` on add: a user-global excludes file must not decide what the fixture can track.
    args = (*args[:1], "-f", *args[1:]) if args[0] == "add" else args
    subprocess.run(("git", "-C", str(root), "-c", f"core.excludesFile={os.devnull}", *args),
                   check=True, capture_output=True, env=gp._ENV)


class PolicyFileTests(unittest.TestCase):
    def test_shipped_policy_is_valid_and_covers_the_known_service_files(self):
        policy = gp.load_policy()
        paths = {p for entry in policy["entries"] for p in entry["paths"]}
        for expected in (".mcp.json", ".mcp.json.example", ".claude/settings.local.json", "CLAUDE.md",
                         "skills-lock.json", ".claude/skills/", ".swissknifeman/backups/",
                         ".grok/config.toml", ".grok/config.toml.example", ".grok/hooks/",
                         ".grok/review-gate.state.json", ".grok/lsp.json", ".grok/plugins/"):
            self.assertIn(expected, paths)

    def test_glob_translation(self):
        self.assertTrue(gp._regex(".claude/**/*.bak").match(".claude/x.bak"))
        self.assertTrue(gp._regex(".claude/**/*.bak").match(".claude/a/b/x.bak"))
        self.assertFalse(gp._regex(".claude/**/*.bak").match(".claude/x.txt"))
        self.assertTrue(gp._regex(".cursor/*.env.ini").match(".cursor/memory.env.ini"))
        self.assertFalse(gp._regex(".cursor/*.env.ini").match(".cursor/a/memory.env.ini"))
        self.assertTrue(gp._regex(".claude/runs/").match(".claude/runs/2026/x.json"))

    def test_invalid_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text('{"schema_version": "gitignore-policy/v1", "entries": [{"id": "x", "policy": "bogus", "paths": ["a"]}]}')
            with self.assertRaises(gp.PolicyError):
                gp.load_policy(path)


class CheckProjectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        git(self.root, "init", "-q")
        self.policy = gp.load_policy()

    def write(self, relative, text="x"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def codes(self):
        return {(f["code"], f["path"]) for f in gp.check_project(self.root, self.policy)}

    def test_clean_project_has_no_findings(self):
        self.write(".gitignore", ".claude/settings.local.json\n")
        self.write(".claude/settings.local.json")
        self.write("CLAUDE.md")
        git(self.root, "add", "CLAUDE.md", ".gitignore")
        self.assertEqual(gp.check_project(self.root, self.policy), [])

    def test_ignore_policy_reports_tracked_and_unignored(self):
        self.write(".claude/settings.local.json")
        self.write(".claude/runs/1.json")
        git(self.root, "add", ".claude/settings.local.json")
        codes = self.codes()
        self.assertIn(("tracked-must-be-ignored", ".claude/settings.local.json"), codes)
        self.assertIn(("unignored", ".claude/runs/1.json"), codes)

    def test_portable_or_ignore_flags_only_machine_specific_content(self):
        self.write(".mcp.json", '{"command": "${MAIND_BIN:-maind}"}')
        git(self.root, "add", ".mcp.json")
        self.assertFalse([c for c in self.codes() if c[1] == ".mcp.json"])
        self.write(".cursor/mcp.json", '{"command": "/home/dev/bin/maind"}')
        self.assertIn(("unignored-machine-specific", ".cursor/mcp.json"), self.codes())
        git(self.root, "add", ".cursor/mcp.json")
        self.assertIn(("tracked-machine-specific", ".cursor/mcp.json"), self.codes())

    def test_commit_policy_reports_ignored_and_uncommitted(self):
        self.write(".gitignore", ".mcp.json.example\n")
        self.write(".mcp.json.example")
        self.write("skills-lock.json")
        codes = self.codes()
        self.assertIn(("ignored-must-be-committed", ".mcp.json.example"), codes)
        self.assertIn(("not-committed-yet", "skills-lock.json"), codes)

    def test_skills_and_instructions_must_be_committed(self):
        self.write(".gitignore", ".claude/skills/\n")
        self.write(".claude/skills/a/SKILL.md")
        self.write("CLAUDE.md")
        codes = self.codes()
        self.assertIn(("ignored-must-be-committed", ".claude/skills"), codes)
        self.assertIn(("not-committed-yet", "CLAUDE.md"), codes)

    def test_ini_is_ignored_only_when_it_holds_machine_paths(self):
        self.write(".claude/memory.env.ini", "MODE=observe\n")
        git(self.root, "add", ".claude/memory.env.ini")
        self.assertFalse([c for c in self.codes() if c[1] == ".claude/memory.env.ini"])
        self.write(".claude/run-report.env.ini", "LOG_DIR=/home/dev/logs\n")
        self.assertIn(("unignored-machine-specific", ".claude/run-report.env.ini"), self.codes())
        git(self.root, "add", ".claude/run-report.env.ini")
        self.assertIn(("tracked-machine-specific", ".claude/run-report.env.ini"), self.codes())

    def test_project_choice_is_not_drift_but_mixing_inside_a_group_is(self):
        self.write(".serena/project.yml")
        self.write(".serena/memories/m.md")
        self.assertEqual(self.codes(), set())  # both untracked: consistent, project's call
        self.write(".gitignore", ".serena/memories/\n")
        git(self.root, "add", ".serena/project.yml", ".gitignore")
        self.assertIn(("mixed-group-state", "serena"), self.codes())

    def test_recommended_block_lists_ignore_patterns(self):
        self.write(".claude/runs/1.json")
        self.write("x.bak")
        block = gp.recommended_block(gp.check_project(self.root, self.policy), self.policy)
        self.assertEqual(block, [".claude/runs/"])

    def test_user_global_excludes_do_not_count_as_protection(self):
        # A repo-local .git/info/exclude hides the file locally only; the policy still flags it.
        (self.root / ".git" / "info").mkdir(exist_ok=True)
        (self.root / ".git" / "info" / "exclude").write_text(".claude/runs/\n")
        self.write(".claude/runs/1.json")
        self.assertIn(("unignored", ".claude/runs/1.json"), self.codes())

    def test_non_git_directory_is_a_single_info_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = gp.check_project(tmp, self.policy)
        self.assertEqual([f["code"] for f in findings], ["not-a-git-worktree"])

    def test_apply_appends_machine_grok_config_and_leaves_shared_files(self):
        self.write(".grok/config.toml", 'command = "/home/dev/bin/maind"\n')
        self.write(".grok/hooks/lifecycle.py", "print('hook')\n")
        self.write(".grok/config.toml.example", "command = \"${MAIND_BIN:-maind}\"\n")
        self.write(".gitignore", ".grok/config.toml.example\n")
        first = gp.apply_recommendations(self.root, self.policy)
        self.assertEqual(first["added"], [".grok/config.toml"])
        lines = (self.root / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [".grok/config.toml.example", ".grok/config.toml"])
        second = gp.apply_recommendations(self.root, self.policy)
        self.assertEqual(second["added"], [])
        self.assertEqual((self.root / ".gitignore").read_text(encoding="utf-8").splitlines(), lines)

    def test_apply_ignores_runtime_state_and_keeps_a_portable_config(self):
        self.write(".grok/review-gate.state.json", "{}\n")
        self.write(".grok/config.toml", 'command = "${MAIND_BIN:-maind}"\n')
        outcome = gp.apply_recommendations(self.root, self.policy)
        self.assertEqual(outcome["added"], [".grok/review-gate.state.json"])
        self.assertNotIn(".grok/config.toml", (self.root / ".gitignore").read_text(encoding="utf-8"))

    def test_apply_dry_run_and_non_worktree_write_nothing(self):
        self.write(".grok/state/session.json", "{}\n")
        dry = gp.apply_recommendations(self.root, self.policy, dry=True)
        self.assertEqual(dry["added"], [".grok/state/"])
        self.assertFalse((self.root / ".gitignore").exists())
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".grok").mkdir()
            (Path(tmp) / ".grok" / "config.toml").write_text('command = "/home/dev/bin/maind"\n')
            skipped = gp.apply_recommendations(tmp, self.policy)
            self.assertEqual(skipped["status"], "skip")
            self.assertFalse((Path(tmp) / ".gitignore").exists())

    def test_apply_keeps_a_tracked_machine_file_in_the_index(self):
        self.write(".grok/config.toml", 'command = "/home/dev/bin/maind"\n')
        git(self.root, "add", ".grok/config.toml")
        outcome = gp.apply_recommendations(self.root, self.policy)
        self.assertEqual(outcome["added"], [".grok/config.toml"])
        self.assertEqual(outcome["tracked"], [".grok/config.toml"])
        tracked = subprocess.run(("git", "-C", str(self.root), "ls-files", "--", ".grok/config.toml"),
                                 check=True, capture_output=True, text=True).stdout
        self.assertIn(".grok/config.toml", tracked)


if __name__ == "__main__":
    unittest.main()
