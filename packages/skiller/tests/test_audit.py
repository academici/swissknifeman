"""Тесты bucket-audit (audit.py) против синтетического реестра (P7.1 SKM-MASTER-002).

Проверяем: чистые примитивы (триггеры/шинглы/Jaccard), сборку реестра, детект
overlap-пар, фан-аут usage по projects.json (fail-safe транскрипты), чистую функцию
вердикта (dead/merge/thin/retrieval-only/keep приоритетом сигналов) и CLI-обёртку."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.quality.audit import (DescriptionDebtError, body_shingles, build_audit,
                           build_description_debt, cmd_bucket_audit, collect_usage,
                           desc_triggers, find_overlaps, iter_registry_skills, jaccard,
                           read_description_debt, render_audit, resident_skill_names,
                           usage_note, verdict)
from skiller.state import upsert_project

try:
    import tests.fixtures as fx
except ImportError:
    import fixtures as fx


# --- примитивы -------------------------------------------------------------------
class TriggersShinglesCase(unittest.TestCase):
    def test_desc_triggers_normalizes_words(self):
        self.assertEqual(desc_triggers("Laravel Testing, Conventions!"),
                         {"laravel", "testing", "conventions"})

    def test_desc_triggers_drops_short_words(self):
        self.assertNotIn("a", desc_triggers("a of PHP style"))

    def test_body_shingles_short_body_is_empty(self):
        # < 5 слов -> пусто, НЕ фолбэк-синглтон (иначе все короткие тела с
        # одинаковым числом слов ложно "совпадают" на 100%).
        self.assertEqual(body_shingles("one two three"), set())

    def test_body_shingles_five_gram(self):
        sh = body_shingles("a b c d e f")
        self.assertEqual(sh, {("a", "b", "c", "d", "e"), ("b", "c", "d", "e", "f")})

    def test_jaccard_basic(self):
        self.assertEqual(jaccard({"a", "b"}, {"a", "b"}), 1.0)
        self.assertEqual(jaccard({"a"}, {"b"}), 0.0)
        self.assertEqual(jaccard(set(), set()), 0.0)
        self.assertAlmostEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)


# --- вердикт: чистая функция -----------------------------------------------------
class VerdictCase(unittest.TestCase):
    def _item(self, tier1=100):
        return {"tier1": tier1}

    def test_merge_wins_over_dead(self):
        # overlap — структурный сигнал (полная уверенность из контента), usage-based
        # dead — неполный (частичный детект, одна машина/окно) -> merge приоритетнее.
        v = verdict(self._item(), overlap_partners=["x/y"], loaded_count=0,
                    scanned_projects=3)
        self.assertEqual(v, "merge")

    def test_dead_when_no_overlap_and_unused(self):
        v = verdict(self._item(), overlap_partners=[], loaded_count=0,
                    scanned_projects=3)
        self.assertEqual(v, "dead")

    def test_no_usage_data_does_not_claim_dead(self):
        v = verdict(self._item(), overlap_partners=[], loaded_count=0,
                    scanned_projects=0)
        self.assertNotEqual(v, "dead")

    def test_merge_when_overlap(self):
        v = verdict(self._item(), overlap_partners=["a/b"], loaded_count=5,
                    scanned_projects=2)
        self.assertEqual(v, "merge")

    def test_thin_for_monolith_body(self):
        from skiller.quality.audit import TIER1_MONOLITH_TOKENS
        v = verdict(self._item(tier1=TIER1_MONOLITH_TOKENS), overlap_partners=[],
                    loaded_count=10, scanned_projects=1)
        self.assertEqual(v, "thin")

    def test_thin_wins_over_dead_for_monolith(self):
        # Известный монолит, просто не пойманный usage-детектом в окне (единичное
        # окно/машина, см. analyze.py про частичный Skill-tool детект) — не должен
        # тонуть под "dead": размер тела виден из контента с полной уверенностью.
        from skiller.quality.audit import TIER1_MONOLITH_TOKENS
        v = verdict(self._item(tier1=TIER1_MONOLITH_TOKENS), overlap_partners=[],
                    loaded_count=0, scanned_projects=5)
        self.assertEqual(v, "thin")

    def test_retrieval_only_for_large_rare(self):
        from skiller.quality.audit import TIER1_LARGE_TOKENS
        v = verdict(self._item(tier1=TIER1_LARGE_TOKENS), overlap_partners=[],
                    loaded_count=1, scanned_projects=4)
        self.assertEqual(v, "retrieval-only")

    def test_keep_default(self):
        v = verdict(self._item(tier1=50), overlap_partners=[], loaded_count=0,
                    scanned_projects=0)
        self.assertEqual(v, "keep")

    def test_usage_note_exact_wording_when_unused(self):
        self.assertEqual(usage_note(0, 3, 30), "не использовался в окне 30 дней")

    def test_usage_note_no_data(self):
        note = usage_note(0, 0, 14)
        self.assertIn("нет данных", note)
        self.assertIn("14", note)

    # --- P2.2 SKM-MASTER-003: резидентный скилл без skill-call ≠ dead -----------
    def test_resident_without_calls_is_keep_not_dead(self):
        v = verdict(self._item(), overlap_partners=[], loaded_count=0,
                    scanned_projects=3, resident=True)
        self.assertEqual(v, "keep")

    def test_non_resident_without_calls_still_dead(self):
        # resident явно False (дефолт) -> старое поведение не тронуто.
        v = verdict(self._item(), overlap_partners=[], loaded_count=0,
                    scanned_projects=3, resident=False)
        self.assertEqual(v, "dead")

    def test_resident_with_calls_is_keep(self):
        v = verdict(self._item(), overlap_partners=[], loaded_count=2,
                    scanned_projects=3, resident=True)
        self.assertEqual(v, "keep")

    def test_usage_note_resident_without_calls_exact_wording(self):
        self.assertEqual(
            usage_note(0, 3, 30, resident=True),
            "резидентный, прямых вызовов не видно (авто-триггер вне детекции)")

    def test_usage_note_resident_with_calls_unaffected(self):
        self.assertEqual(usage_note(5, 3, 30, resident=True), "5× за 30 дней")

    def test_usage_note_resident_no_scan_data_unaffected(self):
        # scanned_projects=0 -> "нет данных", резидентность здесь ни при чём.
        note = usage_note(0, 0, 14, resident=True)
        self.assertIn("нет данных", note)


# --- сборка реестра + overlap на фикстуре -----------------------------------------
class RegistryAndOverlapCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_fixture_has_no_false_overlap(self):
        # Дефолтные скиллы фикстуры делят один и тот же короткий body="Body.\n" —
        # регрессия на пустой body_shingles для коротких тел (см. TriggersShinglesCase):
        # без неё все они ложно "перекрывались" бы shingle=1.0.
        items = iter_registry_skills(self.env)
        pairs = find_overlaps(items)
        self.assertEqual(pairs, [])

    def test_overlap_pair_detected(self):
        long_body = ("Testing patterns for Laravel feature tests with database "
                     "factories and assertions repeated consistently across suite.\n")
        fx.write_skill(self.root / "skills" / "quality" / "test-a", "test-a",
                       description="Laravel feature testing conventions",
                       body=long_body)
        fx.write_skill(self.root / "skills" / "quality" / "test-b", "test-b",
                       description="Laravel feature testing conventions",
                       body=long_body)
        items = iter_registry_skills(self.env)
        pairs = find_overlaps(items)
        keys = {(p["a"], p["b"]) for p in pairs}
        self.assertIn(("quality/test-a", "quality/test-b"), keys)
        pair = next(p for p in pairs if p["a"] == "quality/test-a")
        self.assertGreaterEqual(pair["desc_jaccard"], 0.4)
        self.assertGreaterEqual(pair["body_shingle"], 0.3)

    def test_monolith_verdict_via_build_audit(self):
        fx.write_skill(self.root / "skills" / "quality" / "monolith", "monolith",
                       description="Huge reference monolith",
                       body="word " * 6000)
        report = build_audit(self.env, since_days=30)
        row = next(r for r in report["items"] if r["key"] == "quality/monolith")
        self.assertEqual(row["verdict"], "thin")
        self.assertGreater(row["tier1"], 6000 * 0.9)


class DescriptionDebtCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_ledger(self, *keys):
        path = self.root / "scripts" / "desc-trigger-burndown.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(keys) + ("\n" if keys else ""), encoding="utf-8")

    def test_priority_contract_uses_existing_usage_and_tier0(self):
        self._write_ledger("devops/docker", "php/code-style")
        with mock.patch("skiller.quality.audit.collect_usage", return_value=({"docker": 2}, 3)), \
                mock.patch("skiller.quality.audit.resident_skill_names", return_value=set()):
            report = build_description_debt(self.env)

        self.assertEqual(report["contract_version"], "description-trigger-priority/v1")
        self.assertEqual(report["debt_count"], 2)
        self.assertGreater(report["tier0_denominator"], 0)
        first = report["items"][0]
        self.assertEqual(first["key"], "devops/docker")
        self.assertEqual(first["evidence"], "observed-skill-call")
        self.assertEqual(first["priority_score"]["numerator"], first["tier0"] * 2)
        self.assertEqual(first["priority_score"]["denominator"], report["tier0_denominator"])
        self.assertEqual(report["signal_coverage"]["unobserved"], 1)

    def test_resident_and_unobserved_zero_calls_remain_distinct(self):
        self._write_ledger("devops/docker", "php/code-style")
        with mock.patch("skiller.quality.audit.collect_usage", return_value=({}, 3)), \
                mock.patch("skiller.quality.audit.resident_skill_names", return_value={"docker"}):
            report = build_description_debt(self.env)

        evidence = {row["key"]: row["evidence"] for row in report["items"]}
        self.assertEqual(evidence["devops/docker"], "resident-only")
        self.assertEqual(evidence["php/code-style"], "unobserved")
        self.assertEqual(report["items"][0]["key"], "devops/docker")

    def test_equal_score_ties_are_key_stable(self):
        fx.write_skill(self.root / "skills" / "quality" / "a", "a",
                       description="Use when testing an audit", body="Body.")
        fx.write_skill(self.root / "skills" / "quality" / "b", "b",
                       description="Use when testing an audit", body="Body.")
        self._write_ledger("quality/b", "quality/a")
        with mock.patch("skiller.quality.audit.collect_usage", return_value=({}, 0)), \
                mock.patch("skiller.quality.audit.resident_skill_names", return_value=set()):
            report = build_description_debt(self.env)

        self.assertEqual([row["key"] for row in report["items"]], ["quality/a", "quality/b"])

    def test_invalid_ledger_fails_closed(self):
        registry_keys = {"devops/docker"}
        cases = {
            "missing": None,
            "malformed": "not a key\n",
            "duplicate": "devops/docker\ndevops/docker\n",
            "stale": "quality/missing\n",
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                path = self.root / "scripts" / "desc-trigger-burndown.txt"
                path.unlink(missing_ok=True)
                if content is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                with self.assertRaises(DescriptionDebtError):
                    read_description_debt(self.env, registry_keys)

    def test_empty_ledger_and_json_filter_are_deterministic(self):
        self._write_ledger()
        with mock.patch("skiller.quality.audit.collect_usage", return_value=({}, 0)), \
                mock.patch("skiller.quality.audit.resident_skill_names", return_value=set()):
            report = build_description_debt(self.env)
            first = io.StringIO()
            second = io.StringIO()
            with contextlib.redirect_stdout(first):
                cmd_bucket_audit(self.env, ["--description-debt", "--json"])
            with contextlib.redirect_stdout(second):
                cmd_bucket_audit(self.env, ["--description-debt", "--json"])

        self.assertEqual(report["items"], [])
        self.assertEqual(first.getvalue(), second.getvalue())
        self.assertEqual(json.loads(first.getvalue())["contract_version"], "description-trigger-priority/v1")


# --- usage: фан-аут по projects.json ---------------------------------------------
def _write_session(env, project_path, skill_names):
    """Мини-JSONL сессии с Skill-tool вызовами для skill_names (по одному разу
    каждый) в каталоге логов проекта — как реальный транскрипт Claude Code."""
    from skiller.quality.analyze import logs_root
    root = logs_root(env, project_path)
    root.mkdir(parents=True, exist_ok=True)
    content = [{"type": "tool_use", "name": "Skill", "input": {"skill": n}}
              for n in skill_names]
    event = {"type": "assistant", "message": {
        "model": "claude-sonnet-4-5",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn", "content": content}}
    (root / "session1.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")


class UsageFanOutCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.project = self.tmp / "consumer-project"
        self.project.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_registered_projects_means_no_scan(self):
        loaded, scanned = collect_usage(self.env, since_days=30)
        self.assertEqual(loaded, {})
        self.assertEqual(scanned, 0)

    def test_registered_project_without_logs_not_scanned(self):
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        loaded, scanned = collect_usage(self.env, since_days=30)
        self.assertEqual(scanned, 0)  # нет логов -> честно не просканирован

    def test_skill_loaded_is_counted(self):
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        _write_session(self.env, self.project, ["code-style"])
        loaded, scanned = collect_usage(self.env, since_days=30)
        self.assertEqual(scanned, 1)
        self.assertEqual(loaded.get("code-style"), 1)

    def test_dead_skill_end_to_end(self):
        # "docker" в реестре, но НИ РАЗУ не загружался -> dead с честной формулировкой.
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        _write_session(self.env, self.project, ["code-style"])
        report = build_audit(self.env, since_days=30)
        row = next(r for r in report["items"] if r["key"] == "devops/docker")
        self.assertEqual(row["verdict"], "dead")
        self.assertEqual(row["usage_note"], "не использовался в окне 30 дней")
        used = next(r for r in report["items"] if r["key"] == "php/code-style")
        self.assertEqual(used["loaded_count"], 1)

    def test_transcripts_fail_safe_on_garbage(self):
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        from skiller.quality.analyze import logs_root
        root = logs_root(self.env, self.project)
        root.mkdir(parents=True, exist_ok=True)
        (root / "broken.jsonl").write_text("not-json\n{also broken\n", encoding="utf-8")
        loaded, scanned = collect_usage(self.env, since_days=30)
        self.assertEqual(scanned, 1)     # сессия "просканирована" — просто пусто
        self.assertEqual(loaded, {})


# --- резидент: второй источник видимости (P2.2 SKM-MASTER-003) -------------------
class ResidentChannelCase(unittest.TestCase):
    """collect_usage видит ТОЛЬКО явные Skill-tool-вызовы (слепая зона) — второй,
    независимый источник резидентности (CORE_SKILLS / активный набор проекта)
    закрывает её: резидентный скилл без единого вызова НЕ падает в dead."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.project = self.tmp / "consumer-project"
        self.project.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_core_skill_without_calls_is_not_dead(self):
        # "docker" в реестре объявлен CORE (монки-патч CORE_SKILLS — реальный
        # CORE_SKILLS живёт в другом бакете и в синтетический реестр не входит).
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        _write_session(self.env, self.project, ["code-style"])  # др. скилл грузился
        with mock.patch("skiller.quality.audit.CORE_SKILLS", ["devops/docker"]):
            report = build_audit(self.env, since_days=30)
        row = next(r for r in report["items"] if r["key"] == "devops/docker")
        self.assertEqual(row["loaded_count"], 0)
        self.assertNotEqual(row["verdict"], "dead")
        self.assertEqual(row["verdict"], "keep")
        self.assertEqual(row["channel"], "resident")
        self.assertEqual(row["usage_note"],
                         "резидентный, прямых вызовов не видно (авто-триггер вне детекции)")

    def test_non_core_unresident_skill_stays_dead(self):
        # Без резидентности (не CORE, не в активном наборе ни одного проекта) —
        # поведение до P2.2 не тронуто: dead + канал none.
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        _write_session(self.env, self.project, ["code-style"])
        with mock.patch("skiller.quality.audit.CORE_SKILLS", []):
            report = build_audit(self.env, since_days=30)
        row = next(r for r in report["items"] if r["key"] == "devops/docker")
        self.assertEqual(row["verdict"], "dead")
        self.assertEqual(row["channel"], "none")

    def test_skill_call_channel_wins_over_resident(self):
        # Реальный вызов есть -> channel=skill-call, даже если скилл заодно CORE.
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        _write_session(self.env, self.project, ["code-style"])
        with mock.patch("skiller.quality.audit.CORE_SKILLS", ["php/code-style"]):
            report = build_audit(self.env, since_days=30)
        row = next(r for r in report["items"] if r["key"] == "php/code-style")
        self.assertEqual(row["channel"], "skill-call")

    def test_active_profile_membership_makes_skill_resident(self):
        # "входит в подключённый профиль/каталог проекта": .swissknife.json проекта
        # выбирает бакет devops -> docker резидентен БЕЗ CORE_SKILLS.
        (self.project / ".swissknife.json").write_text(
            json.dumps({"buckets": ["devops"]}) + "\n", encoding="utf-8")
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        _write_session(self.env, self.project, ["code-style"])
        with mock.patch("skiller.quality.audit.CORE_SKILLS", []):
            names = resident_skill_names(self.env)
            self.assertIn("docker", names)
            report = build_audit(self.env, since_days=30)
        row = next(r for r in report["items"] if r["key"] == "devops/docker")
        self.assertEqual(row["verdict"], "keep")
        self.assertEqual(row["channel"], "resident")

    def test_resident_skill_names_graceful_on_unknown_bucket(self):
        # Битый/неизвестный бакет в .swissknife.json проекта -> resolve_active_set
        # die()-ит изнутри -> проект просто пропускается, аудит не падает.
        (self.project / ".swissknife.json").write_text(
            json.dumps({"buckets": ["no-such-bucket"]}) + "\n", encoding="utf-8")
        upsert_project(self.env, {"path": str(self.project), "channel": "vendor"})
        with mock.patch("skiller.quality.audit.CORE_SKILLS", []):
            names = resident_skill_names(self.env)  # не должно бросить исключение
        self.assertEqual(names, set())

    def test_resident_skills_count_in_report(self):
        with mock.patch("skiller.quality.audit.CORE_SKILLS", ["devops/docker"]):
            report = build_audit(self.env, since_days=30)
        self.assertEqual(report["resident_skills"], 1)


# --- рендер / CLI ------------------------------------------------------------------
class RenderAndCliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_render_smoke(self):
        report = build_audit(self.env, since_days=30)
        text = render_audit(report)
        self.assertIn("BUCKET-AUDIT", text)
        self.assertIn("devops/docker", text)

    def test_cmd_json_output(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_bucket_audit(self.env, ["--json"])
        data = json.loads(buf.getvalue())
        self.assertEqual(data["since_days"], 30)
        self.assertGreaterEqual(data["skills"], 4)

    def test_cmd_since_invalid_dies(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                cmd_bucket_audit(self.env, ["--since", "abc"])

    def test_cmd_help(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_bucket_audit(self.env, ["--help"])
        self.assertIn("bucket-audit", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
