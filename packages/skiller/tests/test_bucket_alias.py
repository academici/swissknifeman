"""Тесты alias-механизма слияний бакетов (SKM-MASTER-002 P7.5).

Alias-бакет — метаданные-запись в buckets.json БЕЗ физического skills/<bucket>: старое
имя бакета переживает будущее слияние как marketplace-плагин source:"./" + явный
skills[]-список ссылок на скиллы, теперь живущие в целевом бакете (`alias_of`) — та же
техника, что у курируемого `core` (см. test_registry_state.py
::test_marketplace_emits_curated_core_plugin). D14: сам механизм не исполняет НИКАКИХ
слияний — тесты гоняют его на синтетическом реестре, живой реестр алиасов не объявляет."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import MARKETPLACE
from skiller.connect import do_connect
from skiller.registry import (alias_migration_hints, build_registry,
                              load_bucket_aliases, write_plugin_manifests)
from skiller.status import cmd_status
from skiller.update import cmd_update
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def _add_alias_bucket(root, name, alias_of, skills):
    """Дописать alias-запись в buckets.json синтетического реестра."""
    bj_file = root / "buckets.json"
    bj = json.loads(bj_file.read_text(encoding="utf-8"))
    bj[name] = {"description": f"Alias of {alias_of}", "category": "meta",
               "tags": [], "alias_of": alias_of, "skills": skills}
    bj_file.write_text(json.dumps(bj), encoding="utf-8")


class BuildRegistryAliasCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_alias_bucket_not_orphan_and_no_physical_dir_required(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/docker"])
        reg, meta, dirs = build_registry(self.env)
        self.assertNotIn("docker-legacy", dirs)          # нет физического каталога
        self.assertIn("docker-legacy", meta)              # но метаданные есть
        # реестр скиллов не тронут (алиас не физический бакет со скиллами)
        self.assertNotIn("docker-legacy", reg["buckets"])

    def test_alias_bad_target_dies(self):
        _add_alias_bucket(self.root, "docker-legacy", "no-such-bucket", ["devops/docker"])
        with self.assertRaises(SystemExit):
            build_registry(self.env)

    def test_alias_marketplace_entry_matches_core_precedent(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/docker"])
        _reg, meta, dirs = build_registry(self.env)
        write_plugin_manifests(self.env, meta, dirs)
        mp = json.loads((self.root / ".claude-plugin" / "marketplace.json").read_text())
        alias = next((p for p in mp["plugins"] if p["name"] == "docker-legacy"), None)
        self.assertIsNotNone(alias, "marketplace должен содержать alias-плагин")
        self.assertEqual(alias["source"], "./")
        self.assertEqual(alias["skills"], ["./skills/devops/docker"])
        self.assertEqual(alias["alias_of"], "devops")
        self.assertEqual(alias["package"], "skiller")
        # имя существующего бакета devops не тронуто — по-прежнему обычная запись
        devops = next(p for p in mp["plugins"] if p["name"] == "devops")
        self.assertEqual(devops["source"], "./skills/devops")
        self.assertNotIn("alias_of", devops)

    def test_alias_with_no_resolvable_skills_emits_nothing(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/does-not-exist"])
        _reg, meta, dirs = build_registry(self.env)
        write_plugin_manifests(self.env, meta, dirs)
        mp = json.loads((self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertIsNone(next((p for p in mp["plugins"] if p["name"] == "docker-legacy"), None))

    def test_no_aliases_declared_leaves_marketplace_unchanged(self):
        # Критерий невредимости: без алиасов в buckets.json генерёжка не добавляет плагинов.
        _reg, meta, dirs = build_registry(self.env)
        write_plugin_manifests(self.env, meta, dirs)
        mp = json.loads((self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertFalse(any(p.get("alias_of") for p in mp["plugins"]))


class LoadAliasesAndHintsUnitCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_bucket_aliases_empty_by_default(self):
        self.assertEqual(load_bucket_aliases(self.env), {})

    def test_load_bucket_aliases_reads_declared(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/docker"])
        self.assertEqual(load_bucket_aliases(self.env), {"docker-legacy": "devops"})

    def test_hints_pure(self):
        aliases = {"docker-legacy": "devops"}
        self.assertEqual(
            alias_migration_hints(aliases, ["php", "docker-legacy"]),
            ["бакет 'docker-legacy' теперь 'devops' — обновите enabledPlugins, "
             "когда удобно."])
        self.assertEqual(alias_migration_hints(aliases, ["php"]), [])
        self.assertEqual(alias_migration_hints({}, ["docker-legacy"]), [])


class StatusAliasHintCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _enable_plugins(self, buckets):
        d = self.proj / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "settings.local.json").write_text(json.dumps({
            "extraKnownMarketplaces": {
                MARKETPLACE: {"source": {"source": "directory", "path": str(self.root)}}},
            "enabledPlugins": {f"{b}@{MARKETPLACE}": True for b in buckets},
        }), encoding="utf-8")

    def test_status_prints_alias_hint_for_enabled_legacy_bucket(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/docker"])
        self._enable_plugins(["php", "docker-legacy"])
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertIn("бакет 'docker-legacy' теперь 'devops'", out)

    def test_status_json_carries_alias_hints(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/docker"])
        self._enable_plugins(["php", "docker-legacy"])
        out = run(cmd_status, self.env, ["--target", str(self.proj), "--json"])
        report = json.loads(out)
        self.assertEqual(report["connect"]["alias_hints"],
                         ["бакет 'docker-legacy' теперь 'devops' — обновите "
                          "enabledPlugins, когда удобно."])

    def test_status_no_hint_without_alias(self):
        self._enable_plugins(["php"])
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("Подсказка:", out)


class UpdateAliasHintCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_update_prints_alias_migration_hint(self):
        _add_alias_bucket(self.root, "docker-legacy", "devops", ["devops/docker"])
        proj = fx.make_laravel_project(self.tmp)
        run(do_connect, self.env, proj, {"profile": "laravel-project"})
        settings_file = proj / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        settings["enabledPlugins"][f"docker-legacy@{MARKETPLACE}"] = True
        settings_file.write_text(json.dumps(settings), encoding="utf-8")

        out = run(cmd_update, self.env, ["--target", str(proj)])
        self.assertIn("бакет 'docker-legacy' теперь 'devops'", out)

    def test_update_no_hint_without_legacy_bucket_enabled(self):
        # NB: "Подсказка:" сам по себе не уникален (напр. хаб-подсказка do_connect) —
        # проверяем отсутствие ИМЕННО alias-миграционной фразы.
        proj = fx.make_laravel_project(self.tmp)
        run(do_connect, self.env, proj, {"profile": "laravel-project"})
        out = run(cmd_update, self.env, ["--target", str(proj)])
        self.assertNotIn("теперь", out)


if __name__ == "__main__":
    unittest.main()
