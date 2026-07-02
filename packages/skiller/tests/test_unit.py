"""Юнит-тесты чистых функций: frontmatter, flag-parsing, selection, flat-names."""
import unittest
from pathlib import Path
import sys
import tempfile

# tests/ запускаются с lib/ на sys.path (см. scripts/test.sh); подстрахуемся.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import (parse_flags, parse_frontmatter,
                                  parse_frontmatter_fields, parse_inline_list,
                                  sanitize, skill_content_hash)
import skiller.config as config_mod
from skiller.config import autodetect, resolve_selection
from skiller.vendor import flat_names, resolve_requires, build_requires_index
import tests.fixtures as fx


class TestFrontmatter(unittest.TestCase):
    def _write(self, text):
        f = Path(tempfile.mkdtemp()) / "SKILL.md"
        f.write_text(text, encoding="utf-8")
        return f

    def test_basic_keys(self):
        f = self._write("---\nname: foo\nversion: 1.2.3\n---\nbody\n")
        fm = parse_frontmatter(f)
        self.assertEqual(fm["name"], "foo")
        self.assertEqual(fm["version"], "1.2.3")

    def test_no_frontmatter(self):
        f = self._write("just body\nname: not-fm\n")
        self.assertEqual(parse_frontmatter(f), {})

    def test_quotes_stripped(self):
        f = self._write('---\nname: "quoted"\ndescription: \'single\'\n---\n')
        fm = parse_frontmatter(f)
        self.assertEqual(fm["name"], "quoted")
        self.assertEqual(fm["description"], "single")

    def test_block_scalar_literal(self):
        # `description: |` — многострочный литерал собирается с переносами
        f = self._write(
            "---\nname: foo\ndescription: |\n  line one\n  line two\n---\nbody\n")
        fm = parse_frontmatter(f)
        self.assertEqual(fm["name"], "foo")
        self.assertEqual(fm["description"], "line one\nline two")

    def test_block_scalar_folded_then_next_key(self):
        # `description: >` — фолдинг через пробел; ключ после блока не потерян
        f = self._write("---\ndescription: >\n  a\n  b\nrisk: low\n---\n")
        fm = parse_frontmatter(f)
        self.assertEqual(fm["description"], "a b")
        self.assertEqual(fm["risk"], "low")

    def test_value_starting_with_gt_is_not_block_scalar(self):
        # описание, начинающееся с '>', НЕ должно съедаться как блок-скаляр
        f = self._write("---\ndescription: > see the docs\nname: foo\n---\n")
        fm = parse_frontmatter(f)
        self.assertEqual(fm["description"], "> see the docs")
        self.assertEqual(fm["name"], "foo")

    def test_body_lines_ignored(self):
        f = self._write("---\nname: foo\n---\nkey: should-not-parse\n")
        self.assertNotIn("key", parse_frontmatter(f))

    def test_bom_prefixed_frontmatter(self):
        # UTF-8 BOM перед `---` не должен ронять парсинг (utf-8-sig срезает BOM)
        f = self._write("﻿---\nname: foo\n---\nbody\n")
        self.assertEqual(parse_frontmatter(f)["name"], "foo")

    def test_requires_inline_list(self):
        f = self._write("---\nname: foo\nrequires: [a, b, c]\n---\n")
        fields = parse_frontmatter_fields(f)
        self.assertEqual(fields["requires"], ["a", "b", "c"])

    def test_inline_list_empty_and_malformed(self):
        self.assertEqual(parse_inline_list(""), [])
        self.assertEqual(parse_inline_list("not-a-list"), [])
        self.assertEqual(parse_inline_list("[]"), [])
        self.assertEqual(parse_inline_list('["x", "y"]'), ["x", "y"])


class TestSanitize(unittest.TestCase):
    def test_lowercases_and_dashes(self):
        self.assertEqual(sanitize("My Skill_Name"), "my-skill-name")

    def test_strips_special(self):
        self.assertEqual(sanitize("a@b#c"), "abc")

    def test_collapses_dashes(self):
        self.assertEqual(sanitize("a -- b"), "a-b")


class TestParseFlags(unittest.TestCase):
    SPEC = {"--target": "str", "--list": "bool", "--profile": "str"}

    def test_bool_and_str(self):
        out = parse_flags(["--list", "--profile", "laravel"], self.SPEC)
        self.assertTrue(out["list"])
        self.assertEqual(out["profile"], "laravel")
        self.assertEqual(out["target"], "")
        self.assertFalse(out["help"])

    def test_help(self):
        self.assertTrue(parse_flags(["--help"], self.SPEC)["help"])
        self.assertTrue(parse_flags(["-h"], self.SPEC)["help"])

    def test_dash_in_flag_becomes_underscore(self):
        out = parse_flags(["--cleanup-vendored"], {"--cleanup-vendored": "bool"})
        self.assertTrue(out["cleanup_vendored"])

    def test_unknown_flag_exits(self):
        with self.assertRaises(SystemExit):
            parse_flags(["--nope"], self.SPEC)

    def test_missing_value_exits(self):
        with self.assertRaises(SystemExit):
            parse_flags(["--profile"], self.SPEC)


