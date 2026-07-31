"""Тесты first_turn_report / `skiller budget --first-turn` (P5.1).

Синтетический проект в tmpdir (settings.json со stub-хуком, .claude/agents,
CLAUDE.md, .mcp.json) — проверяем слагаемые, вердикт по порогам 3-7K/10K,
fail-soft на сломанном хуке (n/a, не исключение) и CLI (--json/--strict)."""
import contextlib
import io
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.budget import cmd_budget, first_turn_report
import tests.fixtures as fx


def _write_hook(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class FirstTurnReportCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_root, self.env = fx.make_registry(self.tmp)
        self.proj = self.tmp / "myproj"
        self.proj.mkdir()
        # проект использует бакет quality явно (независимо от autodetect)
        (self.proj / ".swissknife.json").write_text(
            json.dumps({"buckets": ["quality"]}), encoding="utf-8")
        (self.proj / "CLAUDE.md").write_text("word " * 40, encoding="utf-8")
        agents = self.proj / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: Reviews code changes\n---\nBody\n",
            encoding="utf-8")
        _write_hook(self.proj / ".claude" / "hooks" / "stub.sh",
                   "#!/usr/bin/env bash\n"
                   "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\","
                   "\"additionalContext\":\"fixed session digest text\"}}'\n")
        (self.proj / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "bash .claude/hooks/stub.sh"}]}]}}),
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_sums_all_sources_and_verdict_ok(self):
        report = first_turn_report(self.env, self.proj)
        s = report["sources"]
        self.assertGreater(s["skills"]["tokens"], 0)   # quality-бакет непуст
        self.assertGreater(s["agents"]["tokens"], 0)   # reviewer.md
        self.assertGreater(s["claude_md"]["tokens"], 0)
        self.assertGreater(s["hooks"]["tokens"], 0)    # живой прогон stub.sh
        self.assertEqual(s["mcp"]["tokens"], 0)        # нет .mcp.json
        expected_total = sum(s[k]["tokens"] for k in s)
        self.assertEqual(report["total"], expected_total)
        self.assertEqual(report["verdict"], "OK")      # синтетика << 16K

    def test_broken_hook_is_na_not_exception(self):
        _write_hook(self.proj / ".claude" / "hooks" / "broken.sh",
                   "#!/usr/bin/env bash\nexit 1\n")
        (self.proj / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "bash .claude/hooks/broken.sh"}]}]}}),
            encoding="utf-8")
        report = first_turn_report(self.env, self.proj)  # не должно бросить исключение
        self.assertIsNone(report["sources"]["hooks"]["tokens"])
        self.assertIn("n/a", report["sources"]["hooks"]["detail"])
        # total не учитывает n/a-источник, но остальные слагаемые суммируются
        self.assertGreater(report["total"], 0)

    def test_no_settings_json_reports_zero_hooks(self):
        (self.proj / ".claude" / "settings.json").unlink()
        report = first_turn_report(self.env, self.proj)
        self.assertEqual(report["sources"]["hooks"], {
            "tokens": 0, "detail": "нет SessionStart-хуков"})

    def test_known_and_unknown_mcp_servers(self):
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "maind": {"command": "maind"},
            "totally-unknown-server": {"command": "x"}}}), encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        # maind (11 tools) + неизвестный (fallback) — обе учтены, > 0
        self.assertGreater(mcp["tokens"], 11 * 150)
        self.assertIn("maind", mcp["detail"])
        self.assertIn("totally-unknown-server", mcp["detail"])

    def test_listing_entry_capped_at_1536_chars(self):
        # first-party: "combined description and when_to_use text is truncated
        # at 1,536 characters" — запись длиннее капа не должна давать больше
        # токенов, чем капнутый текст.
        from skiller.budget import _listing_entry_tokens, estimate_tokens
        d = self.registry_root / "skills" / "quality" / "long-desc"
        long_desc = "x " * 2000  # 4000 симв, заведомо > 1536
        fx.write_skill(d, "long-desc", description=long_desc)
        capped_expected = estimate_tokens("long-desc") + estimate_tokens(
            long_desc[:1536])
        self.assertEqual(_listing_entry_tokens(d), capped_expected)
        self.assertLess(_listing_entry_tokens(d), estimate_tokens(
            "long-desc " + long_desc))  # некапнутая сумма была бы больше

    def test_listing_budget_caps_raw_sum_and_reports_both(self):
        # бюджет листинга — потолок, не сумма всех описаний (D22 переучёт):
        # заведомо тесный бюджет форсирует raw > budget → resident == budget.
        report = first_turn_report(self.env, self.proj,
                                   listing_fraction=0.0001,
                                   listing_context_window=1_000)
        s = report["sources"]["skills"]
        self.assertEqual(s["listing_budget"], 0)  # int(1000*0.0001) == 0
        self.assertEqual(s["tokens"], 0)
        self.assertGreater(s["raw_tokens"], s["tokens"])
        self.assertIn("бюджет", s["detail"])

    def test_listing_fraction_is_a_parameter_not_a_constant(self):
        narrow = first_turn_report(self.env, self.proj, listing_fraction=0.0001,
                                   listing_context_window=1_000)
        wide = first_turn_report(self.env, self.proj, listing_fraction=1.0,
                                 listing_context_window=1_000_000)
        self.assertLess(narrow["sources"]["skills"]["listing_budget"],
                        wide["sources"]["skills"]["listing_budget"])
        self.assertLessEqual(narrow["sources"]["skills"]["tokens"],
                             wide["sources"]["skills"]["tokens"])

    def test_rules_with_paths_excluded_from_claude_md(self):
        no_rules = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        rules = self.proj / ".claude" / "rules"
        rules.mkdir(parents=True)
        (rules / "scoped.md").write_text(
            "---\npaths:\n  - \"**/tests/**\"\n---\n" + "scoped rule body " * 200,
            encoding="utf-8")
        with_scoped = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        # path-scoped rule (scoped.md) не даёт вклада — токены не выросли
        self.assertEqual(with_scoped["tokens"], no_rules["tokens"])
        (rules / "always.md").write_text(
            "---\nversion: 1\n---\n" + "always-on rule body " * 200,
            encoding="utf-8")
        with_always = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        # always-on rule (без paths) даёт вклад — рост целиком от always.md
        self.assertGreater(with_always["tokens"], with_scoped["tokens"])

    def test_verdict_ladder_matches_declared_thresholds(self):
        # лестница пиновывается ПОИМЁННО на своих границах: пере-издание порога
        # (P1.3 Implementation Rules §6) обязано ронять этот кейс, а не тихо
        # менять смысл вердикта у флота и у `maind doctor --context`.
        from skiller.budget import (FIRST_TURN_TARGET_MAX, FIRST_TURN_WARN,
                                    _first_turn_verdict)
        self.assertEqual((FIRST_TURN_TARGET_MAX, FIRST_TURN_WARN), (16_000, 23_000))
        self.assertEqual(_first_turn_verdict(FIRST_TURN_TARGET_MAX), "OK")
        self.assertEqual(_first_turn_verdict(FIRST_TURN_TARGET_MAX + 1), "ELEVATED")
        self.assertEqual(_first_turn_verdict(FIRST_TURN_WARN), "ELEVATED")
        self.assertEqual(_first_turn_verdict(FIRST_TURN_WARN + 1), "WARN")

    def test_verdict_warn_above_threshold_and_strict_cli_exits(self):
        # раздуваем CLAUDE.md заведомо выше warn-порога; объём выводится ИЗ
        # константы, иначе при следующем пере-издании порога тест «просто
        # перестанет падать» вместо того, чтобы потребовать разбора.
        from skiller.budget import FIRST_TURN_WARN, estimate_tokens
        chunk = "padding word "
        (self.proj / "CLAUDE.md").write_text(
            chunk * (2 * FIRST_TURN_WARN // estimate_tokens(chunk) + 1),
            encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        self.assertGreater(report["total"], FIRST_TURN_WARN)
        self.assertEqual(report["verdict"], "WARN")
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                cmd_budget(self.env, ["--first-turn", "--target", str(self.proj),
                                     "--strict"])

    def test_cli_json_output_shape(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--first-turn", "--target", str(self.proj), "--json"])
        data = json.loads(buf.getvalue())
        self.assertIn("total", data)
        self.assertIn("verdict", data)
        self.assertEqual(set(data["sources"]),
                         {"skills", "agents", "claude_md", "hooks", "mcp"})


if __name__ == "__main__":
    unittest.main()
