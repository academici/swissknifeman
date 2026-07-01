"""Smoke-тесты диспетчера analyst: сборка Env, роутинг команд, doctor."""
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from analyst.cli import COMMANDS, main
from analyst.common import Env


class TestCli(unittest.TestCase):
    def test_env_paths(self):
        env = Env("/tmp/analyst-root", "doctor", home="/tmp/fakehome")
        self.assertEqual(str(env.state_dir), "/tmp/fakehome/.swissknifeman/analyst")

    def test_unknown_command_exits_1(self):
        with self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
            main(["/tmp/root", "nope"])
        self.assertEqual(cm.exception.code, 1)

    def test_too_few_args_exits_2(self):
        with self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
            main(["/tmp/root"])
        self.assertEqual(cm.exception.code, 2)

    def test_doctor_registered_and_runs(self):
        self.assertIn("doctor", COMMANDS)
        out = io.StringIO()
        # doctor может завершиться SystemExit(1), если нет core — но в монорепо core есть.
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            try:
                main(["/tmp/root", "doctor"])
            except SystemExit:
                pass
        self.assertIn("analyst doctor", out.getvalue())


if __name__ == "__main__":
    unittest.main()
