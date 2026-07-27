"""review-gate: поведенческий прогон SubagentStop-хука через subprocess (tmp
git-репо + tmp копия HOOK_DIR — конфиг/состояние изолированы от машины). Ровно
три кейса (P9.1 Validation §2): синтетическое нарушение (`generated-assets`)
ловится с `file:line` в `strict`; чистый дифф проходит без вывода; третье
подряд strict-срабатывание ТОЙ ЖЕ проверки в одной сессии+агенте понижает
режим до `warn` (счётчик диспетчера `checks/run-checks.sh`)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
RG_SRC = PKG / "configs" / "claude-code" / "hooks" / "review-gate"


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _init_repo(root):
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "review-gate-test@example.invalid"], root)
    _run(["git", "config", "user.name", "review-gate-test"], root)
    (root / "README.md").write_text("base\n")
    _run(["git", "add", "."], root)
    _run(["git", "commit", "-q", "-m", "base"], root)


def _hookdir(tmp, state_dir, mode="strict"):
    """Tmp-копия HOOK_DIR (review-gate.sh резолвит его от собственного пути) —
    правки config.json/env.ini не трогают реальный ~/.claude/hooks машины."""
    dst = tmp / "hookdir"
    shutil.copytree(RG_SRC, dst)
    (dst / "env.ini").write_text("MODE=strict\n")
    (dst / "config.json").write_text(json.dumps({
        "version": 2,
        "check_command": "$REVIEW_GATE_DIR/checks/run-checks.sh",
        "checks": [{"name": "generated-assets", "mode": mode}],
    }))
    (dst / "review-gate.sh").chmod(0o755)
    for f in (dst / "checks").glob("*.sh"):
        f.chmod(0o755)
    return dst


def _run_hook(hookdir, cwd, state_dir, session, agent):
    payload = {"cwd": str(cwd), "session_id": session, "agent_id": agent, "agent_type": "test"}
    env = dict(os.environ)
    env["REVIEW_GATE_STATE_DIR"] = str(state_dir)
    p = subprocess.run(
        ["bash", str(hookdir / "review-gate.sh")],
        input=json.dumps(payload).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd, env=env, timeout=30,
    )
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def _write_generated_file(repo):
    f = repo / "generated.sh"
    f.write_text("#!/usr/bin/env bash\n# swissknifeman:generated\necho hi\n")
    return f


class TestReviewGate(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _init_repo(self.repo)
        self.state_dir = self.tmp / "state"
        self.hookdir = _hookdir(self.tmp, self.state_dir)

    def tearDown(self):
        self._td.cleanup()

    def test_synthetic_violation_caught_with_file_line(self):
        _write_generated_file(self.repo)
        rc, out, err = _run_hook(self.hookdir, self.repo, self.state_dir, "sess-a", "agent-a")
        self.assertEqual(rc, 2)
        self.assertIn("generated.sh:2", err)

    def test_clean_diff_passes(self):
        rc, out, err = _run_hook(self.hookdir, self.repo, self.state_dir, "sess-b", "agent-b")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertEqual(err.strip(), "")

    def test_third_consecutive_strict_downgrades_to_warn(self):
        _write_generated_file(self.repo)
        session, agent = "sess-c", "agent-c"
        rc1, _, err1 = _run_hook(self.hookdir, self.repo, self.state_dir, session, agent)
        rc2, _, err2 = _run_hook(self.hookdir, self.repo, self.state_dir, session, agent)
        rc3, out3, err3 = _run_hook(self.hookdir, self.repo, self.state_dir, session, agent)
        self.assertEqual(rc1, 2)
        self.assertEqual(rc2, 2)
        self.assertEqual(rc3, 0)   # понижено до warn — review-gate.sh не блокирует
        self.assertIn("DOWNGRADE", out3)


if __name__ == "__main__":
    unittest.main()
