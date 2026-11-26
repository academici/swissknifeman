"""git-guardrails shell hook blocks exactly the commands described by general/git-safety."""
import json
import subprocess
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "configs/claude-code/hooks/git-guardrails/block-dangerous-git.sh"

BLOCKED = (
    "git push origin main",
    "git push --force origin main",
    "git push --force-with-lease",
    "git reset --hard HEAD~1",
    "git clean -f",
    "git clean -fd",
    "git branch -D feature",
    "git checkout .",
    "git restore .",
    "git rebase --onto main a b",
)
# Audit 2026-10-17 §1.2 / §6.4: variants the literal patterns let through.
BYPASSES = (
    "git -C . push origin main",
    "git  push",
    "git clean -df",
    "git clean -xdf",
    "git branch --delete --force main",
    "git branch -df main",
    "git checkout -- .",
    "git checkout -f main",
    "git checkout HEAD -- .",
    "git reset --keep HEAD~3",
    "git reset --merge",
    "git stash clear",
    "git stash drop",
    "git reflog expire --expire=now --all",
    "git reflog delete HEAD@{1}",
    "git update-ref -d refs/heads/x",
    "git -c core.pager=cat push",
    "git --git-dir=/x/.git push",
    "git --no-pager push",
    "/usr/bin/git push",
    "cd /x && git -C y push --force",
    'bash -c "git push"',
    "sh -c 'git  reset --hard'",
    "echo ok; (git push)",
    "echo $(git push)",
    "env GIT_DIR=x git push",
    "sudo -u root git push",
    "xargs git push",
    "find . -exec git push {} ;",
    "git -c alias.p=push p",
    "git -c alias.x='!git push' x",
    "git filter-branch --all",
    "git push>log",
    "\\git push",
    "git push\ngit status",
)
ALLOWED = (
    "git status",
    "git log --oneline",
    "git commit -m 'x'",
    "git branch -d merged",
    "git checkout feature",
    "git restore file.txt",
    "ls -la",
    "git -C sub status",
    "git clean -n",
    "git clean -nfd",
    "git restore --staged .",
    "git stash",
    "git stash list",
    "git reflog",
    "git branch --delete merged",
    "git checkout -b new",
    "git -c core.pager=cat log",
    "echo git",
    "git log --grep=push",
)


def run_hook(command):
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True, text=True)


def _load_guard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("git_guard", HOOK.parent / "git_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitGuardArgvTest(unittest.TestCase):
    """The argv layer alone (no regex safety net) must catch the variants."""

    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guard()

    def test_bypass_variants_found_by_argv(self):
        for command in BYPASSES:
            with self.subTest(command=command):
                self.assertIsNotNone(self.guard.check(command.replace("\\n", "\n")))

    def test_safe_variants_not_flagged_by_argv(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(self.guard.check(command))

    def test_rule_ids_and_tiers(self):
        self.assertEqual(self.guard.check("git -C . push --force").id, "push-force")
        self.assertEqual(self.guard.check("git -C . push").id, "git-push")
        self.assertEqual(self.guard.check("git clean -xdf").tier, "critical")

    def test_lifecycle_core_uses_argv_layer(self):
        import sys
        sys.path.insert(0, str(HOOK.parents[4] / "lib"))
        from harness.lifecycle_git_guardrails_core import git_guardrails_verdict
        gate = git_guardrails_verdict("git -C . push origin main", mode="strict")
        self.assertEqual((gate.decision, gate.match.id), ("deny", "git-push"))
        self.assertEqual(git_guardrails_verdict("git -C . push", mode="warn").decision, "warn")
        self.assertEqual(git_guardrails_verdict("git -C . push", mode="off").decision, "allow")
        self.assertEqual(git_guardrails_verdict("git status", mode="strict").decision, "allow")


class GitGuardrailsHookTest(unittest.TestCase):
    def test_blocked_commands_exit_2_with_message(self):
        for command in BLOCKED:
            with self.subTest(command=command):
                result = run_hook(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("BLOCKED", result.stderr)

    def test_bypass_variants_exit_2(self):
        for command in BYPASSES:
            with self.subTest(command=command):
                self.assertEqual(run_hook(command.replace("\\n", "\n")).returncode, 2)

    def test_without_python_the_patterns_still_block(self):
        payload = json.dumps({"tool_input": {"command": "git  push"}})
        env = {"PATH": str(self._bin())}
        result = subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 2)

    def _bin(self):
        import shutil
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name in ("bash", "jq", "tr", "echo", "grep", "dirname", "cat"):
            found = shutil.which(name)
            if found:
                (Path(tmp.name) / name).symlink_to(found)
        return tmp.name

    def test_safe_commands_pass(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(run_hook(command).returncode, 0)


if __name__ == "__main__":
    unittest.main()
