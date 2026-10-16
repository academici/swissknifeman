"""Tests first_turn_report / `skiller budget --first-turn` (P5.1).

Synthetic project in tmpdir (settings.json with stub-hook, .claude/agents,
CLAUDE.md, .mcp.json) — check the terms, verdict on thresholds 3-7K/10K,
fail-soft on broken hook (n/a, is no exception) and CLI (--json/--strict)."""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.budget import cmd_budget, first_turn_report
from skiller.host import clear_host_cache
from skiller.doctor import cmd_doctor
import tests.fixtures as fx


def _write_hook(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


# Synthetic host MCP server: exact tool count and instruction tokens owned by the host.
HOST_SERVER = "hub-memory"
HOST_TOOLS = 11


class FirstTurnReportCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        host = self.tmp / "host.json"
        host.write_text(json.dumps({"schema_version": 1, "mcp_servers": {
            HOST_SERVER: {"tools": HOST_TOOLS, "instructions_tokens": 0}}}), encoding="utf-8")
        clear_host_cache()
        patcher = mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(host)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(clear_host_cache)
        self.registry_root, self.env = fx.make_registry(self.tmp)
        self.proj = self.tmp / "myproj"
        self.proj.mkdir()
        # project uses bucket quality explicit (regardless autodetect)
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
        self.assertGreater(s["skills"]["tokens"], 0)   # quality-bucket is not empty
        self.assertGreater(s["agents"]["tokens"], 0)   # reviewer.md
        self.assertGreater(s["claude_md"]["tokens"], 0)
        self.assertGreater(s["hooks"]["tokens"], 0)    # live run stub.sh
        self.assertEqual(s["mcp"]["tokens"], 0)        # no .mcp.json
        expected_total = sum(s[k]["tokens"] for k in s)
        self.assertEqual(report["total"], expected_total)
        self.assertEqual(report["verdict"], "OK")      # synthetic << 16K

    def test_broken_hook_is_na_not_exception(self):
        _write_hook(self.proj / ".claude" / "hooks" / "broken.sh",
                   "#!/usr/bin/env bash\nexit 1\n")
        (self.proj / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "bash .claude/hooks/broken.sh"}]}]}}),
            encoding="utf-8")
        report = first_turn_report(self.env, self.proj)  # should not throw an exception
        self.assertIsNone(report["sources"]["hooks"]["tokens"])
        self.assertIn("n/a", report["sources"]["hooks"]["detail"])
        # total does not take into account n/a-source, but the remaining terms are summed
        self.assertGreater(report["total"], 0)

    def test_no_settings_json_reports_zero_hooks(self):
        (self.proj / ".claude" / "settings.json").unlink()
        report = first_turn_report(self.env, self.proj)
        self.assertEqual(report["sources"]["hooks"], {
            "tokens": 0, "detail": "no SessionStart-hooks"})

    def test_known_and_unknown_mcp_servers(self):
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            HOST_SERVER: {"command": "hub-memory"},
            "totally-unknown-server": {"command": "x"}}}), encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        # deferred (default) — host server (11 names, instructions measured = 0) +
        # unknown (fallback tools + fallback instructions) — both taken into account, > 0
        self.assertGreater(mcp["tokens"], 0)
        self.assertIn(HOST_SERVER, mcp["detail"])
        self.assertIn("totally-unknown-server", mcp["detail"])

    def test_mcp_default_mode_is_deferred_lower_bound(self):
        from aicore.content.budget import TOKENS_PER_MCP_TOOL_NAME
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            HOST_SERVER: {"command": "hub-memory"}}}), encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        self.assertEqual(mcp["mode"], "deferred")
        self.assertEqual(mcp["mode_source"], "default")
        self.assertIn("lower bound", mcp["estimate_class"])
        # host server — instruction text verified by the host (=0) → names only
        self.assertEqual(mcp["tokens"], HOST_TOOLS * TOKENS_PER_MCP_TOOL_NAME)

    def test_mcp_tool_search_off_uses_eager_schema_model(self):
        from aicore.content.budget import FALLBACK_MCP_TOOLS, TOKENS_PER_MCP_TOOL
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            HOST_SERVER: {"command": "hub-memory"},
            "totally-unknown-server": {"command": "x"}}}), encoding="utf-8")
        (self.proj / ".claude" / "settings.json").write_text(json.dumps({
            "env": {"ENABLE_TOOL_SEARCH": "false"}}), encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        self.assertEqual(mcp["mode"], "off")
        self.assertEqual(mcp["mode_source"], "settings.json")
        self.assertIn("accurate model of complete circuits", mcp["estimate_class"])
        expected = (HOST_TOOLS + FALLBACK_MCP_TOOLS) * TOKENS_PER_MCP_TOOL
        self.assertEqual(mcp["tokens"], expected)

    def test_mcp_tool_search_auto_mode_from_settings_local(self):
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            HOST_SERVER: {"command": "hub-memory"}}}), encoding="utf-8")
        (self.proj / ".claude" / "settings.local.json").write_text(json.dumps({
            "env": {"ENABLE_TOOL_SEARCH": "auto"}}), encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        self.assertEqual(mcp["mode"], "auto")
        self.assertEqual(mcp["mode_source"], "settings.local.json")
        self.assertIn("upper limit", mcp["estimate_class"])

    def test_mcp_tool_search_mode_order_env_over_settings_local(self):
        # process environment INTERRUPTS settings.local.json (order Implementation
        # Rules P2.3 §2): local carries auto, but alive env says false.
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            HOST_SERVER: {"command": "hub-memory"}}}), encoding="utf-8")
        (self.proj / ".claude" / "settings.local.json").write_text(json.dumps({
            "env": {"ENABLE_TOOL_SEARCH": "auto"}}), encoding="utf-8")
        with mock.patch.dict("os.environ", {"ENABLE_TOOL_SEARCH": "false"}):
            report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        self.assertEqual(mcp["mode"], "off")
        self.assertEqual(mcp["mode_source"], "env")

    def test_mcp_no_servers_reports_mode_without_estimate(self):
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {}}),
                                             encoding="utf-8")
        report = first_turn_report(self.env, self.proj)
        mcp = report["sources"]["mcp"]
        self.assertEqual(mcp["tokens"], 0)
        self.assertIsNone(mcp["estimate_class"])

    def test_boost_alias_known_next_to_laravel_boost(self):
        from aicore.content.budget import KNOWN_MCP_TOOLS
        self.assertEqual(KNOWN_MCP_TOOLS["boost"], KNOWN_MCP_TOOLS["laravel-boost"])

    def test_listing_entry_capped_at_1536_chars(self):
        # first-party: "combined description and when_to_use text is truncated
        # at 1,536 characters" — a record longer than a cap should not give more
        # tokens than dripped text.
        from aicore.content.budget import (
            listing_entry_tokens as _listing_entry_tokens, estimate_tokens)
        d = self.registry_root / "skills" / "quality" / "long-desc"
        long_desc = "x " * 2000  # 4000 char, obviously > 1536
        fx.write_skill(d, "long-desc", description=long_desc)
        capped_expected = estimate_tokens("long-desc") + estimate_tokens(
            long_desc[:1536])
        self.assertEqual(_listing_entry_tokens(d), capped_expected)
        self.assertLess(_listing_entry_tokens(d), estimate_tokens(
            "long-desc " + long_desc))  # undrawn amount would be higher

    def test_listing_budget_caps_raw_sum_and_reports_both(self):
        # listing budget - ceiling, not the sum of all descriptions (D22 re-registration):
        # obviously tight budget forces raw > budget → resident == budget.
        report = first_turn_report(self.env, self.proj,
                                   listing_fraction=0.0001,
                                   listing_context_window=1_000)
        s = report["sources"]["skills"]
        self.assertEqual(s["listing_budget"], 0)  # int(1000*0.0001) == 0
        self.assertEqual(s["tokens"], 0)
        self.assertGreater(s["raw_tokens"], s["tokens"])
        self.assertIn("budget", s["detail"])

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
        # path-scoped rule (scoped.md) does not provide a contribution - tokens have not grown
        self.assertEqual(with_scoped["tokens"], no_rules["tokens"])
        (rules / "always.md").write_text(
            "---\nversion: 1\n---\n" + "always-on rule body " * 200,
            encoding="utf-8")
        with_always = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        # always-on rule (without paths) makes a contribution - growth entirely from always.md
        self.assertGreater(with_always["tokens"], with_scoped["tokens"])

    def test_rules_subdirectory_without_paths_is_counted(self):
        # P2.3 find: flat `rules_dir.glob("*.md")` was skipping subdirectories
        # `.claude/rules/**`, although upstream loads them always-on on par with
        # top level (RAG:✅ `findings/…probe §6` — «subdirectories …
        # discovered automatically»).
        before = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        sub = self.proj / ".claude" / "rules" / "sub"
        sub.mkdir(parents=True)
        (sub / "rule.md").write_text("nested always-on rule body " * 50,
                                     encoding="utf-8")
        after = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        self.assertGreater(after["tokens"], before["tokens"])

    def test_rules_subdirectory_with_paths_is_excluded(self):
        before = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        sub = self.proj / ".claude" / "rules" / "sub"
        sub.mkdir(parents=True)
        (sub / "scoped.md").write_text(
            "---\npaths:\n  - \"**/tests/**\"\n---\n" + "nested scoped body " * 200,
            encoding="utf-8")
        after = first_turn_report(self.env, self.proj)["sources"]["claude_md"]
        # path-scoped nested rule still doesn't contribute
        self.assertEqual(after["tokens"], before["tokens"])

    def test_verdict_ladder_matches_declared_thresholds(self):
        # the staircase is pinned NAMELY at its boundaries: threshold re-edition
        # (P1.3 Implementation Rules §6) should drop this case and not quietly
        # change the meaning of the verdict for the fleet and the hub's context doctor.
        from aicore.content.budget import (
            FIRST_TURN_TARGET_MAX, FIRST_TURN_WARN, first_turn_verdict as _first_turn_verdict)
        self.assertEqual((FIRST_TURN_TARGET_MAX, FIRST_TURN_WARN), (16_000, 23_000))
        self.assertEqual(_first_turn_verdict(FIRST_TURN_TARGET_MAX), "OK")
        self.assertEqual(_first_turn_verdict(FIRST_TURN_TARGET_MAX + 1), "ELEVATED")
        self.assertEqual(_first_turn_verdict(FIRST_TURN_WARN), "ELEVATED")
        self.assertEqual(_first_turn_verdict(FIRST_TURN_WARN + 1), "WARN")

    def test_verdict_warn_above_threshold_and_strict_cli_exits(self):
        # inflate CLAUDE.md obviously higher warn-threshold; volume is derived FROM
        # constants, otherwise the next time the threshold is re-issued, the test «just
        # will stop crashing» instead of requiring parsing.
        from aicore.content.budget import FIRST_TURN_WARN, estimate_tokens
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

    def test_codex_first_turn_uses_provider_observed_skills_and_agents_md(self):
        (self.proj / "AGENTS.md").write_text("codex instruction " * 20,
                                              encoding="utf-8")
        observed_skill = self.registry_root / "skills" / "quality" / "observed"
        fx.write_skill(observed_skill, "observed", description="Observed by Codex")
        inventory = {
            "ok": True,
            "names": {"observed"},
            "native_names": {"observed"},
            "paths": {"observed": [str(observed_skill / "SKILL.md")]},
            "enabled": ["quality"],
            "notes": [],
        }
        with mock.patch("skiller.budget.native_inventory", return_value=inventory):
            report = first_turn_report(self.env, self.proj, provider="codex")
        self.assertEqual(report["provider"], "codex")
        self.assertEqual(report["measurement_status"], "complete")
        self.assertEqual(report["scope"], "managed-first-turn")
        self.assertEqual(report["platform_overhead"], "excluded")
        self.assertEqual(report["sources"]["skills"]["measurement"],
                         "provider-observed")
        self.assertEqual(report["sources"]["skills"]["observed_count"], 1)
        self.assertGreater(report["sources"]["skills"]["managed_tokens"], 0)
        self.assertEqual(report["sources"]["agents"]["tokens"], 0)
        self.assertEqual(report["sources"]["claude_md"]["surface"], "AGENTS.md")
        self.assertGreater(report["sources"]["claude_md"]["tokens"], 0)
        self.assertEqual(report["sources"]["hooks"]["tokens"], 0)

    def test_codex_native_inventory_failure_is_incomplete_and_strict_fails(self):
        unavailable = {
            "ok": False, "names": set(), "native_names": set(), "paths": {},
            "enabled": [], "notes": ["Codex native discovery unavailable: test"],
        }
        with mock.patch("skiller.budget.native_inventory", return_value=unavailable):
            report = first_turn_report(self.env, self.proj, provider="codex")
            self.assertEqual(report["verdict"], "INCOMPLETE")
            self.assertEqual(report["measurement_status"], "incomplete")
            self.assertIsNone(report["sources"]["skills"]["tokens"])
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cmd_budget(self.env, ["--first-turn", "--provider", "codex",
                                         "--target", str(self.proj), "--strict"])

    def test_context_doctor_reports_codex_collisions_and_policy_drift(self):
        (self.proj / ".swissknife.json").write_text(
            json.dumps({"plugins": ["quality", "php"]}), encoding="utf-8")
        observed_skill = self.registry_root / "skills" / "quality" / "observed"
        fx.write_skill(observed_skill, "observed", description="Observed by Codex")
        inventory = {
            "ok": True,
            "names": {"observed"},
            "native_names": {"observed"},
            "paths": {"observed": [str(observed_skill / "SKILL.md"),
                                    str(observed_skill / "SKILL.md")]},
            "enabled": ["quality", "devops"],
            "notes": [],
        }
        stdout = io.StringIO()
        with mock.patch("skiller.budget.native_inventory", return_value=inventory), \
                contextlib.redirect_stdout(stdout):
            cmd_doctor(self.env, ["--context", "--provider", "codex",
                                  "--target", str(self.proj), "--json"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "degraded")
        self.assertEqual({row["code"] for row in report["diagnostics"]}, {
            "SKILL_DUPLICATE_NAME", "CODEX_PLUGIN_ENABLED_OUTSIDE_PROJECT_POLICY",
            "CODEX_DESIRED_PLUGIN_NOT_EFFECTIVE"})

    def test_codex_policy_drift_is_strict_failure(self):
        (self.proj / ".swissknife.json").write_text(
            json.dumps({"plugins": ["quality", "php"]}), encoding="utf-8")
        observed_skill = self.registry_root / "skills" / "quality" / "observed"
        fx.write_skill(observed_skill, "observed", description="Observed by Codex")
        inventory = {
            "ok": True,
            "names": {"observed"},
            "native_names": {"observed"},
            "paths": {"observed": [str(observed_skill / "SKILL.md"),
                                    str(observed_skill / "SKILL.md")]},
            "enabled": ["quality", "devops"],
            "notes": [],
        }
        with mock.patch("skiller.budget.native_inventory", return_value=inventory):
            report = first_turn_report(self.env, self.proj, provider="codex")
            self.assertEqual(report["integrity"], {
                "status": "degraded",
                "issues": [
                    "SKILL_DUPLICATE_NAME",
                    "CODEX_PLUGIN_ENABLED_OUTSIDE_PROJECT_POLICY",
                    "CODEX_DESIRED_PLUGIN_NOT_EFFECTIVE",
                ],
            })
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cmd_budget(self.env, ["--first-turn", "--provider", "codex",
                                          "--target", str(self.proj), "--strict"])

    # --- listing model: native fields removing record (P3.2, D95/D96) ------
    def _write_skill_fm(self, name, extra_fm=""):
        """Skill in the bucket `quality` synthetic registry with ADDITIONAL
        lines frontmatter (fixtures.write_skill does not know how to touch them, but the general
        helper for the sake of one case - create a second format carrier)."""
        d = self.registry_root / "skills" / "quality" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\nversion: 0.1.0\n"
            f"description: {'listing weight ' * 20}\n{extra_fm}---\n\nBody.\n",
            encoding="utf-8")
        return d

    def _skills_source(self):
        return first_turn_report(self.env, self.proj)["sources"]["skills"]

    def test_disable_model_invocation_entry_leaves_listing_sum(self):
        # first-party: «Description **not** in context» + stand observation P3.1
        # (axis A −88, both runs) — `findings/P3-native-fields-smoke.md` §3.2.
        base = self._skills_source()
        self._write_skill_fm("plain-entry")
        with_plain = self._skills_source()
        self.assertGreater(with_plain["raw_tokens"], base["raw_tokens"])
        self.assertEqual(with_plain["excluded"], 0)

        self._write_skill_fm("silent-entry", "disable-model-invocation: true\n")
        with_silent = self._skills_source()
        # record was added to the active set, but was not included in the listing amount
        self.assertEqual(with_silent["raw_tokens"], with_plain["raw_tokens"])
        self.assertEqual(with_silent["excluded"], 1)
        self.assertEqual(with_silent["excluded_by"], {"disable-model-invocation": 1})
        self.assertGreater(with_silent["excluded_raw"], 0)

    def test_same_skill_without_field_is_counted(self):
        # reverse half of the same case: field cleared → entry is returned to the amount
        d = self._write_skill_fm("toggle-entry", "disable-model-invocation: true\n")
        excluded = self._skills_source()
        self._write_skill_fm("toggle-entry")  # same skill, no field anymore
        included = self._skills_source()
        self.assertEqual(excluded["excluded"], 1)
        self.assertEqual(included["excluded"], 0)
        self.assertGreater(included["raw_tokens"], excluded["raw_tokens"])
        self.assertTrue(d.is_dir())

    def test_paths_entry_leaves_listing_sum(self):
        # OBSERVATION, not doc: `paths:` took down the entire post (axis A −88,
        # byte-to-byte as `disable-model-invocation`) — `findings/
        # P3-native-fields-smoke.md` §3.1/§4; mechanism named P3.6 —
        # `findings/P3-paths-mechanism.md` §2 (condition «file READ», on the first
        # progress unattainable ⇒ exception definitely).
        self._write_skill_fm("plain-entry")
        with_plain = self._skills_source()
        self._write_skill_fm("scoped-entry", "paths:\n  - \"*.zzp31paths\"\n")
        with_scoped = self._skills_source()
        self.assertEqual(with_scoped["raw_tokens"], with_plain["raw_tokens"])
        self.assertEqual(with_scoped["excluded_by"], {"paths": 1})

    def test_indistinguishable_fields_do_not_change_the_model(self):
        # stand P3.1 gave «indistinguishable»/«no device» by `model:`, `effort:` and
        # `context: fork` (§2 table) — Implementation Rules P3.2 §2: such a field
        # is NOT included in the model, a known overestimation is better than an unproven one
        # understatement.
        self._write_skill_fm("plain-entry")
        base = self._skills_source()
        self._write_skill_fm("plain-entry",
                             "model: claude-haiku-4-5-20251001\neffort: high\n"
                             "context: fork\n")
        after = self._skills_source()
        self.assertEqual(after["raw_tokens"], base["raw_tokens"])
        self.assertEqual(after["excluded"], 0)

    def test_json_top_level_keys_unchanged_for_fleet_doctor(self):
        # fleet-consumer reads d["total"]/d["verdict"] and falls into n/a on any
        # KeyError (the hub's fleet doctor, D16) — new
        # information comes ONLY additively, inside sources.skills.
        self._write_skill_fm("silent-entry", "disable-model-invocation: true\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--first-turn", "--target", str(self.proj), "--json"])
        data = json.loads(buf.getvalue())
        self.assertEqual(set(data), {"target", "sources", "total", "verdict"})
        self.assertIsInstance(data["total"], int)
        self.assertIn(data["verdict"], ("OK", "ELEVATED", "WARN"))
        self.assertEqual(data["sources"]["skills"]["excluded_by"],
                         {"disable-model-invocation": 1})

    def test_report_prints_exclusion_line(self):
        self._write_skill_fm("silent-entry", "disable-model-invocation: true\n")
        from aicore.content.budget import format_first_turn_report
        text = format_first_turn_report(first_turn_report(self.env, self.proj))
        self.assertIn("excluded records: 1 (by field disable-model-invocation: 1)",
                      text)


if __name__ == "__main__":
    unittest.main()
