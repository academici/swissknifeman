"""Budget invariant for listing supplied profiles.

Client Claude Code drops descriptions of less frequently called skills when listing
over budget - ≈1% context window, which is at 1M-models is equal to **30 000**
characters, not 10,000: budget unit - TOKENS (1% from 1,000,000 = 10 000 current),
converted to symbols by the coefficient ×3 char/current first-party client, not
context percentages directly in characters (repo fact, `claude --debug-file` WARN
«47021 chars > 30000 budget», see
 §0). 200K-model -
1/5 from this, 6,000 characters.

Characters per profile are considered the SAME production path as the distribution
connect-channel (`config.resolve_selection` + `budget.resolve_active_set` +
`core_skill_tuples`) — amount frontmatter `description` (is not in this registry
`when_to_use`) for all skills of the selected buckets plus supervised `core@`,
without duplicates according to the catalogue. Records removed from listing by native field
(`budget._listing_exclusion` — `disable-model-invocation`/`paths`, observation
stand P3.1/P3.6, plan), amount does NOT include: invariant
about LISTING budget, not registry size. Tests read REAL `profiles/`,
do not write to it."""
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
# standalone = «there are no stack markers - put everything»; narrow it - lose meaning
# profile (Implementation Rules P3.5: «profile, from which without loss of meaning
# does not cross out anything, remains overflowing - the named limitation, and
# is not adjusted by deleting the kernel»). The only one deliberately excluded
# from the strict invariant; test_standalone_* below documents rather than remains silent.
NAMED_OVER_BUDGET_EXCEPTIONS = {"standalone"}


def profile_char_total(env, target, profile):
    """Sum of characters frontmatter `description` active profile set
    (profile buckets + core@, minus DEFAULT_EXCLUDE) — same path as
    is really going connect-channel. Dedup by catalog (core@ may
    intersect with profile bucket). A record removed by a native field is not included in the listing
    falls and is not included in the sum - otherwise the invariant would count the characters
    which the client does not have."""
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
    """Each supplied profile (except named exception `standalone`)
    fits within the actual budget of Listing 1M-models."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = Env(REPO_ROOT, home=Path(self._tmp.name))
        self.target = Path(self._tmp.name) / "dummy-target"

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_shipped_profile_present(self):
        # sanity: the list of profiles is not empty and matches what is actually there
        # on disk (typo protection in SHIPPED_PROFILES/NAMED_OVER_BUDGET_EXCEPTIONS).
        self.assertGreaterEqual(len(SHIPPED_PROFILES), 9)
        self.assertLessEqual(NAMED_OVER_BUDGET_EXCEPTIONS, set(SHIPPED_PROFILES))

    def test_narrowed_profiles_fit_1m_budget(self):
        failures = []
        for name in SHIPPED_PROFILES:
            if name in NAMED_OVER_BUDGET_EXCEPTIONS:
                continue
            total = profile_char_total(self.env, self.target, name)
            if total > BUDGET_1M:
                failures.append(f"{name}: {total} char > {BUDGET_1M}")
        self.assertEqual(failures, [],
                         "profiles overflow Listing 1 budgetM and are not included "
                         "in NAMED_OVER_BUDGET_EXCEPTIONS:\n" + "\n".join(failures))

    def test_standalone_named_exception_over_budget(self):
        """Documents a boundary rather than requiring one: if `standalone` someday
        will be UNDER budget (registry has shrunk) — this is not a breakdown, but the named
        limit in `docs/guide/profiles.md` is obsolete and should be removed."""
        total = profile_char_total(self.env, self.target, "standalone")
        self.assertGreater(
            total, BUDGET_1M,
            f"standalone {total} char <= {BUDGET_1M}: uncheck "
            "'named over-budget exception' in docs/guide/profiles.md")


class BloatedProfileFailsInvariant(unittest.TestCase):
    """Profile with a deliberately inflated composition (synthetic registry) obliged
    is caught by the same invariant - not only «real profiles are green today»."""

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
