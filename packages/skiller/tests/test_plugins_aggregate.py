"""Tests `aicore.delivery.claude` plugin visibility / `skiller budget --with-plugins` (
P1.1). Fixtures - literal output of a living `claude` 2.1.220 (`claude plugin list
--json` / `claude plugin details <id>`, captured 2026-07-31), are substituted
via `SKM_CLAUDE_BIN` (same pattern as online-tests `test_eval.py`). None
live network/CLI in CI — fake binary reads literals embedded in the script."""
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

from skiller.budget import cmd_budget
from aicore.delivery import claude as aicore_claude
import tests.fixtures as fx

FIXTURES_DATA = Path(__file__).resolve().parent / "fixtures_data"
LIST_FIXTURE = (FIXTURES_DATA / "plugin-list.json").read_text(encoding="utf-8")
CODEX_DETAILS = (FIXTURES_DATA / "plugin-details-codex.txt").read_text(encoding="utf-8")
ARCHITECT_DETAILS = (FIXTURES_DATA / "plugin-details-architect.txt").read_text(encoding="utf-8")

# id -> (stdout, exit_code). task@swissknifeman and codex — valid responses;
# brain@brain literally carries a living fact P1.4 (`findings/P1-plugins-cwd-defect-
# 2026-07-31.md` §5): listing declares the plugin to be a broken field `errors`, a
# `claude plugin details brain@brain` replies "not found" (rc=1) from ANY
# cwd — source for class `broken`, and not format drift.
DETAILS = {
    "codex@openai-codex": (CODEX_DETAILS, 0),
    "task@swissknifeman": ("task 0.9.0\n\nProjected token cost\n"
                           "  Always-on:   ~100 tok   added to every session\n", 0),
    "brain@brain": ('Plugin "brain@brain" not found. Run `claude plugin list` to see '
                    "installed plugins, or pass --plugin-dir <path> to load one from disk.\n", 1),
}


def _write_fake_plugin_cli(tmp_dir, *, list_payload=LIST_FIXTURE, list_exit=0,
                           details=None):
    """Fake `claude` (SKM_CLAUDE_BIN): `plugin list --json` -> list_payload/
    list_exit; `plugin details <id>` -> details[id] (default - code 1,
    empty output as undocumented/unfamiliar CLI-response)."""
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


def _write_cwd_gated_details_cli(tmp_dir, plugin_id, expected_cwd, success_text):
    """Fake `claude` for `details`, resolving `plugin_id` ONLY under
    `expected_cwd` (P1.4 §1 — local-scope plugin of someone else's project does not resolve
    without `cwd`): checks `os.getcwd()`, and not that the argument was passed
    line - a dummy case, green BEFORE editing, does not protect anything."""
    script = tmp_dir / "fake_claude_cwd_gated.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        f"PLUGIN_ID = {plugin_id!r}\n"
        f"EXPECTED_CWD = {str(expected_cwd)!r}\n"
        f"SUCCESS_TEXT = {success_text!r}\n"
        "argv = sys.argv[1:]\n"
        "if argv[:2] == ['plugin', 'details'] and len(argv) >= 3 and argv[2] == PLUGIN_ID:\n"
        "    if os.getcwd() == EXPECTED_CWD:\n"
        "        sys.stdout.write(SUCCESS_TEXT)\n"
        "        sys.exit(0)\n"
        "    sys.stdout.write('Plugin \"' + PLUGIN_ID + '\" not found.\\n')\n"
        "    sys.exit(1)\n"
        "sys.exit(1)\n",
        encoding="utf-8")
    script.chmod(0o755)
    return script


