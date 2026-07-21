"""Тесты skillset — vendor-режим на .swissknifeman/config.json.

Покрывают: резолв правил (include/buckets/exclude), sync (install/update/prune),
безопасное удаление по managed (чужие скиллы не трогаются), обновление по sha256,
dry-run без записи."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller.registry import build_registry
from skiller.skillset import (_registry_index, cmd_init, do_sync, load_lock,
                                    load_skillset_config,
                                    materialize_skillset_config, plan_sync,
                                    resolve_skillset, skillset_config_path,
                                    sync_skillset, write_lock)

from skiller.common import MANIFEST, Env

from tests.fixtures import make_laravel_project, make_registry, write_skill


def _write_core_skills(root):
    """Положить CORE_SKILLS + maind-дубли в синтетический реестр и
    дописать их бакеты в buckets.json (требование 1:1 с каталогами)."""
    skills = root / "skills"
    for name in ("context-economy", "anti-drift", "compact-responses",
                 "session-handoff"):
        write_skill(skills / "general" / name, name)
    write_skill(skills / "oss-dev" / "gh-review", "gh-review")
    write_skill(skills / "system" / "shared-memory", "shared-memory")
    bf = root / "buckets.json"
    meta = json.loads(bf.read_text(encoding="utf-8"))
    for b in ("general", "oss-dev", "system"):
        meta[b] = {"description": b, "category": "general", "tags": [b]}
    bf.write_text(json.dumps(meta) + "\n", encoding="utf-8")


def _materialize_registry(env):
    """Записать skills.json из синтетического реестра (как делает cmd_registry)."""
    reg, *_ = build_registry(env)
    (env.root / "skills.json").write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_config(target, cfg):
    d = skillset_config_path(target).parent
    d.mkdir(parents=True, exist_ok=True)
    skillset_config_path(target).write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def _write_preset(root, name, **body):
    """Положить presets/<name>.json в синтетический реестр."""
    d = root / "presets"
    d.mkdir(parents=True, exist_ok=True)
    obj = {"name": name, "description": f"test preset {name}", **body}
    (d / f"{name}.json").write_text(
        json.dumps(obj, ensure_ascii=False), encoding="utf-8")


class TestResolve(unittest.TestCase):
    def test_buckets_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            entries, skipped = resolve_skillset(env, {"buckets": ["php"]})
            names = {e["name"] for e in entries}
            self.assertEqual(names, {"laravel-conventions", "code-style"})
            self.assertEqual(skipped, [])

    def test_include_individual_cross_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            entries, _ = resolve_skillset(
                env, {"include": ["php/code-style", "test-writer"]})
            names = {e["name"] for e in entries}
            self.assertEqual(names, {"code-style", "test-writer"})

    def test_include_drifted_path_resolves_by_basename(self):
        # после раскола бакетов старый путь 'oldbucket/code-style' промахивается
        # по полному ключу, но добивается по базовому имени (а не молча теряется).
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            entries, skipped = resolve_skillset(
                env, {"include": ["oldbucket/code-style"]})
            names = {e["name"] for e in entries}
            self.assertIn("code-style", names)
            self.assertEqual(skipped, [])

    def test_buckets_minus_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            entries, _ = resolve_skillset(
                env, {"buckets": ["php"], "exclude": ["code-style"]})
            names = {e["name"] for e in entries}
            self.assertEqual(names, {"laravel-conventions"})

    def test_include_unknown_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            entries, skipped = resolve_skillset(
                env, {"include": ["nope/ghost"]})
            self.assertEqual(entries, [])
            self.assertEqual(skipped, ["nope/ghost"])


class TestPresets(unittest.TestCase):
    def test_preset_expands_to_include(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            _write_preset(root, "p-core", include=["php/code-style"])
            entries, skipped = resolve_skillset(env, {"presets": ["p-core"]})
            self.assertEqual({e["name"] for e in entries}, {"code-style"})
            self.assertEqual(skipped, [])

    def test_preset_extends_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            _write_preset(root, "p-base", include=["php/code-style"])
            _write_preset(root, "p-ext", extends=["p-base"],
                          include=["test-writer"])
            entries, _ = resolve_skillset(env, {"presets": ["p-ext"]})
            self.assertEqual({e["name"] for e in entries},
                             {"code-style", "test-writer"})

    def test_preset_exclude_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            _write_preset(root, "p-php", buckets=["php"])
            entries, _ = resolve_skillset(
                env, {"presets": ["p-php"], "exclude": ["code-style"]})
            self.assertEqual({e["name"] for e in entries},
                             {"laravel-conventions"})

    def test_preset_unknown_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            entries, skipped = resolve_skillset(env, {"presets": ["ghost"]})
            self.assertEqual(entries, [])
            self.assertIn("ghost", skipped)

    def test_preset_extends_cycle_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            _write_preset(root, "p-a", extends=["p-b"])
            _write_preset(root, "p-b", extends=["p-a"])
            with self.assertRaises(SystemExit):
                resolve_skillset(env, {"presets": ["p-a"]})


class TestSync(unittest.TestCase):
    def test_install_writes_files_and_managed_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            cfg = {"mode": "vendor", "buckets": ["php"]}
            sync_skillset(env, target, cfg)

            self.assertTrue((target / ".claude/skills/laravel-conventions/SKILL.md").is_file())
            self.assertTrue((target / ".claude/skills/code-style/SKILL.md").is_file())
            lock = load_lock(target)["skills"]
            self.assertEqual(lock["code-style"]["source"], "swissknifeman")
            self.assertTrue(lock["code-style"]["managed"])
            self.assertEqual(lock["code-style"]["bucket"], "php")
            self.assertTrue(lock["code-style"]["sha256"])

    def test_skills_path_change_prunes_old_location(self):
        """V-9: смена skills_path в конфиге не должна оставлять осиротевшую копию
        по старому пути — переустановка на новом месте + удаление старого."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            cfg = {"mode": "vendor", "include": ["code-style"]}
            sync_skillset(env, target, cfg)
            self.assertTrue((target / ".claude/skills/code-style/SKILL.md").is_file())

            cfg2 = {"mode": "vendor", "include": ["code-style"],
                    "skills_path": ".claude/skills2"}
            sync_skillset(env, target, cfg2)

            # новое место — есть; старое — осиротевшая копия удалена, не задвоена
            self.assertTrue((target / ".claude/skills2/code-style/SKILL.md").is_file())
            self.assertFalse((target / ".claude/skills/code-style").exists())
            lock = load_lock(target)["skills"]
            self.assertEqual(lock["code-style"]["installed_path"],
                             ".claude/skills2/code-style")

    def test_copy_failure_not_reported_as_installed(self):
        """safe_copy_skill может пропустить копию (containment-стоп/TOCTOU-гонка) —
        такой скилл НЕ должен попасть ни в lock, ни в plan['installed'] (V-2:
        раньше это тихо проглатывалось, sync рапортовал план как факт)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            cfg = {"mode": "vendor", "buckets": ["php"]}
            with mock.patch("skiller.skillset.safe_copy_skill", return_value=False):
                plan = sync_skillset(env, target, cfg)
            self.assertEqual(plan["installed"], [])
            self.assertCountEqual(plan["skip_copy"], plan["add"])
            self.assertEqual(load_lock(target).get("skills", {}), {})
            self.assertFalse((target / ".claude/skills/code-style").exists())

    def test_gitignore_managed_emits_ignore_for_managed_only(self):
        # gitignore_managed: managed-скиллы попадают в <skills_path>/.gitignore
        # (держим вне git, воспроизводимы sync); локальный/кастомный — НЕ попадает.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            local = target / ".claude/skills/my-custom"
            local.mkdir(parents=True)
            (local / "SKILL.md").write_text("# custom\n", encoding="utf-8")

            sync_skillset(env, target, {"mode": "vendor", "buckets": ["php"],
                                        "gitignore_managed": True})
            gi = target / ".claude/skills/.gitignore"
            self.assertTrue(gi.is_file())
            body = gi.read_text(encoding="utf-8")
            self.assertIn("/code-style/", body)       # managed → игнорится
            self.assertNotIn("/my-custom/", body)     # локальный → остаётся в репо
            self.assertTrue((local / "SKILL.md").is_file())  # локальный не тронут

            # выключение флага убирает НАШ .gitignore (managed снова коммитятся)
            sync_skillset(env, target, {"mode": "vendor", "buckets": ["php"]})
            self.assertFalse(gi.exists())

    def test_sync_excludes_ru_source_and_evals(self):
        # Регрессия: sync (канонический Claude-канал) НЕ копирует SKILL.ru.md (русский
        # SSOT), evals/, upstream.json, .claude-plugin — иначе утечка RU-источника во
        # все downstream-проекты. Едет только EN-канон SKILL.md (common.SKILL_IGNORE).
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            src = next((root / "skills").glob("**/code-style/SKILL.md")).parent
            (src / "SKILL.ru.md").write_text("# РУССКИЙ ИСТОЧНИК\n", encoding="utf-8")
            (src / "upstream.json").write_text("{}", encoding="utf-8")
            (src / "evals").mkdir(exist_ok=True)
            (src / "evals" / "evals.json").write_text("[]", encoding="utf-8")
            (src / ".claude-plugin").mkdir(exist_ok=True)
            (src / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

            target = make_laravel_project(tmp)
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})

            dst = target / ".claude/skills/code-style"
            self.assertTrue((dst / "SKILL.md").is_file())      # EN-канон едет
            self.assertFalse((dst / "SKILL.ru.md").exists())   # RU-источник НЕ едет
            self.assertFalse((dst / "evals").exists())
            self.assertFalse((dst / "upstream.json").exists())
            self.assertFalse((dst / ".claude-plugin").exists())

    def test_sync_pulls_transitive_requires(self):
        # skill-granular include тянет зависимость по requires (паритет с vendor);
        # без этого include скилла с requires молча терял зависимость.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            # laravel-conventions requires code-style (см. make_registry)
            sync_skillset(env, target,
                          {"mode": "vendor", "include": ["laravel-conventions"]})
            self.assertTrue((target / ".claude/skills/laravel-conventions/SKILL.md").is_file())
            self.assertTrue((target / ".claude/skills/code-style/SKILL.md").is_file())
            self.assertIn("code-style", load_lock(target)["skills"])

    def test_sync_exclude_beats_requires(self):
        # exclude побеждает зависимость: code-style не приедет, даже будучи requires.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            sync_skillset(env, target, {"mode": "vendor",
                                        "include": ["laravel-conventions"],
                                        "exclude": ["code-style"]})
            self.assertTrue((target / ".claude/skills/laravel-conventions").is_dir())
            self.assertFalse((target / ".claude/skills/code-style").is_dir())

    def test_prune_removes_managed_dropped_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            sync_skillset(env, target, {"mode": "vendor", "buckets": ["php"]})
            self.assertTrue((target / ".claude/skills/laravel-conventions").is_dir())

            # сузили конфиг: только code-style (laravel-conventions им НЕ требуется →
            # выбывает и прунится; code-style зависимостей не имеет).
            sync_skillset(env, target,
                          {"mode": "vendor", "include": ["code-style"]})
            self.assertTrue((target / ".claude/skills/code-style").is_dir())
            self.assertFalse((target / ".claude/skills/laravel-conventions").is_dir())
            self.assertNotIn("laravel-conventions", load_lock(target)["skills"])

    def test_foreign_skill_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            # чужой скилл, поставленный не нами (нет managed)
            foreign = target / ".claude/skills/ecosystem-mcp"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("---\nname: ecosystem-mcp\n---\n")

            sync_skillset(env, target, {"mode": "vendor", "buckets": ["php"]})
            # наш скилл встал, чужой жив, в lock его нет среди managed
            self.assertTrue((target / ".claude/skills/laravel-conventions").is_dir())
            self.assertTrue(foreign.is_dir())

            # повторный sync с сужением — чужой по-прежнему цел
            sync_skillset(env, target, {"mode": "vendor", "include": []})
            self.assertTrue(foreign.is_dir())

    def test_update_on_sha_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})
            sha1 = load_lock(target)["skills"]["code-style"]["sha256"]

            # меняем содержимое скилла в библиотеке + пересобираем реестр
            write_skill(root / "skills" / "php" / "code-style", "code-style",
                        description="PHP code style v2", body="Changed.\n")
            _materialize_registry(env)

            plan = plan_sync(env, target, {"mode": "vendor", "include": ["code-style"]})
            self.assertIn("code-style", plan["update"])
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})
            sha2 = load_lock(target)["skills"]["code-style"]["sha256"]
            self.assertNotEqual(sha1, sha2)
            self.assertIn("Changed.", (target / ".claude/skills/code-style/SKILL.md")
                          .read_text(encoding="utf-8"))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            plan = sync_skillset(env, target, {"mode": "vendor", "buckets": ["php"]},
                                 dry_run=True)
            self.assertEqual(set(plan["add"]), {"laravel-conventions", "code-style"})
            self.assertFalse((target / ".claude/skills").exists())
            self.assertFalse((target / "skills-lock.json").exists())

    def test_idempotent_second_sync_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            cfg = {"mode": "vendor", "buckets": ["php"]}
            sync_skillset(env, target, cfg)
            plan = plan_sync(env, target, cfg)
            self.assertEqual(plan["add"], [])
            self.assertEqual(plan["update"], [])
            self.assertEqual(plan["remove"], [])
            self.assertEqual(set(plan["keep"]), {"laravel-conventions", "code-style"})


class TestConflicts(unittest.TestCase):
    def test_foreign_dir_conflict_skipped_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            # чужой скилл с тем же именем, что наш в конфиге
            foreign = target / ".claude/skills/code-style"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("---\nname: code-style\n---\nMINE\n")

            plan = plan_sync(env, target, {"mode": "vendor", "include": ["code-style"]})
            self.assertIn("code-style", plan["conflicts"])
            self.assertNotIn("code-style", plan["add"])
            # содержимое РАЗНОЕ (MINE vs реестр) — не похоже на прерванный sync (V-6)
            self.assertNotIn("code-style", plan["conflicts_likely_ours"])

            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})
            # чужой не тронут, в lock не попал
            self.assertIn("MINE", (foreign / "SKILL.md").read_text(encoding="utf-8"))
            self.assertNotIn("code-style", load_lock(target).get("skills", {}))

    def test_force_replaces_foreign(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            foreign = target / ".claude/skills/code-style"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("---\nname: code-style\n---\nMINE\n")

            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]},
                          force=True)
            self.assertNotIn("MINE", (foreign / "SKILL.md").read_text(encoding="utf-8"))
            self.assertTrue(load_lock(target)["skills"]["code-style"]["managed"])

    def test_symlink_collision_handled(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            # симлинк-«скилл» с конфликтным именем (как .ai/skills mount)
            real = target / ".ai/skills/code-style"
            real.mkdir(parents=True)
            (real / "SKILL.md").write_text("---\nname: code-style\n---\nLINKED\n")
            link_dir = target / ".claude/skills"
            link_dir.mkdir(parents=True)
            (link_dir / "code-style").symlink_to("../../.ai/skills/code-style")

            plan = plan_sync(env, target, {"mode": "vendor", "include": ["code-style"]})
            self.assertIn("code-style", plan["conflicts"])
            # с force — симлинк снят, на его месте реальная копия, target жив
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]},
                          force=True)
            dst = link_dir / "code-style"
            self.assertFalse(dst.is_symlink())
            self.assertTrue(dst.is_dir())
            self.assertTrue((real / "SKILL.md").is_file())  # цель симлинка цела


class TestConfigLoad(unittest.TestCase):
    def test_rejects_unknown_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "vendor", "bukkit": ["php"]})
            with self.assertRaises(SystemExit):
                load_skillset_config(target)

    def test_rejects_non_vendor_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "connect"})
            with self.assertRaises(SystemExit):
                load_skillset_config(target)

    def test_missing_config_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            target = make_laravel_project(tmp)
            self.assertIsNone(load_skillset_config(target))


class TestCoreAndManifest(unittest.TestCase):
    def test_include_core_injects_core_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _write_core_skills(root)
            _materialize_registry(env)
            entries, _ = resolve_skillset(
                env, {"include": ["php/code-style"]}, include_core=True)
            names = {e["name"] for e in entries}
            self.assertIn("code-style", names)
            self.assertIn("context-economy", names)
            self.assertIn("gh-review", names)
            # без include_core CORE не добавляется
            base, _ = resolve_skillset(env, {"include": ["php/code-style"]})
            self.assertEqual({e["name"] for e in base}, {"code-style"})

    def test_include_core_applies_default_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _write_core_skills(root)
            _materialize_registry(env)
            entries, _ = resolve_skillset(
                env, {"buckets": ["system"]}, include_core=True)
            names = {e["name"] for e in entries}
            self.assertNotIn("shared-memory", names)  # DEFAULT_EXCLUDE

    def test_sync_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "vendor", "buckets": ["php"]})
            sync_skillset(env, target, {"buckets": ["php"]})
            mf = target / ".claude" / "skills" / MANIFEST
            self.assertTrue(mf.is_file())
            data = json.loads(mf.read_text(encoding="utf-8"))
            self.assertEqual(data["layout"], "flat")
            self.assertEqual(data["version"], 1)  # версия схемы манифеста
            # installed_at — ISO с временем (now_iso), не голая дата
            self.assertIn("T", data["installed_at"])
            self.assertTrue(data["installed_at"].endswith("Z"))
            # атомарная запись не оставляет .tmp-хвоста
            self.assertFalse((mf.parent / (MANIFEST + ".tmp")).exists())
            names = {s["flat_name"] for s in data["skills"]}
            self.assertEqual(names, {"laravel-conventions", "code-style"})
            self.assertTrue(all(s["source_path"].startswith("skills/")
                                for s in data["skills"]))

    def test_dry_run_writes_no_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            sync_skillset(env, target, {"buckets": ["php"]}, dry_run=True)
            self.assertFalse((target / ".claude" / "skills" / MANIFEST).exists())


class TestLockHygiene(unittest.TestCase):
    """Разделение managed (наше) vs чужого в skills-lock.json: sync трогает только
    своё, чужие/ручные записи переживают синк, ручная чистка lock не оставляет хвостов."""

    def _seed(self, tmp):
        root, env = make_registry(tmp)
        _materialize_registry(env)
        target = make_laravel_project(tmp)
        return root, env, target

    def test_foreign_lock_entry_survives_sync(self):
        """Запись, добавленная в lock вручную (не managed — свой скилл / другой хаб),
        переживает sync: мы синхронизируем ТОЛЬКО managed=true."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env, target = self._seed(tmp)
            # ставим наш набор и дописываем в lock чужую запись руками
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})
            lock = load_lock(target)
            lock["skills"]["my-own"] = {"source": "local", "managed": False,
                                        "installed_path": ".claude/skills/my-own"}
            (target / "skills-lock.json").write_text(
                json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")

            # повторный sync с тем же конфигом — чужая запись на месте, наша managed жива
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})
            after = load_lock(target)["skills"]
            self.assertIn("my-own", after)
            self.assertFalse(after["my-own"].get("managed"))
            self.assertEqual(after["my-own"]["source"], "local")
            self.assertTrue(after["code-style"]["managed"])

    def test_foreign_lock_entry_survives_even_when_config_empties(self):
        """Сужение конфига до пустого удаляет НАШИ managed, но не чужую запись."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env, target = self._seed(tmp)
            sync_skillset(env, target, {"mode": "vendor", "include": ["code-style"]})
            lock = load_lock(target)
            lock["skills"]["my-own"] = {"source": "local", "managed": False}
            (target / "skills-lock.json").write_text(
                json.dumps(lock, ensure_ascii=False), encoding="utf-8")

            sync_skillset(env, target, {"mode": "vendor", "include": []})
            after = load_lock(target)["skills"]
            self.assertIn("my-own", after)           # чужое цело
            self.assertNotIn("code-style", after)    # наше managed выпало (prune)
            self.assertFalse((target / ".claude/skills/code-style").exists())

    def test_manual_lock_cleanup_readopts_with_force_no_dup(self):
        """Ручная чистка managed-записи из lock при живой папке: без --force путь
        считается чужим (пропуск), с --force скилл чисто пере-усыновляется —
        в lock одна managed-запись, без хвостов/дублей."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env, target = self._seed(tmp)
            cfg = {"mode": "vendor", "include": ["code-style"]}
            sync_skillset(env, target, cfg)
            # пользователь руками вычистил нашу запись (папка осталась)
            lock = load_lock(target)
            del lock["skills"]["code-style"]
            (target / "skills-lock.json").write_text(
                json.dumps(lock, ensure_ascii=False), encoding="utf-8")
            self.assertTrue((target / ".claude/skills/code-style").is_dir())

            # без force — путь занят «чужим» (lock пуст), конфликт-пропуск. Содержимое
            # СОВПАДАЕТ с реестром (файлы не тронуты) — как при прерванном sync (V-6),
            # НО это осознанная ручная чистка → остаётся conflict, не авто-update
            # (см. plan_sync); сигнал доступен через conflicts_likely_ours для warn'а.
            plan = plan_sync(env, target, cfg)
            self.assertIn("code-style", plan["conflicts"])
            self.assertNotIn("code-style", plan["add"])
            self.assertIn("code-style", plan["conflicts_likely_ours"])

            # с force — чистое пере-усыновление: ровно одна managed-запись
            sync_skillset(env, target, cfg, force=True)
            after = load_lock(target)["skills"]
            self.assertEqual(
                [n for n in after if after[n].get("managed")], ["code-style"])
            self.assertTrue(after["code-style"]["managed"])
            self.assertTrue((target / ".claude/skills/code-style/SKILL.md").is_file())

    def test_broken_lock_json_fails_closed_without_reconstruction(self):
        """Повреждённый provenance lock не восстанавливается из манифеста: обычный
        sync обязан сохранить и lock, и managed bytes до явного восстановления."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env, target = self._seed(tmp)
            cfg = {"mode": "vendor", "include": ["code-style"]}
            sync_skillset(env, target, cfg)
            self.assertTrue((target / ".claude/skills/code-style").is_dir())

            # lock физически битый (не валидный JSON) — манифест при этом цел
            (target / "skills-lock.json").write_text("{not valid json", encoding="utf-8")
            plan = plan_sync(env, target, cfg)
            self.assertEqual(plan["provenance_invalid"], "invalid-json")
            before_skill = (target / ".claude/skills/code-style/SKILL.md").read_bytes()
            with self.assertRaises(SystemExit):
                sync_skillset(env, target, cfg)
            self.assertEqual((target / "skills-lock.json").read_text(encoding="utf-8"),
                             "{not valid json")
            self.assertEqual((target / ".claude/skills/code-style/SKILL.md").read_bytes(),
                             before_skill)


class TestDoSync(unittest.TestCase):
    """do_sync — vendor-канал «опубликовать в репо», вызываемый integrate/onboard."""

    def test_materializes_config_from_profile_and_syncs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)  # autodetect → laravel-project
            rec = do_sync(env, target, {})
            # конфиг создан из профиля (laravel-project = php+quality)
            cfg = load_skillset_config(target)
            self.assertEqual(cfg["mode"], "vendor")
            self.assertIn("php", cfg["buckets"])
            # скиллы физически в .claude/skills, lock managed
            self.assertTrue(
                (target / ".claude/skills/code-style/SKILL.md").is_file())
            self.assertTrue(load_lock(target)["skills"]["code-style"]["managed"])
            self.assertEqual(rec["channel"], "vendor")

    def test_respects_existing_curated_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            # курированный конфиг: только одна позиция — do_sync его НЕ перетирает
            _write_config(target, {"mode": "vendor", "include": ["code-style"]})
            do_sync(env, target, {})
            self.assertTrue((target / ".claude/skills/code-style").is_dir())
            self.assertFalse(
                (target / ".claude/skills/laravel-conventions").exists())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            do_sync(env, target, {"dry_run": True})
            self.assertFalse((target / ".swissknifeman").exists())
            self.assertFalse((target / ".claude" / "skills").exists())


class TestRegistryIndexWarns(unittest.TestCase):
    """_registry_index больше не теряет записи молча: warn при пропуске
    (нет name/path) и при дубле имени между бакетами."""

    def _index(self, env, skills):
        (env.root / "skills.json").write_text(
            json.dumps({"skills": skills}), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            by_key, by_name = _registry_index(env)
        return by_key, by_name, err.getvalue()

    def test_skips_entry_without_name_or_path_with_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            by_key, by_name, err = self._index(env, [
                {"name": "good", "bucket": "php",
                 "path": "skills/php/good/SKILL.md"},
                {"bucket": "php", "path": "skills/php/ghost/SKILL.md"},  # нет name
                {"name": "no-path", "bucket": "php"},                   # нет path
            ])
            self.assertIn("good", by_name)
            self.assertNotIn("no-path", by_name)
            self.assertEqual(err.count("пропущена"), 2)

    def test_duplicate_name_warns_keeps_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            by_key, by_name, err = self._index(env, [
                {"name": "dup", "bucket": "php",
                 "path": "skills/php/dup/SKILL.md"},
                {"name": "dup", "bucket": "devops",
                 "path": "skills/devops/dup/SKILL.md"},
            ])
            # по полному пути доступны оба, по короткому имени — первый (php)
            self.assertIn("php/dup", by_key)
            self.assertIn("devops/dup", by_key)
            self.assertEqual(by_name["dup"]["bucket"], "php")
            self.assertIn("дубль имени", err)


class TestInit(unittest.TestCase):
    """materialize_skillset_config — единая материализация конфига для init/do_sync."""

    def _materialize(self, env, target, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return materialize_skillset_config(env, target, kw.pop("opts", {}), **kw)

    def test_materialize_creates_vendor_config_from_autodetect(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)  # autodetect → laravel-project
            cfg, profile, created = self._materialize(env, target)
            self.assertTrue(created)
            self.assertEqual(profile, "laravel-project")
            self.assertEqual(cfg["mode"], "vendor")
            self.assertEqual(cfg["version"], 1)
            self.assertEqual(set(cfg["buckets"]), {"php", "quality"})
            # файл реально записан и валиден как .swissknifeman/config.json
            self.assertTrue(skillset_config_path(target).is_file())
            self.assertEqual(load_skillset_config(target)["mode"], "vendor")

    def test_materialize_respects_existing_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "vendor", "buckets": ["devops"]})
            cfg, _profile, created = self._materialize(env, target)
            self.assertFalse(created)               # курированный не перетёрт
            self.assertEqual(cfg["buckets"], ["devops"])

    def test_materialize_force_overwrites_from_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "vendor", "buckets": ["devops"]})
            cfg, _profile, created = self._materialize(env, target, force=True)
            self.assertTrue(created)
            self.assertEqual(set(cfg["buckets"]), {"php", "quality"})

    def test_materialize_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            self._materialize(env, target, dry=True, force=True)
            self.assertFalse(skillset_config_path(target).is_file())

    # --- cmd_init: верхний слой (resolve_target + idempotency + guard) --------
    def test_cmd_init_idempotent_keeps_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "vendor", "buckets": ["devops"]})
            before = skillset_config_path(target).read_text(encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                cmd_init(env, ["--target", str(target)])
            self.assertIn("уже есть", buf.getvalue())
            self.assertEqual(  # курированный конфиг не перетёрт
                skillset_config_path(target).read_text(encoding="utf-8"), before)

    def test_cmd_init_force_overwrites_from_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            _write_config(target, {"mode": "vendor", "buckets": ["devops"]})
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_init(env, ["--target", str(target), "--force"])
            self.assertEqual(set(load_skillset_config(target)["buckets"]),
                             {"php", "quality"})

    def test_cmd_init_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_init(env, ["--target", str(target), "--dry-run"])
            self.assertFalse(skillset_config_path(target).is_file())

    def test_cmd_init_refuses_registry_root(self):
        # guard resolve_target: init внутри самого реестра отвергается (как sync)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env0 = make_registry(tmp)
            _materialize_registry(env0)
            env = Env(root, "init", home=env0.home)  # cmd=init для guard'а
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stdout(io.StringIO()):
                    cmd_init(env, ["--target", str(root)])
            self.assertFalse(skillset_config_path(root).is_file())  # реестр чист


class TestContentDrift(unittest.TestCase):
    """content_sha256: sync ловит дрейф в snippets/references при неизменном SKILL.md."""

    def test_snippet_only_change_triggers_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            cfg = {"mode": "vendor", "include": ["code-style"]}
            sync_skillset(env, target, cfg)
            self.assertTrue(
                load_lock(target)["skills"]["code-style"]["content_sha256"])
            # правим ТОЛЬКО сниппет в источнике (SKILL.md не трогаем) + реестр
            snip = root / "skills" / "php" / "code-style" / "snippets"
            snip.mkdir(parents=True, exist_ok=True)
            (snip / "ex.md").write_text("v1", encoding="utf-8")
            _materialize_registry(env)
            plan = plan_sync(env, target, cfg)
            self.assertIn("code-style", plan["update"])  # content drift пойман

    def test_legacy_lock_without_content_hash_no_false_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            cfg = {"mode": "vendor", "include": ["code-style"]}
            sync_skillset(env, target, cfg)
            # эмулируем СТАРЫЙ lock (без content_sha256)
            lock = load_lock(target)
            lock["skills"]["code-style"].pop("content_sha256", None)
            write_lock(target, lock)
            plan = plan_sync(env, target, cfg)
            self.assertEqual(plan["update"], [])        # SKILL.md тот же → не update
            self.assertIn("code-style", plan["keep"])
            # очередной sync до-populates content_sha256 БЕЗ перекопирования
            sync_skillset(env, target, cfg)
            self.assertTrue(
                load_lock(target)["skills"]["code-style"]["content_sha256"])


if __name__ == "__main__":
    unittest.main()
