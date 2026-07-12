"""P3.1 (2026.07.12-CONTEXT-ECONOMY): гейт «description ≤450 симв» на РЕАЛЬНОМ реестре.

Гейт batch-укорочения — не синтетический fixtures-реестр (тот не отражает факт
живых SKILL.md), а прямой скан packages/skiller/skills/**/SKILL.md. Порог 450 —
hard-цель item'а (validate.sh уже warn'ит на нём, error станет в P3.2); порог 300
проверяется отдельно как non-regression для явно исправленных в P3.1 скиллов
(не «все ≤300» — часть триггеро-плотных описаний легально остаётся в burn-down
P3.2, см. Completion Notes P3.1)."""
import unittest
from pathlib import Path

from skiller.common import parse_frontmatter

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # packages/skiller
SKILLS_ROOT = PACKAGE_ROOT / "skills"
DESC_HARD_MAX = 450

# Скиллы, укороченные в P3.1 (были >450 симв description) — non-regression:
# описание не должно снова раздуться выше зафиксированного здесь потолка.
FIXED_IN_P31 = {
    "research/research": 350,
    "security/security": 350,
    "finance/finance": 350,
    "creative/content-creative": 350,
    "legal/legal": 350,
    "sales/sales": 350,
    "marketing/marketing": 350,
    "frontend-vue/vue-router-best-practices": 420,
}


def _iter_skill_md():
    for skill_md in sorted(SKILLS_ROOT.glob("**/SKILL.md")):
        yield skill_md


def _description_len(skill_md):
    fm = parse_frontmatter(skill_md)
    return len((fm or {}).get("description", ""))


class DescriptionHardCapCase(unittest.TestCase):
    """Deliverable P3.1: 0 описаний >450 симв на реестре целиком."""

    def test_no_description_exceeds_450_chars(self):
        offenders = []
        for skill_md in _iter_skill_md():
            length = _description_len(skill_md)
            if length > DESC_HARD_MAX:
                offenders.append((str(skill_md.relative_to(PACKAGE_ROOT)), length))
        self.assertEqual(
            offenders, [],
            f"description > {DESC_HARD_MAX} симв (должно быть 0 после P3.1): {offenders}",
        )


class DescriptionP31FixedSkillsCase(unittest.TestCase):
    """Non-regression: 8 скиллов, укороченных в P3.1, не раздуваются обратно."""

    def test_fixed_skills_stay_under_recorded_ceiling(self):
        for rel, ceiling in FIXED_IN_P31.items():
            skill_md = SKILLS_ROOT / rel / "SKILL.md"
            self.assertTrue(skill_md.exists(), f"{rel}: SKILL.md не найден")
            length = _description_len(skill_md)
            self.assertLessEqual(
                length, ceiling,
                f"{rel}: description {length} симв — регресс P3.1 (было ≤{ceiling})",
            )


if __name__ == "__main__":
    unittest.main()
