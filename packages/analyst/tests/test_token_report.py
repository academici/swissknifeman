"""Тесты token-report: rolling-baseline (медиана/p90 stdlib), regression-флаг на синтетическом
тренде, срезы model/role (role — best-effort по .claude/runs/, честная деградация), --json,
die без тренда/без --note, pinned baseline → .claude/analyze/baseline.json (формат СОВМЕСТИМ
с maind.analyze._read_baseline: totals.median_out обязателен)."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from analyst import token_report as tr
from analyst.cli import main


def _write_trend(proj, rows):
    d = Path(proj) / ".claude" / "analyze"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "usage-trend.ndjson", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _trend_row(session, out, in_=5000, model="claude-sonnet-5", ts="2026-06-01T00:00:00Z"):
    return {"ts": ts, "session": session, "in": in_, "out": out,
           "by_model": {model: {"in": in_, "out": out}}}


def _write_run_report(proj, session, agents):
    d = Path(proj) / ".claude" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    rr = {"schema": 2, "session_id": session, "usage": {"agents": agents}}
    (d / f"{session}.json").write_text(json.dumps(rr), encoding="utf-8")


class TmpProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _chdir_run(self, argv):
        """main([proj, *argv]) с cwd=proj (cmd_token_report читает os.getcwd(), как весь P1)."""
        cwd = os.getcwd()
        out, err = io.StringIO(), io.StringIO()
        code = None
        try:
            os.chdir(self.proj)
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    main([self.proj, "token-report", *argv])
                except SystemExit as e:
                    code = e.code
        finally:
            os.chdir(cwd)
        return code, out.getvalue(), err.getvalue()


class TestRollingStatsAndRegression(unittest.TestCase):
    def test_none_below_min_n(self):
        rows = [_trend_row(f"s{i}", 10000) for i in range(tr.MIN_BASELINE_N - 1)]
        self.assertIsNone(tr.rolling_stats(rows))

    def test_regression_flag_synthetic_trend(self):
        # 17 сессий out=10000 + 2 чуть выше (11000) — реалистичный разброс: медиана=10000,
        # p90=10200 (statistics.quantiles(n=10)). Регресс — только явный выброс.
        rows = ([_trend_row(f"h{i}", 10000) for i in range(17)]
               + [_trend_row(f"v{i}", 11000) for i in range(2)])
        stats = tr.rolling_stats(rows)
        self.assertEqual(stats["median_out"], 10000)
        self.assertEqual(stats["p90_out"], 10200)
        self.assertFalse(tr.is_regression(10000, stats))          # норма — не регресс
        self.assertFalse(tr.is_regression(10100, stats))          # < 1.3× и < p90 — не регресс
        self.assertTrue(tr.is_regression(50000, stats))           # >> 1.3×медиана — регресс
        self.assertTrue(tr.is_regression(10300, stats))           # < 1.3×, но > p90 — регресс

    def test_regression_false_without_baseline(self):
        self.assertFalse(tr.is_regression(999999, None))

    def test_regression_false_on_zero_median(self):
        rows = [_trend_row(f"z{i}", 0) for i in range(tr.MIN_BASELINE_N)]
        stats = tr.rolling_stats(rows)
        self.assertFalse(tr.is_regression(5000, stats))           # медиана=0 — не делим на 0


class TestComputeReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_none_without_trend(self):
        self.assertIsNone(tr.compute_report(self.proj, by="model"))

    def test_by_model_slices_and_flags_regression(self):
        rows = [_trend_row(f"h{i}", 10000, model="claude-sonnet-5") for i in range(19)]
        rows.append(_trend_row("spike", 50000, model="claude-opus-5", ts="2026-07-01T00:00:00Z"))
        _write_trend(self.proj, rows)
        rep = tr.compute_report(self.proj, sessions=20, by="model")
        self.assertEqual(rep["sessions_window"], 20)
        self.assertEqual(rep["sessions_total_in_trend"], 20)
        self.assertEqual(rep["regression_count"], 1)
        by_key = {s["key"]: s for s in rep["slices"]}
        self.assertTrue(by_key["claude-opus-5"]["regression"])
        self.assertFalse(by_key["claude-sonnet-5"]["regression"])
        self.assertEqual(by_key["claude-sonnet-5"]["sessions"], 19)

    def test_by_role_degrades_honestly_when_run_report_missing(self):
        rows = [_trend_row(f"s{i}", 10000) for i in range(5)]
        _write_trend(self.proj, rows)
        # только 3 из 5 сессий имеют сохранившийся run-report (имитация ретеншна .claude/runs)
        for i in range(3):
            _write_run_report(self.proj, f"s{i}", [
                {"label": "main", "model": "claude-sonnet-5", "in": 8000, "out": 8000},
                {"label": "sub-x", "model": "claude-sonnet-5", "in": 2000, "out": 2000},
            ])
        rep = tr.compute_report(self.proj, sessions=5, by="role")
        self.assertEqual(rep["role_meta"], {"sessions_total": 5, "sessions_matched": 3})
        by_key = {s["key"]: s for s in rep["slices"]}
        self.assertEqual(by_key["main"]["sessions"], 3)
        self.assertEqual(by_key["main"]["out"], 24000)
        self.assertEqual(by_key["sub-x"]["out"], 6000)

    def test_empty_slices_when_no_run_reports_survive(self):
        _write_trend(self.proj, [_trend_row("s1", 10000)])
        rep = tr.compute_report(self.proj, sessions=1, by="role")
        self.assertEqual(rep["slices"], [])
        self.assertEqual(rep["role_meta"]["sessions_matched"], 0)

    def test_sessions_window_smaller_than_requested_is_honest(self):
        _write_trend(self.proj, [_trend_row(f"s{i}", 10000) for i in range(4)])
        rep = tr.compute_report(self.proj, sessions=50, by="model")
        self.assertEqual(rep["sessions_requested"], 50)
        self.assertEqual(rep["sessions_window"], 4)                # не 50 — честно меньше


class TestPinnedBaseline(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_pin_baseline_writes_maind_compatible_format(self):
        rows = [_trend_row(f"h{i}", 10000, model="claude-sonnet-5") for i in range(15)]
        rows += [_trend_row(f"o{i}", 20000, model="claude-opus-5") for i in range(5)]
        _write_trend(self.proj, rows)
        doc = tr.pin_baseline(self.proj, None, "wave2 pin")
        # контракт maind.analyze._read_baseline: totals.median_out — число, обязателен
        self.assertIsInstance(doc["totals"]["median_out"], (int, float))
        self.assertEqual(doc["note"], "wave2 pin")
        self.assertIn("claude-sonnet-5", doc["by_model"])
        self.assertIsInstance(doc["by_model"]["claude-sonnet-5"]["median_out"], (int, float))
        written = json.loads(tr.baseline_path(self.proj).read_text(encoding="utf-8"))
        self.assertEqual(written, doc)

    def test_pin_baseline_dies_without_trend_and_writes_nothing(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                tr.pin_baseline(self.proj, None, "note")
        self.assertFalse(tr.baseline_path(self.proj).exists())

    def test_pin_baseline_dies_below_min_n_and_writes_nothing(self):
        _write_trend(self.proj, [_trend_row("s1", 10000)])          # < MIN_BASELINE_N
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                tr.pin_baseline(self.proj, None, "note")
        self.assertFalse(tr.baseline_path(self.proj).exists())

    def test_read_pinned_baseline_reads_back_written_doc(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        tr.pin_baseline(self.proj, None, "note")
        pinned = tr.read_pinned_baseline(self.proj)
        self.assertEqual(pinned["median_out"], 10000)


class TestCli(TmpProjectCase):
    def test_die_without_trend(self):
        code, _out, err = self._chdir_run([])
        self.assertEqual(code, 1)
        self.assertIn("нет тренда токенов", err)

    def test_json_output_is_valid_and_shaped(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, out, _err = self._chdir_run(["--json"])
        self.assertIsNone(code)
        data = json.loads(out)
        self.assertEqual(data["by"], "model")
        self.assertIn("rolling", data)
        self.assertIn("slices", data)

    def test_by_phase_dies_with_escalation_message(self):
        code, _out, err = self._chdir_run(["--by", "phase"])
        self.assertEqual(code, 1)
        self.assertIn("--by phase недоступен", err)

    def test_by_unknown_dies(self):
        code, _out, err = self._chdir_run(["--by", "nope"])
        self.assertEqual(code, 1)
        self.assertIn("--by ждёт", err)

    def test_baseline_set_requires_note(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, _out, err = self._chdir_run(["--baseline", "set"])
        self.assertEqual(code, 1)
        self.assertIn("--note", err)
        self.assertFalse(tr.baseline_path(self.proj).exists())

    def test_baseline_set_writes_file_via_cli(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, out, _err = self._chdir_run(["--baseline", "set", "--note", "release v1"])
        self.assertIsNone(code)
        self.assertIn("baseline закреплён", out)
        self.assertTrue(tr.baseline_path(self.proj).is_file())
        doc = json.loads(tr.baseline_path(self.proj).read_text(encoding="utf-8"))
        self.assertEqual(doc["note"], "release v1")
        self.assertEqual(doc["totals"]["median_out"], 10000)

    def test_baseline_set_json(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, out, _err = self._chdir_run(["--baseline", "set", "--note", "n", "--json"])
        self.assertIsNone(code)
        data = json.loads(out)
        self.assertEqual(data["note"], "n")
        self.assertIn("written", data)

    def test_vs_baseline_without_pin_is_honest_not_crash(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, out, _err = self._chdir_run(["--vs-baseline"])
        self.assertIsNone(code)
        self.assertIn("не установлен", out)

    def test_vs_baseline_without_pin_warns_but_does_not_die(self):
        # P2.6 (LOW-находка аудита P8): --vs-baseline без пина — мягкая деградация
        # (warn в stderr), НЕ ошибка запроса (die/exit≠0). Отчёт всё равно строится.
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, out, err = self._chdir_run(["--vs-baseline"])
        self.assertIsNone(code)                       # никакого SystemExit — не die
        self.assertIn("WARN:", err)
        self.assertIn("pinned baseline не установлен", err)
        self.assertIn("не установлен", out)            # отчёт по-прежнему построен

    def test_vs_baseline_with_pin_no_warn(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, _out, err = self._chdir_run(["--baseline", "set", "--note", "n"])
        self.assertIsNone(code)
        code, _out, err = self._chdir_run(["--vs-baseline"])
        self.assertIsNone(code)
        self.assertNotIn("WARN:", err)

    def test_vs_baseline_without_pin_warns_in_json_mode_too(self):
        # warn() — на уровне CLI (до ветвления json/human), не только в человекочитаемом выводе.
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, out, err = self._chdir_run(["--vs-baseline", "--json"])
        self.assertIsNone(code)
        self.assertIn("WARN:", err)
        data = json.loads(out)                          # stdout остаётся чистым JSON
        self.assertIsNone(data["pinned_baseline"])

    def test_without_vs_baseline_no_warn_even_if_unpinned(self):
        _write_trend(self.proj, [_trend_row(f"h{i}", 10000) for i in range(tr.MIN_BASELINE_N)])
        code, _out, err = self._chdir_run([])
        self.assertIsNone(code)
        self.assertNotIn("WARN:", err)


if __name__ == "__main__":
    unittest.main()
