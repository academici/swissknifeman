"""Тесты doctor.py: диагностика окружения (--help, провал при отсутствии демона, успех
при замоканном окружении). Без живых бинарей/демона — изолированно в tmpdir."""
import contextlib
import io
import tempfile
import unittest

from maind import doctor
from maind.doctor import cmd_doctor
from tests.fixtures import capture, make_repo


class TestDoctor(unittest.TestCase):
    def test_help_returns_without_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            _, out = capture(cmd_doctor, env, ["--help"])
            self.assertIn("maind doctor", out)

    def test_reports_issue_when_agentmemory_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)               # node_modules/.bin/agentmemory нет
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
                cmd_doctor(env, ["--quiet"])      # quiet → печатает только провалы
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("agentmemory", buf.getvalue())

    def test_passes_when_env_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)               # iii-config.yaml уже на месте
            bindir = env.root / "node_modules" / ".bin"
            bindir.mkdir(parents=True)
            (bindir / "agentmemory").write_text("", encoding="utf-8")
            orig = doctor.shutil.which
            doctor.shutil.which = lambda name: "/usr/bin/node"
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cmd_doctor(env, ["--quiet"])  # все проверки ок → без SystemExit
                self.assertIn("Все проверки пройдены", buf.getvalue())
            finally:
                doctor.shutil.which = orig


if __name__ == "__main__":
    unittest.main()
