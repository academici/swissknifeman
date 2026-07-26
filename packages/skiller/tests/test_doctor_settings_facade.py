"""Фасад `skiller doctor --settings` (P1.4): делегирование в `harness doctor
--settings` через subprocess, прокидывание кода возврата, graceful skip при
отсутствующем harness. Логики проверок в skiller НЕТ (D10) — тестируем только
поведение фасада, не таксономию (её тесты живут в harness).

Плюс P4.2 `skiller doctor --effective-source`: composed read-only doctor —
здесь же (Files item'а называет ровно этот тестовый файл), тестируем и фасад
(`--settings`), и composed-diagnostics record-shape/fixtures отдельно."""
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.doctor import (
    EffectiveSourceDoctorError,
    build_effective_source_report,
    cmd_doctor,
    gather_effective_source_diagnostics,
)

FIXTURES_DATA = Path(__file__).resolve().parent / "fixtures_data"


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


class EffectiveSourceDoctorFixtureCase(unittest.TestCase):
    """P4.2: `build_effective_source_report` against the committed healthy/degraded
    fixtures — pure composition, no filesystem/subprocess involved (the gathering
    functions that DO touch the filesystem are exercised by `EffectiveSourceDoctorLiveCase`
    below against the real repo, read-only)."""

    def setUp(self):
        self.cases = json.loads(
            (FIXTURES_DATA / "effective-source-doctor-cases.json").read_text(encoding="utf-8"))["cases"]

    def test_healthy_case_folds_to_ok(self):
        case = self.cases["healthy"]
        report = build_effective_source_report(case["diagnostics"])
        self.assertEqual(report["overall"], case["expected_overall"])
        self.assertEqual(report["schema_version"], "effective-source-doctor/v1")

    def test_degraded_case_folds_to_degraded(self):
        case = self.cases["degraded"]
        report = build_effective_source_report(case["diagnostics"])
        self.assertEqual(report["overall"], case["expected_overall"])

    def test_missing_required_key_raises(self):
        broken = [{"id": "x", "owner": "o", "source": "s", "status": "ok", "evidence": {}}]  # no quality/next_command
        with self.assertRaises(EffectiveSourceDoctorError):
            build_effective_source_report(broken)

    def test_out_of_vocabulary_status_raises(self):
        broken = [{"id": "x", "owner": "o", "source": "s", "status": "green",
                  "evidence": {}, "quality": {}, "next_command": "c"}]
        with self.assertRaises(EffectiveSourceDoctorError):
            build_effective_source_report(broken)


class EffectiveSourceDoctorLiveCase(unittest.TestCase):
    """`--effective-source` against the real registry (read-only, this repo's own
    checked-out tree) — proves the CLI wiring and the record shape hold on live data,
    not just the fixture. No write is asserted at the Validation shell-command layer
    (git status before/after); here we only assert shape/no-crash."""

    def test_gather_and_build_round_trip(self):
        from skiller.common import Env as RealEnv
        root = Path(__file__).resolve().parents[1]
        env = RealEnv(root)
        diagnostics = gather_effective_source_diagnostics(env, repo_root=root.parents[1])
        report = build_effective_source_report(diagnostics)
        self.assertEqual(report["schema_version"], "effective-source-doctor/v1")
        self.assertEqual({d["id"] for d in report["diagnostics"]},
                          {"identity-ownership", "cache", "capability-reference-coverage",
                           "hook-ownership", "trace-quality"})
        for d in report["diagnostics"]:
            self.assertIn(d["status"], ("ok", "degraded", "unknown", "n/a"))
        self.assertIn(report["overall"], ("ok", "degraded"))

    def test_cli_effective_source_json_prints_one_document(self):
        from skiller.common import Env as RealEnv
        root = Path(__file__).resolve().parents[1]
        env = RealEnv(root)
        exc, out = _run(cmd_doctor, env, ["--effective-source", "--json"])
        self.assertIsNone(exc)
        doc = json.loads(out)
        self.assertEqual(doc["schema_version"], "effective-source-doctor/v1")


if __name__ == "__main__":
    unittest.main()