class TestAutodetect(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_laravel(self):
        proj = fx.make_laravel_project(self.tmp)
        self.assertEqual(autodetect(proj), "laravel-project")

    def test_php_package(self):
        p = self.tmp / "pkg"
        p.mkdir()
        (p / "composer.json").write_text("{}")
        self.assertEqual(autodetect(p), "php-package")

    def test_obsidian(self):
        p = self.tmp / "vault"
        (p / ".obsidian").mkdir(parents=True)
        self.assertEqual(autodetect(p), "obsidian-vault")

    def test_standalone(self):
        p = self.tmp / "plain"
        p.mkdir()
        self.assertEqual(autodetect(p), "standalone")


class TestResolveSelection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_flags_win(self):
        items, name, src, _, _ = resolve_selection(
            self.env, self.proj, {}, "", ["php"])
        self.assertEqual(items, ["php"])
        self.assertEqual(src, "items")

    def test_profile_flag(self):
        items, name, src, _, _ = resolve_selection(
            self.env, self.proj, {}, "laravel-project", [])
        self.assertEqual(set(items), {"php", "quality"})
        self.assertEqual(name, "laravel-project")

    def test_config_buckets(self):
        items, _, src, _, _ = resolve_selection(
            self.env, self.proj, {"buckets": ["devops"]}, "", [])
        self.assertEqual(items, ["devops"])
        self.assertEqual(src, "config")

    def test_autodetect_laravel(self):
        items, name, src, _, _ = resolve_selection(self.env, self.proj, {}, "", [])
        self.assertEqual(name, "laravel-project")
        self.assertEqual(src, "autodetect")

    def test_star_expands_with_include_meta(self):
        # ЯВНЫЙ project_type=standalone (в .swissknife.json) → legitimate «поставь всё».
        items, name, _, _, include_meta = resolve_selection(
            self.env, self.proj, {"project_type": "standalone"}, "", [])
        self.assertEqual(set(items), {"php", "quality", "devops"})
        self.assertTrue(include_meta)

    def test_autodetect_fallback_not_all_buckets(self):
        # Тип НЕ распознан (autodetect → standalone) → минимальный набор, НЕ «всё подряд»,
        # и маркер источника autodetect-fallback (вызывающий печатает warn).
        blank = fx.make_standalone_project(self.tmp)
        items, name, src, _, include_meta = resolve_selection(
            self.env, blank, {}, "", [])
        self.assertEqual(src, "autodetect-fallback")
        self.assertNotEqual(set(items), {"php", "quality", "devops"})
        self.assertTrue(set(items) <= set(config_mod.MINIMAL_BUCKETS))
        self.assertFalse(include_meta)

    def test_explicit_standalone_profile_still_expands(self):
        # Явный --profile standalone остаётся «поставь всё» (не fallback).
        blank = fx.make_standalone_project(self.tmp)
        items, name, src, label, _ = resolve_selection(
            self.env, blank, {}, "standalone", [])
        self.assertEqual(set(items), {"php", "quality", "devops"})
        self.assertEqual(src, "flag")
        self.assertEqual(label, "--profile")


class TestRequiresResolution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pulls_transitive_requires(self):
        # laravel-conventions requires code-style; select only laravel-conventions
        d = self.root / "skills" / "php" / "laravel-conventions"
        skills = [("php", "laravel-conventions", d, "laravel-conventions")]
        index = build_requires_index(self.env)
        pulled = resolve_requires(skills, index, set())
        names = {fm for _, _, _, fm in skills}
        self.assertIn("code-style", names)
        self.assertEqual(pulled.get("code-style"), "laravel-conventions")

    def test_exclude_beats_requires(self):
        d = self.root / "skills" / "php" / "laravel-conventions"
        skills = [("php", "laravel-conventions", d, "laravel-conventions")]
        index = build_requires_index(self.env)
        resolve_requires(skills, index, {"code-style"})  # мутирует skills на месте
        names = {fm for _, _, _, fm in skills}
        self.assertNotIn("code-style", names)


class TestFlatNames(unittest.TestCase):
    def test_collision_prefixes_bucket(self):
        skills = [
            ("php", "a", Path("/x/php/a"), "deploy"),
            ("devops", "b", Path("/x/devops/b"), "deploy"),
        ]
        names = flat_names(skills)
        self.assertEqual(set(names.values()), {"php-deploy", "devops-deploy"})

    def test_no_collision_keeps_name(self):
        skills = [("php", "a", Path("/x/php/a"), "code-style")]
        self.assertEqual(flat_names(skills)[0], "code-style")


class TestSkillContentHash(unittest.TestCase):
    """__pycache__/*.pyc не должны влиять на content_sha256: найдено при
    расследовании нестабильного skills.json (registry --check зеленел на машине с
    локально запущенным .py-сниппетом, но дрейфовал в чистом чекауте/CI — байткод-
    кэш от `python3 snippets/check.py` считался частью содержимого скилла)."""
    def _make_skill(self, tmp):
        d = tmp / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: x\n---\nBody.\n", encoding="utf-8")
        snippets = d / "snippets"
        snippets.mkdir()
        (snippets / "check.py").write_text("print('ok')\n", encoding="utf-8")
        return d

    def test_pycache_does_not_change_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            d = self._make_skill(tmp)
            before = skill_content_hash(d)

            pycache = d / "snippets" / "__pycache__"
            pycache.mkdir()
            (pycache / "check.cpython-312.pyc").write_bytes(b"\x00fake bytecode")
            (d / "snippets" / "stray.pyc").write_bytes(b"\x00another")

            after = skill_content_hash(d)
            self.assertEqual(before, after)

    def test_real_content_change_still_detected(self):
        # Регресс-предохранитель: исключение __pycache__ не должно случайно
        # исключить реальные правки .py-файлов (только их скомпилированный кэш).
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            d = self._make_skill(tmp)
            before = skill_content_hash(d)
            (d / "snippets" / "check.py").write_text("print('changed')\n",
                                                      encoding="utf-8")
            after = skill_content_hash(d)
            self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
