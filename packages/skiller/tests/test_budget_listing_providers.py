"""Provider-aware detection budget model (listing) — P3.4.

Codex — fallback 8,000 CHARACTERS (worst case, real window [UNVERIFIED], D3),
without per-entry mouth guard (the original source does not name him). Claude Code — existing
token model (1% windows @1M = 10 000 current, cap entries 1,536 characters), untouched
and is not reinvented here - only caused by the next (D52). Units of two models
DIFFERENT and do not mix: so that this does not spread unnoticed, each test
checks both the number and `unit`."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.budget import (CODEX_LISTING_FALLBACK_CHARS, cmd_budget,
                            format_listing_report,
                            format_profiles_listing_report,
                            measure_listing_budget, profiles_listing_report,
                            resolve_active_set)
import tests.fixtures as fx


class MeasureListingBudgetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.target = self.tmp / "dummy-target"

    def tearDown(self):
        self._tmp.cleanup()

    def _skills(self, profile):
        skills, _meta = resolve_active_set(self.env, self.target, {}, profile=profile)
        return skills

    def test_codex_unit_is_raw_characters_uncapped(self):
        skills = self._skills("laravel-project")
        report = measure_listing_budget(skills, "codex")
        self.assertEqual(report["unit"], "char")
        # compare with direct sum len(name)+len(description) by frontmatter
        from skiller.common import parse_frontmatter
        raw = 0
        for _b, _rel, d, _fm in skills:
            fm = parse_frontmatter(d / "SKILL.md")
            raw += len(fm.get("name", "")) + len((fm.get("description", "") or ""))
        self.assertEqual(report["raw"], raw)
        self.assertEqual(report["budget"], CODEX_LISTING_FALLBACK_CHARS)

    def test_claude_code_unit_is_tokens_not_characters(self):
        skills = self._skills("laravel-project")
        report = measure_listing_budget(skills, "claude-code")
        self.assertEqual(report["unit"], "current")
        # tokens are strictly less than raw characters of the same sample (otherwise the units are mixed)
        codex = measure_listing_budget(skills, "codex")
        self.assertLess(report["raw"], codex["raw"])

    def test_cursor_unit_is_raw_characters_like_codex(self):
        skills = self._skills("laravel-project")
        report = measure_listing_budget(skills, "cursor")
        self.assertEqual(report["unit"], "char")
        codex = measure_listing_budget(skills, "codex")
        self.assertEqual(report["raw"], codex["raw"])

    def test_unknown_provider_dies(self):
        skills = self._skills("laravel-project")
        with self.assertRaises(SystemExit):
            measure_listing_budget(skills, "windsurf")

    def test_codex_entry_uncapped_unlike_claude(self):
        # entry longer than 1,536 characters (client cap Claude) is obliged to give MISCELLANEOUS
        # increase in two models: Claude the record drops to 1,536, at Codex — no.
        before = measure_listing_budget(self._skills("laravel-project"), "codex")["raw"]
        long_desc = "x " * 2000  # 4000 char, obviously > cap Claude (1 536)
        fx.write_skill(self.root / "skills" / "quality" / "long-desc",
                       "long-desc", description=long_desc)
        after = measure_listing_budget(
            self._skills("laravel-project"), "codex")["raw"]
        # gain from one record (name + 4000 description symbol) will not drip - obviously
        # more than if the client was used cap Claude (1 536)
        self.assertGreater(after - before, 1_536)

    def test_boundary_exactly_at_fallback_is_not_over(self):
        # one synthetic skill, listing exactly on the fallback border → NOT OVERWHELMING (strict >)
        tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(tmp2.cleanup)
        root2, env2 = fx.make_registry(Path(tmp2.name))
        # "boundary" name (8 chars) + description filling exactly to the budget
        name = "boundary"
        pad = CODEX_LISTING_FALLBACK_CHARS - len(name)
        fx.write_skill(root2 / "skills" / "quality" / "boundary-only", name,
                       description="x" * pad)
        (root2 / "profiles" / "boundary-profile.json").write_text(
            '{"name": "boundary-profile", "description": "t",'
            ' "buckets": ["quality"], "include_meta": false}\n')
        skills, _meta = resolve_active_set(
            env2, Path(tmp2.name) / "dummy", {}, profile="boundary-profile")
        # isolate from other bucket skills quality (test-writer) — we count only ours
        skills = [s for s in skills if s[3] == name]
        report = measure_listing_budget(skills, "codex")
        self.assertEqual(report["raw"], CODEX_LISTING_FALLBACK_CHARS)
        self.assertFalse(report["over"])

    def test_degradation_wording_not_mixed(self):
        skills = self._skills("laravel-project")
        codex = measure_listing_budget(skills, "codex")
        claude = measure_listing_budget(skills, "claude-code")
        self.assertIn("removed", codex["degradation"])
        self.assertIn("is truncated", claude["degradation"])
        self.assertNotEqual(codex["degradation"], claude["degradation"])

    def test_format_listing_report_shows_provider_and_status(self):
        skills = self._skills("laravel-project")
        text = format_listing_report(measure_listing_budget(skills, "codex"))
        self.assertIn("codex", text)
        self.assertIn("char", text)


class ProfilesListingReportCase(unittest.TestCase):
    """--profiles: detection budget for EACH supplied profile versus BOTH
    providers, on a synthetic registry (fixtures) — does not depend on the current
    live composition packages/skiller/profiles/*.json."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_covers_every_shipped_profile(self):
        rows = profiles_listing_report(self.env)
        names = {r["profile"] for r in rows}
        shipped = {p.stem for p in (self.root / "profiles").glob("*.json")}
        self.assertEqual(names, shipped)
        for r in rows:
            self.assertIn("codex", r)
            self.assertIn("claude-code", r)
            self.assertGreaterEqual(r["count"], 1)

    def test_format_profiles_listing_report_is_a_table(self):
        rows = profiles_listing_report(self.env)
        text = format_profiles_listing_report(rows)
        self.assertIn("Profile", text)
        self.assertIn("Codex", text)
        self.assertIn("Claude Code", text)
        for r in rows:
            self.assertIn(r["profile"], text)


class CmdBudgetProviderCliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.target = self.tmp / "dummy-target"

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_output_unchanged_without_provider_flag(self):
        buf_a, buf_b = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_a):
            cmd_budget(self.env, ["--profile", "laravel-project", "--target",
                                  str(self.target)])
        with contextlib.redirect_stdout(buf_b):
            cmd_budget(self.env, ["--profile", "laravel-project", "--target",
                                  str(self.target), "--provider", "claude-code"])
        # without the provider flag, the report does not contain the listing sections at all
        self.assertNotIn("Discovery budget (listing)", buf_a.getvalue())
        self.assertIn("Discovery budget (listing)", buf_b.getvalue())

    def test_provider_codex_json_shape(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--profile", "laravel-project", "--target",
                                  str(self.target), "--provider", "codex", "--json"])
        data = json.loads(buf.getvalue())
        self.assertIn("listing", data)
        self.assertEqual(data["listing"]["provider"], "codex")
        self.assertEqual(data["listing"]["unit"], "char")

    def test_profiles_flag_cli_json(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--profiles", "--json"])
        rows = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(rows), 1)
        self.assertIn("codex", rows[0])
        self.assertIn("claude-code", rows[0])

    def test_unknown_provider_cli_exits(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                cmd_budget(self.env, ["--profile", "laravel-project", "--target",
                                      str(self.target), "--provider", "windsurf"])


if __name__ == "__main__":
    unittest.main()
