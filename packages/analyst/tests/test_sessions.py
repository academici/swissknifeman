"""Тесты analyst sessions (P5.3): недельные медианы first_turn_overhead/fresh-per-turn
из синтетических jsonl-транскриптов, encode_cwd (подтверждено на живых каталогах —
только '/'→'-'), trend-warn week-over-week >20%, CLI (--project реестр/--weeks/--json)."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from analyst import sessions as ss
from analyst.cli import main


def _assistant(in_=0, out=0, cache_read=0, cache_creation=0, ts=None, model="claude-sonnet-5"):
    ev = {"type": "assistant", "message": {
        "model": model,
        "usage": {"input_tokens": in_, "output_tokens": out,
                  "cache_read_input_tokens": cache_read,
                  "cache_creation_input_tokens": cache_creation}}}
    if ts:
        ev["timestamp"] = ts
    return ev


def _write_jsonl(path, events, extra_lines=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(ev) for ev in events]
    if extra_lines:
        lines.extend(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class EncodeCwdCase(unittest.TestCase):
    def test_slash_to_dash(self):
        # подтверждено чтением живых ~/.claude/projects/* этой машины (см. докстринг
        # модуля) — единственное, что проверено, остальное не угадываем
        self.assertEqual(ss.encode_cwd("/home/vostrikov/projects/packages/swissknifeman"),
                         "-home-vostrikov-projects-packages-swissknifeman")

    def test_sessions_dir_under_home(self):
        d = ss.sessions_dir("/a/b", home="/fake-home")
        self.assertEqual(str(d), str(Path("/fake-home") / ".claude" / "projects" / "-a-b"))


class SessionMetricsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_turn_overhead_and_fresh_per_turn(self):
        p = self.root / "sess-1.jsonl"
        _write_jsonl(p, [
            _assistant(in_=100, out=20, cache_creation=50, ts="2026-07-06T10:00:00Z"),
            _assistant(in_=10, out=5, cache_creation=0, ts="2026-07-06T10:05:00Z"),
        ])
        m = ss.session_metrics(p)
        self.assertEqual(m["session"], "sess-1")
        self.assertEqual(m["first_turn_overhead"], 150)   # 100+50 первой записи
        self.assertEqual(m["turns"], 2)
        # fresh_per_turn = (Σin+Σcache_creation)/turns = (110+50)/2
        self.assertAlmostEqual(m["fresh_per_turn"], 80.0)
        self.assertEqual(m["week"], "2026-W28")

    def test_broken_line_skipped_not_raising(self):
        p = self.root / "sess-2.jsonl"
        _write_jsonl(p, [_assistant(in_=5, out=1, ts="2026-07-06T10:00:00Z")],
                     extra_lines=["{битая строка без закрытия"])
        m = ss.session_metrics(p)
        self.assertIsNotNone(m)
        self.assertEqual(m["turns"], 1)

    def test_no_assistant_events_returns_none(self):
        p = self.root / "empty.jsonl"
        _write_jsonl(p, [{"type": "user", "message": {"content": "hi"}}])
        self.assertIsNone(ss.session_metrics(p))

    def test_no_timestamp_returns_none(self):
        # без timestamp — неделя не определяется, сессия честно выпадает (не 1970-я неделя)
        p = self.root / "no-ts.jsonl"
        _write_jsonl(p, [_assistant(in_=5, out=1)])
        self.assertIsNone(ss.session_metrics(p))


class WeeklyReportCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.cwd = "/proj/demo"
        self.dir = ss.sessions_dir(self.cwd, home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _add(self, name, overhead_in, ts):
        _write_jsonl(self.dir / f"{name}.jsonl", [
            _assistant(in_=overhead_in, out=10, ts=ts)])

    def test_weekly_medians_and_trend_warn(self):
        # неделя W27: две сессии медиана overhead 1000; неделя W28: рост >20% (медиана 1500)
        self._add("s1", 900, "2026-06-29T10:00:00Z")   # W27
        self._add("s2", 1100, "2026-06-30T10:00:00Z")  # W27 → медиана 1000
        self._add("s3", 1500, "2026-07-06T10:00:00Z")  # W28 → медиана 1500 (рост 50%)
        rep = ss.build_report(self.cwd, home=self.home)
        self.assertIsNotNone(rep)
        weeks = {w["week"]: w for w in rep["weeks"]}
        self.assertEqual(weeks["2026-W27"]["median_first_turn_overhead"], 1000)
        self.assertEqual(weeks["2026-W28"]["median_first_turn_overhead"], 1500)
        self.assertEqual(rep["sessions_total"], 3)
        self.assertTrue(rep["trend_warnings"])
        self.assertIn("2026-W27→2026-W28", rep["trend_warnings"][0])

    def test_no_warn_within_20_percent(self):
        self._add("s1", 1000, "2026-06-29T10:00:00Z")   # W27
        self._add("s2", 1150, "2026-07-06T10:00:00Z")   # W28, +15% — не WARN
        rep = ss.build_report(self.cwd, home=self.home)
        self.assertEqual(rep["trend_warnings"], [])

    def test_weeks_limits_window(self):
        self._add("s1", 500, "2026-06-15T10:00:00Z")    # W25
        self._add("s2", 600, "2026-06-22T10:00:00Z")    # W26
        self._add("s3", 700, "2026-06-29T10:00:00Z")    # W27
        rep = ss.build_report(self.cwd, weeks=1, home=self.home)
        self.assertEqual(len(rep["weeks"]), 1)
        self.assertEqual(rep["sessions_window"], 1)

    def test_no_sessions_dir_returns_none(self):
        self.assertIsNone(ss.build_report("/nowhere/else", home=self.home))

    def test_no_warn_across_week_gap(self):
        # W20 → W28: рост >20%, но недели не смежные (7-недельный разрыв без сессий) —
        # не рецидив, а разрыв данных, warn не должен печататься
        self._add("s1", 1000, "2026-05-11T10:00:00Z")   # W20
        self._add("s2", 2000, "2026-07-06T10:00:00Z")   # W28
        rep = ss.build_report(self.cwd, home=self.home)
        self.assertEqual(rep["trend_warnings"], [])


class IsNextIsoWeekCase(unittest.TestCase):
    def test_adjacent_weeks(self):
        self.assertTrue(ss._is_next_iso_week("2026-W27", "2026-W28"))

    def test_gap_weeks(self):
        self.assertFalse(ss._is_next_iso_week("2026-W20", "2026-W28"))

    def test_year_boundary(self):
        self.assertTrue(ss._is_next_iso_week("2025-W52", "2026-W01"))


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(ss, "HOME", self.home):
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    main([str(self.root), "sessions", *argv])
                except SystemExit as e:
                    code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_no_sessions_dies(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.root)
            code, _, err = self._run([])
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 1)
        self.assertIn("нет сессий", err)

    def test_json_output(self):
        cwd_dir = self.root / "proj"
        cwd_dir.mkdir()
        sdir = ss.sessions_dir(str(cwd_dir), home=self.home)
        _write_jsonl(sdir / "sess-1.jsonl", [_assistant(in_=100, out=10, cache_creation=20,
                                                        ts="2026-07-06T10:00:00Z")])
        cwd = os.getcwd()
        try:
            os.chdir(cwd_dir)
            code, out, _ = self._run(["--json"])
        finally:
            os.chdir(cwd)
        self.assertIsNone(code)
        data = json.loads(out)
        self.assertEqual(data["sessions_total"], 1)
        self.assertEqual(data["weeks"][0]["median_first_turn_overhead"], 120)

    def test_unknown_project_dies(self):
        (self.root / "config.json").write_text(json.dumps(
            {"projects": [{"id": "known", "local_path": str(self.root), "enabled": True}]}),
            encoding="utf-8")
        code, _, err = self._run(["--project", "ghost"])
        self.assertEqual(code, 1)
        self.assertIn("не найден", err)

    def test_bad_weeks_dies(self):
        code, _, err = self._run(["--weeks", "abc"])
        self.assertEqual(code, 1)
        self.assertIn("--weeks", err)


if __name__ == "__main__":
    unittest.main()
