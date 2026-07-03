"""Тесты service.py (systemd-юнит демона памяти) и foreground-запуска memory.run."""
import tempfile
import unittest
from unittest import mock

from maind import memory
from maind.provision import service
from maind.config import load_config
from tests.fixtures import make_repo, write_maind_config


def _env(tmp):
    root, env = make_repo(tmp)
    write_maind_config(root)
    return env


class TestUnitText(unittest.TestCase):
    def test_unit_points_to_foreground_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp)
            txt = service._unit_text(env)
            self.assertIn("Type=simple", txt)
            self.assertIn(f"ExecStart={env.root / 'bin' / 'maind'} memory run", txt)
            self.assertIn(f"WorkingDirectory={env.root}", txt)
            self.assertIn("Restart=on-failure", txt)
            self.assertIn("WantedBy=default.target", txt)

    def test_unit_path_is_user_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp)
            p = service._unit_path(env)
            self.assertEqual(p, env.home / ".config" / "systemd" / "user"
                             / "maind-memory.service")

    def test_help_does_not_require_systemd(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp)
            with mock.patch.object(service, "_ensure_systemd") as ens:
                service.cmd_service(env, ["--help"])
                ens.assert_not_called()  # help печатается до проверки systemd


class TestDaemonArgv(unittest.TestCase):
    def test_argv_carries_ports_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp)
            config, _ = load_config(env)
            binp = env.root / "node_modules" / ".bin" / "agentmemory"
            binp.parent.mkdir(parents=True, exist_ok=True)
            binp.write_text("#!/bin/sh\n", encoding="utf-8")
            with mock.patch.object(memory.shutil, "which", return_value="/usr/bin/node"):
                cmd, child_env, url = memory._daemon_argv(env, config)
            self.assertEqual(cmd[0], "node")
            self.assertEqual(cmd[-1], str(binp))
            self.assertEqual(child_env["AGENTMEMORY_URL"], url)
            self.assertEqual(child_env["AGENTMEMORY_PORT"], "4111")
            self.assertEqual(child_env["AGENTMEMORY_III_CONFIG"], str(env.memory_config))

    def test_argv_dies_without_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp)
            config, _ = load_config(env)
            with mock.patch.object(memory.shutil, "which", return_value="/usr/bin/node"):
                with self.assertRaises(SystemExit):
                    memory._daemon_argv(env, config)  # бинаря agentmemory нет


if __name__ == "__main__":
    unittest.main()
