"""Тесты токенового бюджета (budget.py) против синтетического реестра.

Проверяем: грубую оценку токенов, раздельный подсчёт ярусов, транзитивное
раскрытие requires (метка transitive), генерацию карты docs/guide/budget.md."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.budget import (aggregate_measurements, budget_for_set, cmd_budget,
                            estimate_tokens, make_measurement, resolve_active_set,
                            skill_budget, write_budget_map)
from skiller.registry import build_registry
import tests.fixtures as fx
from core import atomic_write_text
import json


class EstimateTokensCase(unittest.TestCase):
    def test_empty_is_zero(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens(None), 0)

    def test_deterministic_and_monotonic(self):
        a, b = estimate_tokens("x" * 30), estimate_tokens("x" * 60)
        self.assertEqual(a, estimate_tokens("x" * 30))  # детерминизм
        self.assertLess(a, b)                            # монотонность

    def test_len_based(self):
        # ceil(len/CHARS_PER_TOKEN), грубая, но > 0 для непустого
        self.assertGreater(estimate_tokens("hello world"), 0)


class SkillBudgetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tiers_split(self):
        d = self.root / "skills" / "quality" / "big-body"
        fx.write_skill(d, "big-body", description="short",
                       body="word " * 500)
        b = skill_budget(d)
        self.assertEqual(b["name"], "big-body")
        # короткое описание (ярус-0) << длинное тело (ярус-1)
        self.assertLess(b["tier0"], b["tier1"])

    def test_missing_skill_md(self):
        self.assertIsNone(skill_budget(self.root / "skills" / "nope"))

    def test_snippets_counted_on_demand(self):
        d = self.root / "skills" / "quality" / "with-snip"
        fx.write_skill(d, "with-snip", description="d")
        (d / "snippets").mkdir()
        (d / "snippets" / "ex.md").write_text("x" * 90, encoding="utf-8")
        (d / "snippets" / "index.json").write_text("{}", encoding="utf-8")
        b = skill_budget(d)
        self.assertEqual(b["snippets"], 1)   # index.json не считаем
        self.assertGreater(b["tier2"], 0)

    def test_references_counted_on_demand(self):
        # P2.1 SKM-MASTER-003 (T1): references/ — ярус-2 ⌥ on-demand, симметрично
        # snippets/ (тела монолитов после thin-navigator-волны P7 SKM-MASTER-002).
        d = self.root / "skills" / "quality" / "with-refs"
        fx.write_skill(d, "with-refs", description="d")
        (d / "references").mkdir()
        (d / "references" / "full.md").write_text("y" * 90, encoding="utf-8")
        b = skill_budget(d)
        self.assertEqual(b["references"], 1)
        self.assertEqual(b["snippets"], 0)
        self.assertGreater(b["tier2"], 0)

    def test_references_do_not_leak_into_tier1(self):
        # references — ⌥ on-demand (ярус-2), НЕ ↻ on-trigger (ярус-1): тело
        # SKILL.md короткое, references/ рядом объёмные — tier1 не должен расти.
        d = self.root / "skills" / "quality" / "with-refs-tier1"
        fx.write_skill(d, "with-refs-tier1", description="d", body="short body\n")
        b_before = skill_budget(d)
        (d / "references").mkdir()
        (d / "references" / "full.md").write_text("z " * 2000, encoding="utf-8")
        b_after = skill_budget(d)
        self.assertEqual(b_after["tier1"], b_before["tier1"])
        self.assertGreater(b_after["tier2"], b_before["tier2"])

    def test_snippets_and_references_both_counted(self):
        d = self.root / "skills" / "quality" / "with-both"
        fx.write_skill(d, "with-both", description="d")
        (d / "snippets").mkdir()
        (d / "snippets" / "ex.md").write_text("x" * 90, encoding="utf-8")
        (d / "references").mkdir()
        (d / "references" / "full.md").write_text("y" * 90, encoding="utf-8")
        b = skill_budget(d)
        self.assertEqual(b["snippets"], 1)
        self.assertEqual(b["references"], 1)
        snip_only_tokens = estimate_tokens("x" * 90)
        ref_only_tokens = estimate_tokens("y" * 90)
        self.assertEqual(b["tier2"], snip_only_tokens + ref_only_tokens)


class ResolveActiveSetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        # кросс-бакетная зависимость: quality/needs-docker requires docker(devops)
        fx.write_skill(self.root / "skills" / "quality" / "needs-docker",
                       "needs-docker", requires=["docker"], description="needs docker")

    def tearDown(self):
        self._tmp.cleanup()

    def test_transitive_pulled_and_marked(self):
        skills, meta = resolve_active_set(
            self.env, self.tmp, {"buckets": ["quality"]})
        names = {fm for _, _, _, fm in skills}
        self.assertIn("needs-docker", names)
        self.assertIn("docker", names)            # подтянут транзитивно из devops
        self.assertIn("docker", meta["pulled"])   # помечен как pulled
        self.assertEqual(meta["pulled"]["docker"], "needs-docker")

    def test_budget_aggregates_by_bucket(self):
        skills, meta = resolve_active_set(
            self.env, self.tmp, {"buckets": ["quality"]})
        b = budget_for_set(skills, meta["pulled"])
        self.assertEqual(b["count"], len(skills))
        self.assertEqual(b["if_all_triggered"], b["tier0"] + b["tier1"])
        # docker учтён в бакете devops (его родной), а не в quality
        self.assertIn("devops", b["by_bucket"])
        self.assertEqual(b["transitive"], 1)


class ProviderQualifiedMeasurementCase(unittest.TestCase):
    BASE = {
        "surface": "listing",
        "value": 120,
        "unit": "characters",
        "method": "provider-counter:v1",
        "uncertainty": "none",
        "measurement_class": "exact",
        "observed_at": "2026-08-16T10:00:00Z",
        "expires_at": "2026-09-16T10:00:00Z",
        "source_id": "skiller.test.measurement",
        "threshold": 1000,
    }

    def row(self, provider="codex", **changes):
        values = {**self.BASE, "provider": provider, "model": "model-v1", **changes}
        return make_measurement(**values)

    def test_required_fields_and_exactly_one_model_identity(self):
        with self.assertRaisesRegex(ValueError, "MODEL_IDENTITY_INVALID"):
            make_measurement(**{**self.BASE, "provider": "codex"})
        with self.assertRaisesRegex(ValueError, "MODEL_IDENTITY_INVALID"):
            make_measurement(**{
                **self.BASE, "provider": "codex", "model": "model-v1",
                "model_family": "family-v1",
            })
        complete = self.row()
        for field in (set(complete) - {"model"}):
            incomplete = dict(complete)
            incomplete.pop(field)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "SCHEMA_INVALID"):
                    aggregate_measurements([incomplete])

    def test_unknown_is_nullable_and_stale_is_visible(self):
        unknown = self.row(
            provider="provider-c", value=None, measurement_class="unknown")
        self.assertEqual(unknown["status"], "unknown")
        stale = self.row(evaluated_at="2026-10-01T00:00:00Z")
        self.assertEqual(stale["status"], "stale")

    def test_exact_and_estimate_cannot_be_mixed(self):
        exact = self.row(source_id="source.exact")
        estimated = self.row(
            source_id="source.estimate", measurement_class="estimate",
            uncertainty="estimated")
        with self.assertRaisesRegex(ValueError, "CLASS_MIXED"):
            aggregate_measurements([estimated, exact])

    def test_third_provider_uses_same_schema_and_deterministic_order(self):
        codex = self.row(provider="codex")
        third = self.row(
            provider="provider-c", model=None, model_family="family-v1",
            unit="provider-c-units", threshold=500)
        result = aggregate_measurements([third, codex])
        self.assertEqual(
            [row["provider"] for row in result["rows"]], ["codex", "provider-c"])
        self.assertEqual(set(third) - {"model_family"}, set(codex) - {"model"})


class WriteBudgetMapCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        # P2.1 SKM-MASTER-003: скилл с references/ — карта/агрегация должны
        # видеть его тело в ⌥ on-demand (не только snippets/).
        refs_skill = self.root / "skills" / "quality" / "with-refs-map"
        fx.write_skill(refs_skill, "with-refs-map", description="refs demo")
        (refs_skill / "references").mkdir()
        (refs_skill / "references" / "full.md").write_text(
            "монолит " * 400, encoding="utf-8")
        (self.root / "docs" / "guide").mkdir(parents=True)
        registry, _, _ = build_registry(self.env)
        atomic_write_text(self.root / "skills.json",
                          json.dumps(registry, ensure_ascii=False))

    def tearDown(self):
        self._tmp.cleanup()

    def test_map_generated(self):
        write_budget_map(self.env)
        out = self.root / "docs" / "guide" / "budget.md"
        self.assertTrue(out.is_file())
        text = out.read_text(encoding="utf-8")
        self.assertIn("flowchart LR", text)
        self.assertIn("classDef hot", text)
        self.assertIn("⊕", text)               # легенда яруса-0
        self.assertIn("laravel-conventions", text)  # скилл из фикстуры на карте

    def test_map_reflects_references_in_tier2(self):
        # references/full.md скилла with-refs-map попадает в ⌥ on-demand карты
        # (P2.1 T1) — итоговое tier2 больше, чем без учёта references/.
        b = skill_budget(self.root / "skills" / "quality" / "with-refs-map")
        self.assertEqual(b["references"], 1)
        self.assertGreater(b["tier2"], 0)
        write_budget_map(self.env)
        out = self.root / "docs" / "guide" / "budget.md"
        text = out.read_text(encoding="utf-8")
        self.assertIn("on-demand", text)  # переименованная колонка/итог


class CheckCoreCase(unittest.TestCase):
    """--check-core должен фейлить и на НЕДОБОРЕ CORE_SKILLS (переехавший/опечатанный
    путь молча уменьшает резидент → гейт раньше «зеленел» вместо ошибки, аудит B-2).
    Синтетический реестр (fx.make_registry) не содержит ни одного пути из дефолтных
    CORE_SKILLS (context-economy/anti-drift/…) — гарантированный недобор для теста."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_core_skill_dies_under_strict(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                cmd_budget(self.env, ["--check-core", "--strict"])

    def test_missing_core_skill_reports_json_without_strict(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_budget(self.env, ["--check-core", "--json"])
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "MISSING")
        self.assertGreater(data["missing"], 0)
        self.assertEqual(data["skills"], 0)


if __name__ == "__main__":
    unittest.main()
