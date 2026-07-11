"""Фасад `skiller doctor --settings` (P1.4): делегирование в `harness doctor
--settings` через subprocess, прокидывание кода возврата, graceful skip при
отсутствующем harness. Логики проверок в skiller НЕТ (D10) — тестируем только
поведение фасада, не таксономию (её тесты живут в harness)."""
import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.doctor import cmd_doctor


def _run(fn, *a):
    buf = io.StringIO()
    exc = None
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            fn(*a)
        except SystemExit as e:
            exc = e
    return exc, buf.getvalue()


class DoctorSettingsFacadeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        # root — tmpdir без маркеров монорепо: harness_bin не найдёт лаунчер в
        # раскладке пакетов, останется только env-override SKM_HARNESS_BIN.
        self.env = Env(self.tmp / "registry", home=self.home)
        (self.tmp / "registry").mkdir()
        self._saved_bin = os.environ.pop("SKM_HARNESS_BIN", None)

    def tearDown(self):
        if self._saved_bin is not None:
            os.environ["SKM_HARNESS_BIN"] = self._saved_bin
        else:
            os.environ.pop("SKM_HARNESS_BIN", None)
        self._tmp.cleanup()

    # harness не установлен → warn и graceful skip (rc 0, без падения)
    def test_missing_harness_warns_and_skips(self):
        exc, out = _run(cmd_doctor, self.env, ["--settings", "--target", str(self.tmp)])
        self.assertIsNone(exc)  # не sys.exit — фасад мягко пропустил
        self.assertIn("harness не установлен", out)

    # harness присутствует → код возврата прокидывается (2 → sys.exit(2)).
    # Заглушка не пишет в stdout: subprocess наследует реальный fd (redirect_stdout
    # ловит только python-уровень sys.stdout) — проверяем контракт кода возврата.
    def test_proxies_harness_exit_code(self):
        stub = self.tmp / "harness-stub"
        stub.write_text("#!/usr/bin/env bash\nexit 2\n", encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        os.environ["SKM_HARNESS_BIN"] = str(stub)
        exc, _out = _run(cmd_doctor, self.env, ["--settings", "--target", str(self.tmp)])
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 2)


if __name__ == "__main__":
    unittest.main()
