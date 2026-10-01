"""P3.1: gate «description ≤450 char» on the REAL registry.

Gate batch-shortening - not synthetic fixtures-registry (that does not reflect the fact
alive SKILL.md), and direct scan packages/skiller/skills/**/SKILL.md. Threshold 450 —
hard-target item'a (validate.sh already warn'it on it, error will become in P3.2); threshold 300
is checked separately as non-regression for those explicitly corrected in P3.1 skills
(not «all ≤300» — part of the trigger-dense descriptions legally remains in burn-down
P3.2, see Completion Notes P3.1)."""
import unittest
from pathlib import Path

from skiller.common import parse_frontmatter

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # packages/skiller
SKILLS_ROOT = PACKAGE_ROOT / "skills"
DESC_HARD_MAX = 450

# Skills shortened in P3.1 (were >450 char description) — non-regression:
# the description should not again inflate beyond the ceiling recorded here.
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
    """Deliverable P3.1: 0 descriptions >450 entire symbol on the registry."""

    def test_no_description_exceeds_450_chars(self):
        offenders = []
        for skill_md in _iter_skill_md():
            length = _description_len(skill_md)
            if length > DESC_HARD_MAX:
                offenders.append((str(skill_md.relative_to(PACKAGE_ROOT)), length))
        self.assertEqual(
            offenders, [],
            f"description > {DESC_HARD_MAX} char (should be 0 after P3.1): {offenders}",
        )


class DescriptionP31FixedSkillsCase(unittest.TestCase):
    """Non-regression: 8 skills shortened in P3.1, do not inflate back."""

    def test_fixed_skills_stay_under_recorded_ceiling(self):
        for rel, ceiling in FIXED_IN_P31.items():
            skill_md = SKILLS_ROOT / rel / "SKILL.md"
            self.assertTrue(skill_md.exists(), f"{rel}: SKILL.md not found")
            length = _description_len(skill_md)
            self.assertLessEqual(
                length, ceiling,
                f"{rel}: description {length} char - regression P3.1 (was ≤{ceiling})",
            )


if __name__ == "__main__":
    unittest.main()
