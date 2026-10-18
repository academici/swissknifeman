"""Command logs of the hooks (audit 2026-10-17 §6.7): secrets masked, file mode 0600, one rotation."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "configs" / "claude-code" / "hooks"
LOG_HOOK = HOOKS / "log-bash-command.sh"
AUTO_APPROVE = HOOKS / "auto-approve" / "auto-approve.sh"
HAS_JQ = shutil.which("jq") is not None
SECRET_COMMAND = ('curl -H "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123" https://x; '
                  "export X_API_KEY='supersecretvalue1'; echo sk-abcdefghijklmnopqrstuvwx " + "ghp_" + "A" * 36)
LEAKS = ("abcdefghijklmnopqrstuvwxyz0123", "supersecretvalue1", "sk-abcdefghijklmnopqrstuvwx", "ghp_" + "A" * 36)


@unittest.skipUnless(HAS_JQ, "needs jq")
class HookLogs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.logs = self.home / ".claude" / "logs"

    def run_hook(self, script, payload, **extra):
        env = {**os.environ, "HOME": str(self.home), **extra}
        env.pop("CLAUDE_PROJECT_DIR", None)
        subprocess.run(["bash", str(script)], input=json.dumps(payload).encode(), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)

    def test_command_log_masks_secrets_and_is_private(self):
        self.run_hook(LOG_HOOK, {"cwd": "/x", "session_id": "s",
                                 "tool_input": {"command": SECRET_COMMAND, "description": "d"}})
        log = self.logs / "bash-commands.jsonl"
        text = log.read_text(encoding="utf-8")
        for leak in LEAKS:
            self.assertNotIn(leak, text)
        self.assertIn("‹redacted›", text)
        self.assertEqual(json.loads(text)["cwd"], "/x")
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.logs.stat().st_mode), 0o700)

    def test_command_log_rotates_once_past_the_limit(self):
        payload = {"cwd": "/x", "session_id": "s", "tool_input": {"command": "ls"}}
        for _ in range(3):
            self.run_hook(LOG_HOOK, payload, CLAUDE_LOG_MAX_BYTES="100")
        self.assertTrue((self.logs / "bash-commands.jsonl.1").is_file())
        self.assertLessEqual(len((self.logs / "bash-commands.jsonl").read_text().splitlines()), 2)

    def test_decision_log_masks_secrets_and_is_private(self):
        hook_dir = self.home / "hook"
        shutil.copytree(AUTO_APPROVE.parent, hook_dir, ignore=shutil.ignore_patterns("__pycache__"))
        (hook_dir / "env.ini").write_text("MODE=strict\n", encoding="utf-8")
        self.run_hook(hook_dir / "auto-approve.sh", {"tool_name": "Bash", "tool_input": {"command": SECRET_COMMAND}})
        log = self.logs / "auto-approve-decisions.jsonl"
        text = log.read_text(encoding="utf-8")
        for leak in LEAKS:
            self.assertNotIn(leak, text)
        self.assertIn("‹redacted›", text)
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
