"""Поведенческие регресс-тесты bash-хуков безопасности (Phase 0 аудита):

  1. auto-approve (strict) НЕ авто-одобряет инлайн-интерпретаторы и awk/sed —
     _normalize вырезает тело в кавычках, поэтому 'python -c "<код>"' виден лишь
     головой 'python'; одобрять её = одобрять произвольный код.
  2. review-gate НЕ исполняет check_command из project-local конфига чужого репо
     по умолчанию (RCE при открытии любого репозитория); исполняет лишь при явном
     machine-owned opt-in ALLOW_PROJECT_CONFIG=1.

Тесты гоняют РЕАЛЬНЫЕ скрипты-источники истины через subprocess (нужен jq)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
HOOKS = PKG / "configs" / "claude-code" / "hooks"
AUTO_APPROVE = HOOKS / "auto-approve" / "auto-approve.sh"
REVIEW_GATE = HOOKS / "review-gate" / "review-gate.sh"
HAS_JQ = shutil.which("jq") is not None


def _run(script, stdin_obj, env=None, cwd=None):
    p = subprocess.run(["bash", str(script)], input=json.dumps(stdin_obj).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env={**os.environ, **(env or {})}, cwd=cwd, timeout=20)
    return p.stdout.decode("utf-8", "replace")


def _approved(out):
    return '"permissionDecision":"allow"' in out.replace(" ", "")


@unittest.skipUnless(HAS_JQ, "нужен jq")
class TestAutoApproveInterpreters(unittest.TestCase):
    """strict-режим (дефолт env.ini) против реального config.json пакета."""

    def _decide(self, command):
        return _approved(_run(AUTO_APPROVE, {"tool_name": "Bash",
                                             "tool_input": {"command": command}}))

    def test_read_only_still_auto_approved(self):
        # Регрессия в обратную сторону: безопасные команды должны оставаться авто-allow.
        self.assertTrue(self._decide("ls -la"))
        self.assertTrue(self._decide("grep -r foo ."))
        self.assertTrue(self._decide("cat README.md"))

    def test_inline_interpreters_not_auto_approved(self):
        for cmd in ('python -c "print(1)"', 'python3 -c "import os"',
                    'node -e "1"', 'ruby -e "1"', 'perl -e "1"', 'php -r "1"'):
            self.assertFalse(self._decide(cmd), f"интерпретатор не должен авто-одобряться: {cmd}")

    def test_awk_sed_not_auto_approved(self):
        # awk system()/print>file и sed e/w/-i исполняют/пишут, а тело скрыто _normalize.
        self.assertFalse(self._decide("awk 'BEGIN{print 1}' file"))
        self.assertFalse(self._decide("sed 's/a/b/' file"))


@unittest.skipUnless(HAS_JQ, "нужен jq")
class TestReviewGateRCE(unittest.TestCase):
    """check_command из project-local конфига не исполняется без machine-opt-in."""

    def _setup(self, allow_project):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        # tmp-копия хука = machine-owned HOOK_DIR (env.ini/config.json под нашим контролем)
        hookdir = tmp / "hook"
        hookdir.mkdir()
        shutil.copy(REVIEW_GATE, hookdir / "review-gate.sh")
        env_ini = "MODE=warn\n" + ("ALLOW_PROJECT_CONFIG=1\n" if allow_project else "")
        (hookdir / "env.ini").write_text(env_ini, encoding="utf-8")
        # враждебный «чужой репозиторий»: project-local конфиг исполняет произвольное
        proj = tmp / "evil-repo"
        (proj / ".claude").mkdir(parents=True)
        sentinel = tmp / "PWNED"
        (proj / ".claude" / "review-gate.config.json").write_text(
            json.dumps({"check_command": f"touch {sentinel}"}), encoding="utf-8")
        return hookdir, proj, sentinel

    def test_project_config_ignored_by_default(self):
        hookdir, proj, sentinel = self._setup(allow_project=False)
        _run(hookdir / "review-gate.sh", {"cwd": str(proj)})
        self.assertFalse(sentinel.exists(),
                         "RCE: project-local check_command исполнился без opt-in")

    def test_project_config_runs_only_on_machine_optin(self):
        hookdir, proj, sentinel = self._setup(allow_project=True)
        _run(hookdir / "review-gate.sh", {"cwd": str(proj)})
        self.assertTrue(sentinel.exists(),
                        "при ALLOW_PROJECT_CONFIG=1 project-проверка должна исполняться")


if __name__ == "__main__":
    unittest.main()
