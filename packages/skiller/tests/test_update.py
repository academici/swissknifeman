"""Тесты update-реплея: подключаем проект, затем update восстанавливает выбор
из projects.json и повторно применяет его идемпотентно.

Диск — источник истины: update детектит маркеры (settings/манифест) и проигрывает
сохранённые опции. Сеть/composer не нужны — всё в tmpdir против фикстуры."""
import io
import contextlib
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import MANIFEST, MARKETPLACE
from skiller.connect import do_connect
from skiller.registry import build_registry
from skiller.skillset import do_sync, skillset_config_path
from skiller.vendor import do_vendor
from skiller.update import cmd_update, replay_opts, update_one, retire_orphaned_codex_vendor_manifest, retire_legacy_codex_vendor, retire_legacy_codex_links
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
        # autodetect/config переразрешаются с диска — флаги не навязываются
        self.assertEqual(replay_opts({"profile_source": "autodetect"}), {})

    def test_update_marketplace_idempotent(self):
        proj = fx.make_laravel_project(self.tmp)
        silently(do_connect, self.env, proj, {"profile": "laravel-project"})
        before = (proj / ".claude" / "settings.local.json").read_text()
        silently(cmd_update, self.env, ["--target", str(proj)])
        after = (proj / ".claude" / "settings.local.json").read_text()
        # повторный update не меняет включённые плагины
        b = {k for k, v in json.loads(before)["enabledPlugins"].items() if v}
        a = {k for k, v in json.loads(after)["enabledPlugins"].items() if v}
        self.assertEqual(a, b)
        self.assertEqual(a, {f"php@{MARKETPLACE}", f"quality@{MARKETPLACE}"})

    def test_update_prunes_only_recognised_legacy_task_runtime_link(self):
        proj = fx.make_laravel_project(self.tmp)
        silently(do_connect, self.env, proj, {"profile": "laravel-project"})
        task_source = self.root / "packages" / "task"
        task_source.mkdir(parents=True)
        legacy = proj / "packages" / "task"
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(task_source)

        silently(cmd_update, self.env, ["--target", str(proj)])

        self.assertFalse(legacy.exists())
        self.assertFalse(legacy.is_symlink())

    def test_update_adopt_codex_persists_dual_contract_and_bundle(self):
        proj = fx.make_laravel_project(self.tmp)
        materialize = self.root / ".agents" / "plugins" / "marketplace.json"
        materialize.parent.mkdir(parents=True, exist_ok=True)
        materialize.write_text(json.dumps({"name": MARKETPLACE, "plugins": [
            {"name": name, "source": f"./skills/{name}"}
            for name in ("core", "task", "php", "quality")
        ]}), encoding="utf-8")
        for name in ("core", "task", "php", "quality"):
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
        # update должен переразложить тот же набор по записи projects.json
        silently(cmd_update, self.env, ["--target", str(proj)])
        self.assertTrue((dest / "devops" / "docker" / "SKILL.md").exists())
        manifest = json.loads((dest / MANIFEST).read_text())
        self.assertEqual(manifest["agent"], "generic")

    def test_update_routes_sync_config_to_sync(self):
        # sync-проект (.swissknifeman/config.json) обновляется sync'ом, а НЕ legacy
        # vendor: update должен пере-применить skill-granular include из конфига.
        _materialize(self.env)
        proj = fx.make_laravel_project(self.tmp)
        _write_sync_config(proj, {"mode": "vendor", "include": ["code-style"]})
        silently(do_sync, self.env, proj, {})
        skills = proj / ".claude" / "skills"
        self.assertTrue((skills / "code-style" / "SKILL.md").exists())
        self.assertFalse((skills / "test-writer").exists())
        # расширяем конфиг → update должен пере-sync'нуть из него
        _write_sync_config(proj, {"mode": "vendor",
                                  "include": ["code-style", "test-writer"]})
        silently(cmd_update, self.env, ["--target", str(proj)])
        self.assertTrue((skills / "test-writer" / "SKILL.md").exists())

    def test_update_all_survives_broken_manifest(self):
        """U-1: битый манифест одного vendor-проекта не должен ронять весь
        `update --all` НЕОБРАБОТАННЫМ исключением. Без манифеста do_vendor не может
        отличить старые свои файлы от чужих — legitimate die()/collision (нужен
        --force), что и раньше (безопасное поведение, паритет с V-6): но теперь это
        КОНТРОЛИРУЕМЫЙ SystemExit, пойманный циклом --all как "failed", а НЕ краш,
        уносящий весь батч и остальные проекты."""
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
                with self.assertRaises(SystemExit):  # p1 легитимно failed (см. докстринг)
                    cmd_update(self.env, ["--all"])  # раньше падало здесь НЕОБРАБОТАННО

        # соседний проект реально дообновился — батч не прервался на первом же
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


if __name__ == "__main__":
    unittest.main()
