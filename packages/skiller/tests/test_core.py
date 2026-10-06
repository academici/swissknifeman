"""CORE-distribution policy: default token skills + default-exclude takes.

The default fixture registry does NOT contain general/oss-dev/system (for accurate
the assertions of other tests held, and CORE was there no-op). Here we add to the registry
with these buckets and check the injection CORE (vendor=skills, connect=buckets),
default-exclude duplicates hub/manual skills and disabling via --no-core."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.connect import do_connect
from skiller.vendor import do_vendor
from skiller.config import core_skill_tuples
from skiller.host import clear_host_cache
from unittest import mock
import tests.fixtures as fx


class CoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        skills = self.root / "skills"
        for name in ("context-economy", "anti-drift", "compact-responses",
                     "session-handoff", "verify-claims"):
            fx.write_skill(skills / "general" / name, name)
        fx.write_skill(skills / "oss-dev" / "gh-review", "gh-review")
        fx.write_skill(skills / "system" / "shared-memory", "shared-memory")
        fx.write_skill(skills / "system" / "cross-project-coordinator",
                       "cross-project-coordinator")
        fx.write_skill(skills / "system" / "local-topology", "local-topology")
        # marketplace must DECLARE supervised core-plugin, otherwise connect-CORE doesn't push him
        # (protection _marketplace_declares: on the old one marketplace/may not be present in plugin tests).
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
            "name": "swissknifeman",
            "plugins": [{"name": "core", "source": "./",
                         "skills": ["./skills/general/context-economy"]}],
        }) + "\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_core_skill_tuples_resolves_and_respects_exclude(self):
        names = {t[3] for t in core_skill_tuples(self.env, set())}
        self.assertEqual(names, {"context-economy", "anti-drift",
                                 "session-handoff", "verify-claims"})
        # exclude (in the form bucket/rel) wins CORE
        excluded = {t[3] for t in core_skill_tuples(self.env, {"general/verify-claims"})}
        self.assertNotIn("verify-claims", excluded)

    def test_vendor_injects_core_even_outside_profile(self):
        # profile laravel-project -> [php, quality]; CORE-skills from general/oss-dev
        # should lie down, although their buckets are not in the profile
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj, {"agent": "generic"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "general" / "context-economy" / "SKILL.md").exists())
        self.assertTrue((dest / "general" / "verify-claims" / "SKILL.md").exists())
        self.assertFalse((dest / "oss-dev" / "gh-review" / "SKILL.md").exists())
        self.assertFalse((dest / "general" / "compact-responses" / "SKILL.md").exists())

    def test_vendor_default_excludes_maind_dupes(self):
        # system is selected explicitly: shared-memory and cross-project-coordinator are removed
        # by default, local-topology remains
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "system"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "system" / "local-topology").exists())
        self.assertFalse((dest / "system" / "shared-memory").exists())
        self.assertFalse((dest / "system" / "cross-project-coordinator").exists())

    def test_no_core_disables_injection_and_default_exclude(self):
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj,
                  {"agent": "generic", "buckets": "system", "no_core": True})
        dest = proj / ".ai" / "skills"
        self.assertFalse((dest / "general" / "context-economy").exists())
        # default-exclude removed -> duplicates in place
        self.assertTrue((dest / "system" / "shared-memory").exists())

    def test_connect_adds_core_plugin(self):
        # Smart connection: CORE-policy push EASY curated plugin `core`,
        # and NOT whole buckets general+oss-dev (saving of resident tokens).
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertIn("core", enabled)
        self.assertNotIn("general", enabled)   # we no longer push entire buckets
        self.assertNotIn("oss-dev", enabled)

    def test_connect_dry_run_redacts_existing_environment_secrets(self):
        proj = fx.make_laravel_project(self.tmp)
        settings_path = proj / ".claude" / "settings.local.json"
        settings_path.parent.mkdir()
        settings_path.write_text(json.dumps({
            "env": {"PERPLEXITY_API_KEY": "private-value"},
            "extraKnownMarketplaces": {},
        }), encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            do_connect(self.env, proj, {"dry_run": True, "no_core": True})

        self.assertNotIn("private-value", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertIn("private-value", settings_path.read_text(encoding="utf-8"))

    def test_cleanup_finds_legacy_claude_manifest_after_provider_path_changes(self):
        proj = fx.make_laravel_project(self.tmp)
        legacy = proj / ".claude" / "skills"
        skill = legacy / "legacy-managed"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("managed\n", encoding="utf-8")
        (legacy / ".swissknifeman-manifest.json").write_text(json.dumps({
            "version": 1,
            "skills": [{"flat_name": "legacy-managed"}],
        }) + "\n", encoding="utf-8")
        # Simulate the new provider contract selecting a different projection.
        (proj / ".swissknifeman" / "config.json").parent.mkdir(parents=True)
        (proj / ".swissknifeman" / "config.json").write_text(json.dumps({
            "version": 1, "mode": "vendor", "skills_path": ".agents/skills",
        }) + "\n", encoding="utf-8")

        do_connect(self.env, proj, {"cleanup_vendored": True, "no_core": True})

        self.assertFalse(skill.exists())
        self.assertFalse((legacy / ".swissknifeman-manifest.json").exists())

    def test_connect_no_core_omits_core_plugin(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {"no_core": True})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertNotIn("core", enabled)

    def test_connect_core_skipped_when_marketplace_lacks_it(self):
        # Protection: marketplace does not declare core (old/empty) → CORE doesn't push,
        # but NOT quiet (C-1) — explicit warn on stderr, tested separately below.
        (self.root / ".claude-plugin" / "marketplace.json").write_text("{}\n")
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertNotIn("core", enabled)

    def test_connect_core_skipped_warns_not_silent(self):
        # C-1: earlier skip CORE (marketplace does not declare the plugin) was quiet -
        # token savings promise voided without signal. Now explicit warn.
        (self.root / ".claude-plugin" / "marketplace.json").write_text("{}\n")
        proj = fx.make_laravel_project(self.tmp)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            do_connect(self.env, proj, {})
        self.assertIn("does not declare the plugin", buf.getvalue())
        self.assertIn("core", buf.getvalue())

    def test_connect_adds_default_command_plugins(self):
        # C-3: host default command plugins (here `plugin-a`) — marketplace-guarded, like core,
        # but NOT CORE-skill: --no-core doesn't touch them (checked below). Previously this thread
        # (connect.py cmd_added) was not covered by the test - command distribution regression
        # wouldn't have been caught.
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
            "name": "swissknifeman",
            "plugins": [
                {"name": "core", "source": "./",
                 "skills": ["./skills/general/context-economy"]},
                {"name": "plugin-a", "source": "./vendor/plugin-a"},
            ],
        }) + "\n")
        host = self.tmp / "host.json"
        host.write_text(json.dumps({"schema_version": 1, "default_command_plugins": ["plugin-a"]}))
        clear_host_cache()
        self.addCleanup(clear_host_cache)
        patcher = mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(host)})
        patcher.start()
        self.addCleanup(patcher.stop)
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {"no_core": True})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        # --no-core disables CORE-skills, but NOT command plugins (not CORE)
        self.assertNotIn("core", enabled)
        self.assertIn("plugin-a", enabled)


if __name__ == "__main__":
    unittest.main()
