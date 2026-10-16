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
ALLOWED = (
    "git status",
    "git log --oneline",
    "git commit -m 'x'",
    "git branch -d merged",
    "git checkout feature",
    "git restore file.txt",
    "ls -la",
)


def run_hook(command):
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True, text=True)


class GitGuardrailsHookTest(unittest.TestCase):
    def test_blocked_commands_exit_2_with_message(self):
        for command in BLOCKED:
            with self.subTest(command=command):
                result = run_hook(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("BLOCKED", result.stderr)

    def test_safe_commands_pass(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(run_hook(command).returncode, 0)


if __name__ == "__main__":
    unittest.main()
