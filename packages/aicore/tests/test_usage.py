"""Tests aicore/usage.py — single transcript parser usage-metrics Claude Code.

Fixtures - inline events in the form of real JSONL-transcript lines
(~/.claude/projects/<slug>/*.jsonl). We separately protect the self-sufficiency of the module:
it is copied byte-for-byte into the hook without PYTHONPATH, therefore any
not-stdlib imports (from aicore... / from .).

Launch: bash packages/aicore/scripts/test.sh"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from aicore.usage import (feed_event, finish, iter_jsonl, merge, new_acc,
                          similar_ratio)

USAGE_PY = Path(__file__).resolve().parent.parent / "lib" / "aicore" / "usage.py"


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
             "message": {"content": "  Check usage-parser\nsecond line"}},
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
            # tool_result with an error - comes user-event
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": True, "content": "boom"}]}},
            # tool_result without error - NOT considered
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
        self.assertEqual(agg["model"], "claude-sonnet-4")  # latest model
        self.assertEqual(agg["models"], ["claude-opus-4", "claude-sonnet-4"])
        self.assertEqual(agg["label"], "Check usage-parser")
        self.assertAlmostEqual(agg["wall_seconds"], 65.0)
        # first_turn_overhead = input+cache_creation FIRST assistant-records (100+50),
        # not total for all (P5.3)
        self.assertEqual(agg["first_turn_overhead"], 150)

    def test_label_from_blocks_and_truncation(self):
        long_line = "x" * 200
        events = [{"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "noise"},
            {"type": "text", "text": "\n\n" + long_line + "\ntail"}]}}]
        agg = finish(_feed_all(events))
        self.assertEqual(agg["label"], "x" * 80)  # trim to 80 characters.
        # explicit label is more important than automatic
        self.assertEqual(finish(_feed_all(events), label="agent-1")["label"], "agent-1")

    def test_tolerant_to_garbage(self):
        # garbage events should not throw exceptions and do not affect amounts
        events = [
            None, 42, "string", [], {},
            {"type": "assistant"},                          # without message
            {"type": "assistant", "message": "not dict"},
            {"type": "assistant", "message": {"usage": "not dict", "model": 7}},
            _assistant(usage={"input_tokens": "trash", "output_tokens": None,
                              "cache_read_input_tokens": True},
                       content=[None, "string", {"type": "text", "text": 5},
                                {"type": "thinking"}]),
            {"type": "user", "message": {"content": [{"is_error": True}]}},  # not tool_result
            {"timestamp": 123},
        ]
        agg = finish(_feed_all(events))
        self.assertEqual(agg["in"], 0)
        self.assertEqual(agg["out"], 0)
        self.assertEqual(agg["cache_read"], 0)  # True — are not tokens
        self.assertEqual(agg["msgs"], 2)
        self.assertEqual(agg["tool_errors"], 0)
        self.assertEqual(agg["thinking_chars"], 0)
        self.assertEqual(agg["text_chars"], 0)
        self.assertEqual(agg["model"], "claude-opus-4")

    def test_first_turn_overhead_none_without_usage(self):
        # first assistant-entry without usage-block → first_turn_overhead remains None,
        # subsequent ones also do not overwrite it
        agg = finish(_feed_all([
            _assistant(content=[{"type": "text", "text": "no usage here"}]),
            _assistant(usage={"input_tokens": 5, "output_tokens": 1,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
        ]))
        self.assertIsNone(agg["first_turn_overhead"])
        self.assertEqual(agg["msgs"], 2)

    def test_wall_seconds_none_on_bad_ts(self):
        agg = finish(_feed_all([{"type": "user", "timestamp": "not a date",
                                 "message": {"content": "hi"}}]))
        self.assertIsNone(agg["wall_seconds"])
        # events with timestamp was not there at all
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
        # does not drop garbage in the list of agents merge
        self.assertIsNone(merge([None, "trash"])["cache_hit"])


class TestSimilarRatio(unittest.TestCase):
    def test_jaccard(self):
        self.assertAlmostEqual(similar_ratio("fix the parser", "fix the tests"),
                               2 / 4)  # {fix,the} / {fix,the,parser,tests}
        self.assertEqual(similar_ratio("same text", "same text"), 1.0)
        self.assertEqual(similar_ratio("alpha beta", "gamma delta"), 0.0)

    def test_empty_and_short_tokens(self):
        self.assertEqual(similar_ratio("", ""), 0.0)
        self.assertEqual(similar_ratio(None, None), 0.0)
        # single-character words are discarded → sets are empty → 0.0
        self.assertEqual(similar_ratio("a b c", "a b c"), 0.0)


class TestIterJsonl(unittest.TestCase):
    def test_skips_broken_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.jsonl"
            p.write_text('\n'.join([
                json.dumps({"type": "assistant"}),
                "{broken string",
                "",
                '"is just a string"',           # valid JSON, but not dict — pass
                json.dumps({"type": "user"}),
            ]), encoding="utf-8")
            recs = list(iter_jsonl(p))
            self.assertEqual([r["type"] for r in recs], ["assistant", "user"])

    def test_empty_and_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.jsonl"
            p.write_text("", encoding="utf-8")
            self.assertEqual(list(iter_jsonl(p)), [])
            self.assertEqual(list(iter_jsonl(Path(td) / "no-file.jsonl")), [])

    def test_stream_into_acc(self):
        # end-to-end script: file → iter_jsonl → feed_event → finish
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run.jsonl"
            lines = [
                json.dumps({"type": "user", "timestamp": "2026-07-02T09:00:00Z",
                            "message": {"content": "task"}}),
                "garbage not json",
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
            self.assertEqual(agg["label"], "task")
            self.assertAlmostEqual(agg["wall_seconds"], 10.0)


class TestSelfContained(unittest.TestCase):
    def test_no_forbidden_imports(self):
        """Protecting self-sufficiency: usage.py is copied to the hook without PYTHONPATH,
        therefore relative/aicore-imports would break it silently."""
        src = USAGE_PY.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*from\s+(?:core|aicore)\b", src, re.M),
                          "usage.py should not import from core or aicore")
        self.assertIsNone(re.search(r"^\s*from\s+\.", src, re.M),
                          "usage.py should not use relative imports")
        self.assertIsNone(re.search(r"^\s*import\s+(?:core|aicore)\b", src, re.M),
                          "usage.py should not import the package core or aicore")


if __name__ == "__main__":
    unittest.main()
