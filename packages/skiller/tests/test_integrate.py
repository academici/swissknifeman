"""Wizard tests integrate (after moving the environment into the host environment tool).

Here we are left with ORCHESTRATION and selection policy: dry-run does not write anything,
minimal-bundle connects skills, `_gather`/`_default_mcp` resolve set MCP.
The environment EXECUTION itself (permissions/MCP/auto-approve/memory) is delegated to
host commands via subprocess — the tool's own blocks are tested with that tool.
In the fixture no host command is installed → env-blocks are skipped softly (graceful skip);
HostDelegationCase pins the argv handed to a synthetic host tool.

Racing against a synthetic registry (tests/fixtures) in temporary directories;
env.home points to tmp — real ~/.swissknifeman and ~/.claude are not touched."""
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

from skiller.common import apply_permissions
from skiller.host import clear_host_cache
from skiller.integrate import (cmd_integrate, _available_mcp, _block_brain, _default_mcp, _gather,
                               _run_environment)
from skiller.registry import build_registry
from skiller.skillset import load_skillset_config
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
        cfg = load_skillset_config(self.proj, self.env)
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

    # --- MCP choice policy (remains in the wizard; execution - in the host tool) ------
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



class HostDelegationCase(unittest.TestCase):
    """Environment blocks run the host's `environment`/`permissions` argv, nothing else."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.env = fx.make_registry(self.tmp)[1]
        self.log = self.tmp / "argv.log"
        # Host paths resolve against the host root: the registry root outside any Git repo.
        tool = self.env.root / "bin" / "env-tool"
        tool.parent.mkdir()
        tool.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {self.log}\n"
                        "[[ \"$1\" == mcp ]] && printf 'context7\\ngithub\\n'\nexit 0\n",
                        encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        self.host = self.tmp / "host.json"
        self.write_host({"commands": {
            "environment": {"argv": ["bin/env-tool"], "install_hint": "env-tool/install.sh"},
            "permissions": {"argv": ["bin/env-tool", "permissions"]}}})
        patcher = mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(self.host)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(clear_host_cache)

    def write_host(self, config):
        self.host.write_text(json.dumps({"schema_version": 1, **config}), encoding="utf-8")
        clear_host_cache()

    def lines(self):
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_environment_blocks_and_permissions_use_host_argv(self):
        target = self.tmp / "project"
        self.assertTrue(_run_environment(self.env, ["hooks", "--global"]))
        self.assertEqual(_available_mcp(self.env), ["context7", "github"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(apply_permissions(self.env, target, "php", dry_run=True))
        self.assertEqual(self.lines(), ["hooks --global", "mcp --list",
                                        f"permissions --target {target} --preset php --dry-run"])

    def test_missing_commands_skip_with_install_hint(self):
        self.write_host({"commands": {"environment": {
            "argv": ["bin/absent"], "install_hint": "env-tool/install.sh"}}})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertFalse(_run_environment(self.env, ["hooks", "--global"]))
            self.assertFalse(apply_permissions(self.env, self.tmp))
        self.assertIn("environment command not configured or not installed - skip "
                      "(install: env-tool/install.sh)", err.getvalue())
        self.assertIn("permissions command not configured or not installed - skip permissions\n",
                      err.getvalue())
        self.assertEqual(_available_mcp(self.env), [])
        self.assertFalse(self.log.exists())


class BrainDocsDelegationCase(unittest.TestCase):
    """Block [9] hands document sync to the host's `brain_docs` command and survives its absence."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.env = fx.make_registry(self.tmp)[1]
        self.target = self.tmp / "project"
        self.log = self.tmp / "argv.log"
        self.tool = self.tmp / "brain-fixture"
        self.write_tool(0)
        self.host = self.tmp / "host.json"
        self.host.write_text(json.dumps({"schema_version": 1, "commands": {"brain_docs": {
            "argv": ["bin/brain", "docs", "integrate"], "env_override": "SKM_BRAIN_BIN",
            "install_hint": "bin/brain"}}}), encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(self.host),
                                               "SKM_BRAIN_BIN": str(self.tool)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(clear_host_cache)
        clear_host_cache()

    def write_tool(self, code, message=""):
        self.tool.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {self.log}\n"
                             f"echo '{message}' >&2\nexit {code}\n", encoding="utf-8")
        self.tool.chmod(self.tool.stat().st_mode | stat.S_IEXEC)

    def block(self, choices, dry):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            _block_brain(self.env, self.target, choices, dry)
        return out.getvalue(), err.getvalue()

    def test_dry_run_passes_project_and_flag(self):
        out, _ = self.block({"brain": True}, True)
        self.assertIn("[9] Brain docs-sync", out)
        self.assertIn(f"repo: {self.target}", out)
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines(),
                         [f"docs integrate --project {self.target} --dry-run"])

    def test_apply_passes_project_only(self):
        self.block({"brain": True}, False)
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines(),
                         [f"docs integrate --project {self.target}"])

    def test_choice_off_does_nothing(self):
        self.assertEqual(self.block({"brain": False}, False), ("", ""))
        self.assertFalse(self.log.exists())

    def test_missing_command_warns_and_continues(self):
        with mock.patch.dict(os.environ, {"SKM_BRAIN_BIN": str(self.tmp / "absent")}):
            out, err = self.block({"brain": True}, False)
        self.assertIn("brain command not configured or not installed - skip (install: bin/brain)", err)
        self.assertIn("Then: brain status", out)
        self.assertFalse(self.log.exists())

    def test_host_without_command_warns_and_continues(self):
        self.host.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        clear_host_cache()
        _, err = self.block({"brain": True}, False)
        self.assertIn("brain command not configured or not installed - skip", err)

    def test_failure_warns_with_stderr_and_does_not_raise(self):
        self.write_tool(3, "VAULT_MISSING: gone")
        _, err = self.block({"brain": True}, False)
        self.assertIn("brain command returned the code 3", err)
        self.assertIn("VAULT_MISSING: gone", err)


if __name__ == "__main__":
    unittest.main()
