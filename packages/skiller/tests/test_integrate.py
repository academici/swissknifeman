"""Wizard tests integrate (after moving the environment into the package harness).

Here we are left with ORCHESTRATION and selection policy: dry-run does not write anything,
minimal-bundle connects skills, `_gather`/`_default_mcp` resolve set MCP.
The environment EXECUTION itself (permissions/MCP/auto-approve/memory) is delegated
package harness via subprocess — its blocks are covered with tests in packages/harness/tests.
In the fixture harness not installed → env-blocks are skipped softly (graceful skip).

Racing against a synthetic registry (tests/fixtures) in temporary directories;
env.home points to tmp — real ~/.swissknifeman and ~/.claude are not touched."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.integrate import cmd_integrate, _default_mcp, _gather
from skiller.registry import build_registry
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def _materialize_registry(env):
    """skills.json from the synthetic registry - needed vendor-channel (sync)."""
    reg, *_ = build_registry(env)
    (env.root / "skills.json").write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


class IntegrateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    # --- dry-run ------------------------------------------------------------
    def test_dry_run_writes_nothing(self):
        run(cmd_integrate, self.env,
            ["--target", str(self.proj), "--bundle", "full", "--yes", "--dry-run"])
        self.assertFalse((self.proj / ".claude").exists())
        self.assertFalse((self.proj / ".swissknife.json").exists())
        self.assertFalse((self.proj / ".mcp.json").exists())

    # --- minimal bundle = connect only (env-blocks disabled) ----------------
    def test_minimal_connects_skills(self):
        run(cmd_integrate, self.env,
            ["--target", str(self.proj), "--bundle", "minimal", "--yes"])
        settings = json.loads(
            (self.proj / ".claude" / "settings.local.json").read_text())
        self.assertIn("swissknifeman", settings.get("extraKnownMarketplaces", {}))
        self.assertTrue(any(k.endswith("@swissknifeman")
                            for k in settings.get("enabledPlugins", {})))
        # registered in projects.json (in tmp home, not real)
        db = json.loads((self.env.home / ".swissknifeman" / "projects.json").read_text())
        self.assertTrue(any(p["path"] == str(self.proj) for p in db["projects"]))

    # --- skills channel (connect vs vendor) ---------------------------------
    def test_vendor_channel_syncs_into_claude_skills(self):
        """--skills-channel vendor → physical. copies in .claude/skills/ via sync
        (for external developers without registry access), and not plugins."""
        _materialize_registry(self.env)
        run(cmd_integrate, self.env,
            ["--target", str(self.proj), "--bundle", "minimal",
             "--skills-channel", "vendor", "--yes"])
        # config vendor-mode materialized from project profile
        cfg = json.loads(
            (self.proj / ".swissknifeman" / "config.json").read_text())
        self.assertEqual(cfg["mode"], "vendor")
        self.assertIn("php", cfg["buckets"])  # laravel-project fixture profile
        # skills physically in the repo, in lock — managed:true, source swissknifeman
        self.assertTrue(
            (self.proj / ".claude/skills/code-style/SKILL.md").is_file())
        lock = json.loads((self.proj / "skills-lock.json").read_text())["skills"]
        self.assertTrue(lock["code-style"]["managed"])
        self.assertEqual(lock["code-style"]["source"], "swissknifeman")
        # vendor DOES NOT write plugins marketplace
        settings = self.proj / ".claude" / "settings.local.json"
        if settings.exists():
            self.assertNotIn("enabledPlugins",
                             json.loads(settings.read_text()))
        # registered as channel=vendor
        db = json.loads(
            (self.env.home / ".swissknifeman" / "projects.json").read_text())
        rec = next(p for p in db["projects"] if p["path"] == str(self.proj))
        self.assertEqual(rec["channel"], "vendor")

    def test_skills_channel_skip_installs_nothing(self):
        _materialize_registry(self.env)
        run(cmd_integrate, self.env,
            ["--target", str(self.proj), "--bundle", "minimal",
             "--skills-channel", "skip", "--yes"])
        self.assertFalse((self.proj / ".claude" / "skills").exists())
        self.assertFalse((self.proj / ".swissknifeman").exists())

    def test_invalid_skills_channel_exits(self):
        with self.assertRaises(SystemExit):
            run(cmd_integrate, self.env,
                ["--target", str(self.proj), "--skills-channel", "bogus", "--yes"])

    # --- MCP choice policy (remains in the wizard; execution - in harness) ------
    def test_default_mcp_dev_vs_vault(self):
        self.assertEqual(_default_mcp(self.proj), ["context7"])   # laravel = dev
        vault = self.tmp / "vault"; (vault / ".obsidian").mkdir(parents=True)
        self.assertEqual(_default_mcp(vault), [])                 # vault ≠ dev

    def test_bundle_resolves_dev_mcp(self):
        # recommended/full on dev-project → context7; minimal → empty
        rec = _gather(self.env, self.proj, {"file": None}, "recommended", False)
        self.assertEqual(rec["mcp"], ["context7"])
        mn = _gather(self.env, self.proj, {"file": None}, "minimal", False)
        self.assertEqual(mn["mcp"], [])
        # same bundle on obsidian-vault → empty (not dev-environment)
        vault = self.tmp / "vault"; (vault / ".obsidian").mkdir(parents=True)
        rv = _gather(self.env, vault, {"file": None}, "recommended", False)
        self.assertEqual(rv["mcp"], [])

    def test_mcp_flag_unions_with_default(self):
        # --mcp adds opt-in presets on top dev-default, no duplicates
        rec = _gather(self.env, self.proj,
                      {"file": None, "mcp": "playwright"}, "recommended", False)
        self.assertEqual(rec["mcp"], ["context7", "playwright"])
        # minimal: context7 no, but explicit --mcp is set
        mn = _gather(self.env, self.proj,
                     {"file": None, "mcp": "playwright"}, "minimal", False)
        self.assertEqual(mn["mcp"], ["playwright"])
        # take context7 does not breed
        dup = _gather(self.env, self.proj,
                      {"file": None, "mcp": "context7,playwright"}, "recommended", False)
        self.assertEqual(dup["mcp"], ["context7", "playwright"])
        # on obsidian-vault explicit --mcp hits dev-gate
        vault = self.tmp / "vault2"; (vault / ".obsidian").mkdir(parents=True)
        rv = _gather(self.env, vault,
                     {"file": None, "mcp": "playwright"}, "recommended", False)
        self.assertEqual(rv["mcp"], ["playwright"])

    # --- output-style (agent terse voice, token saving - for ALL bundles) ---
    def test_output_style_lean_in_every_bundle(self):
        for bundle in ("minimal", "recommended", "full"):
            g = _gather(self.env, self.proj, {"file": None}, bundle, False)
            self.assertEqual(g["output_style"], "lean", bundle)

    def test_output_style_custom_bundle_defaults_lean_noninteractive(self):
        g = _gather(self.env, self.proj, {"file": None}, "custom", False)
        self.assertEqual(g["output_style"], "lean")

    def test_minimal_bundle_still_applies_output_style_block(self):
        # minimal turns off perms/mcp/autoapprove/memory/hub/brain, but NOT output-style —
        # token-saving needed «for all projects» regardless of the amount of automation.
        out = run(cmd_integrate, self.env,
                  ["--target", str(self.proj), "--bundle", "minimal", "--yes"])
        self.assertIn("output-style: lean", out)

    # --- plans-dir (per-project plans/, default «yes» — for ALL bundles) ---
    def test_plans_dir_enabled_in_every_bundle(self):
        for bundle in ("minimal", "recommended", "full"):
            g = _gather(self.env, self.proj, {"file": None}, bundle, False)
            self.assertTrue(g["plans_dir"], bundle)

    def test_plans_dir_custom_bundle_defaults_true_noninteractive(self):
        g = _gather(self.env, self.proj, {"file": None}, "custom", False)
        self.assertTrue(g["plans_dir"])

    def test_minimal_bundle_still_applies_plans_dir_block(self):
        # minimal turns off perms/mcp/autoapprove/memory/hub/brain, but NOT plans-dir —
        # same principle as output-style: applies regardless of the scope of automation.
        out = run(cmd_integrate, self.env,
                  ["--target", str(self.proj), "--bundle", "minimal", "--yes"])
        self.assertIn("plans-dir: plans", out)

    # --- guards -------------------------------------------------------------
    def test_unknown_bundle_exits(self):
        with self.assertRaises(SystemExit):
            run(cmd_integrate, self.env,
                ["--target", str(self.proj), "--bundle", "nope", "--yes"])

    def test_refuses_registry_root(self):
        with self.assertRaises(SystemExit):
            run(cmd_integrate, self.env, ["--target", str(self.root), "--yes"])

    def test_help(self):
        out = run(cmd_integrate, self.env, ["--help"])
        self.assertIn("integrate", out)


if __name__ == "__main__":
    unittest.main()
