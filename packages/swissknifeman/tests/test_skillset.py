"""Тесты skillset — vendor-режим на .swissknifeman/config.json.

Покрывают: резолв правил (include/buckets/exclude), sync (install/update/prune),
безопасное удаление по managed (чужие скиллы не трогаются), обновление по sha256,
dry-run без записи."""
import json
import tempfile
import unittest
from pathlib import Path

from swissknifeman.registry import build_registry
from swissknifeman.skillset import (load_lock, load_skillset_config, plan_sync,
                                    resolve_skillset, skillset_config_path,
                                    sync_skillset)

from swissknifeman.common import MANIFEST

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

    def test_prune_removes_managed_dropped_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            target = make_laravel_project(tmp)
            sync_skillset(env, target, {"mode": "vendor", "buckets": ["php"]})
            self.assertTrue((target / ".claude/skills/code-style").is_dir())

            # сузили конфиг: только одна позиция
            sync_skillset(env, target,
                          {"mode": "vendor", "include": ["laravel-conventions"]})
            self.assertTrue((target / ".claude/skills/laravel-conventions").is_dir())
            self.assertFalse((target / ".claude/skills/code-style").is_dir())
            self.assertNotIn("code-style", load_lock(target)["skills"])

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


if __name__ == "__main__":
    unittest.main()
