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
VC_SRC = PKG.parents[1] / "plans" / "verify-citations.py"


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


def _hookdir_citations(tmp):
    """Tmp-копия HOOK_DIR с ЕДИНСТВЕННОЙ проверкой `plan-citations` — образец
    `_hookdir` выше, но набор/режим свои (P11.7, третья точка принуждения)."""
    dst = tmp / "hookdir"
    shutil.copytree(RG_SRC, dst)
    (dst / "env.ini").write_text("MODE=strict\n")
    (dst / "config.json").write_text(json.dumps({
        "version": 2,
        "check_command": "$REVIEW_GATE_DIR/checks/run-checks.sh",
        "checks": [{"name": "plan-citations", "mode": "strict"}],
    }))
    (dst / "review-gate.sh").chmod(0o755)
    for f in (dst / "checks").glob("*.sh"):
        f.chmod(0o755)
    return dst


class TestPlanCitationsCheck(unittest.TestCase):
    """P11.7: `plan-citations` — прогон РЕАЛЬНОГО `plans/verify-citations.py`
    (не стаб) по задетому плану. Скрипт резолвит свой `REPO_ROOT` от
    собственного пути, поэтому копия в tmp-репо работает автономно."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _init_repo(self.repo)
        plan_dir = self.repo / "plans" / "TESTPLAN"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# TESTPLAN\n")
        (plan_dir / "phases" / "P1.md").write_text("Cite `plans/TESTPLAN/plan.md:1` here.\n")
        (self.repo / "plans").mkdir(exist_ok=True)
        shutil.copy(VC_SRC, self.repo / "plans" / "verify-citations.py")
        _run(["git", "add", "."], self.repo)
        _run(["git", "config", "user.email", "review-gate-test@example.invalid"], self.repo)
        _run(["git", "commit", "-q", "-m", "plan skeleton"], self.repo)
        self.state_dir = self.tmp / "state"
        self.hookdir = _hookdir_citations(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_broken_citation_caught(self):
        (self.repo / "plans" / "TESTPLAN" / "phases" / "P1.md").write_text(
            "Cite `plans/TESTPLAN/nonexistent-file.py:1` here.\n"
        )
        rc, out, err = _run_hook(self.hookdir, self.repo, self.state_dir, "sess-vc-a", "agent-vc-a")
        self.assertEqual(rc, 2)
        self.assertIn("plans/TESTPLAN:", err)
        self.assertIn("nonexistent-file.py", err)

    def test_clean_citation_passes(self):
        (self.repo / "plans" / "TESTPLAN" / "phases" / "P1.md").write_text(
            "Cite `plans/TESTPLAN/plan.md:1` here (updated).\n"
        )
        rc, out, err = _run_hook(self.hookdir, self.repo, self.state_dir, "sess-vc-b", "agent-vc-b")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertEqual(err.strip(), "")


if __name__ == "__main__":
    unittest.main()
