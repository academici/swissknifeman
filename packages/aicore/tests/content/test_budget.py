"""aicore.content.budget: token estimate, skill and set budgets, listing, measurements and first-turn sources."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aicore.content import budget


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_skill(root, name, description="A demo skill.", extra="", body="Body of the skill.\n"):
    directory = Path(root) / name
    write(directory / "SKILL.md", f"---\nname: {name}\ndescription: {description}\n{extra}---\n{body}")
    return directory


class EstimateTokensCase(unittest.TestCase):
    # Literals come from running the function before it moved out of the skill library.
    def test_values_are_the_historical_ones(self):
        self.assertEqual(budget.estimate_tokens(""), 0)
        self.assertEqual(budget.estimate_tokens("hello world"), 4)
        self.assertEqual(budget.estimate_tokens("Привет, мир"), 4)
        self.assertEqual(budget.estimate_tokens("Привет world, это mixed text with `code`"), 13)
        self.assertEqual(budget.estimate_tokens("a" * 100), 30)
        self.assertEqual(budget.estimate_tokens("ж" * 100), 35)
        self.assertEqual(budget.estimate_tokens("Ԁ" * 29), 10)  # Cyrillic Supplement counts as Cyrillic

    def test_cyrillic_costs_more_than_latin(self):
        self.assertGreater(budget.estimate_tokens("ж" * 100), budget.estimate_tokens("a" * 100))

    def test_constants(self):
        self.assertEqual((budget.CHARS_PER_TOKEN_CYR, budget.CHARS_PER_TOKEN_LAT), (2.9, 3.4))


class SkillBudgetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_three_tiers(self):
        directory = make_skill(self.root, "demo", body="b" * 340 + "\n")
        write(directory / "snippets" / "a.md", "s" * 34)
        write(directory / "references" / "full.md", "r" * 68)
        write(directory / "references" / "index.json", "{}")
        result = budget.skill_budget(directory)
        self.assertEqual(result["name"], "demo")
        self.assertEqual(result["tier0"], budget.estimate_tokens("demo A demo skill."))
        self.assertEqual(result["tier1"], budget.estimate_tokens("b" * 340 + "\n"))
        self.assertEqual(result["tier2"], budget.estimate_tokens("s" * 34) + budget.estimate_tokens("r" * 68))
        self.assertEqual((result["snippets"], result["references"]), (1, 1))

    def test_missing_skill_md_is_none(self):
        self.assertIsNone(budget.skill_budget(self.root / "nothing"))

    def test_budget_for_set_aggregates_by_bucket(self):
        one = make_skill(self.root, "one")
        two = make_skill(self.root, "two", body="x" * 100)
        skills = [("alpha", "alpha/one", one, "one"), ("beta", "beta/two", two, "two"),
                  ("beta", "beta/gone", self.root / "gone", "gone")]
        result = budget.budget_for_set(skills, pulled={"two": 1})
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["transitive"], 1)
        self.assertEqual(result["tier0"], sum(i["tier0"] for i in result["items"]))
        self.assertEqual(result["if_all_triggered"], result["tier0"] + result["tier1"])
        self.assertEqual(sorted(result["by_bucket"]), ["alpha", "beta"])
        self.assertEqual([i["transitive"] for i in result["items"]], [False, True])
        report = budget.format_report("demo set", result)
        self.assertIn("Set:        demo set", report)
        self.assertIn("alpha/one", report)
        self.assertIn("[transitive]", report)


class ListingCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.listed = make_skill(self.root, "listed", description="Listed skill.")
        self.hidden = make_skill(self.root, "hidden", description="Hidden skill.",
                                 extra="disable-model-invocation: true\n")
        self.scoped = make_skill(self.root, "scoped", extra="paths: [src/**]\n")
        self.skills = [("b", "b/listed", self.listed, "listed"), ("b", "b/hidden", self.hidden, "hidden"),
                       ("b", "b/scoped", self.scoped, "scoped")]

    def test_claude_code_counts_tokens_and_excludes_native_fields(self):
        report = budget.measure_listing_budget(self.skills, "claude-code")
        self.assertEqual(report["unit"], "current")
        self.assertEqual(report["raw"], budget.listing_entry_tokens(self.listed))
        self.assertEqual(report["budget"], 10_000)
        self.assertFalse(report["over"])
        self.assertEqual(report["excluded"], 2)
        self.assertEqual(report["excluded_by"], {"disable-model-invocation": 1, "paths": 1})
        self.assertGreater(report["excluded_raw"], 0)
        self.assertIn("excluded records: 2 (by field disable-model-invocation: 1, paths: 1)",
                      budget.format_listing_exclusions(report["excluded_by"]))
        self.assertIn("Listing:", budget.format_listing_report(report))

    def test_codex_counts_characters_and_excludes_nothing(self):
        report = budget.measure_listing_budget(self.skills, "codex")
        self.assertEqual(report["unit"], "char")
        self.assertEqual(report["budget"], budget.CODEX_LISTING_FALLBACK_CHARS)
        self.assertEqual(report["raw"], sum(budget.listing_entry_chars(d) for d in
                                            (self.listed, self.hidden, self.scoped)))
        self.assertEqual((report["excluded"], report["excluded_by"]), (0, {}))
        self.assertEqual(budget.listing_entry_chars(self.listed), len("listed") + len("Listed skill."))

    def test_entry_is_capped_for_claude_code_only(self):
        long = make_skill(self.root, "long", description="d" * 4000)
        self.assertEqual(budget.listing_entry_tokens(long),
                         budget.estimate_tokens("long") + budget.estimate_tokens("d" * 1536))
        self.assertEqual(budget.listing_entry_chars(long), len("long") + 4000)

    def test_over_budget_report_names_the_breakthrough(self):
        many = [("b", f"b/s{i}", make_skill(self.root, f"s{i}", description="d" * 1000), f"s{i}")
                for i in range(40)]
        report = budget.measure_listing_budget(many, "codex")
        self.assertTrue(report["over"])
        self.assertIn("BREAKTHROUGH", budget.format_listing_report(report))

    def test_unknown_provider_exits(self):
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            budget.measure_listing_budget(self.skills, "nope")
        self.assertIn("unknown --provider: nope", err.getvalue())

    def test_listing_measurements_give_one_row_per_provider(self):
        result = budget.listing_measurements(self.skills, observed_at="2026-01-01T00:00:00Z")
        self.assertEqual([row["provider"] for row in result["rows"]], sorted(budget.LISTING_PROVIDERS))
        self.assertEqual(result["status"], "green")
        units = {row["provider"]: row["unit"] for row in result["rows"]}
        self.assertEqual(units["codex"], "characters")
        self.assertEqual(units["claude-code"], "estimated_tokens")


def measurement(**changes):
    values = dict(
        provider="p", surface="listing", value=10, unit="characters", method="m", uncertainty="u",
        measurement_class="estimate", observed_at="2026-01-01T00:00:00Z", expires_at="2026-01-31T00:00:00Z",
        source_id="s", threshold=100, model_family="f")
    values.update(changes)
    return budget.make_measurement(**values)


class MeasurementCase(unittest.TestCase):
    def test_status_pass_over_budget_stale_unknown(self):
        self.assertEqual(measurement()["status"], "pass")
        self.assertEqual(measurement(value=101)["status"], "over-budget")
        self.assertEqual(measurement(evaluated_at="2026-02-01T00:00:00Z")["status"], "stale")
        unknown = measurement(value=None, measurement_class="unknown")
        self.assertEqual(unknown["status"], "unknown")

    def test_row_carries_exactly_one_model_identity(self):
        self.assertIn("model_family", measurement())
        self.assertIn("model", measurement(model="m1", model_family=None))
        for changes in ({"model_family": None}, {"model": "m1"}):
            with self.assertRaisesRegex(ValueError, "SKILL_MEASUREMENT_MODEL_IDENTITY_INVALID"):
                measurement(**changes)

    def test_invalid_rows_are_refused_with_stable_codes(self):
        cases = [
            ({"surface": "other"}, ValueError, "SURFACE_INVALID"),
            ({"measurement_class": "weird"}, ValueError, "CLASS_INVALID"),
            ({"value": None}, TypeError, "VALUE_INVALID"),
            ({"measurement_class": "unknown"}, ValueError, "CLASS_VALUE_MISMATCH"),
            ({"value": float("nan")}, ValueError, "VALUE_INVALID"),
            ({"value": True}, TypeError, "VALUE_INVALID"),
            ({"expires_at": "2026-01-01T00:00:00Z"}, ValueError, "FRESHNESS_INVALID"),
            ({"observed_at": "2026-01-01"}, ValueError, "TIMESTAMP_INVALID"),
            ({"unit": " "}, ValueError, "UNIT_INVALID"),
        ]
        for changes, error, code in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(error, f"SKILL_MEASUREMENT_.*{code}"):
                measurement(**changes)

    def test_aggregate_orders_rows_and_never_sums(self):
        rows = [measurement(provider="b"), measurement(provider="a", measurement_class="upper-bound")]
        result = budget.aggregate_measurements(rows)
        self.assertEqual([row["provider"] for row in result["rows"]], ["a", "b"])
        self.assertEqual(result["status"], "green")
        self.assertEqual(budget.aggregate_measurements([])["status"], "non-green")
        over = budget.aggregate_measurements([measurement(value=101)])
        self.assertEqual(over["status"], "non-green")

    def test_aggregate_refuses_conflicting_rows(self):
        cases = [
            ([measurement(), measurement()], "SKILL_MEASUREMENT_DUPLICATE"),
            ([measurement(), measurement(measurement_class="exact")], "SKILL_MEASUREMENT_CLASS_MIXED"),
            ([measurement(), measurement(measurement_class="lower-bound", unit="tokens")],
             "SKILL_MEASUREMENT_UNIT_MIXED"),
            ([measurement(), measurement(model_family="g", threshold=200)],
             "SKILL_MEASUREMENT_THRESHOLD_CONFLICT"),
        ]
        for rows, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                budget.aggregate_measurements(rows)
        with self.assertRaises(TypeError):
            budget.aggregate_measurements(["row"])
        with self.assertRaisesRegex(ValueError, "SKILL_MEASUREMENT_SCHEMA_INVALID"):
            budget.aggregate_measurements([dict(measurement(), extra=1)])
        tampered = dict(measurement(), status="over-budget")
        with self.assertRaisesRegex(ValueError, "SKILL_MEASUREMENT_STATUS_INVALID"):
            budget.aggregate_measurements([tampered])


class FirstTurnCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name)

    def test_verdict_boundaries(self):
        verdicts = [(0, "OK"), (16_000, "OK"), (16_001, "ELEVATED"), (23_000, "ELEVATED"), (23_001, "WARN")]
        for total, verdict in verdicts:
            self.assertEqual(budget.first_turn_verdict(total), verdict, total)
        self.assertEqual((budget.FIRST_TURN_TARGET_MAX, budget.FIRST_TURN_WARN), (16_000, 23_000))

    def test_agents(self):
        self.assertEqual(budget.measure_agents(self.target), {"tokens": 0, "detail": "no .claude/agents"})
        self.assertEqual(budget.measure_agents(self.target, "codex")["tokens"], 0)
        write(self.target / ".claude" / "agents" / "helper.md",
              "---\nname: helper\ndescription: Helps.\n---\nBody that is not counted.\n")
        result = budget.measure_agents(self.target)
        self.assertEqual(result, {"tokens": budget.estimate_tokens("helper Helps."), "detail": "1 agents"})

    def test_claude_md_and_rules_without_paths(self):
        self.assertEqual(budget.measure_claude_md(self.target)["detail"], "no CLAUDE.md")
        write(self.target / "CLAUDE.md", "c" * 34)
        write(self.target / ".claude" / "rules" / "a" / "always.md", "r" * 68)
        write(self.target / ".claude" / "rules" / "scoped.md", "---\npaths: [src/**]\n---\nignored\n")
        result = budget.measure_claude_md(self.target)
        self.assertEqual(result["tokens"], budget.estimate_tokens("c" * 34) + budget.estimate_tokens("r" * 68))
        self.assertEqual(result["detail"], f"CLAUDE.md={budget.estimate_tokens('c' * 34)} + 1 rules without paths")

    def test_instructions_by_provider(self):
        self.assertEqual(budget.measure_instructions(self.target)["surface"], "CLAUDE.md + .claude/rules")
        self.assertEqual(budget.measure_instructions(self.target, "codex"),
                         {"tokens": 0, "detail": "no AGENTS.md", "surface": "AGENTS.md"})
        write(self.target / "AGENTS.md", "a" * 34)
        self.assertEqual(budget.measure_instructions(self.target, "codex")["tokens"], 10)

    def test_hooks_run_live_and_fail_soft(self):
        self.assertEqual(budget.measure_hooks(self.target, provider="codex")["tokens"], 0)
        self.assertEqual(budget.measure_hooks(self.target)["detail"], "no SessionStart-hooks")
        script = self.target / "hook.sh"
        write(script, "#!/bin/sh\nprintf '%s' '{\"hookSpecificOutput\":{\"additionalContext\":\"" + "x" * 34 + "\"}}'\n")
        bad = self.target / "bad.sh"
        write(bad, "#!/bin/sh\nexit 3\n")
        settings = {"hooks": {"SessionStart": [{"hooks": [
            {"command": f"sh {script}"}, {"command": f"sh {bad}"}]}]}}
        write(self.target / ".claude" / "settings.json", json.dumps(settings))
        result = budget.measure_hooks(self.target)
        self.assertEqual(result, {"tokens": budget.estimate_tokens("x" * 34), "detail": "1 hook(ov), 1 n/a"})
        write(self.target / ".claude" / "settings.json", json.dumps(
            {"hooks": {"SessionStart": [{"hooks": [{"command": f"sh {bad}"}]}]}}))
        self.assertIsNone(budget.measure_hooks(self.target)["tokens"])

    def test_run_hook_reads_plain_stdout_and_sets_project_dir(self):
        tokens, ok = budget.run_hook('printf "%s" "$CLAUDE_PROJECT_DIR"', self.target)
        self.assertTrue(ok)
        self.assertEqual(tokens, budget.estimate_tokens(str(self.target)))
        self.assertEqual(budget.run_hook("true", self.target), (0, True))
        self.assertEqual(budget.run_hook("exit 1", self.target), (None, False))

    def test_mcp_uses_host_servers_only_through_their_attributes(self):
        self.assertEqual(budget.measure_mcp(self.target)["detail"], "no .mcp.json")
        write(self.target / ".mcp.json", json.dumps({"mcpServers": {"hosted": {}, "context7": {}, "mystery": {}}}))
        host = {"hosted": SimpleNamespace(tools=3, instructions_tokens=7)}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(budget.ENABLE_TOOL_SEARCH_ENV, None)
            result = budget.measure_mcp(self.target, host_servers=host)
            without_host = budget.measure_mcp(self.target)
        name, instructions = budget.TOKENS_PER_MCP_TOOL_NAME, budget.FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS
        self.assertEqual(result["mode"], budget.MCP_MODE_DEFERRED)
        self.assertEqual(result["tokens"], (3 * name + 7) + (2 * name + instructions)
                         + (budget.FALLBACK_MCP_TOOLS * name + instructions))
        fallback = budget.FALLBACK_MCP_TOOLS * name + instructions
        self.assertEqual(without_host["tokens"], fallback + (2 * name + instructions) + fallback)
        self.assertEqual(result["detail"], "3 server(ov): context7, hosted, mystery")

    def test_mcp_modes(self):
        write(self.target / ".mcp.json", json.dumps({"mcpServers": {"context7": {}}}))
        per_tool = budget.TOKENS_PER_MCP_TOOL
        for value, mode, tokens in (("false", budget.MCP_MODE_OFF, 2 * per_tool),
                                    ("auto", budget.MCP_MODE_AUTO, 2 * per_tool)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {budget.ENABLE_TOOL_SEARCH_ENV: value}):
                result = budget.measure_mcp(self.target)
                self.assertEqual((result["mode"], result["mode_source"], result["tokens"]), (mode, "env", tokens))
        write(self.target / ".claude" / "settings.json", json.dumps({"env": {budget.ENABLE_TOOL_SEARCH_ENV: "0"}}))
        with mock.patch.dict(os.environ):
            os.environ.pop(budget.ENABLE_TOOL_SEARCH_ENV, None)
            self.assertEqual(budget.tool_search_mode(self.target), (budget.MCP_MODE_OFF, "settings.json"))

    def test_mcp_invalid_json_and_no_servers(self):
        write(self.target / ".mcp.json", "{broken")
        self.assertIsNone(budget.measure_mcp(self.target)["tokens"])
        write(self.target / ".mcp.json", json.dumps({"mcpServers": {}}))
        self.assertEqual(budget.measure_mcp(self.target)["detail"], "no servers")

    def test_report_formatting(self):
        report = {
            "target": "/p", "total": 120, "verdict": "OK",
            "sources": {
                "skills": {"tokens": 100, "detail": "3 skills", "excluded": 1, "excluded_by": {"paths": 1},
                           "excluded_raw": 5, "raw_tokens": 105},
                "agents": {"tokens": 0, "detail": "no .claude/agents"},
                "claude_md": {"tokens": 20, "detail": "CLAUDE.md=20", "surface": "CLAUDE.md + .claude/rules"},
                "hooks": {"tokens": None, "detail": "n/a"},
                "mcp": {"tokens": 0, "detail": "no servers", "mode": "deferred", "mode_source": "default",
                        "estimate_class": "lower bound"},
            },
        }
        text = budget.format_first_turn_report(report)
        self.assertIn("FIRST-TURN BUDGET", text)
        self.assertIn("Provider: claude-code", text)
        self.assertIn("excluded records: 1 (by field paths: 1)", text)
        self.assertIn("(target ≤16000 · warn >23000)", text)
        self.assertIn("   n/a current", text)
        self.assertEqual([key for key, _label in budget.FIRST_TURN_SOURCE_LABELS],
                         ["skills", "agents", "claude_md", "hooks", "mcp"])

    def test_codex_integrity(self):
        clean = {"sources": {"skills": {}}}
        self.assertEqual(budget.codex_integrity(clean), {"status": "clean", "issues": []})
        degraded = {"sources": {"skills": {"duplicates": [1], "enabled_outside_project_policy": ["x"],
                                           "desired_plugins_not_effective": ["y"]}}}
        self.assertEqual(budget.codex_integrity(degraded)["issues"], [
            "SKILL_DUPLICATE_NAME", "CODEX_PLUGIN_ENABLED_OUTSIDE_PROJECT_POLICY",
            "CODEX_DESIRED_PLUGIN_NOT_EFFECTIVE"])

    def test_plugins_block(self):
        self.assertEqual(budget.format_plugins_block({"status": "off", "warnings": ["w"]})[1], "    n/a — w")
        plugins = {"status": "ok", "entries": [{"id": "p@m", "scope": "user", "tokens": 12}], "broken": [],
                   "unparsed": [], "warnings": [], "total": 12, "partial": False}
        text = "\n".join(budget.format_plugins_block(plugins))
        self.assertIn("p@m (user)", text)
        self.assertIn("Total plugins: 12 current", text)


if __name__ == "__main__":
    unittest.main()
