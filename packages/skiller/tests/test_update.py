"""Tests update-replay: connect the project, then update restores selection
from projects.json and reapplies it idempotently.

The disk is the source of truth: update detects markers (settings/manifest) and loses
saved options. Network/composer are not needed - everything is in tmpdir against fixture."""
import io
import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import MANIFEST, MARKETPLACE
from skiller.connect import do_connect
from skiller.host import clear_host_cache
from skiller.registry import build_registry
from skiller.skillset import do_sync, skillset_config_path
from skiller.vendor import do_vendor
from skiller.update import (cmd_update, prune_legacy_runtime_links, replay_opts, retire_equivalent_codex_skill_links,
                            retire_legacy_codex_links, retire_legacy_codex_vendor,
                            retire_orphaned_codex_vendor_manifest, update_one)
try:
    from . import fixtures as fx
except ImportError:  # unittest discover loads this module without a package.
    import tests.fixtures as fx


def silently(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _materialize(env):
    reg, *_ = build_registry(env)
    (env.root / "skills.json").write_text(json.dumps(reg, ensure_ascii=False),
                                          encoding="utf-8")


def _write_sync_config(target, cfg):
    p = skillset_config_path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


class UpdateCase(unittest.TestCase):
    def test_equivalent_link_cleanup_archives_only_identical_runtime_content(self):
        project = self.tmp / "equivalent-links"
        directory = project / ".agents/skills"
        directory.mkdir(parents=True)
        inventory_paths = {}
        for name in ("same", "different"):
            source = self.tmp / "local" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
            (source / "upstream.json").write_text("provenance", encoding="utf-8")
            (directory / name).symlink_to(source)
            native = self.tmp / "plugins/cache/swissknifeman/quality/1" / name
            native.mkdir(parents=True)
            (native / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
            inventory_paths[name] = [str(native / "SKILL.md")]
            if name == "different":
                (source / "guide.md").write_text("local-only", encoding="utf-8")
        inventory = {"ok": True, "paths": inventory_paths}
        with mock.patch("skiller.native_codex.native_inventory", return_value=inventory):
            self.assertTrue(silently(retire_equivalent_codex_skill_links, self.env, project,
                                     dry_run=True))
            self.assertTrue((directory / "same").is_symlink())
            self.assertTrue(silently(retire_equivalent_codex_skill_links, self.env, project))
        self.assertFalse((directory / "same").is_symlink())
        self.assertTrue((directory / "different").is_symlink())
        backup = next((project / ".swissknifeman/backups").iterdir())
        self.assertTrue((backup / "same").is_symlink())

    def test_link_cleanup_requires_native_replacement_and_preserves_unique_capability(self):
        project = self.tmp / "linked-project"
        directory = project / ".agents/skills"
        directory.mkdir(parents=True)
        links = {}
        for name in ("duplicate", "unique"):
            source = self.env.root / "skills/php" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(f"---\nname: {name}\ndescription: skill\n---\n")
            (directory / name).symlink_to(source)
            links[name] = str(source)
        marker = project / ".agents/.swissknifeman-codex-links.json"
        marker.write_text(json.dumps({"version": 1, "links": links}))
        before = marker.read_bytes()
        native = self.tmp / "plugins/cache/swissknifeman/php/1/duplicate"
        import shutil
        shutil.copytree(Path(links["duplicate"]), native)
        (Path(links["duplicate"]) / "guide.md").write_text("unique safety rule")
        inventory = {"ok": True, "native_names": {"duplicate"},
                     "paths": {"duplicate": [str(native / "SKILL.md")]}}
        with mock.patch("skiller.native_codex.native_inventory", return_value=inventory):
            self.assertFalse(silently(retire_legacy_codex_links, self.env, project))
            self.assertTrue((directory / "duplicate").is_symlink())
            (native / "guide.md").write_text("unique safety rule")
            self.assertTrue(silently(retire_legacy_codex_links, self.env, project, dry_run=True))
            self.assertEqual(marker.read_bytes(), before)
            self.assertTrue((directory / "duplicate").is_symlink())
            self.assertTrue(silently(retire_legacy_codex_links, self.env, project))
            self.assertFalse((directory / "duplicate").is_symlink())
            self.assertTrue((directory / "unique").is_symlink())
            self.assertEqual(set(json.loads(marker.read_text())["links"]), {"unique"})
            backup = next((project / ".swissknifeman/backups").iterdir())
            self.assertEqual((backup / marker.name).read_bytes(), before)
            self.assertTrue((backup / "duplicate").is_symlink())
            self.assertFalse(silently(retire_legacy_codex_links, self.env, project))
            # Explicit local opt-out permits retirement without any replacement.
            config = project / ".codex/config.toml"
            config.parent.mkdir()
            config.write_text('[[skills.config]]\npath = ' + json.dumps(str(directory / "unique/SKILL.md")) + '\nenabled = false\n')
            disabled_config = config.read_text()
            config.write_text(disabled_config + disabled_config.replace('enabled = false', 'enabled = true'))
            self.assertFalse(silently(retire_legacy_codex_links, self.env, project))
            self.assertTrue((directory / "unique").is_symlink())
            config.write_text(disabled_config)
            self.assertTrue(silently(retire_legacy_codex_links, self.env, project))
            self.assertFalse((directory / "unique").is_symlink())
            self.assertEqual(json.loads(marker.read_text())["links"], {})

    def test_link_cleanup_refuses_modified_destination_before_mutation(self):
        project = self.tmp / "modified-project"
        directory = project / ".agents/skills"
        directory.mkdir(parents=True)
        (directory / "local").mkdir()
        marker = project / ".agents/.swissknifeman-codex-links.json"
        marker.write_text(json.dumps({"version": 1, "links": {"local": str(self.env.root / "skills/php/local")}}))
        with mock.patch("skiller.native_codex.native_inventory", return_value={"ok": True, "native_names": {"local"}}):
            with self.assertRaisesRegex(ValueError, "LEGACY_LINK_MODIFIED"):
                retire_legacy_codex_links(self.env, project)
        self.assertTrue((directory / "local").is_dir())
        self.assertFalse((project / ".swissknifeman/backups").exists())

    def legacy_marker(self, project, *, existing=False):
        path = project / ".agents/skills" / MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"version": 1, "agent": "claude", "layout": "flat", "skills": [{"flat_name": "old", "source_path": "skills/php/old"}]}))
        if existing:
            (path.parent / "old").mkdir()
            (path.parent / "old/SKILL.md").write_text("old bytes")
        return path

    def test_orphan_marker_archives_only_when_all_declared_dirs_are_absent(self):
        project = self.tmp / "legacy"
        path = self.legacy_marker(project, existing=True)
        with mock.patch("skiller.update.detect_codex_marketplace", return_value=True):
            self.assertFalse(retire_orphaned_codex_vendor_manifest(project))
            (path.parent / "old/SKILL.md").unlink()
            (path.parent / "old").rmdir()
            self.assertTrue(retire_orphaned_codex_vendor_manifest(project))
        self.assertFalse(path.exists())
        self.assertEqual(len(list((project / ".swissknifeman/backups").glob("*.json"))), 1)

    def test_explicit_vendor_cleanup_preserves_unlisted_local_and_all_preimages(self):
        project = self.tmp / "legacy"
        path = self.legacy_marker(project, existing=True)
        local = path.parent / "local"
        local.mkdir()
        (local / "SKILL.md").write_text("local bytes")
        with mock.patch("skiller.update.detect_codex_marketplace", return_value=True):
            self.assertTrue(retire_legacy_codex_vendor(self.env, project))
        self.assertTrue((local / "SKILL.md").exists())
        self.assertFalse((path.parent / "old").exists())
        self.assertEqual(next((project / ".swissknifeman/backups").glob("*/old/SKILL.md")).read_text(), "old bytes")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_replay_opts_maps_sources(self):
        self.assertEqual(replay_opts({"profile_source": "flag",
                                      "profile": "laravel-project"}),
                         {"profile": "laravel-project"})
        self.assertEqual(replay_opts({"profile_source": "plugins",
                                      "plugins": ["php", "quality"]}),
                         {"plugins": "php,quality"})
        self.assertEqual(replay_opts({"profile_source": "buckets",
                                      "buckets": ["php"]}),
                         {"buckets": "php"})
        # autodetect/config are re-resolved from disk - flags are not enforced
        self.assertEqual(replay_opts({"profile_source": "autodetect"}), {})

    def test_update_marketplace_idempotent(self):
        proj = fx.make_laravel_project(self.tmp)
        silently(do_connect, self.env, proj, {"profile": "laravel-project"})
        before = (proj / ".claude" / "settings.local.json").read_text()
        silently(cmd_update, self.env, ["--target", str(proj)])
        after = (proj / ".claude" / "settings.local.json").read_text()
        # repeated update does not change enabled plugins
        b = {k for k, v in json.loads(before)["enabledPlugins"].items() if v}
        a = {k for k, v in json.loads(after)["enabledPlugins"].items() if v}
        self.assertEqual(a, b)
        self.assertEqual(a, {f"php@{MARKETPLACE}", f"quality@{MARKETPLACE}"})

    def _with_host(self, config):
        path = self.tmp / "host.json"
        path.write_text(json.dumps({"schema_version": 1, **config}), encoding="utf-8")
        clear_host_cache()
        self.addCleanup(clear_host_cache)
        patcher = mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_update_prunes_only_recognised_legacy_runtime_link(self):
        self._with_host({"legacy_runtime_links": [
            {"link": "vendor/plugin-a", "plugin": "plugin-a", "source": "vendor/plugin-a"}]})
        proj = fx.make_laravel_project(self.tmp)
        silently(do_connect, self.env, proj, {"profile": "laravel-project"})
        plugin_source = self.root / "vendor" / "plugin-a"
        plugin_source.mkdir(parents=True)
        legacy = proj / "vendor" / "plugin-a"
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(plugin_source)

        silently(cmd_update, self.env, ["--target", str(proj)])

        self.assertFalse(legacy.exists())
        self.assertFalse(legacy.is_symlink())

    def test_legacy_runtime_link_cleanup_keeps_project_owned_and_unlisted_links(self):
        self._with_host({"legacy_runtime_links": [
            {"link": "vendor/plugin-a", "plugin": "plugin-a", "source": "vendor/plugin-a"}]})
        proj = self.tmp / "owned"
        own = proj / "lib" / "plugin-a"
        own.mkdir(parents=True)
        legacy = proj / "vendor" / "plugin-a"
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(own)  # same path, project-owned destination
        cached = self.env.home / ".codex/plugins/cache" / MARKETPLACE / "plugin-a" / "1.0.0"
        cached.mkdir(parents=True)
        unlisted = proj / "vendor" / "plugin-b"
        unlisted.symlink_to(cached)  # historical destination, but not a host entry

        self.assertFalse(silently(prune_legacy_runtime_links, self.env, proj))
        self.assertTrue(legacy.is_symlink())
        self.assertTrue(unlisted.is_symlink())
        legacy.unlink()
        legacy.symlink_to(cached)
        self.assertTrue(silently(prune_legacy_runtime_links, self.env, proj, dry_run=True))
        self.assertTrue(legacy.is_symlink())
        self.assertTrue(silently(prune_legacy_runtime_links, self.env, proj))
        self.assertFalse(legacy.is_symlink())

    def test_empty_host_prunes_no_runtime_link(self):
        self._with_host({})
        proj = self.tmp / "standalone"
        cached = self.env.home / ".claude/plugins/cache" / MARKETPLACE / "plugin-a"
        cached.mkdir(parents=True)
        legacy = proj / "vendor" / "plugin-a"
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(cached)
        self.assertFalse(silently(prune_legacy_runtime_links, self.env, proj))
        self.assertTrue(legacy.is_symlink())

    def test_codex_link_roots_extend_owned_sources(self):
        self._with_host({"codex_link_roots": ["vendor/plugin-a/adapters/codex/skills"]})
        project = self.tmp / "host-linked"
        directory = project / ".agents/skills"
        directory.mkdir(parents=True)
        source = self.root / "vendor/plugin-a/adapters/codex/skills/run"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("---\nname: run\ndescription: skill\n---\n")
        (directory / "run").symlink_to(source)
        marker = project / ".agents/.swissknifeman-codex-links.json"
        marker.write_text(json.dumps({"version": 1, "links": {"run": str(source)}}))
        native = self.tmp / "plugins/cache/swissknifeman/plugin-a/1/run"
        import shutil
        shutil.copytree(source, native)
        inventory = {"ok": True, "native_names": {"run"}, "paths": {"run": [str(native / "SKILL.md")]}}
        with mock.patch("skiller.native_codex.native_inventory", return_value=inventory):
            self.assertTrue(silently(retire_legacy_codex_links, self.env, project))
        self.assertFalse((directory / "run").is_symlink())
        self._with_host({})
        (directory / "run").symlink_to(source)
        marker.write_text(json.dumps({"version": 1, "links": {"run": str(source)}}))
        with mock.patch("skiller.native_codex.native_inventory", return_value=inventory):
            with self.assertRaisesRegex(ValueError, "source outside owned skill roots"):
                retire_legacy_codex_links(self.env, project)

    def test_update_adopt_codex_persists_dual_contract_and_bundle(self):
        proj = fx.make_laravel_project(self.tmp)
        materialize = self.root / ".agents" / "plugins" / "marketplace.json"
        materialize.parent.mkdir(parents=True, exist_ok=True)
        materialize.write_text(json.dumps({"name": MARKETPLACE, "plugins": [
            {"name": name, "source": f"./skills/{name}"}
            for name in ("core", "plugin-a", "php", "quality")
        ]}), encoding="utf-8")
        for name in ("core", "plugin-a", "php", "quality"):
            plugin = self.root / "skills" / name
            plugin.mkdir(parents=True, exist_ok=True)
            (plugin / ".codex-plugin").mkdir(exist_ok=True)
            (plugin / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": name, "version": "0.1.0", "skills": ["./"]}),
                encoding="utf-8")
            (plugin / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\n", encoding="utf-8")
        silently(do_connect, self.env, proj, {"profile": "laravel-project"})

        silently(cmd_update, self.env, ["--target", str(proj), "--adopt-codex"])

        config = json.loads((proj / ".swissknife.json").read_text())
        self.assertTrue(config["providers"]["selection"]["claude-code"]["enabled"])
        self.assertTrue(config["providers"]["selection"]["codex"]["enabled"])
        self.assertTrue(config["providers"]["selection"]["cursor"]["enabled"])
        self.assertIn("plugins", config)

    def test_first_dual_connect_excludes_codex_from_following_vendor_sync(self):
        proj = fx.make_laravel_project(self.tmp)
        (proj / ".claude").mkdir(exist_ok=True)
        (proj / ".claude" / "settings.local.json").write_text(json.dumps({
            "extraKnownMarketplaces": {MARKETPLACE: {"source": {}}},
        }), encoding="utf-8")
        _write_sync_config(proj, {"mode": "vendor", "include": ["code-style"]})
        (proj / ".swissknife.json").write_text(json.dumps({"providers": {
            "contract_version": "1.0.0",
            "selection": {"claude-code": {"enabled": True}, "codex": {"enabled": True}},
        }}), encoding="utf-8")

        def connect_then_create_marker(*_args, **_kwargs):
            marker = proj / ".agents/plugins/marketplace.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("{}", encoding="utf-8")

        with mock.patch("skiller.update.do_connect", side_effect=connect_then_create_marker), \
                mock.patch("skiller.update.do_sync") as sync:
            update_one(self.env, proj)

        self.assertEqual(sync.call_args.args[2]["provider_ids"], ("claude-code",))

    def test_update_vendor_replays_buckets(self):
        proj = fx.make_laravel_project(self.tmp)
        silently(do_vendor, self.env, proj,
                 {"agent": "generic", "buckets": "devops"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "devops" / "docker").exists())
        # update should re-decompose the same set by record projects.json
        silently(cmd_update, self.env, ["--target", str(proj)])
        self.assertTrue((dest / "devops" / "docker" / "SKILL.md").exists())
        manifest = json.loads((dest / MANIFEST).read_text())
        self.assertEqual(manifest["agent"], "generic")

    def test_update_routes_sync_config_to_sync(self):
        # sync-project (.swissknifeman/config.json) is being updated sync'ohm, NOT legacy
        # vendor: update should be re-applied skill-granular include from the config.
        _materialize(self.env)
        proj = fx.make_laravel_project(self.tmp)
        _write_sync_config(proj, {"mode": "vendor", "include": ["code-style"]})
        silently(do_sync, self.env, proj, {})
        skills = proj / ".claude" / "skills"
        self.assertTrue((skills / "code-style" / "SKILL.md").exists())
        self.assertFalse((skills / "test-writer").exists())
        # expand the config → update must be re-sync'extract from it
        _write_sync_config(proj, {"mode": "vendor",
                                  "include": ["code-style", "test-writer"]})
        silently(cmd_update, self.env, ["--target", str(proj)])
        self.assertTrue((skills / "test-writer" / "SKILL.md").exists())

    def test_update_all_survives_broken_manifest(self):
        """U-1: broken manifest of one vendor-of the project should not drop the entire
        `update --all` UNHANDLED exception. Without a manifesto do_vendor cannot
        distinguish your old files from others - legitimate die()/collision (needed
        --force), as before (safe behavior, parity with V-6): but now it's
        CONTROLLED SystemExit, caught in loop --all like "failed", and NOT crash,
        taking away the entire batch and other projects."""
        (self.tmp / "p1").mkdir()
        (self.tmp / "p2").mkdir()
        proj1 = fx.make_laravel_project(self.tmp / "p1")
        proj2 = fx.make_laravel_project(self.tmp / "p2")
        silently(do_vendor, self.env, proj1, {"agent": "generic", "buckets": "devops"})
        silently(do_vendor, self.env, proj2, {"agent": "generic", "buckets": "devops"})
        (proj1 / ".ai" / "skills" / MANIFEST).write_text(
            "{not valid json", encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):  # p1 legit failed (see docstring)
                    cmd_update(self.env, ["--all"])  # used to crash here RAW

        # the neighboring project was actually updated - the batch was not interrupted on the first
        self.assertTrue(
            (proj2 / ".ai" / "skills" / "devops" / "docker" / "SKILL.md").exists())
        self.assertIn(str(proj1), buf.getvalue())
        self.assertIn(str(proj2), buf.getvalue())
        self.assertIn("failed", buf.getvalue())

    def test_update_unconnected_dies(self):
        proj = fx.make_laravel_project(self.tmp)
        with self.assertRaises(SystemExit):
            silently(cmd_update, self.env, ["--target", str(proj)])

    def test_update_help(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_update(self.env, ["--help"])
        self.assertIn("skiller update", buf.getvalue())


class TestCursorConnectDistribution(unittest.TestCase):
    def test_build_connect_distribution_plan_skips_cursor_marketplace(self):
        from skiller.publication import build_connect_distribution_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agents" / "plugins").mkdir(parents=True)
            (root / ".agents" / "plugins" / "marketplace.json").write_text(
                json.dumps({"plugins": []}), encoding="utf-8")
            config = {"providers": {
                "contract_version": "1.0.0",
                "selection": {
                    "claude-code": {"enabled": True},
                    "codex": {"enabled": True},
                    "cursor": {"enabled": True},
                },
            }}
            plans = build_connect_distribution_plan(
                config, root, project_id="demo", repo_root=root)
            self.assertEqual(tuple(plan.provider_id for plan in plans),
                             ("claude-code", "codex"))

    def test_build_vendor_distribution_plan_skips_cursor_vendor_path(self):
        from skiller.publication import build_vendor_distribution_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"providers": {
                "contract_version": "1.0.0",
                "selection": {
                    "claude-code": {"enabled": True},
                    "codex": {"enabled": True},
                    "cursor": {"enabled": True},
                },
            }}
            plans = build_vendor_distribution_plan(
                config, root, project_id="demo",
                claude_path=".claude/skills", codex_path=".agents/skills")
            self.assertEqual(tuple(plan.provider_id for plan in plans),
                             ("claude-code", "codex"))


if __name__ == "__main__":
    unittest.main()
