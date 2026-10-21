#!/usr/bin/env python3
"""Worktree development commands, with temporary repositories, HOME and workspace CLI."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name("dev-worktree.sh")
MARKER = {"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "wsx",
          "project_id": "demo", "plans_store": "workspace"}


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="skm-worktree-test-")
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name).resolve()
        self.live = self.tmp / "live checkout"
        self.directory = self.tmp / "next checkout"
        home = self.tmp / "home"
        home.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("SKM_", "XDG_", "GIT_"))}
        self.log = self.tmp / "workspace.log"
        self.env.update(HOME=str(home), SKM_HOME=str(home / "skm"),
                        XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                        XDG_STATE_HOME=str(home / ".local/state"), XDG_CACHE_HOME=str(home / ".cache"),
                        CODEX_HOME=str(home / "codex"), GROK_HOME=str(home / "grok"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, FAKE_LOG=str(self.log))
        fake = self.tmp / "fake ws"
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_FAIL"):
    print("first line\\nFAKE_WS_FAILED: last line", file=sys.stderr)
    sys.exit(1)
if sys.argv[1:3] == ["project", "show"] and os.environ.get("FAKE_PRIMARY"):
    print(json.dumps({"binding": {"primary": os.environ["FAKE_PRIMARY"]}}))
else:
    print(json.dumps({"ok": True}))
''', encoding="utf-8")
        fake.chmod(0o755)
        self.env["SKM_DEV_WORKTREE_WORKSPACE_CLI"] = str(fake)
        self.live.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.live / ".swissknifeman").mkdir()
        (self.live / ".swissknifeman/project.json").write_text(json.dumps(MARKER), encoding="utf-8")
        (self.live / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self.commit(self.live)

    def git(self, *args, cwd=None):
        result = subprocess.run(["git", "-c", "user.name=Worktree Test", "-c", "user.email=worktree@example.test",
                                 *map(str, args)], cwd=cwd or self.live, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, cwd):
        self.git("add", ".", cwd=cwd)
        self.git("commit", "-qm", "fixture", cwd=cwd)

    def command(self, *args, cwd=None):
        return subprocess.run(["bash", str(SCRIPT), *map(str, args)], cwd=cwd or self.live,
                              env=self.env, capture_output=True, text=True)

    def create(self):
        result = self.command("create", "--path", self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def refusal(self, code, *args):
        result = self.command(*args)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(result.stderr.startswith(code + ": "), result.stderr)
        return result

    def test_create_and_repeat(self):
        result = self.create()
        self.assertTrue((self.directory / ".git").is_file())
        self.assertEqual(self.git("branch", "--show-current", cwd=self.directory), "stable/p1")
        self.assertIn("bind --path", result.stdout)
        self.assertIn("orch conduct --project", result.stdout)
        self.refusal("DEV_WORKTREE_EXISTS", "create", "--path", self.directory)

    def test_create_refuses_an_existing_branch(self):
        self.git("branch", "stable/p1")
        self.refusal("DEV_WORKTREE_BRANCH_EXISTS", "create", "--path", self.directory)
        self.assertFalse(self.directory.exists())

    def test_status_counts_commits_changes_and_untracked_files(self):
        self.create()
        (self.directory / "tracked.txt").write_text("committed\n", encoding="utf-8")
        self.commit(self.directory)
        (self.directory / "tracked.txt").write_text("modified\n", encoding="utf-8")
        (self.directory / "untracked.txt").write_text("untracked\n", encoding="utf-8")
        self.env["FAKE_PRIMARY"] = str(self.directory)
        result = self.command("status", "--path", self.directory, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(set(status), {"path", "branch", "head", "ahead", "behind", "changed", "untracked",
                                       "project", "primary", "bound"})
        self.assertEqual((status["ahead"], status["behind"], status["changed"], status["untracked"]), (1, 0, 1, 1))
        self.assertEqual((status["path"], status["branch"], status["project"]),
                         (str(self.directory), "stable/p1", "wsx/demo"))
        self.assertEqual(status["head"], self.git("rev-parse", "HEAD", cwd=self.directory))
        self.assertEqual(status["primary"], str(self.directory))
        self.assertIs(status["bound"], True)

    def test_bind_and_unbind_call_only_the_fake_workspace(self):
        self.create()
        for verb in ("bind", "unbind"):
            result = self.command(verb, "--path", self.directory)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line) for line in self.log.read_text().splitlines()], [
            ["project", "rebind", "demo", "--path", str(self.directory), "--json"],
            ["project", "attach", "--project", str(self.live), "--yes", "--json"],
            ["project", "rebind", "demo", "--path", str(self.live), "--json"]])

    def test_promote_check_prints_commands_without_merging(self):
        self.create()
        (self.directory / "tracked.txt").write_text("next\n", encoding="utf-8")
        self.commit(self.directory)
        before = self.git("rev-parse", "main")
        candidate = self.git("rev-parse", "stable/p1")
        result = self.command("promote-check", "--branch", "stable/p1", "--path", self.directory,
                              cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 2)
        promotion, doctor = result.stdout.splitlines()
        guard, merge = promotion.split(" && ", 1)
        guard_args = shlex.split(guard)
        self.assertEqual(guard_args[:1] + guard_args[2:], ["[", "=", "refs/heads/main", "]"])
        self.assertTrue(guard_args[1].startswith("$(") and guard_args[1].endswith(")"))
        self.assertEqual(shlex.split(guard_args[1][2:-1]),
                         ["git", "-C", str(self.live), "symbolic-ref", "--quiet", "HEAD"])
        self.assertEqual(shlex.split(merge), ["git", "-C", str(self.live), "merge", "--ff-only", "stable/p1"])
        self.assertEqual(doctor, "swissknifeman doctor")
        self.assertEqual(self.git("rev-parse", "main"), before)
        self.assertEqual(self.git("rev-parse", "stable/p1"), candidate)
        self.assertEqual(self.git("symbolic-ref", "HEAD"), "refs/heads/main")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("status", "--porcelain", cwd=self.directory), "")
        self.assertFalse(self.log.exists())

    def test_promote_check_refuses_other_live_branch_at_main(self):
        self.create()
        (self.directory / "tracked.txt").write_text("next\n", encoding="utf-8")
        self.commit(self.directory)
        self.git("switch", "-c", "hotfix", "main")
        before = self.git("show-ref", "--heads")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "main"))
        self.assertEqual(self.git("status", "--porcelain"), "")
        result = self.refusal("DEV_WORKTREE_LIVE_NOT_MAIN", "promote-check", "--branch", "stable/p1",
                              "--path", self.directory)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.git("symbolic-ref", "HEAD"), "refs/heads/hotfix")
        self.assertEqual(self.git("show-ref", "--heads"), before)
        self.assertFalse(self.log.exists())

    def test_promote_check_refuses_detached_live_head_at_main(self):
        self.create()
        (self.directory / "tracked.txt").write_text("next\n", encoding="utf-8")
        self.commit(self.directory)
        self.git("switch", "--detach", "main")
        before = self.git("show-ref", "--heads")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "main"))
        self.assertEqual(self.git("status", "--porcelain"), "")
        result = self.refusal("DEV_WORKTREE_LIVE_NOT_MAIN", "promote-check", "--branch", "stable/p1",
                              "--path", self.directory)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.git("branch", "--show-current"), "")
        self.assertEqual(self.git("show-ref", "--heads"), before)
        self.assertFalse(self.log.exists())

    def test_printed_promotion_refuses_if_live_leaves_main(self):
        self.create()
        (self.directory / "tracked.txt").write_text("next\n", encoding="utf-8")
        self.commit(self.directory)
        result = self.command("promote-check", "--branch", "stable/p1", "--path", self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        promotion = result.stdout.splitlines()[0]
        for args in (("switch", "-c", "hotfix", "main"), ("switch", "--detach", "main")):
            with self.subTest(args=args):
                self.git(*args)
                before = self.git("show-ref", "--heads")
                result = subprocess.run(["bash", "-c", promotion], cwd=self.directory, env=self.env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(self.git("show-ref", "--heads"), before)
        self.assertFalse(self.log.exists())

    def test_promote_check_refuses_divergent_main(self):
        self.create()
        (self.live / "tracked.txt").write_text("live commit\n", encoding="utf-8")
        self.commit(self.live)
        self.refusal("DEV_WORKTREE_NOT_FF", "promote-check", "--branch", "stable/p1", "--path", self.directory)

    def test_promote_check_refuses_dirty_live_tracked_files(self):
        self.create()
        (self.live / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        result = self.refusal("DEV_WORKTREE_LIVE_DIRTY", "promote-check", "--branch", "stable/p1",
                              "--path", self.directory)
        self.assertIn("tracked.txt", result.stderr)

    def test_missing_command_and_invalid_options_are_usage(self):
        for args in ((), ("unknown",), ("status", "--branch", "main"), ("create", "--path"),
                     ("bind", "--json"), ("promote-check",), ("create", "--branch", "")):
            with self.subTest(args=args):
                self.assertEqual(self.command(*args).returncode, 2)

    def test_promote_check_refuses_missing_branch_and_dirty_worktree(self):
        self.create()
        self.refusal("DEV_WORKTREE_NO_BRANCH", "promote-check", "--branch", "absent", "--path", self.directory)
        for name in ("tracked.txt", "untracked.txt"):
            with self.subTest(name=name):
                path = self.directory / name
                path.write_text("dirty\n", encoding="utf-8")
                self.refusal("DEV_WORKTREE_DIRTY", "promote-check", "--branch", "stable/p1", "--path", self.directory)
                if name == "tracked.txt":
                    path.write_text("initial\n", encoding="utf-8")

    def test_status_displays_workspace_failure_without_refusing(self):
        self.create()
        self.env["FAKE_FAIL"] = "1"
        result = self.command("status", "--path", self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("binding primary: unknown (FAKE_WS_FAILED)", result.stdout)
        self.assertIn("bound to worktree: no", result.stdout)
        self.refusal("DEV_WORKTREE_BIND_FAILED", "bind", "--path", self.directory)
        self.assertEqual(len(self.log.read_text().splitlines()), 2)  # show, then failed rebind; no attach

    def test_defaults_from_a_linked_worktree_and_explicit_ref(self):
        result = self.command("create", "--branch", "stable/p2", "--from", "HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)
        default = self.tmp / "swissknifeman-next"
        self.assertEqual(self.git("branch", "--show-current", cwd=default), "stable/p2")
        result = self.command("status", "--json", cwd=default)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["path"], str(default))

    def test_workspace_command_prefix_is_split_into_arguments(self):
        self.create()
        plain = self.tmp / "fakews"
        plain.write_text(Path(self.env["SKM_DEV_WORKTREE_WORKSPACE_CLI"]).read_text(), encoding="utf-8")
        self.env["SKM_DEV_WORKTREE_WORKSPACE_CLI"] = "python3 " + str(plain)
        result = self.command("bind", "--path", self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([call[:2] for call in calls], [["project", "rebind"], ["project", "attach"]])

    def test_status_handles_an_unavailable_workspace_cli(self):
        self.create()
        self.env["SKM_DEV_WORKTREE_WORKSPACE_CLI"] = str(self.tmp / "absent-cli")
        result = self.command("status", "--path", self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("binding primary: unknown (WORKSPACE_CLI_UNAVAILABLE)", result.stdout)

    def test_invalid_project_marker_is_refused_before_calling_workspace(self):
        self.create()
        marker = self.directory / ".swissknifeman/project.json"
        marker.write_text(json.dumps({**MARKER, "project_id": "../other"}), encoding="utf-8")
        self.refusal("DEV_WORKTREE_BIND_FAILED", "bind", "--path", self.directory)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
