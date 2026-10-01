"""Инвариант бюджета листинга поставляемых профилей.

Клиент Claude Code роняет описания реже вызываемых скиллов, когда листинг
превышает бюджет — ≈1% контекстного окна, что на 1M-моделях равно **30 000**
символов, не 10 000: единица бюджета — ТОКЕНЫ (1% от 1 000 000 = 10 000 ток),
переведённые в символы коэффициентом ×3 симв/ток first-party клиента, а не
проценты контекста напрямую в символах (репо-факт, `claude --debug-file` WARN
«47021 chars > 30000 budget», см.
 §0). 200K-модель —
1/5 от этого, 6 000 симв.

Символы на профиль считаются ТЕМ ЖЕ производственным путём, что и раздача
connect-канала (`config.resolve_selection` + `budget.resolve_active_set` +
`core_skill_tuples`) — сумма frontmatter `description` (в этом реестре нет
`when_to_use`) по всем скиллам выбранных бакетов плюс курируемый `core@`,
без дублей по каталогу. Записи, снятые с листинга нативным полем
(`budget._listing_exclusion` — `disable-model-invocation`/`paths`, наблюдение
стенда P3.1/P3.6, план), в сумму НЕ входят: инвариант
о бюджете ЛИСТИНГА, а не о размере реестра. Тесты читают РЕАЛЬНЫЙ `profiles/`,
не пишут в него."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.budget import _listing_exclusion, resolve_active_set
from skiller.common import Env, parse_frontmatter
import tests.fixtures as fx

BUDGET_1M = 30_000
BUDGET_200K = 6_000

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_PROFILES = sorted(p.stem for p in (REPO_ROOT / "profiles").glob("*.json"))
# standalone = «маркеров стека нет — поставь всё»; сузить его — потерять смысл
# профиля (Implementation Rules P3.5: «профиль, из которого без потери смысла
# ничего не вычёркивается, остаётся переполненным — названное ограничение, а
# не подгоняется вычёркиванием ядра»). Единственный сознательно исключённый
# из строгого инварианта; test_standalone_* ниже документирует, а не молчит.
NAMED_OVER_BUDGET_EXCEPTIONS = {"standalone"}


def profile_char_total(env, target, profile):
    """Сумма символов frontmatter `description` активного набора профиля
    (бакеты профиля + core@, минус DEFAULT_EXCLUDE) — тот же путь, которым
    реально собирается connect-канал. Дедуп по каталогу (core@ может
    пересекаться с бакетом профиля). Запись, снятая нативным полем, в листинг не
    попадает и в сумму не входит — иначе инвариант считал бы символы,
    которых у клиента нет."""
    skills, _meta = resolve_active_set(env, target, {}, profile=profile)
    total, seen = 0, set()
    for _bucket, _rel, d, _fm_name in skills:
        key = str(d)
        if key in seen or _listing_exclusion(d) is not None:
            continue
        seen.add(key)
        fm = parse_frontmatter(d / "SKILL.md")
        total += len(fm.get("description", "") or "")
    return total


class ShippedProfilesFitListingBudget(unittest.TestCase):
    """Каждый поставляемый профиль (кроме именованного исключения `standalone`)
    укладывается в реальный бюджет листинга 1M-модели."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = Env(REPO_ROOT, home=Path(self._tmp.name))
        self.target = Path(self._tmp.name) / "dummy-target"

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_shipped_profile_present(self):
        # sanity: список профилей не пуст и совпадает с тем, что реально лежит
        # на диске (защита от опечатки в SHIPPED_PROFILES/NAMED_OVER_BUDGET_EXCEPTIONS).
        self.assertGreaterEqual(len(SHIPPED_PROFILES), 9)
        self.assertLessEqual(NAMED_OVER_BUDGET_EXCEPTIONS, set(SHIPPED_PROFILES))

    def test_narrowed_profiles_fit_1m_budget(self):
        failures = []
        for name in SHIPPED_PROFILES:
            if name in NAMED_OVER_BUDGET_EXCEPTIONS:
                continue
            total = profile_char_total(self.env, self.target, name)
            if total > BUDGET_1M:
                failures.append(f"{name}: {total} симв > {BUDGET_1M}")
        self.assertEqual(failures, [],
                         "профили переполняют бюджет листинга 1M и не входят "
                         "в NAMED_OVER_BUDGET_EXCEPTIONS:\n" + "\n".join(failures))

    def test_standalone_named_exception_over_budget(self):
        """Документирует границу, а не требует её: если `standalone` когда-нибудь
        окажется ПОД бюджетом (реестр сжался) — это не поломка, но названное
        ограничение в `docs/guide/profiles.md` устарело и подлежит снятию."""
        total = profile_char_total(self.env, self.target, "standalone")
        self.assertGreater(
            total, BUDGET_1M,
            f"standalone {total} симв <= {BUDGET_1M}: снять пометку "
            "'named over-budget exception' в docs/guide/profiles.md")


class BloatedProfileFailsInvariant(unittest.TestCase):
    """Профиль с намеренно раздутым составом (синтетический реестр) обязан
    ловиться тем же инвариантом — не только «настоящие профили сегодня зелёные»."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.target = self.tmp / "dummy-target"

    def tearDown(self):
        self._tmp.cleanup()

    def test_bloated_bucket_overflows_budget(self):
        fx.write_skill(self.root / "skills" / "quality" / "bloated",
                       "bloated", description="X" * (BUDGET_1M + 1))
        (self.root / "profiles" / "bloated-profile.json").write_text(
            '{"name": "bloated-profile", "description": "test",'
            ' "buckets": ["quality"], "include_meta": false}\n')
        total = profile_char_total(self.env, self.target, "bloated-profile")
        self.assertGreater(total, BUDGET_1M)


if __name__ == "__main__":
    unittest.main()
