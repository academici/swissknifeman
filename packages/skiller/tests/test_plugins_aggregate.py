"""Тесты `skiller.plugins` / `skiller budget --with-plugins` (2026.07.31-SKM-LEAN
P1.1). Фикстуры — дословный вывод живого `claude` 2.1.220 (`claude plugin list
--json` / `claude plugin details <id>`, captured 2026-07-31), подставляются
через `SKM_CLAUDE_BIN` (тот же паттерн, что online-тесты `test_eval.py`). Никакой
живой сети/CLI в CI — фейковый бинарь читает вшитые в скрипт литералы."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller import plugins as pl
from skiller.budget import cmd_budget
import tests.fixtures as fx

FIXTURES_DATA = Path(__file__).resolve().parent / "fixtures_data"
LIST_FIXTURE = (FIXTURES_DATA / "plugin-list.json").read_text(encoding="utf-8")
CODEX_DETAILS = (FIXTURES_DATA / "plugin-details-codex.txt").read_text(encoding="utf-8")

# id -> (stdout, exit_code). task@swissknifeman и codex — валидные ответы;
# brain@brain дословно несёт дрейф формата (`~1.1k`, как в per-component
# таблице зонда, но НЕ в строке Always-on — регэксп якорится на целые токены).
DETAILS = {
    "codex@openai-codex": (CODEX_DETAILS, 0),
    "task@swissknifeman": ("task 0.9.0\n\nProjected token cost\n"
                           "  Always-on:   ~100 tok   added to every session\n", 0),
    "brain@brain": ("brain 1.0.0\n\nProjected token cost\n"
                    "  Always-on:   ~1.1k tok   added to every session\n", 0),
}


def _write_fake_plugin_cli(tmp_dir, *, list_payload=LIST_FIXTURE, list_exit=0,
                           details=None):
    """Фейковый `claude` (SKM_CLAUDE_BIN): `plugin list --json` -> list_payload/
    list_exit; `plugin details <id>` -> details[id] (по умолчанию — код 1,
    пустой вывод, как недокументированный/незнакомый CLI-ответ)."""
    script = tmp_dir / "fake_claude_plugins.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"LIST_PAYLOAD = {list_payload!r}\n"
        f"LIST_EXIT = {list_exit!r}\n"
        f"DETAILS = {(details if details is not None else DETAILS)!r}\n"
        "argv = sys.argv[1:]\n"
        "if argv[:2] == ['plugin', 'list']:\n"
        "    sys.stdout.write(LIST_PAYLOAD)\n"
        "    sys.exit(LIST_EXIT)\n"
        "if argv[:2] == ['plugin', 'details'] and len(argv) >= 3:\n"
        "    text, code = DETAILS.get(argv[2], ('', 1))\n"
        "    sys.stdout.write(text)\n"
        "    sys.exit(code)\n"
        "sys.exit(1)\n",
        encoding="utf-8")
    script.chmod(0o755)
    return script


class PluginsAggregateCase(unittest.TestCase):
    """`plugins_summary` напрямую — без CLI-обвязки `cmd_budget`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        pl._details_cache.clear()
        self._old_env = os.environ.get("SKM_CLAUDE_BIN")

    def tearDown(self):
        pl._details_cache.clear()
        if self._old_env is None:
            os.environ.pop("SKM_CLAUDE_BIN", None)
        else:
            os.environ["SKM_CLAUDE_BIN"] = self._old_env
        self._tmp.cleanup()

    def _use_fake(self, **kwargs):
        os.environ["SKM_CLAUDE_BIN"] = str(_write_fake_plugin_cli(self.tmp, **kwargs))

    def test_happy_path_sum_dedup_exclusion_and_warnings(self):
        self._use_fake()
        summary = pl.plugins_summary(self.proj)
        self.assertEqual(summary["status"], "ok")
        ids = sorted(e["id"] for e in summary["entries"])
        # ai@swissknifeman (enabled:false) исключён; task@swissknifeman дважды
        # в листинге (scope local/project) — дедуп по id даёт ОДНУ запись.
        self.assertEqual(ids, ["brain@brain", "codex@openai-codex", "task@swissknifeman"])
        # happy-path сумма: codex(449) + task(100); brain не распознан (drift) —
        # unparsed, вне суммы; молчаливого 0 нет — total считает только 549.
        self.assertEqual(summary["total"], 549)
        self.assertTrue(summary["partial"])
        self.assertTrue(any("brain@brain" in u for u in summary["unparsed"]))
        # errors из записи листинга brain@brain доезжают до warnings[]
        self.assertTrue(any("brain@brain" in w for w in summary["warnings"]))

    def test_always_on_suffix_format_is_not_guessed(self):
        # Implementation Rules §Code Guidance: суффикс (~1.1k) НЕ наблюдался в
        # замере и не угадывается — уходит в unparsed, а не домножается.
        tokens, error = None, None
        with mock.patch.object(pl, "claude_bin", return_value=str(
                _write_fake_plugin_cli(self.tmp, details={"x@y": (
                    "Always-on:   ~1.1k tok   added to every session\n", 0)}))):
            tokens, error = pl.plugin_always_on_tokens("x@y")
        self.assertIsNone(tokens)
        self.assertIn("не распознана", error)

    def test_missing_claude_binary_gives_na_not_zero(self):
        with mock.patch.object(pl, "claude_bin", return_value=None):
            summary = pl.plugins_summary(self.proj)
        self.assertEqual(summary["status"], "n/a")
        self.assertIsNone(summary["total"])
        self.assertTrue(summary["partial"])
        self.assertTrue(summary["warnings"])

    def test_listing_failure_gives_na_not_zero(self):
        self._use_fake(list_payload="", list_exit=1)
        summary = pl.plugins_summary(self.proj)
        self.assertEqual(summary["status"], "n/a")
        self.assertIsNone(summary["total"])

    def test_details_cached_per_run(self):
        # `details` CWD-независим — один вызов на УНИКАЛЬНЫЙ id, не на пару
        # проект×плагин (D14 §5).
        self._use_fake()
        calls = []
        real_run = pl._run_claude

        def _counting_run(argv, **kw):
            calls.append(tuple(argv))
            return real_run(argv, **kw)

        with mock.patch.object(pl, "_run_claude", side_effect=_counting_run):
            pl.plugin_always_on_tokens("codex@openai-codex")
            pl.plugin_always_on_tokens("codex@openai-codex")
        self.assertEqual(len(calls), 1)


