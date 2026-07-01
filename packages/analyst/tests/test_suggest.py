"""Тесты suggest (P4): чистые генераторы, slug-правила, edit-safety re-suggest, dry-run,
--min-weight, сироты-WARN, mutual-exclusion. Изоляция в tmpdir; без сети/демонов."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from analyst import suggest
from analyst.common import Env


class TestSuggest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = Env(self.base, "suggest", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_index(self, pid, namespace, projects, *, trigger="положить сервис в domain-слой",
                    action="классы сервисов под Domain", kind="gotcha", members=None):
        """Засеять полный index/by_pattern/<pid>.json (как пишет scan.write_artifacts)."""
        data = {
            "pattern_id": pid, "namespace": namespace, "projects": list(projects),
            "weight": len(projects), "lessons": len(projects),
            "representative": {"trigger": trigger, "action": action, "kind": kind},
            "members": members or [{"project": p, "id": f"{p}-1", "trigger": trigger} for p in projects],
            "generated_at": "2026-01-01T00:00:00Z",
        }
        idx = self.env.state_dir / "index" / "by_pattern" / f"{pid}.json"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def _run_json(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            suggest.cmd_suggest(self.env, argv + ["--json"])
        return json.loads(out.getvalue())

    def _draft_paths(self, pid):
        d = self.env.state_dir / "drafts" / pid
        return d / "SKILL.ru.md", d / "draft.meta.json"

    # ── чистые генераторы ─────────────────────────────────────────────────────
    def test_slug_name_rules(self):
        self.assertEqual(suggest._slug_name({"trigger": "Put Service In Domain"}),
                         "put-service-in-domain")
        # reserved слова вырезаются, ведущие/хвостовые дефисы сняты
        self.assertEqual(suggest._slug_name({"trigger": "  Claude helper for Anthropic  "}),
                         "helper-for")
        # Кириллица не образует валидное name скилла (офиц. ограничение — только [a-z0-9-]) →
        # выживает лишь латинский токен; сплошная кириллица → fallback. Человек финализирует name.
        self.assertEqual(suggest._slug_name({"trigger": "положить сервис в Domain"}), "domain")
        self.assertEqual(suggest._slug_name({"trigger": "только кириллица"}), "skill")
        # пусто → fallback
        self.assertEqual(suggest._slug_name({}), "skill")
        # ≤64 и без хвостового дефиса после обрезки
        long = suggest._slug_name({"trigger": "x" * 200})
        self.assertLessEqual(len(long), 64)
        self.assertFalse(long.startswith("-") or long.endswith("-"))

    def test_build_skill_ru_deterministic_and_abstracted(self):
        data = self._seed_index("p-1", "axioma", ["a", "b", "c"],
                                trigger="put service in domain layer")
        t1 = suggest.build_skill_ru(data, "TODO")
        t2 = suggest.build_skill_ru(data, "TODO")
        self.assertEqual(t1, t2)                       # детерминизм (нет timestamp в теле)
        self.assertIn("name: put-service-in-domain-layer", t1)
        self.assertIn("bucket: TODO", t1)
        self.assertIn("повторился в **3 проектах**", t1)
        self.assertIn("`a` —", t1)                     # members-экземпляры
        self.assertNotIn("2026-01-01", t1)             # generated_at НЕ в теле

    def test_description_escapes_yaml_breakers(self):
        # action с backslash (PHP namespace) в double-quoted YAML description → должен быть экранирован
        data = self._seed_index("p-1", "axioma", ["a", "b", "c"],
                                action='put under App\\Domain', trigger='say "hi"')
        ru = suggest.build_skill_ru(data, "TODO")
        desc_line = next(l for l in ru.splitlines() if l.startswith("description:"))
        self.assertIn("App\\\\Domain", desc_line)     # backslash удвоен
        self.assertNotIn('say "hi"', desc_line)        # голая кавычка не просочилась
        self.assertIn('say \\"hi\\"', desc_line)       # кавычки экранированы

    # ── запись / meta ─────────────────────────────────────────────────────────
    def test_create_draft_writes_ru_and_meta(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        payload = self._run_json(["p-1"])
        self.assertEqual(payload["results"][0]["status"], "created")
        ru, meta_p = self._draft_paths("p-1")
        self.assertTrue(ru.is_file() and meta_p.is_file())
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        self.assertEqual(meta["namespace"], "axioma")
        self.assertEqual(meta["projects"], ["a", "b", "c"])
        self.assertEqual(meta["weight"], 3)
        self.assertEqual(meta["source_index"], "index/by_pattern/p-1.json")
        self.assertEqual(meta["seed_sha256"], suggest._seed_hash(ru.read_text(encoding="utf-8")))

    def test_pattern_not_found_dies(self):
        with self.assertRaises(SystemExit):
            suggest.cmd_suggest(self.env, ["missing"])

    def test_pos_and_all_mutually_exclusive(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        with self.assertRaises(SystemExit):
            suggest.cmd_suggest(self.env, ["p-1", "--all"])

    # ── edit-safety (D6) ──────────────────────────────────────────────────────
    def test_resuggest_unedited_updates_not_skips(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        self._run_json(["p-1"])                         # created
        # тот же паттерн → тело идентично → unchanged
        p2 = self._run_json(["p-1"])
        self.assertEqual(p2["results"][0]["status"], "unchanged")
        # паттерн изменился, тело НЕ правили руками → updated
        self._seed_index("p-1", "axioma", ["a", "b", "c", "d"])
        p3 = self._run_json(["p-1"])
        self.assertEqual(p3["results"][0]["status"], "updated")
        ru, _ = self._draft_paths("p-1")
        self.assertIn("4 проектах", ru.read_text(encoding="utf-8"))

    def test_resuggest_preserves_human_edits(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        self._run_json(["p-1"])
        ru, _ = self._draft_paths("p-1")
        ru.write_text(ru.read_text(encoding="utf-8") + "\nРУЧНАЯ ПРАВКА ЧЕЛОВЕКА\n", encoding="utf-8")
        p2 = self._run_json(["p-1"])
        self.assertEqual(p2["results"][0]["status"], "skipped-edited")
        self.assertIn("РУЧНАЯ ПРАВКА ЧЕЛОВЕКА", ru.read_text(encoding="utf-8"))   # тело не тронуто
        # --force перезаписывает правку
        p3 = self._run_json(["p-1", "--force"])
        self.assertEqual(p3["results"][0]["status"], "forced")
        self.assertNotIn("РУЧНАЯ ПРАВКА ЧЕЛОВЕКА", ru.read_text(encoding="utf-8"))

    # ── флаги ─────────────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        payload = self._run_json(["p-1", "--dry-run"])
        self.assertEqual(payload["results"][0]["status"], "dry-run")
        ru, _ = self._draft_paths("p-1")
        self.assertFalse(ru.exists())

    def test_min_weight_filters(self):
        self._seed_index("small", "axioma", ["a", "b", "c"])       # weight 3
        self._seed_index("big", "axioma", ["a", "b", "c", "d", "e"])  # weight 5
        payload = self._run_json(["--all", "--min-weight", "4"])
        ids = sorted(r["pattern_id"] for r in payload["results"])
        self.assertEqual(ids, ["big"])

    def test_min_weight_non_numeric_dies(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        with self.assertRaises(SystemExit):
            suggest.cmd_suggest(self.env, ["--all", "--min-weight", "abc"])

    def test_all_generates_each_pattern(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"], trigger="первый паттерн триггер")
        self._seed_index("p-2", "other", ["x", "y", "z"], trigger="второй паттерн триггер")
        payload = self._run_json(["--all"])
        self.assertEqual(len(payload["results"]), 2)
        for pid in ("p-1", "p-2"):
            self.assertTrue((self.env.state_dir / "drafts" / pid / "SKILL.ru.md").is_file())

    # ── сироты (D6): WARN, не delete ──────────────────────────────────────────
    def test_orphan_draft_reported_not_deleted(self):
        # черновик есть, паттерна в индексе нет → сирота
        self._seed_index("live", "axioma", ["a", "b", "c"])
        self._run_json(["live"])
        # засеять черновик без индекса
        orphan_dir = self.env.state_dir / "drafts" / "gone"
        orphan_dir.mkdir(parents=True)
        (orphan_dir / "SKILL.ru.md").write_text("draft", encoding="utf-8")
        (orphan_dir / "draft.meta.json").write_text(json.dumps({"pattern_id": "gone"}), encoding="utf-8")
        payload = self._run_json(["--all"])
        self.assertIn("gone", payload["orphans"])
        self.assertTrue((orphan_dir / "SKILL.ru.md").exists())   # НЕ удалён

    def test_bucket_override_in_frontmatter(self):
        self._seed_index("p-1", "axioma", ["a", "b", "c"])
        self._run_json(["p-1", "--bucket", "architect"])
        ru, meta_p = self._draft_paths("p-1")
        self.assertIn("bucket: architect", ru.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(meta_p.read_text(encoding="utf-8"))["bucket"], "architect")


if __name__ == "__main__":
    unittest.main()
