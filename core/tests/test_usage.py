"""Тесты core/usage.py — единого транскрипт-парсера usage-метрик Claude Code.

Фикстуры — инлайн-события в форме реальных JSONL-строк транскриптов
(~/.claude/projects/<slug>/*.jsonl). Отдельно охраняем самодостаточность модуля:
он копируется байт-в-байт в хук без PYTHONPATH, поэтому запрещены любые
не-stdlib импорты (from core... / from .).

Запуск: PYTHONPATH=<корень монорепо> python3 -m unittest discover -s core/tests"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from core.usage import (feed_event, finish, iter_jsonl, merge, new_acc,
                        similar_ratio)

USAGE_PY = Path(__file__).resolve().parent.parent / "usage.py"


def _assistant(model="claude-opus-4", usage=None, content=None, ts=None):
    ev = {"type": "assistant", "message": {"model": model}}
    if usage is not None:
        ev["message"]["usage"] = usage
    if content is not None:
        ev["message"]["content"] = content
    if ts is not None:
        ev["timestamp"] = ts
    return ev


def _feed_all(events):
    acc = new_acc()
    for ev in events:
        feed_event(acc, ev)
    return acc


class TestFeedFinish(unittest.TestCase):
    def test_sums_usage_and_chars(self):
        events = [
            {"type": "user", "timestamp": "2026-07-02T10:00:00Z",
             "message": {"content": "  Проверь usage-парсер\nвторая строка"}},
            _assistant(ts="2026-07-02T10:00:05Z",
                       usage={"input_tokens": 100, "output_tokens": 20,
                              "cache_read_input_tokens": 300,
                              "cache_creation_input_tokens": 50},
                       content=[{"type": "thinking", "thinking": "abcd"},
                                {"type": "text", "text": "ok!"},
                                {"type": "tool_use", "name": "Bash"}]),
            _assistant(model="claude-sonnet-4", ts="2026-07-02T10:01:05Z",
                       usage={"input_tokens": 10, "output_tokens": 5,
                              "cache_read_input_tokens": 0,
                              "cache_creation_input_tokens": 0},
                       content=[{"type": "text", "text": "done"}]),
            # tool_result с ошибкой — приходит user-событием
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": True, "content": "boom"}]}},
            # tool_result без ошибки — НЕ считается
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": False, "content": "fine"}]}},
        ]
        agg = finish(_feed_all(events))
        self.assertEqual(agg["in"], 110)
        self.assertEqual(agg["out"], 25)
        self.assertEqual(agg["cache_read"], 300)
        self.assertEqual(agg["cache_creation"], 50)
        self.assertEqual(agg["msgs"], 2)
        self.assertEqual(agg["thinking_chars"], 4)
        self.assertEqual(agg["text_chars"], 3 + 4)
        self.assertEqual(agg["tool_errors"], 1)
        self.assertEqual(agg["model"], "claude-sonnet-4")  # последняя модель
        self.assertEqual(agg["models"], ["claude-opus-4", "claude-sonnet-4"])
        self.assertEqual(agg["label"], "Проверь usage-парсер")
        self.assertAlmostEqual(agg["wall_seconds"], 65.0)
        # first_turn_overhead = input+cache_creation ПЕРВОЙ assistant-записи (100+50),
        # не суммарно по всем (P5.3)
        self.assertEqual(agg["first_turn_overhead"], 150)

    def test_label_from_blocks_and_truncation(self):
        long_line = "x" * 200
        events = [{"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "noise"},
            {"type": "text", "text": "\n\n" + long_line + "\nхвост"}]}}]
        agg = finish(_feed_all(events))
        self.assertEqual(agg["label"], "x" * 80)  # обрезка до 80 симв.
        # явный label важнее автоматического
        self.assertEqual(finish(_feed_all(events), label="agent-1")["label"], "agent-1")

    def test_tolerant_to_garbage(self):
        # мусорные события не должны бросать исключений и не влияют на суммы
        events = [
            None, 42, "строка", [], {},
            {"type": "assistant"},                          # без message
            {"type": "assistant", "message": "не dict"},
            {"type": "assistant", "message": {"usage": "не dict", "model": 7}},
            _assistant(usage={"input_tokens": "мусор", "output_tokens": None,
                              "cache_read_input_tokens": True},
                       content=[None, "строка", {"type": "text", "text": 5},
                                {"type": "thinking"}]),
            {"type": "user", "message": {"content": [{"is_error": True}]}},  # не tool_result
            {"timestamp": 123},
        ]
        agg = finish(_feed_all(events))
        self.assertEqual(agg["in"], 0)
        self.assertEqual(agg["out"], 0)
        self.assertEqual(agg["cache_read"], 0)  # True — не токены
        self.assertEqual(agg["msgs"], 2)
        self.assertEqual(agg["tool_errors"], 0)
        self.assertEqual(agg["thinking_chars"], 0)
        self.assertEqual(agg["text_chars"], 0)
        self.assertEqual(agg["model"], "claude-opus-4")

    def test_first_turn_overhead_none_without_usage(self):
        # первая assistant-запись без usage-блока → first_turn_overhead остаётся None,
        # последующие тоже её не перезаписывают
        agg = finish(_feed_all([
            _assistant(content=[{"type": "text", "text": "no usage here"}]),
            _assistant(usage={"input_tokens": 5, "output_tokens": 1,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
        ]))
        self.assertIsNone(agg["first_turn_overhead"])
        self.assertEqual(agg["msgs"], 2)

    def test_wall_seconds_none_on_bad_ts(self):
        agg = finish(_feed_all([{"type": "user", "timestamp": "не дата",
                                 "message": {"content": "hi"}}]))
        self.assertIsNone(agg["wall_seconds"])
        # событий с timestamp не было вовсе
        self.assertIsNone(finish(new_acc())["wall_seconds"])


class TestMerge(unittest.TestCase):
    def test_totals_by_model_cache_hit(self):
        a1 = finish(_feed_all([
            _assistant(usage={"input_tokens": 100, "output_tokens": 10,
                              "cache_read_input_tokens": 300,
                              "cache_creation_input_tokens": 0})]))
        a2 = finish(_feed_all([
            _assistant(model="claude-sonnet-4",
                       usage={"input_tokens": 100, "output_tokens": 30,
                              "cache_read_input_tokens": 100,
                              "cache_creation_input_tokens": 40}),
            _assistant(model="claude-sonnet-4",
                       usage={"input_tokens": 0, "output_tokens": 1,
                              "cache_read_input_tokens": 0,
                              "cache_creation_input_tokens": 0})]))
        res = merge([a1, a2])
        self.assertEqual(res["totals"],
                         {"in": 200, "out": 41, "cache_read": 400, "cache_creation": 40})
        self.assertEqual(res["by_model"]["claude-opus-4"]["in"], 100)
        self.assertEqual(res["by_model"]["claude-opus-4"]["msgs"], 1)
        self.assertEqual(res["by_model"]["claude-sonnet-4"]["out"], 31)
        self.assertEqual(res["by_model"]["claude-sonnet-4"]["msgs"], 2)
        # cache_hit = cache_read / (cache_read + in) = 400/600
        self.assertAlmostEqual(res["cache_hit"], 400 / 600)

    def test_cache_hit_none_on_zero(self):
        res = merge([])
        self.assertIsNone(res["cache_hit"])
        self.assertEqual(res["totals"]["in"], 0)
        self.assertEqual(res["by_model"], {})
        # мусор в списке агентов не роняет merge
        self.assertIsNone(merge([None, "мусор"])["cache_hit"])


class TestSimilarRatio(unittest.TestCase):
    def test_jaccard(self):
        self.assertAlmostEqual(similar_ratio("fix the parser", "fix the tests"),
                               2 / 4)  # {fix,the} / {fix,the,parser,tests}
        self.assertEqual(similar_ratio("одинаковый текст", "одинаковый текст"), 1.0)
        self.assertEqual(similar_ratio("alpha beta", "gamma delta"), 0.0)

    def test_empty_and_short_tokens(self):
        self.assertEqual(similar_ratio("", ""), 0.0)
        self.assertEqual(similar_ratio(None, None), 0.0)
        # односимвольные слова отбрасываются → множества пусты → 0.0
        self.assertEqual(similar_ratio("a b c", "a b c"), 0.0)


class TestIterJsonl(unittest.TestCase):
    def test_skips_broken_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.jsonl"
            p.write_text('\n'.join([
                json.dumps({"type": "assistant"}),
                "{битая строка",
                "",
                '"просто строка"',           # валидный JSON, но не dict — пропуск
                json.dumps({"type": "user"}),
            ]), encoding="utf-8")
            recs = list(iter_jsonl(p))
            self.assertEqual([r["type"] for r in recs], ["assistant", "user"])

    def test_empty_and_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.jsonl"
            p.write_text("", encoding="utf-8")
            self.assertEqual(list(iter_jsonl(p)), [])
            self.assertEqual(list(iter_jsonl(Path(td) / "нет-файла.jsonl")), [])

    def test_stream_into_acc(self):
        # сквозной сценарий: файл → iter_jsonl → feed_event → finish
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run.jsonl"
            lines = [
                json.dumps({"type": "user", "timestamp": "2026-07-02T09:00:00Z",
                            "message": {"content": "задача"}}),
                "мусор не json",
                json.dumps(_assistant(usage={"input_tokens": 7, "output_tokens": 3,
                                             "cache_read_input_tokens": 0,
                                             "cache_creation_input_tokens": 0},
                                      ts="2026-07-02T09:00:10Z")),
            ]
            p.write_text("\n".join(lines), encoding="utf-8")
            acc = new_acc()
            for ev in iter_jsonl(p):
                feed_event(acc, ev)
            agg = finish(acc)
            self.assertEqual(agg["in"], 7)
            self.assertEqual(agg["label"], "задача")
            self.assertAlmostEqual(agg["wall_seconds"], 10.0)


class TestSelfContained(unittest.TestCase):
    def test_no_forbidden_imports(self):
        """Охрана самодостаточности: usage.py копируется в хук без PYTHONPATH,
        поэтому relative/core-импорты его сломали бы молча."""
        src = USAGE_PY.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*from\s+core\b", src, re.M),
                          "usage.py не должен импортировать из core")
        self.assertIsNone(re.search(r"^\s*from\s+\.", src, re.M),
                          "usage.py не должен использовать относительные импорты")
        self.assertIsNone(re.search(r"^\s*import\s+core\b", src, re.M),
                          "usage.py не должен импортировать пакет core")


if __name__ == "__main__":
    unittest.main()