class PluginsAggregateCase(unittest.TestCase):
    """`plugins_summary` directly - without CLI-strapping `cmd_budget`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        aicore_claude._details_cache.clear()
        self._old_env = os.environ.get("SKM_CLAUDE_BIN")

    def tearDown(self):
        aicore_claude._details_cache.clear()
        if self._old_env is None:
            os.environ.pop("SKM_CLAUDE_BIN", None)
        else:
            os.environ["SKM_CLAUDE_BIN"] = self._old_env
        self._tmp.cleanup()

    def _use_fake(self, **kwargs):
        os.environ["SKM_CLAUDE_BIN"] = str(_write_fake_plugin_cli(self.tmp, **kwargs))

    def test_happy_path_sum_dedup_exclusion_and_broken(self):
        self._use_fake()
        summary = aicore_claude.plugins_summary(self.proj)
        self.assertEqual(summary["status"], "ok")
        ids = sorted(e["id"] for e in summary["entries"])
        # ai@swissknifeman (enabled:false) excluded; task@swissknifeman twice
        # in the listing (scope local/project) — dedup by id gives ONE entry.
        self.assertEqual(ids, ["brain@brain", "codex@openai-codex", "task@swissknifeman"])
        # happy-path amount: codex(449) + task(100); brain — announced
        # broken listing (errors) AND details did not give a price → broken, NOT
        # unparsed; silent 0 no — total only counts 549.
        self.assertEqual(summary["total"], 549)
        self.assertTrue(summary["partial"])
        self.assertEqual(summary["unparsed"], [])
        self.assertEqual(len(summary["broken"]), 1)
        self.assertEqual(summary["broken"][0]["id"], "brain@brain")
        self.assertIn("invalid manifest", summary["broken"][0]["reason"])
        # broken is not duplicated in warnings — is a SEPARATE class of incompleteness.
        self.assertFalse(any("brain@brain" in w for w in summary["warnings"]))

    def test_errors_entry_that_resolves_counts_in_total_and_warnings(self):
        # Implementation Rules §4: record with errors, STILL paid the price, -
        # normal (in total), errors remains in warnings, NOT in broken.
        self._use_fake(details={
            "codex@openai-codex": (CODEX_DETAILS, 0),
            "task@swissknifeman": ("task 0.9.0\n\nProjected token cost\n"
                                   "  Always-on:   ~100 tok   added to every session\n", 0),
            "brain@brain": ("brain 1.0.0\n\nProjected token cost\n"
                            "  Always-on:   ~42 tok   added to every session\n", 0),
        })
        summary = aicore_claude.plugins_summary(self.proj)
        self.assertEqual(summary["total"], 449 + 100 + 42)
        self.assertEqual(summary["broken"], [])
        self.assertTrue(any("brain@brain" in w for w in summary["warnings"]))

    def test_always_on_suffix_format_is_not_guessed(self):
        # Implementation Rules §Code Guidance: suffix (~1.1k) NOT observed in
        # measured and not guessed - goes into unparsed (not broken — entry without
        # errors listing), and not multiplied.
        with mock.patch.object(aicore_claude, "claude_bin", return_value=str(
                _write_fake_plugin_cli(self.tmp, details={"x@y": (
                    "Always-on:   ~1.1k tok   added to every session\n", 0)}))):
            tokens, error = aicore_claude.plugin_always_on_tokens("x@y", self.proj)
        self.assertIsNone(tokens)
        self.assertIn("not recognized", error)

    def test_thousands_separator_is_parsed(self):
        # P1.4 §1/§3: cwd forwarded to `details`, `~1,275` parses 1275
        # (was unparsed until repaired) — fixture for verbatim live output.
        script = _write_fake_plugin_cli(self.tmp, details={
            "architect@swissknifeman": (ARCHITECT_DETAILS, 0)})
        with mock.patch.object(aicore_claude, "claude_bin", return_value=str(script)):
            tokens, error = aicore_claude.plugin_always_on_tokens("architect@swissknifeman", self.proj)
        self.assertEqual(tokens, 1275)
        self.assertIsNone(error)

    def test_cwd_reaches_details_call(self):
        # P1.4 §1 (living fact): local-scope plugin of someone else's project resolves
        # ONLY under cwd of his project - the fake actually checks os.getcwd(),
        # crashes without what is expected cwd, rather than just accepting a parameter.
        target_cwd = str(self.proj.resolve())
        script = _write_cwd_gated_details_cli(
            self.tmp, "architect@swissknifeman", target_cwd,
            "architect 0.1.0\n\nProjected token cost\n"
            "  Always-on:   ~1,275 tok   added to every session\n")
        with mock.patch.object(aicore_claude, "claude_bin", return_value=str(script)):
            tokens, error = aicore_claude.plugin_always_on_tokens("architect@swissknifeman", self.proj)
            self.assertEqual(tokens, 1275)
            self.assertIsNone(error)
            aicore_claude._details_cache.clear()
            wrong_cwd_tokens, wrong_cwd_error = aicore_claude.plugin_always_on_tokens(
                "architect@swissknifeman", self.tmp)
        self.assertIsNone(wrong_cwd_tokens)
        self.assertIn("code 1", wrong_cwd_error)

    def test_missing_claude_binary_gives_na_not_zero(self):
        with mock.patch.object(aicore_claude, "claude_bin", return_value=None):
            summary = aicore_claude.plugins_summary(self.proj)
        self.assertEqual(summary["status"], "n/a")
        self.assertIsNone(summary["total"])
        self.assertTrue(summary["partial"])
        self.assertTrue(summary["warnings"])

    def test_listing_failure_gives_na_not_zero(self):
        self._use_fake(list_payload="", list_exit=1)
        summary = aicore_claude.plugins_summary(self.proj)
        self.assertEqual(summary["status"], "n/a")
        self.assertIsNone(summary["total"])

    def test_details_cached_per_run(self):
        # success cached by id global - one call per UNIQUE id
        # (P1.4 §2, fan-out savings for the fleet remain).
        self._use_fake()
        calls = []
        real_run = aicore_claude.run_claude

        def _counting_run(argv, **kw):
            calls.append(tuple(argv))
            return real_run(argv, **kw)

        with mock.patch.object(aicore_claude, "run_claude", side_effect=_counting_run):
            aicore_claude.plugin_always_on_tokens("codex@openai-codex", self.proj)
            aicore_claude.plugin_always_on_tokens("codex@openai-codex", self.proj)
        self.assertEqual(len(calls), 1)

    def test_failure_not_cached_retries_under_different_cwd(self):
        # P1.4 §2: failure is NOT cached by id — same id under another cwd
        # will be resolved again, otherwise the first alien project would poison the cache.
        target_cwd = str(self.proj.resolve())
        script = _write_cwd_gated_details_cli(
            self.tmp, "architect@swissknifeman", target_cwd,
            "architect 0.1.0\n\nProjected token cost\n"
            "  Always-on:   ~1,275 tok   added to every session\n")
        with mock.patch.object(aicore_claude, "claude_bin", return_value=str(script)):
            miss_tokens, miss_error = aicore_claude.plugin_always_on_tokens(
                "architect@swissknifeman", self.tmp)
            self.assertIsNone(miss_tokens)
            self.assertIsNotNone(miss_error)
            hit_tokens, hit_error = aicore_claude.plugin_always_on_tokens(
                "architect@swissknifeman", self.proj)
        self.assertEqual(hit_tokens, 1275)
        self.assertIsNone(hit_error)


class PluginsCliIntegrationCase(unittest.TestCase):
    """`skiller budget --first-turn --with-plugins` — additivity JSON and
    `die` with no flag `--first-turn`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_root, self.env = fx.make_registry(self.tmp)
        self.proj = self.tmp / "myproj"
        self.proj.mkdir()
        (self.proj / ".swissknife.json").write_text(
            json.dumps({"buckets": ["quality"]}), encoding="utf-8")
        (self.proj / "CLAUDE.md").write_text("word " * 40, encoding="utf-8")
        aicore_claude._details_cache.clear()
        self._old_env = os.environ.get("SKM_CLAUDE_BIN")
        os.environ["SKM_CLAUDE_BIN"] = str(_write_fake_plugin_cli(self.tmp))

    def tearDown(self):
        aicore_claude._details_cache.clear()
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
