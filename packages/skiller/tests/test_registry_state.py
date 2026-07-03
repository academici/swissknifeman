"""Тесты ядра CLI: registry-генерация, state (projects.json), doctor, status.

Гоняются против синтетического реестра (tests/fixtures) во временных каталогах,
без сети и subprocess. registry тестируется через build_registry/
write_plugin_manifests/render_graph напрямую (cmd_registry вызывает write_graph
in-process, без subprocess — раньше это был отдельный shell-скрипт)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import MARKETPLACE
from skiller.registry import build_registry, write_plugin_manifests
from skiller.state import (db_records, load_db, save_db, upsert_project)
from skiller.doctor import cmd_doctor
from skiller.status import cmd_status
from skiller.connect import do_connect
import tests.fixtures as fx


def _schema_prop(pytype, json_type):
    """Собрать schema-свойство под Python-тип из CONFIG_KEYS. Кортеж типов
    (memory_brain = (str, dict)) → oneOf-члены; одиночный тип → {"type": ...}."""
    if isinstance(pytype, tuple):
        return {"oneOf": [{"type": json_type[t]} for t in pytype]}
    return {"type": json_type[pytype]}


def capture(fn, *a, **kw):
    """Выполнить fn, вернуть (result, stdout-текст)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


class RegistryBuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_build_registry_shape(self):
        reg, bucket_meta, bucket_dirs = build_registry(self.env)
        self.assertEqual(reg["version"], 5)
        self.assertEqual(reg["name"], "swissknifeman")
        names = {s["name"] for s in reg["skills"]}
        # 4 скилла из фикстуры (generate-skill живёт вне skills/, в реестр не идёт)
        self.assertEqual(
            names, {"laravel-conventions", "code-style", "test-writer", "docker"})
        # счётчики бакетов
        self.assertEqual(reg["buckets"]["php"]["count"], 2)
        self.assertEqual(reg["buckets"]["devops"]["count"], 1)
        self.assertEqual(sorted(bucket_dirs), ["devops", "php", "quality"])

    def test_local_skill_has_source_local(self):
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "local")
        self.assertNotIn("upstream", docker)

    def test_marketplace_emits_curated_core_plugin(self):
        # Умное подключение: registry эмитит курируемый плагин `core` (source:"./" + skills[]
        # из существующих CORE_SKILLS), грузящий РОВНО эти скиллы вместо целых бакетов.
        from skiller.config import CORE_PLUGIN
        skills = self.root / "skills"
        fx.write_skill(skills / "general" / "context-economy", "context-economy")
        fx.write_skill(skills / "oss-dev" / "gh-review", "gh-review")
        bj = json.loads((self.root / "buckets.json").read_text())
        bj["general"] = {"description": "General", "category": "eng", "tags": []}
        bj["oss-dev"] = {"description": "OSS", "category": "eng", "tags": []}
        (self.root / "buckets.json").write_text(json.dumps(bj))
        _reg, meta, dirs = build_registry(self.env)
        write_plugin_manifests(self.env, meta, dirs)
        mp = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        core = next((p for p in mp["plugins"] if p["name"] == CORE_PLUGIN), None)
        self.assertIsNotNone(core, "marketplace должен содержать курируемый core-плагин")
        self.assertEqual(core["source"], "./")
        self.assertIn("./skills/general/context-economy", core["skills"])
        self.assertIn("./skills/oss-dev/gh-review", core["skills"])
        # курируемый core не имеет каталога-плагина на диске (ссылки, не копии)
        self.assertFalse((skills / CORE_PLUGIN).exists())

    def test_upstream_skill_carries_provenance(self):
        fx.write_upstream(self.root / "skills" / "devops" / "docker",
                          source="github",
                          url="https://raw.example/SKILL.md",
                          fetched_at="2026-02-02")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/SKILL.md")
        self.assertEqual(docker["fetched_at"], "2026-02-02")

    def test_fork_skill_provenance_via_non_skill_path(self):
        # fork: files[].path указывает на зеркало (references/source.md), а не на
        # SKILL.md → registry должен взять provenance из files[0] (fallback).
        fx.write_upstream(self.root / "skills" / "devops" / "docker",
                          source="github", strategy="fork",
                          path="references/source.md",
                          url="https://raw.example/SKILL.md",
                          fetched_at="2026-03-03")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/SKILL.md")
        self.assertEqual(docker["fetched_at"], "2026-03-03")

    def test_body_path_provenance_preferred_over_skill_md_entry(self):
        # P7.3 thin-navigator: body_path явно называет files[]-запись с реальным
        # телом апстрима — registry должен брать provenance из НЕЁ, а не из первой
        # найденной записи с path=="SKILL.md" (даже если такая по какой-то причине
        # тоже трекается) и не из files[0] (порядок в files[] не должен решать).
        fx.write_upstream(
            self.root / "skills" / "devops" / "docker",
            source="github", strategy="notify",
            path="SKILL.md", url="https://raw.example/SKILL.md", sha256="stale",
            fetched_at="2026-01-01",
            body_path="references/full.md",
            extra_files=[{"path": "references/full.md",
                         "url": "https://raw.example/references/full.md",
                         "sha256": "fresh", "fetched_at": "2026-07-01"}])
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/references/full.md")
        self.assertEqual(docker["fetched_at"], "2026-07-01")

    def test_broken_upstream_json_dies_with_path(self):
        # Битый upstream.json → внятная ошибка с путём, не голый traceback
        # на полпути генерации и не тихий провал в source="local".
        skill_dir = self.root / "skills" / "devops" / "docker"
        (skill_dir / "upstream.json").write_text("{ this is not json",
                                                 encoding="utf-8")
        with self.assertRaises(SystemExit):
            build_registry(self.env)

    def test_requires_only_when_present(self):
        reg, *_ = build_registry(self.env)
        conv = next(s for s in reg["skills"] if s["name"] == "laravel-conventions")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(conv["requires"], ["code-style"])
        # у скилла без requires поле отсутствует, а не пустой список
        self.assertNotIn("requires", style)

    def test_level_only_when_present(self):
        # опц. поле level: пишется в skills.json при наличии, иначе ключа нет
        (self.root / "skills" / "devops" / "docker" / "SKILL.md").write_text(
            "---\nname: docker\nversion: 0.1.0\ndescription: Docker\n"
            "level: foundation\n---\n\nBody.\n", encoding="utf-8")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(docker["level"], "foundation")
        self.assertNotIn("level", style)  # omit-when-empty

    def test_content_sha256_covers_whole_dir(self):
        # content_sha256 шире sha256 (по SKILL.md): ловит правки snippets/references
        docker = self.root / "skills" / "devops" / "docker"
        reg1, *_ = build_registry(self.env)
        e1 = next(s for s in reg1["skills"] if s["name"] == "docker")
        self.assertTrue(e1["content_sha256"])
        self.assertNotEqual(e1["content_sha256"], e1["sha256"])  # разный охват
        # правим ТОЛЬКО сниппет (SKILL.md не трогаем)
        (docker / "snippets").mkdir(exist_ok=True)
        (docker / "snippets" / "ex.md").write_text("v1", encoding="utf-8")
        reg2, *_ = build_registry(self.env)
        e2 = next(s for s in reg2["skills"] if s["name"] == "docker")
        self.assertEqual(e2["sha256"], e1["sha256"])  # SKILL.md не менялся
        self.assertNotEqual(e2["content_sha256"], e1["content_sha256"])  # дир иная

    def test_content_sha256_ignores_ru_alternate(self):
        # SKILL.ru.md (языковой альтернат) не входит в content_sha256
        docker = self.root / "skills" / "devops" / "docker"
        e1 = next(s for s in build_registry(self.env)[0]["skills"]
                  if s["name"] == "docker")
        (docker / "SKILL.ru.md").write_text("полный русский источник\n",
                                            encoding="utf-8")
        e2 = next(s for s in build_registry(self.env)[0]["skills"]
                  if s["name"] == "docker")
        self.assertEqual(e2["content_sha256"], e1["content_sha256"])

    def test_missing_buckets_json_dies(self):
        (self.root / "buckets.json").unlink()
        with self.assertRaises(SystemExit):
            build_registry(self.env)

    def test_write_plugin_manifests(self):
        _, bucket_meta, bucket_dirs = build_registry(self.env)
        n = write_plugin_manifests(self.env, bucket_meta, bucket_dirs)
        # 3 бакета + generate-skill
        self.assertEqual(n, 4)
        # per-bucket манифест
        php_plugin = json.loads(
            (self.root / "skills" / "php" / ".claude-plugin" / "plugin.json")
            .read_text())
        self.assertEqual(php_plugin["name"], "php")
        # корневой marketplace
        mk = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(mk["name"], MARKETPLACE)
        plugin_names = {p["name"] for p in mk["plugins"]}
        self.assertIn("generate-skill", plugin_names)
        self.assertIn("php", plugin_names)


class StateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_db_default_when_absent(self):
        self.assertFalse(self.env.db_file.exists())
        db = load_db(self.env)
        self.assertEqual(db["projects"], [])
        self.assertIn("version", db)

    def test_upsert_insert_then_update_preserves_first_connected(self):
        upsert_project(self.env, {"path": "/p", "channel": "vendor",
                                  "buckets": ["php"]})
        rec1 = load_db(self.env)["projects"][0]
        first = rec1["first_connected_at"]
        self.assertEqual(rec1["buckets"], ["php"])
        # обновляем тот же (path, channel) — first_connected_at сохраняется
        upsert_project(self.env, {"path": "/p", "channel": "vendor",
                                  "buckets": ["php", "devops"]})
        db = load_db(self.env)
        self.assertEqual(len(db["projects"]), 1)
        rec2 = db["projects"][0]
        self.assertEqual(rec2["buckets"], ["php", "devops"])
        self.assertEqual(rec2["first_connected_at"], first)

    def test_upsert_distinct_channels_coexist(self):
        upsert_project(self.env, {"path": "/p", "channel": "vendor"})
        upsert_project(self.env, {"path": "/p", "channel": "marketplace"})
        recs = db_records(self.env, "/p")
        self.assertEqual({r["channel"] for r in recs}, {"vendor", "marketplace"})

    def test_upsert_normalizes_path_dedupes(self):
        # разные repr одного пути (./, ..) → одна запись (нормализация resolve())
        upsert_project(self.env, {"path": "/p", "channel": "vendor"})
        upsert_project(self.env, {"path": "/p/.", "channel": "vendor"})
        db = load_db(self.env)
        self.assertEqual(len(db["projects"]), 1)
        self.assertEqual(db["projects"][0]["path"], "/p")
        # lookup тоже нормализует — находит запись по «грязному» repr
        self.assertEqual(len(db_records(self.env, "/p/.")), 1)

    def test_save_load_round_trip_no_tmp_left(self):
        save_db(self.env, {"version": 1, "projects": [{"path": "/x",
                                                       "channel": "vendor"}]})
        self.assertEqual(load_db(self.env)["projects"][0]["path"], "/x")
        # атомарная запись не оставляет временного файла
        leftovers = list(self.env.state_dir.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_doctor_runs_and_reports(self):
        # doctor может вернуть код 1 (нет симлинка/не git-репо в tmp) — это норма;
        # важно, что он не падает с исключением и печатает диагностику.
        try:
            _, out = capture(cmd_doctor, self.env, [])
        except SystemExit:
            # issues>0 -> sys.exit(1); перехватываем вывод повторно без exit-чувствительности
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with contextlib.suppress(SystemExit):
                    cmd_doctor(self.env, [])
            out = buf.getvalue()
        self.assertIn("skiller doctor", out)
        self.assertIn("python3", out)
        self.assertIn("профили загружаются", out)
        # Doc-1: harness не найден в синтетическом tmp-реестре (нет monorepo вокруг)
        # — это опциональная зависимость, НЕ должна считаться FAIL.
        self.assertIn("harness не установлен", out)
        self.assertNotIn("FAIL] harness", out)

    def test_doctor_help(self):
        _, out = capture(cmd_doctor, self.env, ["--help"])
        self.assertIn("skiller doctor", out)

    def test_doctor_flags_broken_harness_not_missing(self):
        """Doc-1: harness УСТАНОВЛЕН (SKM_HARNESS_BIN указывает на исполняемый файл),
        но СЛОМАН (ненулевой exit) — doctor должен различать это от «не установлен»
        и репортить FAIL, а не молчаливое 'ok'. Единственный тест файла, реально
        зовущий subprocess (сути проверки не проверить иначе)."""
        broken = self.tmp / "broken-harness.sh"
        broken.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        broken.chmod(0o755)
        old = os.environ.get("SKM_HARNESS_BIN")
        os.environ["SKM_HARNESS_BIN"] = str(broken)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with contextlib.suppress(SystemExit):
                    cmd_doctor(self.env, [])
            out = buf.getvalue()
        finally:
            if old is None:
                os.environ.pop("SKM_HARNESS_BIN", None)
            else:
                os.environ["SKM_HARNESS_BIN"] = old
        self.assertIn("FAIL] harness исполняется", out)
        self.assertNotIn("не установлен", out)

    def test_doctor_flags_schema_type_mismatch_not_just_key_names(self):
        """Doc-2: раньше doctor сверял ТОЛЬКО имена ключей схемы (⇄ ключи) — при
        расхождении ТИПА свойства (напр. schema говорит array, CONFIG_KEYS — str)
        печатал ложное "OK". Схема ниже: имена 1:1 с CONFIG_KEYS, но у
        'project_type' тип 'array' вместо ожидаемого 'string'."""
        from skiller.common import CONFIG_KEYS
        json_type = {str: "string", list: "array", int: "integer",
                    dict: "object", bool: "boolean"}
        props = {k: _schema_prop(t, json_type) for k, t in CONFIG_KEYS.items()}
        props["project_type"]["type"] = "array"  # намеренное расхождение
        schema_dir = self.root / "schema"
        schema_dir.mkdir(parents=True, exist_ok=True)
        (schema_dir / "swissknife.schema.json").write_text(
            json.dumps({"properties": props}), encoding="utf-8")
        # вторая схема (SKILLSET_KEYS) — доктор её тоже читает, кладём валидной
        from skiller.skillset import SKILLSET_KEYS
        props2 = {k: _schema_prop(t, json_type) for k, t in SKILLSET_KEYS.items()}
        (schema_dir / "swissknifeman-config.schema.json").write_text(
            json.dumps({"properties": props2}), encoding="utf-8")

        buf = io.StringIO()
        with contextlib.suppress(SystemExit):
            with contextlib.redirect_stdout(buf):
                cmd_doctor(self.env, [])
        out = buf.getvalue()
        self.assertIn("⇄ ключи .swissknife.json", out)   # имена совпали — OK
        self.assertIn("FAIL] схема swissknife.schema.json ⇄ типы", out)
        self.assertIn("project_type", out)


class StatusCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_status_on_connected_project(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        _, out = capture(cmd_status, self.env, ["--target", str(proj)])
        self.assertIn(str(proj), out)
        self.assertIn("marketplace", out)
        self.assertIn("Профиль", out)

    def test_status_on_unconnected_project(self):
        proj = fx.make_laravel_project(self.tmp)
        _, out = capture(cmd_status, self.env, ["--target", str(proj)])
        self.assertIn("не подключён", out)


class DownstreamAuditCase(unittest.TestCase):
    """skiller doctor --downstream: гигиена publish-surface онбордженных проектов."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_project(self, name, *, claude_lines, scoped, unscoped, deny):
        pdir = self.tmp / name
        (pdir / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
        (pdir / "CLAUDE.md").write_text(
            "\n".join(f"line {i}" for i in range(claude_lines)), encoding="utf-8")
        for i in range(scoped):
            (pdir / ".claude" / "rules" / f"s{i}.md").write_text(
                '---\npaths:\n  - "app/**"\n---\nscoped rule\n', encoding="utf-8")
        for i in range(unscoped):
            (pdir / ".claude" / "rules" / f"u{i}.md").write_text(
                "unscoped rule, no frontmatter\n", encoding="utf-8")
        perms = {"deny": ["Read(storage/logs/**)"]} if deny else {}
        (pdir / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": perms}), encoding="utf-8")
        return pdir

    def test_audit_flags_oversize_unscoped_and_missing_deny(self):
        big = self._make_project("bigproj", claude_lines=300, scoped=1,
                                  unscoped=2, deny=False)
        lean = self._make_project("leanproj", claude_lines=50, scoped=2,
                                   unscoped=0, deny=True)
        save_db(self.env, {"projects": [
            {"id": "bigproj", "path": str(big)},
            {"id": "leanproj", "path": str(lean)},
        ]})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with contextlib.suppress(SystemExit):
                cmd_doctor(self.env, ["--downstream"])
        out = buf.getvalue()
        self.assertIn("Downstream publish-surface", out)
        # over-budget project flagged on all three axes
        self.assertIn("CLAUDE.md 300>200", out)
        self.assertIn("2 unscoped-rules", out)
        self.assertIn("нет deny", out)
        # lean project is clean
        self.assertRegex(out, r"\[ok \] leanproj:")


if __name__ == "__main__":
    unittest.main()
