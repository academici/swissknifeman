"""Тесты analyze-run (analyze.py) — офлайн, на синтетических JSONL-событиях.

Проверяем чистые функции разбора транскрипта: агрегат токенов/инструментов/скиллов,
cache-hit, wall-clock, skill-usage (effective/dead), скан рантайм-маркеров,
нормализацию имени скилла, метку задачи, толерантный парсер. Без сети/реестра."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.analyze import (agent_stats, build_report, cache_hit,
                             parse_transcript, render_report, scan_markers,
                             skill_key, skill_usage, wall_seconds,
                             _first_user_text)


def _asst(usage, model="claude-haiku-4-5", tools=None, stop="end_turn", ts=None):
    content = [{"type": "tool_use", "name": n, "input": inp}
               for n, inp in (tools or [])]
    msg = {"role": "assistant", "model": model, "usage": usage,
           "stop_reason": stop, "content": content}
    e = {"type": "assistant", "message": msg}
    if ts:
        e["timestamp"] = ts
    return e


def _user(content, ts=None, is_error=False):
    if is_error:
        blocks = [{"type": "tool_result", "is_error": True}]
    elif isinstance(content, str):
        blocks = content
    else:
        blocks = content
    e = {"type": "user", "message": {"role": "user", "content": blocks}}
    if ts:
        e["timestamp"] = ts
    return e


class SkillKeyCase(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(skill_key("general/verify-claims"), "verify-claims")
        self.assertEqual(skill_key("skm:verify-claims"), "verify-claims")
        self.assertEqual(skill_key("anti-drift"), "anti-drift")


class ParseCase(unittest.TestCase):
    def test_tolerant_parser_skips_junk(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text('{"a":1}\n\nnot-json\n{"b":2}\n', encoding="utf-8")
            evs = parse_transcript(p)
            self.assertEqual(evs, [{"a": 1}, {"b": 2}])

    def test_missing_file(self):
        self.assertEqual(parse_transcript("/no/such/file.jsonl"), [])


class AgentStatsCase(unittest.TestCase):
    def setUp(self):
        self.events = [
            _asst({"input_tokens": 100, "output_tokens": 50,
                   "cache_read_input_tokens": 900, "iterations": 2},
                  tools=[("Read", {"file_path": "x"}),
                         ("Skill", {"skill": "general/verify-claims"})],
                  ts="2026-07-01T05:00:00.000Z"),
            _asst({"input_tokens": 200, "output_tokens": 80,
                   "cache_read_input_tokens": 100},
                  tools=[("Read", {"file_path": "y"}), ("Bash", {})],
                  stop="tool_use", ts="2026-07-01T05:05:00.000Z"),
            _user("irrelevant", is_error=True, ts="2026-07-01T05:02:00.000Z"),
        ]

    def test_token_sums(self):
        st = agent_stats(self.events, "a")
        self.assertEqual(st["in"], 300)
        self.assertEqual(st["out"], 130)
        self.assertEqual(st["cache_read"], 1000)
        self.assertEqual(st["iterations"], 2)

    def test_tools_and_skills(self):
        st = agent_stats(self.events, "a")
        self.assertEqual(st["tools"]["Read"], 2)
        self.assertEqual(st["tools"]["Bash"], 1)
        self.assertEqual(st["tools"]["Skill"], 1)
        self.assertEqual(st["skills"]["verify-claims"], 1)

    def test_stop_reasons_and_errors(self):
        st = agent_stats(self.events, "a")
        self.assertEqual(st["stop_reasons"], {"end_turn": 1, "tool_use": 1})
        self.assertEqual(st["tool_errors"], 1)

    def test_cache_hit(self):
        st = agent_stats(self.events, "a")
        # cache_read 1000 / (in 300 + cache_read 1000 + cache_creation 0)
        self.assertAlmostEqual(cache_hit(st), 1000 / 1300, places=4)

    def test_wall_seconds(self):
        st = agent_stats(self.events, "a")
        self.assertEqual(wall_seconds(st["ts_min"], st["ts_max"]), 300.0)


class SkillUsageCase(unittest.TestCase):
    def test_effective_dead_outside(self):
        a1 = agent_stats([_asst({}, tools=[("Skill", {"skill": "laravel"})])], "a1")
        a2 = agent_stats([_asst({}, tools=[("Skill", {"skill": "misc/other"})])], "a2")
        active = {"laravel", "anti-drift", "verify-claims"}
        u = skill_usage([a1, a2], active)
        self.assertIn("laravel", u["effective"])       # активный + загружен
        self.assertIn("anti-drift", u["dead"])          # активный, 0 загрузок
        self.assertIn("verify-claims", u["dead"])
        self.assertIn("other", u["loaded_outside"])     # загружен, но вне набора

    def test_no_active_set_all_dead_empty(self):
        a = agent_stats([_asst({}, tools=[("Skill", {"skill": "laravel"})])], "a")
        u = skill_usage([a], set())
        self.assertEqual(u["dead"], [])
        self.assertEqual(u["loaded_outside"], ["laravel"])


class MarkersCase(unittest.TestCase):
    def test_scan_and_context(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.jsonl"
            # один маркер на строку (break после первого) — по строке на сигнал
            p.write_text(
                'xxx failed: Rate limited yyy\n'
                'clean line\n'
                'zzz Rate limited again\n'
                'boom: API Error occurred\n', encoding="utf-8")
            mk = scan_markers([p])
            self.assertEqual(mk["counts"]["Rate limited"], 2)
            self.assertEqual(mk["counts"]["API Error"], 1)
            self.assertTrue(all("Rate limited" in s or "API Error" in s
                                for s in mk["sample"]))


class LabelCase(unittest.TestCase):
    def test_first_user_text_string_and_blocks(self):
        self.assertEqual(_first_user_text([_user("Explore workflow docs\nmore")]),
                         "Explore workflow docs")
        self.assertEqual(
            _first_user_text([_user([{"type": "text", "text": "  Do a thing  "}])]),
            "Do a thing")
        self.assertIsNone(_first_user_text([_asst({})]))


class RenderCase(unittest.TestCase):
    def test_render_smoke(self):
        a = agent_stats(
            [_asst({"input_tokens": 1200, "output_tokens": 400,
                    "cache_read_input_tokens": 3000},
                   model="claude-opus-4-8", tools=[("Edit", {})],
                   ts="2026-07-01T05:00:00Z")], "impl:forum-4")
        report = {
            "session": "sess", "project": "/p", "logs_root": "/l",
            "agents": [a], "totals": {"in": 1200, "out": 400,
                                      "cache_read": 3000, "cache_creation": 0},
            "wall_seconds": 120.0,
            "skills": {"loaded": {}, "effective": [], "dead": ["anti-drift"],
                       "loaded_outside": []},
            "active_note": None,
            "markers": {"counts": {"Rate limited": 1}, "sample": ["… Rate limited"]},
        }
        txt = render_report(report)
        self.assertIn("ПОСТ-РАН РАЗБОР", txt)
        self.assertIn("impl:forum-4", txt)
        self.assertIn("DEAD", txt)
        self.assertIn("opus", txt)


class BuildReportCase(unittest.TestCase):
    def test_missing_logs_returns_error(self):
        # env-заглушка: .home указывает в пустой tmp → логов нет.
        class _Env:
            def __init__(self, home):
                self.home = Path(home)
        with tempfile.TemporaryDirectory() as d:
            rep, err = build_report(_Env(d), Path("/nonexistent/project"))
            self.assertIsNone(rep)
            self.assertIn("не найдены", err)


if __name__ == "__main__":
    unittest.main()