class PluginsCliIntegrationCase(unittest.TestCase):
    """`skiller budget --first-turn --with-plugins` — аддитивность JSON (D16) и
    `die` при флаге без `--first-turn`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_root, self.env = fx.make_registry(self.tmp)
        self.proj = self.tmp / "myproj"
        self.proj.mkdir()
        (self.proj / ".swissknife.json").write_text(
            json.dumps({"buckets": ["quality"]}), encoding="utf-8")
        (self.proj / "CLAUDE.md").write_text("word " * 40, encoding="utf-8")
        pl._details_cache.clear()
        self._old_env = os.environ.get("SKM_CLAUDE_BIN")
        os.environ["SKM_CLAUDE_BIN"] = str(_write_fake_plugin_cli(self.tmp))

    def tearDown(self):
        pl._details_cache.clear()
        if self._old_env is None:
            os.environ.pop("SKM_CLAUDE_BIN", None)
        else:
            os.environ["SKM_CLAUDE_BIN"] = self._old_env
        self._tmp.cleanup()

    def test_with_plugins_without_first_turn_dies(self):
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cmd_budget(self.env, ["--with-plugins", "--target", str(self.proj)])

    def test_back_compat_key_set_unchanged_without_flag(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--first-turn", "--target", str(self.proj), "--json"])
        data = json.loads(buf.getvalue())
        self.assertEqual(set(data), {"target", "sources", "total", "verdict"})

    def test_with_plugins_json_is_additive(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--first-turn", "--with-plugins",
                                 "--target", str(self.proj), "--json"])
        data = json.loads(buf.getvalue())
        self.assertEqual({"target", "sources", "total", "verdict", "plugins",
                          "session_total", "session_verdict"}, set(data))
        self.assertEqual(data["plugins"]["total"], 549)
        self.assertEqual(data["session_total"], data["total"] + 549)
        self.assertGreater(data["session_total"], data["total"])


if __name__ == "__main__":
    unittest.main()
