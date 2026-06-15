"""Тесты cli.py: диспетчер команд (маршрутизация, неизвестная команда, exit-коды)."""
import contextlib
import io
import unittest

from maind import cli


class TestCli(unittest.TestCase):
    def test_too_few_args_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["/root"])          # есть root, нет команды
        self.assertEqual(cm.exception.code, 2)

    def test_unknown_command_exits_1(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                cli.main(["/root", "bogus"])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("bogus", err.getvalue())

    def test_routes_to_handler_with_env_and_args(self):
        captured = {}

        def fake(env, args):
            captured.update(root=str(env.root), cmd=env.cmd, args=args)

        orig = cli.COMMANDS["status"]
        cli.COMMANDS["status"] = fake
        try:
            cli.main(["/some/root", "status", "--json"])
        finally:
            cli.COMMANDS["status"] = orig
        self.assertEqual(captured["root"], "/some/root")
        self.assertEqual(captured["cmd"], "status")
        self.assertEqual(captured["args"], ["--json"])

    def test_all_handlers_callable(self):
        self.assertTrue(cli.COMMANDS)        # реестр не пуст
        for name, fn in cli.COMMANDS.items():
            self.assertTrue(callable(fn), name)

    def test_known_top_commands_registered(self):
        for cmd in ("start", "status", "graph", "memory", "sync", "health",
                    "namespaces", "mcp", "doctor"):
            self.assertIn(cmd, cli.COMMANDS)


if __name__ == "__main__":
    unittest.main()
